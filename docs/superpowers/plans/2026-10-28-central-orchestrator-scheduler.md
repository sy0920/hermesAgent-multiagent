# 自研中心化团长调度器（方案 A）实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将编排层重构为方案 A 的中心化团长调度器：团长（限预算 Hermes Agent）出 JSON 方案 → 调度器代码解析分配 → 专家（限预算 Hermes Agent）执行 → 团长聚合复审 → 最终报告；支持 Plan 确认与多轮增量迭代。

**Architecture:** 新增独立 `scheduler/` 包（SQLite 台账 + 5 模块），团长/专家通过 `hermes_client.chat_budgeted`（`-Q --max-turns N --run-budget S -t 白名单`）调用；调度器主循环后台线程驱动状态机；看板由调度器单向回写（只读展示）。旧 `llm_worker.py` 退休。

**Tech Stack:** Python/FastAPI/pytest（mock subprocess + mock Hermes）；Hermes CLI 预算能力已验证（`--max-turns`/`--toolsets`/`--run-budget`/`-Q`）。

**Spec:** `docs/superpowers/specs/2026-10-28-central-orchestrator-scheduler.md`

## Global Constraints

- 所有团长/专家调用**必须**走 `hermes_client.chat_budgeted`（带 max_turns/run_budget/toolsets），禁止直接 run_hermes chat
- 专家预算：`MAX_TURNS=10`、`RUN_SECONDS=180`、`TOOLSET_WHITELIST=["file","skills","terminal"]`（禁 delegate/kanban/send_message）
- 团长预算：出方案 `MAX_TURNS=5/RUN_SECONDS=60/toolsets=["file","skills"]`；聚合 `MAX_TURNS=8/RUN_SECONDS=120`
- 专家子任务失败 → `failed` 标记，**不自动重派**
- 专家不碰看板；`engine.py` 是唯一写 kanban 的模块（单向回写）
- 多轮：`round_no` 隔离，团长每轮输入 = `上轮 final_report + 用户反馈 + 花名册`（不含全量历史）
- 状态机 8 态：`submitting → planning → waiting_confirm ⇄ running → aggregating → finished → resuming → running` + `error`
- 存储：独立 `~/.hermes/scheduler.db`（SQLite，不与 kanban.db 混用）

## Review Focus

1. **预算必须严格生效**：任何专家/团长调用若绕过 `chat_budgeted`（如直接用 run_hermes chat 或走到旧 llm_worker），成本就会失控——测试需断言 executor/leader 只通过 chat_budgeted 调 Hermes
2. **并发上限**：专家级 concurrency_limit 与团级 max_parallel_tasks 同时满足才派发；并发测试需验证"满了不派、释放后继续"
3. **依赖解析**：deps 未完成不派发；deps 含失败任务 → 该子任务标记 failed（不无限等待）
4. **多轮上下文拼接**：resuming 时团长输入含上一轮 final_report + 反馈，**不含全量旧 subtask 历史**（防 token 膨胀）——测试断言输入中无旧轮子任务细节
5. **看板单向性**：专家执行过程中不会创建/修改 kanban 任务；只有 engine 的 `_sync_kanban` 写
6. **Plan 确认流程**：waiting_confirm 状态时调度循环不派发任务；确认后才 running

---

### Task 1: scheduler.db（SQLite 台账）

**Files:**
- Create: `backend/scheduler/__init__.py`
- Create: `backend/scheduler/db.py`
- Test: `backend/tests/test_scheduler_db.py`

**Interfaces:**
- Consumes: 无（独立新模块）
- Produces:
  - `DB_PATH = ~/.hermes/scheduler.db`（模块级，测试可 patch）
  - `class SessionRow`: `session_id: str, group_id: str, status: str, user_query: str, round_no: int, plan_json: str = "", final_report: str = "", created_at: str, updated_at: str`
  - `class SubtaskRow`: `subtask_id: str, session_id: str, round_no: int, expert_id: str, title: str, instruction: str, input_context: str, deps: list[str], status: str, output: str = ""`
  - `create_session(session_id, group_id, user_query) -> None`
  - `update_session(session_id, **fields) -> None`
  - `get_session(session_id) -> dict | None`
  - `create_subtask(row: SubtaskRow) -> None`
  - `update_subtask(subtask_id, **fields) -> None`（status/output）
  - `get_subtask(subtask_id) -> dict | None`
  - `list_subtasks(session_id, round_no) -> list[dict]`
  - `list_sessions(status=None) -> list[dict]`

- [ ] **Step 1: 写失败测试**（`backend/tests/test_scheduler_db.py`）

```python
import pytest
from app import teams as _  # unused
from scheduler.db import (DB_PATH, create_session, get_session,
                          update_session, create_subtask, get_subtask,
                          update_subtask, list_subtasks, list_sessions)

def _home(tmp_path, monkeypatch):
    monkeypatch.setattr("scheduler.db.DB_PATH", tmp_path / "sched.db")

def test_session_roundtrip(tmp_path, monkeypatch):
    _home(tmp_path, monkeypatch)
    create_session("s1", "g1", "调研 AutoGen")
    s = get_session("s1")
    assert s["group_id"] == "g1"
    assert s["status"] == "submitting"

def test_update_session(tmp_path, monkeypatch):
    _home(tmp_path, monkeypatch)
    create_session("s1", "g1", "q")
    update_session("s1", status="running", plan_json="{}")
    assert get_session("s1")["status"] == "running"

def test_session_status_filter(tmp_path, monkeypatch):
    _home(tmp_path, monkeypatch)
    create_session("s1", "g1", "q")
    create_session("s2", "g1", "q")
    update_session("s1", status="finished")
    assert {s["session_id"] for s in list_sessions(status="finished")} == {"s1"}

def test_subtask_roundtrip_with_deps(tmp_path, monkeypatch):
    _home(tmp_path, monkeypatch)
    create_session("s1", "g1", "q")
    create_subtask(SubtaskRow("t1", "s1", 1, "expert-a", "调研", "读文档", "ctx", ["t0"], "pending"))
    r = get_subtask("t1")
    assert r["deps"] == ["t0"]
    assert r["status"] == "pending"
    update_subtask("t1", status="success", output="结果")
    assert get_subtask("t1")["status"] == "success"
    assert get_subtask("t1")["output"] == "结果"

def test_list_subtasks_by_round(tmp_path, monkeypatch):
    _home(tmp_path, monkeypatch)
    create_session("s1", "g1", "q")
    create_subtask(SubtaskRow("t1", "s1", 1, "a", "x", "i", "c", [], "pending"))
    create_subtask(SubtaskRow("t2", "s1", 2, "b", "y", "i", "c", [], "pending"))
    assert {t["subtask_id"] for t in list_subtasks("s1", 1)} == {"t1"}
    assert {t["subtask_id"] for t in list_subtasks("s1", 2)} == {"t2"}
```

- [ ] **Step 2: 运行确认失败**（`pytest tests/test_scheduler_db.py -v` → ModuleNotFoundError）
- [ ] **Step 3: 实现 `scheduler/db.py`**（SQLite + threading.RLock，表存在则 create，幂等）
- [ ] **Step 4: 运行确认通过**
- [ ] **Step 5: Commit**

```bash
git add backend/scheduler/ backend/tests/test_scheduler_db.py
git commit -m "feat: 调度器 SQLite 台账(session/subtask)"
```

---

### Task 2: hermes_client.chat_budgeted（预算封装）

**Files:**
- Modify: `backend/app/hermes_client.py`
- Test: `backend/tests/test_chat_budgeted.py`

**Interfaces:**
- Consumes: 现有 `run_hermes`、`ensure_gateway`
- Produces:
  - `chat_budgeted(profile: str, message: str, *, max_turns: int, run_budget: int, toolsets: list[str] | None = None, timeout: int | None = None) -> str`

- [ ] **Step 1: 写失败测试**（`backend/tests/test_chat_budgeted.py`）

```python
def test_chat_budgeted_builds_budget_args(monkeypatch):
    captured = []
    class FakeProc:
        returncode = 0
        stdout = "回复\n"
        stderr = ""
    def fake_run(args, **kw):
        captured.append(args)
        return FakeProc()
    monkeypatch.setattr("app.hermes_client.subprocess.run", fake_run)
    monkeypatch.setattr("app.hermes_client.subprocess.Popen", FakeGatewayOrSkip)
    monkeypatch.setattr("app.hermes_client.time.sleep", lambda s: None)
    from app.hermes_client import chat_budgeted
    chat_budgeted("researcher-a", "调研X", max_turns=10, run_budget=180,
                  toolsets=["file", "skills", "terminal"])
    joined = " ".join(captured[0])
    assert "--max-turns" in joined and "10" in joined
    assert "--run-budget" in joined and "180" in joined
    assert "-t" in joined and "file,skills,terminal" in joined or "-Q" in joined

def test_chat_budgeted_no_toolsets_omits_t(monkeypatch):
    # verbose form: ensure -t only when toolsets provided
    ...

def test_chat_budgeted_timeout_defaults_to_run_budget_plus_30(monkeypatch):
    captured = {}
    class FakeProc:
        returncode = 0; stdout = "ok\n"; stderr = ""
    def fake_run(args, timeout=None, **kw):
        captured["timeout"] = timeout
        return FakeProc()
    monkeypatch.setattr("app.hermes_client.subprocess.run", fake_run)
    ...
    chat_budgeted("a", "m", max_turns=5, run_budget=60)
    assert captured["timeout"] == 90
```

> 注意：`ensure_gateway` 会被调用，测试需 monkeypatch `app.hermes_client.subprocess.Popen` 与 `time.sleep`（仿 Task3 的 test_gateway_warm 模式）。

- [ ] **Step 2: 运行确认失败**
- [ ] **Step 3: 实现 `chat_budgeted`**

```python
def chat_budgeted(profile, message, *, max_turns, run_budget, toolsets=None, timeout=None):
    ensure_gateway(profile)
    args = ["-p", profile, "chat", "-Q", "--max-turns", str(max_turns),
            "--run-budget", str(run_budget)]
    if toolsets:
        args += ["-t", ",".join(toolsets)]
    args += ["-q", message]
    return run_hermes(args, timeout=timeout or (run_budget + 30))
```

- [ ] **Step 4: 运行确认通过**
- [ ] **Step 5: Commit**

---

### Task 3: leader.py（团长出方案 + 聚合复审）

**Files:**
- Create: `backend/scheduler/leader.py`
- Test: `backend/tests/test_scheduler_leader.py`

**Interfaces:**
- Consumes: Task 2 `chat_budgeted`
- Produces:
  - `LEADER_PLAN_TURNS = 5`, `LEADER_PLAN_SECONDS = 60`
  - `LEADER_AGGREGATE_TURNS = 8`, `LEADER_AGGREGATE_SECONDS = 120`
  - `PLAN_PROMPT_TEMPLATE`（.format(user_query, roster, history, round_no)）
  - `lead_plan(leader_expert_id, user_query, roster: str, history: str = "", round_no: int = 1) -> dict`（返回解析后的 plan dict：`{summary, subtasks:[{expert_id, instruction, input_context, deps, parallel_group}]}`；LLM 输出非法 → 返回 None）
  - `lead_aggregate(leader_expert_id, results_text: str) -> str | None`（返回 final_report 文本）

- [ ] **Step 1: 写失败测试**

```python
def test_lead_plan_parses_json(monkeypatch):
    monkeypatch.setattr("scheduler.leader.chat_budgeted",
        lambda *a, **k: '{"summary":"s","subtasks":[{"expert_id":"a","instruction":"i","input_context":"c","deps":[],"parallel_group":"g"}]}')
    from scheduler.leader import lead_plan
    plan = lead_plan("team-lead", "需求", "a,b")
    assert plan["subtasks"][0]["expert_id"] == "a"

def test_lead_plan_fence_json(monkeypatch):
    monkeypatch.setattr("scheduler.leader.chat_budgeted",
        lambda *a, **k: '```json\n{"summary":"s","subtasks":[]}\n```')
    plan = lead_plan("team-lead", "需求", "a")
    assert plan["summary"] == "s"

def test_lead_plan_invalid_returns_none(monkeypatch):
    monkeypatch.setattr("scheduler.leader.chat_budgeted", lambda *a, **k: "不是JSON")
    assert lead_plan("team-lead", "需求", "a") is None

def test_lead_plan_includes_history_and_round(monkeypatch):
    captured = {}
    def fake(profile, msg, **kw):
        captured["msg"] = msg; return "{}"
    monkeypatch.setattr("scheduler.leader.chat_budgeted", fake)
    lead_plan("t", "需求", "a,b", history="上轮报告", round_no=2)
    assert "上轮报告" in captured["msg"] and "2" in captured["msg"]

def test_lead_aggregate_returns_report(monkeypatch):
    monkeypatch.setattr("scheduler.leader.chat_budgeted", lambda *a, **k: "最终报告")
    from scheduler.leader import lead_aggregate
    assert lead_aggregate("team-lead", "结果1\n结果2") == "最终报告"
```

- [ ] **Step 2: 运行确认失败**
- [ ] **Step 3: 实现 `leader.py`**
  - 复用 `_extract_plan` 思路（容忍 ` ```json ` fence 与前后缀）——复制到 leader.py 私有函数（不 import teams）。
  - `PLAN_PROMPT_TEMPLATE`：含用户需求、花名册（"只能从这些专家选择"）、历史（多轮时附上轮报告）、round_no，要求只输出 JSON。
  - `lead_plan`：调用 chat_budgeted（turns=5/sec=60, toolsets=["file","skills"]）→ 解析 → None 失败
  - `lead_aggregate`：合并结果文本 → chat_budgeted（turns=8/sec=120）→ 返回文本
- [ ] **Step 4: 运行确认通过**
- [ ] **Step 5: Commit**

---

### Task 4: executor.py（专家执行）

**Files:**
- Create: `backend/scheduler/executor.py`
- Test: `backend/tests/test_scheduler_executor.py`

**Interfaces:**
- Consumes: Task 2 `chat_budgeted`
- Produces:
  - `EXECUTOR_MAX_TURNS = 10`, `EXECUTOR_RUN_SECONDS = 180`, `TOOLSET_WHITELIST = ["file", "skills", "terminal"]`
  - `run_expert(expert_id: str, instruction: str, input_context: str) -> str` （返回专家输出文本；失败抛异常）
  - `class ExpertExecutionError(RuntimeError)`（LLM 调用失败时抛）

- [ ] **Step 1: 写失败测试**

```python
def test_run_expert_forwards_budget(monkeypatch):
    captured = {}
    def fake(profile, msg, *, max_turns, run_budget, toolsets, timeout):
        captured.update(profile=profile, msg=msg, mt=max_turns, rb=run_budget, ts=toolsets)
        return "输出"
    monkeypatch.setattr("scheduler.executor.chat_budgeted", fake)
    from scheduler.executor import run_expert
    out = run_expert("researcher-a", "调研X", "上下文")
    assert out == "输出"
    assert captured["profile"] == "researcher-a"
    assert captured["mt"] == 10 and captured["rb"] == 180
    assert captured["ts"] == ["file", "skills", "terminal"]
    assert "上下文" in captured["msg"]

def test_run_expert_failure_raises(monkeypatch):
    def fake(*a, **k): raise Exception("boom")
    monkeypatch.setattr("scheduler.executor.chat_budgeted", fake)
    from scheduler.executor import run_expert, ExpertExecutionError
    import pytest
    with pytest.raises(ExpertExecutionError):
        run_expert("a", "i", "c")
```

- [ ] **Step 2: 运行确认失败**
- [ ] **Step 3: 实现 `executor.py`**
  - `run_expert`：组装 prompt（`instruction + "\n\n" + input_context`），调用 chat_budgeted（常量预算），成功返回文本；异常包一层抛 `ExpertExecutionError`
  - **禁止任何其它 Hermes 调用路径**（仅 chat_budgeted）
- [ ] **Step 4: 运行确认通过**
- [ ] **Step 5: Commit**

---

### Task 5: engine.py（调度主循环 + 看板回写）

**Files:**
- Create: `backend/scheduler/engine.py`
- Test: `backend/tests/test_scheduler_engine.py`

**Interfaces:**
- Consumes: Task 1 db、Task 3 leader、Task 4 executor、`app.hermes_client.kanban_create`（回写看板）
- Produces:
  - `ENGINE_POLL_SECONDS = 3.0`
  - `ensure_engine_loop() -> None`（后台线程单例启动）
  - `advance_sessions() -> int`（单次扫描全部会话，返回处理数；可同步调用测试）
  - `handle_plan_confirm(session_id, decision: str, feedback: str = "") -> None`（decision ∈ confirm/regenerate/edit）
  - `request_resume(session_id, feedback: str) -> None`（用户不满 → resuming）

**调度逻辑（advance_sessions 内）：**

```
for session in list_sessions():
    status = session['status']
    if status == 'submitting':
        # 启动团长出方案
        lead_plan(...) → plan_json；status=planning
        if group.enable_plan_confirm: status=waiting_confirm
        else: status=running
        create subtasks(pending)；事件 plan_ready
    if status == 'waiting_confirm': continue  # 等用户
    if status == 'running':
        扫描就绪 subtask（pending & deps 全 success）→ 并发检查 → run_expert
    if status == 'resuming':
        团长带 history(上轮报告+反馈) 再出方案 → 新一轮 subtasks → running
    if subtasks 全终态(success/failed):
        status=aggregating → lead_aggregate → final_report → status=finished
```

看板回写：`_sync_kanban(subtasks)` 对每条 pending/running/success/failed 子任务 upsert 到 kanban（复用 `kanban_create`）。

- [ ] **Step 1: 写失败测试**（核心：状态迁移、依赖、并发、resume、失败不重派、看板回写单次）

```python
def test_submitting_to_waiting_confirm(monkeypatch):
    # create_session → advance_sessions → 团长出方案 → waiting_confirm
    ...

def test_waiting_confirm_does_not_dispatch(monkeypatch):
    # running 会话 + waiting_confirm 会话；仅 running 派发
    ...

def test_dependencies_blocked(monkeypatch):
    # subtask B deps=A(failed) → B 不派发且标记 failed
    ...

def test_concurrency_limit(monkeypatch):
    # 专家并发满 → 不派；释放后派
    ...

def test_resume_brings_history(monkeypatch):
    # request_resume → advance → 团长输入含上轮报告+反馈，不含旧轮子任务细节
    ...

def test_failed_subtask_not_redispatched(monkeypatch):
    # expert 抛异常 → subtask failed；下一轮 advance 不重派
    ...

def test_kanban_sync_single_writer(monkeypatch):
    # advance 后 kanban_create 被调用（engine 是唯一写入方）
    ...
```

- [ ] **Step 2: 运行确认失败**
- [ ] **Step 3: 实现 `engine.py`**（后台线程 + `_advance_loop` 每 3s；状态机逻辑；`_sync_kanban`）
- [ ] **Step 4: 运行确认通过**
- [ ] **Step 5: Commit**

---

### Task 6: API 路由（sessions/subtasks/plan-confirm/resume）

**Files:**
- Create: `backend/scheduler/api.py`
- Modify: `backend/app/main.py`（include router + 启动 engine loop）
- Modify: `backend/app/schemas.py`
- Test: `backend/tests/test_scheduler_api.py`

**Interfaces:**
- Consumes: Task 5 `handle_plan_confirm`/`request_resume`/`advance_sessions`、Task 1 db
- Produces:
  - `POST /api/teams/{team_id}/sessions  {user_query}` → `{session_id, status}`
  - `GET /api/sessions/{session_id}` → session + subtasks + plan_json
  - `POST /api/sessions/{session_id}/confirm  {decision: "confirm"|"regenerate"|"edit", feedback?}`
  - `POST /api/sessions/{session_id}/resume {feedback}` → resuming
  - `GET /api/sessions/{session_id}/events` → SSE（复用现有 StreamingResponse 模式，poll db 变化）

- [ ] **Step 1: 写失败测试**（直接调路由函数，mock db/engine）
- [ ] **Step 2: 运行确认失败**
- [ ] **Step 3: 实现 `api.py`** + schemas 扩展 + main.py 注册
- [ ] **Step 4: 运行确认通过**
- [ ] **Step 5: Commit**

---

### Task 7: 前端 API client + TeamChat 改造（方案确认/多轮）

**Files:**
- Modify: `frontend/src/api/client.ts`
- Modify: `frontend/src/pages/TeamChat.tsx`
- Create: `frontend/src/components/SessionRunner.tsx`
- Create: `frontend/src/components/PlanConfirmCard.tsx`

**Interfaces:**
- Consumes: Task 6 API
- Produces:
  - `createSession(teamId, userQuery) -> {session_id, status}`
  - `fetchSession(sessionId) -> SessionDetail`
  - `confirmPlan(sessionId, decision, feedback?)`
  - `resumeSession(sessionId, feedback)`
  - `subscribeSession(sessionId, cb) -> unsub`（SSE）
  - SessionRunner：状态机驱动的执行视图（planning→方案卡→执行进度→报告→继续对话）

- [ ] **Step 1: client.ts 新增类型与函数**
- [ ] **Step 2: PlanConfirmCard**（方案子任务列表 + 确认/重新生成/编辑需求按钮）
- [ ] **Step 3: SessionRunner**（挂 SSE，渲染各状态；点「对这个结果继续对话」→ resume）
- [ ] **Step 4: TeamChat 集成**（提交需求 → createSession → SessionRunner）
- [ ] **Step 5: 构建验证 + import 检查**
- [ ] **Step 6: Commit**

---

### Task 8: 迁移 + 回归（llm_worker 退休，teams 精简）

**Files:**
- Delete: `backend/app/llm_worker.py`
- Modify: `backend/app/teams.py`（移除 invoke/advance_once/_invoke_windows/advance 循环；保留团队 CRUD）
- Modify: `backend/app/kanban.py`（list_tasks 保留但数据源改为调度器回写；移除 _dispatch 引用）
- Modify: `backend/tests/test_llm_worker.py`（删除）、`test_review_round3.py`/`test_teams*.py`（适配新团队模型）
- Modify: `README.md`

- [ ] **Step 1: 移除 llm_worker.py 及其测试**
- [ ] **Step 2: teams.py 精简**（删 invoke 相关；`invoke` 改为创建 session 的薄封装或删除由前端直调 /api/teams/{id}/sessions）
- [ ] **Step 3: 适配其余测试**（全量 pytest 绿）
- [ ] **Step 4: README 更新**（新架构：团长调度器/多轮/Plan 确认）
- [ ] **Step 5: 全量回归 + 前端 import 检查**
- [ ] **Step 6: Commit**

---

### Task 9: 端到端 + 统一推送

**Files:**
- Modify: 全局

- [ ] **Step 1: Codespace 端到端清单**
  - [ ] 创建团 → 召唤 → 团长出方案 → 方案卡片出现
  - [ ] 确认执行 → 任务自动派发 → 看板只读展示（唯一写入方是调度器）
  - [ ] 专家执行（限预算）→ 结果回写 → 完成
  - [ ] 团长聚合 → 报告出现
  - [ ] 点「继续对话」→ 第二轮增量（团长记住上轮报告）
  - [ ] token 观察：每轮调用次数 = 1(团长方案) + N(子任务) + 1(聚合)，无循环
- [ ] **Step 2: 统一提交并推送**

```bash
git add -A
git commit -m "feat: 自研中心化团长调度器(方案A)完成——Plan确认+多轮迭代+预算防护"
git push -u origin main --force
```