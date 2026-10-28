# WorkBuddy 式专家团中心 + 页面化重构 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 Hermes 多 Agent 平台从 4-Tab 单团硬编码重构为 WorkBuddy 式"专家团中心 + 专家/专家团详情/召唤 + 专属对话页（多轮专家聊、按团过滤看板+DAG）"，并支持创建专家团。

**Architecture:** 前端 Tab → React Router 8 路由；后端团队模型 `~/.hermes/teams.json` 持久化（创建+展示），移除 `_TEAM_DEFS`/team-lead；专家对话走 Hermes `--resume` 会话续聊；团队执行复用现有 Planner/Executor + 推进循环，团长=该团 leader、assignee 白名单=该团 members。

**Tech Stack:** Python/FastAPI/pytest（mock subprocess）；React 18/Vite/TS/zustand/react-router-dom/@xyflow/react。

**Spec:** `docs/superpowers/specs/2026-10-27-workbuddy-teams-redesign.md`

## Global Constraints

- 团队存储路径 `~/.hermes/teams.json`；MVP 只做创建+展示，无 PUT/DELETE
- 无默认团：teams.json 不存在或空 → 返回空列表
- 专家 id 来自现有专家中心（Profile）；团长 = 该团 `leader`，仅调度
- assignee 白名单 = 该团 `members`；invoke 计划校验失败回落默认 4 任务树（recruiter — 保留现有 `_build_default_tree` 但成员动态）
- 专家对话：`hermes -p <id> chat -q "<msg>"` / `hermes -p <id> chat --resume <sid> -q "<msg>"`，返回 `{reply, session_id}`
- 看板/DAG 按团过滤在**前端**做（`tasks.filter(t => team.members.includes(t.assignee))`）
- 首页 `/` 重定向 `/experts`
- 移除 `_TEAM_DEFS`、team-lead 相关代码与测试；bootstrap_experts.sh 不再创建 team-lead

## Review Focus

- **团队 id 生成**：display_name 是中文时（如"SQL 优化团"）需生成合法 slug（复用 experts._slugify 思路），重复创建同名额返回 409
- **teams.json 并发/缺失**：文件不存在返回 `[]` 不崩溃；写入用临时文件+原子替换防并发撕裂
- **专家 chat 会话续聊**：`--resume <sid>` 必须在 args 正确位置；Hermes 输出可能含警告前缀，reply 取最后非空行
- **invoke 的 leader 必须是 members 之一**：前端表单约束 + 后端兜底校验；leader 不在 members 时 422
- **团过滤的 DAG**：某任务 assignee 不在该团 members 但仍被 parent 引用时，DAG 应显示该任务（占位灰显），否则边悬挂
- 无团的 `/teams` 空态与"创建第一个团"按钮；创建后刷新列表（表单成功后 fetchTeams）

---

### Task 1: 后端团队持久化模型（teams.json CRUD）

**Files:**
- Create: `backend/app/team_store.py`
- Modify: `backend/app/teams.py`（`_TEAM_DEFS` 移除，改从 team_store 读）
- Modify: `backend/app/schemas.py`
- Test: `backend/tests/test_team_store.py`

**Interfaces:**
- Consumes: 无（独立新模块）
- Produces:
  - `class Team(BaseModel)`: `id: str, display_name: str, avatar: str, description: str = "", leader: str, members: list[str], created_at: str`
  - `class TeamCreate(BaseModel)`: `display_name, description="", leader, members: list[str]`
  - `class TeamStore`:
    - `load() -> list[Team]`（文件缺失→[]）
    - `create(payload: TeamCreate) -> Team`（slug 校验重复→ValueError）
    - `get(team_id) -> Team | None`
  - `teams.py` 中 `_teams()` 替换 `_TEAM_DEFS`；`_get_team(team_id)` 从 store 读

- [ ] **Step 1: 写失败测试** `backend/tests/test_team_store.py`

```python
import json
import pytest
from pathlib import Path
from app.team_store import TeamStore


def test_load_empty_when_file_missing(tmp_path, monkeypatch):
    monkeypatch.setattr("app.team_store.TEAMS_PATH", tmp_path / "teams.json")
    s = TeamStore()
    assert s.load() == []


def test_create_and_load_roundtrip(tmp_path, monkeypatch):
    p = tmp_path / "teams.json"
    monkeypatch.setattr("app.team_store.TEAMS_PATH", p)
    s = TeamStore()
    t = s.create(TeamCreate(display_name="SQL 优化团", description="慢 SQL 诊断",
                            leader="sql", members=["sql", "reviewer", "writer"]))
    assert t.id == "sql"  # slug of "SQL 优化团"
    reloaded = TeamStore().load()
    assert reloaded[0].id == "sql"
    assert reloaded[0].leader == "sql"


def test_create_duplicate_raises(tmp_path, monkeypatch):
    p = tmp_path / "teams.json"
    monkeypatch.setattr("app.team_store.TEAMS_PATH", p)
    s = TeamStore()
    s.create(TeamCreate(display_name="a", leader="x", members=["x"]))
    with pytest.raises(ValueError, match="already exists"):
        s.create(TeamCreate(display_name="a", leader="x", members=["x"]))
```

- [ ] **Step 2: 运行确认失败**：`pytest tests/test_team_store.py -v` → ModuleNotFoundError
- [ ] **Step 3: 实现 `team_store.py`**
  - `TEAMS_PATH = Path.home() / ".hermes" / "teams.json"`
  - `slugify`：复用 experts 逻辑（ascii 保留、中文→`team-<ts>`），抽到 team_store 内私有函数
  - `load`：文件不存在/损坏→`[]`；`create`：load→查重→append→**临时文件+`os.replace`**写回；`get`：按 id 查
  - slug 生成后若与已有 id 冲突抛 `ValueError`
- [ ] **Step 4: 运行确认通过**
- [ ] **Step 5: Commit**

```bash
git add backend/app/team_store.py backend/tests/test_team_store.py
git commit -m "feat(backend): 团队持久化模型 teams.json CRUD"
```

---

### Task 2: 后端团队路由改造（读 store + POST 创建 + 详情）

**Files:**
- Modify: `backend/app/teams.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_teams_crud.py`

**Interfaces:**
- Consumes: Task 1 `TeamStore`/`Team`/`TeamCreate`
- Produces:
  - `GET /api/teams -> list[Team]`（列表改为含 description/leader/members）
  - `POST /api/teams (TeamCreate) -> Team`（201；重复→409；leader 不在 members→422）
  - `GET /api/teams/{id} -> Team`（不存在→404）
  - teams.py 移除 `_TEAM_DEFS` 常量和 `_get_team` 改用 store；`list_teams`/`team_final`/`invoke_team` 改接新模型

- [ ] **Step 1: 写失败测试** `backend/tests/test_teams_crud.py`（直接调路由函数，因沙箱禁 loopback）

```python
from app import teams
from app.team_store import TeamStore, TeamCreate
import pytest


def test_create_team_via_route(monkeypatch, tmp_path):
    fake_home = tmp_path / "home"
    (fake_home / ".hermes").mkdir(parents=True)
    monkeypatch.setattr("app.team_store.Path.home", staticmethod(lambda: fake_home))
    created = teams.create_team(TeamCreate(
        display_name="SQL 优化团", description="d",
        leader="sql", members=["sql", "reviewer"]))
    assert created.id == "sql"
    assert "reviewer" in created.members


def test_create_team_leader_must_be_member(monkeypatch, tmp_path):
    fake_home = tmp_path / "home"
    (fake_home / ".hermes").mkdir(parents=True)
    monkeypatch.setattr("app.team_store.Path.home", staticmethod(lambda: fake_home))
    with pytest.raises(Exception) as e:
        teams.create_team(TeamCreate(
            display_name="x", leader="nobody", members=["a"]))
    assert e.type.__name__ == "HTTPException" and e.value.status_code == 422


def test_get_missing_team_404(monkeypatch, tmp_path):
    fake_home = tmp_path / "home"
    (fake_home / ".hermes").mkdir(parents=True)
    monkeypatch.setattr("app.team_store.Path.home", staticmethod(lambda: fake_home))
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as e:
        teams.get_team("nope")
    assert e.value.status_code == 404
```

- [ ] **Step 2: 运行确认失败**
- [ ] **Step 3: 改造 `teams.py`**
  - 顶部 `from app.team_store import TeamStore, Team, TeamCreate`
  - 删 `_TEAM_DEFS`；`_get_team` → `store.get(id)` 或抛 404
  - `create_team(payload)`：`leader not in members` → 422；`store.create` 异常（重复）→ 409
  - `invoke_team`：`team["leader"]` 作团长；`team["members"]` 作白名单
- [ ] **Step 4: 注册路由到 main.py**（`@router.post("/teams")`、`@router.get("/teams/{team_id}")` 等）
- [ ] **Step 5: 运行测试通过**
- [ ] **Step 6: Commit**

---

### Task 3: 专家对话 API（多轮会话）

**Files:**
- Modify: `backend/app/experts.py`
- Modify: `backend/app/hermes_client.py`
- Modify: `backend/app/schemas.py`
- Test: `backend/tests/test_expert_chat.py`

**Interfaces:**
- Consumes: 无（纯新增）
- Produces:
  - `ChatRequest`: `message: str, session_id: str | None = None`
  - `ChatResponse`: `reply: str, session_id: str`
  - `hermes_client.expert_chat(profile: str, message: str, session_id: str | None = None) -> str`（返回 reply 文本）
  - `POST /api/experts/{id}/chat (ChatRequest) -> ChatResponse`（id 不存在→404）

- [ ] **Step 1: 写失败测试** `backend/tests/test_expert_chat.py`

```python
import pytest
from app import experts
from app.schemas import ChatRequest


def test_expert_chat_new_session(monkeypatch):
    captured = {}
    monkeypatch.setattr("app.experts.expert_chat",
        lambda p, m, sid=None: captured.update(p=p, m=m, sid=sid) or "hi")
    r = experts.expert_chat_route("sql", ChatRequest(message="你好"))
    assert r.reply == "hi"
    assert captured["sid"] is None


def test_expert_chat_resume(monkeypatch):
    captured = {}
    monkeypatch.setattr("app.experts.expert_chat",
        lambda p, m, sid=None: captured.update(p=p, m=m, sid=sid) or "ok")
    experts.expert_chat_route("sql", ChatRequest(message="继续", session_id="s_1"))
    assert captured["sid"] == "s_1"
```

**hermes_client.expert_chat 的 subprocess 测试（在 test_expert_chat.py）**：

```python
def test_expert_chat_builds_resume_args(monkeypatch):
    captured = []
    class Fake: returncode = 0; stdout = "回复文本\n"; stderr = ""
    monkeypatch.setattr("app.hermes_client.subprocess.run",
        lambda a, **k: captured.append(a) or Fake())
    from app.hermes_client import expert_chat
    expert_chat("sql", "继续", session_id="s_1")
    joined = " ".join(captured[0])
    assert "--resume" in joined and "s_1" in joined
    assert "-p" in joined and "sql" in joined


def test_expert_chat_new_no_resume(monkeypatch):
    captured = []
    class Fake: returncode = 0; stdout = "回复\n"; stderr = ""
    monkeypatch.setattr("app.hermes_client.subprocess.run",
        lambda a, **k: captured.append(a) or Fake())
    from app.hermes_client import expert_chat
    expert_chat("sql", "你好", session_id=None)
    joined = " ".join(captured[0])
    assert "--resume" not in joined
```

- [ ] **Step 2: 运行确认失败**
- [ ] **Step 3: 实现 `hermes_client.expert_chat`**
  - `subprocess.run(["hermes", "-p", profile, "chat", *(["--resume", session_id] if session_id else []), "-q", message], ...)`
  - 返回过滤警告前缀后的 reply（取最后一段非空，含 `Session:` 行则剥离）
- [ ] **Step 4: 实现 `experts.expert_chat_route`**
  - profile 必须存在于 `profile_list()`，否则 404
  - 调用 `expert_chat` → 返回 `ChatResponse(reply, session_id)`（session_id = 客户端传的或新生成的）
- [ ] **Step 5: 注册 `POST /api/experts/{id}/chat` 路由**
- [ ] **Step 6: 运行测试通过**
- [ ] **Step 7: Commit**

---

### Task 4: 现有团队测试适配（移除 team-lead / _TEAM_DEFS）

**Files:**
- Modify: `backend/tests/test_teams.py`
- Modify: `backend/tests/test_teams_plan.py`
- Modify: `backend/tests/test_review_round2.py`
- Modify: `backend/tests/test_round3.py`（如有对 _TEAM_DEFS 的引用）
- Modify: `backend/app/presets.py`（移除 team-lead 预设）
- Modify: `scripts/bootstrap_experts.sh`

**Interfaces:**
- Consumes: Task 1-2 的 `TeamStore`/`TeamCreate`
- Produces: 全量测试绿；`presets.PRESET_EXPERTS` 不含 `team-lead`

- [ ] **Step 1: 全局搜索** `grep -rn "_TEAM_DEFS\|team-lead" backend/ scripts/` → 列出所有引用点
- [ ] **Step 2: 修复测试**
  - test_teams.py / test_teams_plan.py：所有 `monkeypatch.setattr("app.teams._registered_expert_ids", ...)` 保留；`invoke_team` 相关测试需先建一个 team 或 mock `store.get` 返回含 leader/members 的 team
  - 为每个 invoke 相关测试加 `monkeypatch.setattr("app.team_store.TeamStore.get", lambda s, i: Team(...))` 或直接在测试内 `teams.team_store = TeamStore()` 并预建 team
  - test_review_round2.py 的 `test_invoke_auto_dispatches_workers_in_parallel` 同样适配 leader/members
- [ ] **Step 3: 移除 team-lead 预设** — presets.py 删 team-lead 条目；bootstrap_experts.sh 对应处理（不再创建）
- [ ] **Step 4: 全量运行** `pytest tests/ -q` → 全绿
- [ ] **Step 5: Commit**

---

### Task 5: 前端脚手架 — React Router + Header + store

**Files:**
- Modify: `frontend/package.json`（+`react-router-dom`）
- Modify: `frontend/src/main.tsx`（BrowserRouter 包裹）
- Modify: `frontend/src/App.tsx`（Routes + Header 链接，替代 Tab）
- Modify: `frontend/src/api/client.ts`（+`createTeam`/`fetchTeam`/`expertChat`）
- Modify: `frontend/src/store.ts`（+`sessionIds` 或沿用组件状态；teams 已存在）

**Interfaces:**
- Consumes: Task 2 API（`POST /api/teams`、`GET /api/teams/{id}`）；Task 3 API（`POST /api/experts/{id}/chat`）
- Produces:
  - `createTeam(payload): Promise<Team>`、`fetchTeam(id): Promise<Team>`
  - `expertChat(id, message, sessionId?): Promise<{reply, session_id}>`
  - 路由变化时 `useStore` 全局数据继续供各页消费

- [ ] **Step 1: 依赖** — `npm install react-router-dom`（Codespace 执行；本地改 package.json）
- [ ] **Step 2: client.ts 新增 3 个函数**（契约见 Review Focus）
- [ ] **Step 3: main.tsx** — `<BrowserRouter><App/></BrowserRouter>`
- [ ] **Step 4: App.tsx 重构**
  - Header：`NavLink`（/、/teams、/kanban、/settings）
  - Routes：全部 8 条，`/` → `<Navigate to="/experts" replace/>`
  - 移除 `activeTab`/Tab 逻辑；数据预取（experts/teams/tasks/SSE）保留在 App 顶层
- [ ] **Step 5: 构建验证**（Codespace：`npm run build`；本地 import 检查）
- [ ] **Step 6: Commit**

---

### Task 6: 前端 — 专家中心/详情/对话页

**Files:**
- Modify: `frontend/src/pages/ExpertCenter.tsx`（网格 + 点卡片→路由）
- Create: `frontend/src/pages/ExpertDetail.tsx`
- Create: `frontend/src/pages/ExpertChat.tsx`

**Interfaces:**
- Consumes: Task 5 `expertChat`/client；store.experts
- Produces: 三个路由页组件

- [ ] **Step 1: ExpertCenter** — 卡片 onClick → `navigate(/experts/${e.id})`；保留创建专家 modal
- [ ] **Step 2: ExpertDetail** — 读 `useParams().id`；从 store 找专家展示人设/技能/模型/状态；「召唤专家」按钮 → `/chat/expert/:id`
- [ ] **Step 3: ExpertChat** — 聊天 UI（消息数组 + 输入框 + 发送）；维护 `session_id` 状态；SSE 不需要（独立对话）
- [ ] **Step 4: 构建验证**
- [ ] **Step 5: Commit**

---

### Task 7: 前端 — 专家团中心/详情

**Files:**
- Create: `frontend/src/pages/TeamCenter.tsx`
- Create: `frontend/src/pages/TeamDetail.tsx`
- Create: `frontend/src/components/CreateTeamModal.tsx`

**Interfaces:**
- Consumes: Task 2 API（`createTeam`/`fetchTeams`）；store.experts（供主理人/成员下拉）
- Produces: 路由页组件；创建团表单

- [ ] **Step 1: TeamCenter** — 团卡片网格（无团空态+主创建按钮）；「+ 创建专家团」→ CreateTeamModal；点卡片 → `/teams/:id`
- [ ] **Step 2: CreateTeamModal** — 表单字段：display_name/description/leader(下拉)/members(多选)，提交 `createTeam` → 刷新 `fetchTeams` + 关闭
- [ ] **Step 3: TeamDetail** — 显示 description/leader/members（leader 高亮「主理人」tag）；「召唤专家团」→ `/chat/team/:id`
- [ ] **Step 4: 构建验证**
- [ ] **Step 5: Commit**

---

### Task 8: 前端 — 专家团对话页（按团过滤看板 + DAG + 报告）

**Files:**
- Create: `frontend/src/pages/TeamChat.tsx`
- Modify: `frontend/src/components/KanbanColumns.tsx`（可选 `filterAssignees?: string[]` prop）
- Modify: `frontend/src/components/TaskDag.tsx`（可选过滤分配）
- Modify: `frontend/src/components/TaskDetailDrawer.tsx`（复用）

**Interfaces:**
- Consumes: Task 5 client（invokeTeam/runTask/fetchTeamFinal）；store.tasks/teams
- Produces: `/chat/team/:id` 页面；过滤后的看板+DAG

- [ ] **Step 1: TeamChat 骨架** — 顶部团信息（名/主理人/成员 tag）+ 需求输入 + 「🚀 召唤专家团」+「▶ 并行执行待办」（复用 runAllPending 并行版）+ 报告区（复用 ExpertTeam 的自动拉取逻辑，加 `tasks` 依赖）
- [ ] **Step 2: 按团过滤** — `filtered = tasks.filter(t => team.members.includes(t.assignee))`；看板列与 DAG 都用 filtered
- [ ] **Step 3: DAG 悬挂任务占位** — filtered 中若某任务 parent 不在 filtered，在 DAG 加灰显占位节点（防边悬挂）
- [ ] **Step 4: 组件 props 扩展** — KanbanColumns/TaskDag 接受可选 tasks 过滤（或直接传 filtered）
- [ ] **Step 5: 构建验证 + 整体冒烟**
- [ ] **Step 6: Commit**

---

### Task 9: 全局看板 + 配置页兼容 + 端到端验证

**Files:**
- Modify: `frontend/src/pages/KanbanBoard.tsx`（确认全局视图仍可用）
- Modify: `frontend/src/pages/Settings.tsx`（专家团展示适配新 Team 模型）
- Modify: `docs/superpowers/README.md`（快速开始/使用流程更新）

- [ ] **Step 1: KanbanBoard** — 确认仍展示全部任务（不改过滤）；若 Task 8 加了 prop，此处不传即全局
- [ ] **Step 2: Settings** — `t.members.join` 仍在（TeamOut 已含 members）；确认 leader 字段展示
- [ ] **Step 3: README** — 更新：路由结构、创建专家团、召唤流程、首页=专家中心
- [ ] **Step 4: 全量测试** `pytest tests/ -q` → 绿；`npm run build`（Codespace）→ 绿
- [ ] **Step 5: 端到端手测清单**（Codespace）：
  - [ ] 首页 `/experts` 重定向 OK
  - [ ] 创建专家团（选主理人+成员）成功 → 团队中心出现卡片
  - [ ] 团详情 → 召唤 → `/chat/team/:id`
  - [ ] 输入需求 invoke → 任务树建成 → 看板按团过滤 → 推进循环自动跑
  - [ ] 全部 done → 最终报告自动出现
  - [ ] 专家对话页多轮续聊（第二句有记忆）
- [ ] **Step 6: Commit**

---

### Task 10: 收尾 — 移除幽灵引用 + 统一推送

**Files:**
- Modify: 全局（扫 `_TEAM_DEFS`/team-lead/TabKey 残留）
- Modify: `frontend/src/store.ts`（若 activeTab/TabKey 无消费则删）

- [ ] **Step 1: 全局搜索残留** — `grep -rn "_TEAM_DEFS\|team-lead\|TabKey\|activeTab" frontend/src backend/app` → 清理
- [ ] **Step 2: store 精简** — 删除无消费者的 TabKey/activeTab/setActiveTab
- [ ] **Step 3: 全量回归** — pytest 全绿 + import 检查 + Control build
- [ ] **Step 4: 统一提交并推送**

```bash
git add -A
git commit -m "refactor: WorkBuddy 式专家团中心+页面化重构完成"
git push -u origin main --force
```