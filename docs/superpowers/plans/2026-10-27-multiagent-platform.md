# Hermes 多 Agent 协作平台实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 基于 Hermes Agent v0.22.5 构建带可视化 Kanban 与专家/专家团能力的前后端协作平台（后续移植 LakeAgent）。

**Architecture:** FastAPI 后端封装 Hermes CLI（subprocess），以 Profile=专家、kanban.db=任务树为接口层；React+Vite 前端单页 4 Tab 可视化；SSE 推送看板状态。部署环境为 GitHub Codespace（Hermes 已装好），代码先写于本地仓库后统一推送。

**Tech Stack:** Python 3.12+ / FastAPI / uvicorn / subprocess / Hermes CLI；React 18 / Vite / TypeScript / zustand / @xyflow/react / EventSource。

**Spec:** `docs/superpowers/specs/2026-10-27-multiagent-platform-design.md`

## Global Constraints

- Hermes 位于 Codespace `~/.hermes`，全部交互通过 `hermes` CLI（`subprocess.run`），**不直接 import hermes 内部库**
- `hermes kanban create` 支持 `--json` 输出（含 `id` 字段）；任务 id 形如 `t_<hex>`
- 专家 = Profile：创建 = `hermes profile create <id>` + 写 `~/.hermes/profiles/<id>/SOUL.md` + 配置 model
- 后端命令前缀集中定义于 `hermes_client.py`（复用，便于单点改动）
- 模型默认 `deepseek-chat`；API key 已存在于 `~/.hermes/.env`
- MVP 执行模式为**手动触发**（`POST /api/tasks/{id}/run` → `hermes -p <expert> chat -q "work kanban task <id>"`）
- 前端端口 3000，后端 8000，vite proxy `/api → :8000`

## Review Focus

- Hermes CLI 命令缺失/报错时（如 profile 不存在），后端返回结构化错误而非裸堆栈
- kanban task id 含非 UUID 前缀（`t_`），前端/后端解析须按字符串处理不按 UUID 解析
- `--json` 输出解析失败（CLI 打印中文警告混入 stdout）→ 只解析最后 JSON 行；解析失败时抛 `HermesError("failed to parse ...")`
- 创建专家时 profile id 重复 → 返回 409 + 明确提示
- SSE 连接中断 → EventSource 自动重连；后端轮询间隔不阻塞其他请求

---

### Task 1: Hermes CLI 封装（hermes_client）

**Files:**
- Create: `backend/app/hermes_client.py`
- Test: `backend/tests/test_hermes_client.py`

**Interfaces:**
- Consumes: 无
- Produces:
  - `run_hermes(args: list[str], timeout: int = 120) -> str` — 执行 hermes CLI，返回 stdout，非零退出抛 `HermesError`
  - `kanban_create(title: str, *, assignee: str, parent_ids: list[str] | None = None, body: str = "", priority: int = 2, workspace: str | None = None) -> str` — 返回 task id
  - `kanban_list() -> list[dict]` — 返回任务列表（每条含 id/title/status/assignee）
  - `kanban_show(task_id: str) -> dict` — 单任务详情
  - `kanban_unblock(task_id: str) -> None`
  - `profile_create(name: str) -> None`
  - `profile_list() -> list[str]`
  - `profile_soul_path(name: str) -> str`
  - `execute_kanban_task(profile: str, task_id: str, timeout: int = 600) -> str` — 手动触发专家执行
  - `class HermesError(RuntimeError)` — 附带 `stderr`

- [ ] **Step 1: 写失败测试**（tests/test_hermes_client.py，全部用 `monkeypatch` 模拟 subprocess）

```python
def test_kanban_create_parses_json_id(monkeypatch):
    def fake_run(*a, **k):
        class R: stdout = '{"id": "t_abc123"}'; returncode = 0; stderr = ""
        return R()
    monkeypatch.setattr("app.hermes_client.subprocess.run", fake_run)
    assert kanban_create("调研", assignee="researcher-a") == "t_abc123"

def test_kanban_list_tolerates_warning_prefix(monkeypatch):
    def fake_run(*a, **k):
        class R: stdout = '⚠ some warning\n[{"id": "t_1", "title": "x", "status": "todo", "assignee": "a"}]'; returncode = 0; stderr = ""
        return R()
    monkeypatch.setattr("app.hermes_client.subprocess.run", fake_run)
    tasks = kanban_list()
    assert tasks == [{"id": "t_1", "title": "x", "status": "todo", "assignee": "a"}]

def test_nonzero_exit_raises_hermes_error(monkeypatch):
    class R: returncode = 2; stderr = "boom"; stdout = ""
    monkeypatch.setattr("app.hermes_client.subprocess.run", lambda *a, **k: R())
    try:
        kanban_list()
        assert False, "should raise"
    except HermesError as e:
        assert "boom" in str(e)

def test_parse_json_failure_raises(monkeypatch):
    def fake_run(*a, **k):
        class R: stdout = "not json"; returncode = 0; stderr = ""
        return R()
    monkeypatch.setattr("app.hermes_client.subprocess.run", fake_run)
    try:
        kanban_list()
        assert False, "should raise"
    except HermesError:
        pass
```

- [ ] **Step 2: 运行验证失败**
- [ ] **Step 3: 实现 `backend/app/hermes_client.py`**
  - `run_hermes`：`subprocess.run(["hermes", *args], capture_output=True, text=True, timeout=timeout)`；`returncode != 0` 抛 `HermesError(stderr)`；`HermesError` 定义于同文件
  - JSON 解析：从 stdout 中取**最后一个 `[` 或 `{` 起始的完整 JSON 行**（容忍中文警告前缀）
- [ ] **Step 4: 运行测试通过**
- [ ] **Step 5: Commit**

```bash
git add backend/app/hermes_client.py backend/tests/test_hermes_client.py
git commit -m "feat(backend): Hermes CLI 封装与测试"
```

---

### Task 2: 专家 CRUD（experts 路由）

**Files:**
- Create: `backend/app/experts.py`
- Create: `backend/app/schemas.py`
- Test: `backend/tests/test_experts.py`

**Interfaces:**
- Consumes: Task 1 的 `profile_create`, `profile_list`, `profile_soul_path`, `run_hermes`, `HermesError`
- Produces:
  - `GET /api/experts -> list[ExpertOut]`
  - `POST /api/experts (ExpertCreate) -> ExpertOut`（201）
  - `DELETE /api/experts/{name} -> {ok: true}`
  - `GET /api/skills -> list[{name, description}]`
  - `class ExpertCreate(BaseModel)`: `display_name, persona, expertise, prompt, model="deepseek-chat", skills: list[str] = [], avatar: str | None`
  - `class ExpertOut(BaseModel)`: 上述字段 + `id`（=profile 名）+ `status: str`

- [ ] **Step 1: 写失败测试**（tests/test_experts.py，mock hermes_client）

```python
def test_create_expert_writes_soul_and_calls_profile(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr("app.experts.profile_create", lambda n: calls.append(("create", n)))
    monkeypatch.setattr("app.experts.profile_soul_path", lambda n: str(tmp_path / n / "SOUL.md"))
    monkeypatch.setattr("app.experts.run_hermes", lambda *a, **k: calls.append(("run", a)))
    client = TestClient(app)
    r = client.post("/api/experts", json={"display_name": "文档评审官", "persona": "10年经验后端", "expertise": "评审文档不写代码", "prompt": "输出格式：列表", "skills": ["code-review"]})
    assert r.status_code == 201
    assert any(c[0] == "create" for c in calls)
    soul = (tmp_path / "文档评审官" / "SOUL.md").read_text(encoding="utf-8")
    assert "10年经验后端" in soul and "评审文档不写代码" in soul

def test_create_duplicate_profile_returns_409(monkeypatch):
    def fail_create(n):
        raise HermesError("profile exists")
    monkeypatch.setattr("app.experts.profile_create", fail_create)
    r = client.post("/api/experts", json={...})
    assert r.status_code == 409

def test_list_experts_maps_profiles(monkeypatch):
    monkeypatch.setattr("app.experts.profile_list", lambda: ["researcher-a", "team-lead"])
    r = client.get("/api/experts")
    assert r.status_code == 200
    assert {e["id"] for e in r.json()} == {"researcher-a", "team-lead"}
```

- [ ] **Step 2: 运行验证失败**
- [ ] **Step 3: 实现**
  - `schemas.py`：两个 Pydantic model（`ExpertCreate`, `ExpertOut`）
  - `experts.py`：`APIRouter(prefix="/api")`
    - POST：`profile_create(id)`（id 由 display_name 经 slug 化生成，保留中文，非法字符替为 `-`）→ 写 SOUL.md（persona/expertise/prompt 三段）→ skills 拷贝到 `profiles/<id>/skills/`（源目录为 `~/.hermes/skills`）
    - GET：`profile_list()` 每个通过读 SOUL.md 解析出三段（无则默认）
    - GET /api/skills：`run_hermes(["skills", "list", "--json"])` 兜底扫描 `~/.hermes/skills/*/SKILL.md` 提取 name/description
- [ ] **Step 4: 运行测试通过**
- [ ] **Step 5: Commit**

---

### Task 3: 看板桥接（kanban 路由）

**Files:**
- Create: `backend/app/kanban.py`
- Test: `backend/tests/test_kanban.py`

**Interfaces:**
- Consumes: Task 1 `kanban_list`, `kanban_show`, `kanban_unblock`, `execute_kanban_task`, `HermesError`
- Produces:
  - `GET /api/kanban/tasks -> list[KanbanTask]`（含 children 注水）
  - `GET /api/kanban/tasks/{id} -> KanbanTaskDetail`（含 summary/metadata/body）
  - `POST /api/kanban/tasks/{id}/unblock -> {ok}`()
  - `POST /api/tasks/{id}/run -> {run_id, status: "started"}`
  - `GET /api/kanban/events -> SSE 流`
  - `class KanbanTask(BaseModel)`: `id, title, status, assignee, parents: list[str], children: list[str]`
  - `class KanbanTaskDetail(KanbanTask)`: `body: str, summary: str | None, metadata: dict, runs: list`

- [ ] **Step 1: 写失败测试**

```python
def test_task_children_derived_from_parents(monkeypatch):
    rows = [
        {"id": "t_a", "title": "a", "status": "done", "assignee": "r", "parents": []},
        {"id": "t_b", "title": "b", "status": "todo", "assignee": "w", "parents": ["t_a"]},
    ]
    monkeypatch.setattr("app.kanban.kanban_list", lambda: rows)
    r = client.get("/api/kanban/tasks")
    body = r.json()
    ta = next(x for x in body if x["id"] == "t_a")
    assert ta["children"] == ["t_b"]

def test_run_task_returns_started(monkeypatch):
    monkeypatch.setattr("app.kanban.execute_kanban_task", lambda p, t: "done")
    r = client.post("/api/tasks/t_1/run")
    assert r.status_code == 200 and r.json()["status"] == "started"

def test_unknown_task_404(monkeypatch):
    monkeypatch.setattr("app.kanban.kanban_show", lambda i: (_ for _ in ()).throw(HermesError("no matching task")))
    r = client.get("/api/kanban/tasks/t_nope")
    assert r.status_code == 404
```

- [ ] **Step 2: 运行验证失败**
- [ ] **Step 3: 实现**
  - `kanban.py`：tasks 列表从 `kanban_list()` 构建并注水 children；detail 组装 parents/children/summary/metadata/runs
  - run 端点：`execute_kanban_task(task.assignee, id)` 用 `BackgroundTasks` 异步执行，立即返回 `started`
  - SSE：`StreamingResponse`，后台 `asyncio.create_task` 每 3s 轮询 `kanban_list()`，与上次快照 diff→ push `{"type":"update","tasks":[...]}`；连接关闭取消任务
- [ ] **Step 4: 运行测试通过**（SSE 测试仅验证 200 + content-type）
- [ ] **Step 5: Commit**

---

### Task 4: 专家团编排（teams 路由）

**Files:**
- Create: `backend/app/teams.py`
- Test: `backend/tests/test_teams.py`

**Interfaces:**
- Consumes: Task 1 `kanban_create`, `kanban_list`, `execute_kanban_task`, `run_hermes`；Task 3 SSE
- Produces:
  - `GET /api/teams -> list[{id, display_name, members: list[str]}]`
  - `POST /api/teams/{tid}/invoke {request: str} -> {orchestrator_task_id}` — 团长拆解后返回根任务
  - `GET /api/teams/{tid}/tasks -> list[KanbanTask]`（TeamTask = KanbanTask + `body`）
  - `GET /api/teams/{tid}/final -> {report: str | None}` — 扫描 done 任务 `metadata["final"]`
  - `TEAMS = [{"id": "research", "display_name": "全栈研究团", "members": ["researcher-a","researcher-b","reviewer","writer"], "orchestrator": "team-lead"}]` — 当前仅预置 1 团

- [ ] **Step 1: 写失败测试**

```python
def test_invoke_calls_team_lead(monkeypatch):
    calls = []
    monkeypatch.setattr("app.teams.run_hermes", lambda *a, **k: calls.append(a) or "")
    monkeypatch.setattr("app.teams.kanban_create", lambda title, **kw: "t_root")
    r = client.post("/api/teams/research/invoke", json={"request": "调研多Agent框架"})
    assert r.status_code == 200 and r.json() == {"orchestrator_task_id": "t_root"}
    assert any("team-lead" in str(c) for c in calls)

def test_final_reads_metadata(monkeypatch):
    monkeypatch.setattr("app.teams.kanban_list", lambda: [
        {"id": "t_f", "title": "综合报告", "status": "done", "assignee": "writer",
         "parents": ["t_r"], "metadata": {"final": "# 报告\n内容"}},
    ])
    r = client.get("/api/teams/research/final")
    assert r.json()["report"] == "# 报告\n内容"
```

- [ ] **Step 2: 运行验证失败**
- [ ] **Step 3: 实现**
  - `teams.py`：TEAMS 常量 + 路由
  - invoke：构建团长提示词（含 request + "请用 kanban_create 拆解并分配"）→ `run_hermes(["-p", ovator, "chat", "-q", prompt])`；若 LLM 未实际建卡，后端兜底 `kanban_create` 注册目标任务（assignee=writer）
  - final：`kanban_list()` 中 status=="done" 且 `metadata.final` 存在 → 返回；无则 `{"report": None}`
- [ ] **Step 4: 运行测试通过**
- [ ] **Step 5: Commit**

---

### Task 5: FastAPI 入口 + SSE + 预置专家配置

**Files:**
- Create: `backend/app/main.py`
- Create: `backend/requirements.txt`
- Create: `backend/presets.py`（预置 4 专家 + 1 团长 SOUL 常量）
- Modify: 无

**Interfaces:**
- Consumes: Tasks 2-4 的路由/常量
- Produces:
  - `app: FastAPI`（`main.py` 的 uvicorn 入口，`include_router` x4）
  - `scripts/bootstrap_experts.sh`：一次性创建预置 profile（researcher-a/b、reviewer、writer、team-lead 及其 SOUL.md）
  - `requirements.txt`: `fastapi, uvicorn[standard], pydantic>=2, httpx, sse-starlette`

- [ ] **Step 1: 写主入口并冒烟测试**

```python
def test_app_boots(test_client):
    r = test_client.get("/api/experts")
    assert r.status_code == 200
    r2 = test_client.get("/api/kanban/events")
    assert r2.status_code == 200 and "text/event-stream" in r2.headers["content-type"]
```

- [ ] **Step 2: 安装依赖并运行**
- [ ] **Step 3: 创建 `backend/presets.py`** — 5 个专家 SOUL.md 常量（身份/职责/指令三段，Align 设计）
- [ ] **Step 4: 创建 `scripts/bootstrap_experts.sh`** — 循环 create profile + 写 SOUL（幂等：存在则跳过），可执行
- [ ] **Step 5: Commit**

---

### Task 6: 前端脚手架 + API client

**Files:**
- Create: `frontend/`（Vite react-ts 模板）
- Create: `frontend/src/api/client.ts`
- Create: `frontend/src/store.ts`（zustand）

**Interfaces:**
- Consumes: API 契约（Task 2-5）
- Produces:
  - `fetchExperts()`, `createExpert(payload)`, `fetchSkills()`
  - `fetchTasks()`, `fetchTask(id)`, `runTask(id)`, `unblockTask(id)`
  - `invokeTeam(id, request)`, `fetchTeamTasks(id)`, `fetchTeamFinal(id)`
  - `subscribeKanban(cb) -> () => void`（EventSource 封装，自动重连）
  - zustand store：`{ activeTab, experts, tasks, sseEnabled, setActiveTab, ... }`

- [ ] **Step 1: 脚手架**（`npm create vite@latest frontend -- --template react-ts` + deps: `zustand @xyflow/react`）
- [ ] **Step 2: 配置 vite proxy**（`server.proxy = {"/api": "http://localhost:8000"}`）
- [ ] **Step 3: 实现 `api/client.ts`**（fetch 封装 + SSE 封装 + 类型定义并按 API 契约导出函数）
- [ ] **Step 4: 实现 `store.ts`**（zustand）
- [ ] **Step 5: `npm run build` 通过后 Commit**

---

### Task 7: 前端 — 专家中心 Tab

**Files:**
- Create: `frontend/src/pages/ExpertCenter.tsx`
- Create: `frontend/src/components/ExpertCard.tsx`
- Create: `frontend/src/components/CreateExpertModal.tsx`

**Interfaces:**
- Consumes: Task 6 client/store
- Produces: ExpertCenter 组件（网格 + 「+ 创建专家」→ modal 表单：display_name/persona/expertise/prompt/skills 多选/model 下拉）

- [ ] **Step 1: 写组件**（ExpertCard：头像 emoji、名称、领域、skills 标签、model、状态色点）
- [ ] **Step 2: 写 CreateExpertModal**（受控表单 → `createExpert()` → 刷新列表 + toast）
- [ ] **Step 3: 集成到 ExpertCenter**（网格布局 `grid-template-columns: repeat(auto-fill, minmax(260px,1fr))`）
- [ ] **Step 4: `npm run build` 通过后 Commit**

---

### Task 8: 前端 — 看板 Tab（列视图 + DAG 视图）

**Files:**
- Create: `frontend/src/pages/KanbanBoard.tsx`
- Create: `frontend/src/components/KanbanColumns.tsx`
- Create: `frontend/src/components/TaskDag.tsx`
- Create: `frontend/src/components/TaskDetailDrawer.tsx`

**Interfaces:**
- Consumes: Task 6 client/store（`subscribeKanban` 实时刷新）
- Produces: KanbanBoard（顶部切换「列视图 | DAG 视图」；列视图四列 todo/doing/done/blocked 按 assignee 着色；DAG 用 `@xyflow/react`：parent→child 定向边、状态着节点色、点击开 TaskDetailDrawer）

- [ ] **Step 1: 实现 KanbanColumns**（读 store.tasks 分组渲染；空列提示）
- [ ] **Step 2: 实现 TaskDag**（由 parents/children 推导 edges；`position` 计算：按拓扑层数分层布局）
- [ ] **Step 3: 实现 TaskDetailDrawer**（body/summary/metadata/runs 展示 + 「运行」「解封」按钮调 API）
- [ ] **Step 4: 挂载 SSE**（组件 mount → `subscribeKanban(update store)`）
- [ ] **Step 5: 构建通过后 Commit**

---

### Task 9: 前端 — 专家团 Tab + 配置 Tab + App 整合

**Files:**
- Create: `frontend/src/pages/ExpertTeam.tsx`
- Create: `frontend/src/pages/Settings.tsx`
- Modify: `frontend/src/App.tsx`（Tab 布局 + zustand activeTab）

**Interfaces:**
- Consumes: 前置全部
- Produces: ExpertTeam（输入框 → invokeTeam → 实时任务 DAG/列表 → 全部 done 后显示「最终报告」区，调 fetchTeamFinal 渲染 markdown 文本）；Settings（展示 base_url/model/health 只读）

- [ ] **Step 1: 实现 ExpertTeam.tsx**
- [ ] **Step 2: 实现 Settings.tsx**（读 `GET /api/health` 一类的只读信息；无则显示静态配置说明）
- [ ] **Step 3: 改 App.tsx**（Header Tab 切换 + 4 页）
- [ ] **Step 4: `npm run build` + 整体冒烟**
- [ ] **Step 5: Commit**

---

### Task 10: 一键启动脚本 + README + 统一推送

**Files:**
- Create: `dev.sh`
- Create: `README.md`
- Modify: 无

- [ ] **Step 1: 写 `dev.sh`**（`set -e`；后台起 uvicorn（`--port 8000 --reload`）；起 vite `--host 0.0.0.0 --port 3000`；trap 清理子进程；打印访问地址）
- [ ] **Step 2: 写 `README.md`**（背景 / 架构图 / 快速开始（Codespace 内 `bash dev.sh`）/ API 一览 / 与 LakeAgent 迁移关系 / 故障排查）
- [ ] **Step 3: 在 Codespace 实际跑通**（bootstrap 预置专家 → 看板建任务 → 手动 run → 前端可见流转）
- [ ] **Step 4: 统一提交并推送**

```bash
git add -A
git commit -m "feat: Hermes 多Agent协作平台（可视化Kanban+专家/专家团）"
git push origin main
```