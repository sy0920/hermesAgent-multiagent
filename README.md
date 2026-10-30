# Hermes 多 Agent 协作平台

基于 **Hermes Agent** 的多 Agent 协作平台原型，提供**可视化 Kanban**、**专家（Expert）**、**专家团（Expert Team）** 与**中心化团长调度器**能力，架构与 LakeAgent 对齐。

## 核心概念

| 平台概念 | 实现 | 说明 |
|---|---|---|
| **专家** | Hermes Profile（SOUL.md + 模型 + skills） | 限预算 Agent 实例（`--max-turns`/`--toolsets`/`--run-budget`）|
| **专家团** | teams.json（成员 + 主理人）| 团长=成员专家，只调度不执行 |
| **中心化调度器** | scheduler 包（SQLite 台账 + 引擎）| 团长出方案 → 调度器代码分配 → 专家执行 → 团长聚合复审 |
| **Plan 确认** | waiting_confirm 状态机 | 先方案后执行（确认/重新生成/编辑需求）|
| **多轮迭代** | resuming 状态 | 不满意 → 团长基于上轮报告+反馈规划新一轮 |
| **可视化看板** | Kanban（调度器单向回写）| 只读展示，专家不碰 |

## 架构

```
浏览器 (React + Vite) — 专家团对话页(方案确认/执行进度/多轮)
   │  REST + SSE
   ▼
Backend (Python + FastAPI)
   ├─ /api/experts          专家 CRUD
   ├─ /api/teams            专家团 CRUD
   ├─ /api/teams/{id}/sessions  创建调度会话
   ├─ /api/sessions/*       会话查询/confirm/resume
   ├─ /api/kanban/*         看板（调度器回写，只读展示）
   │
   ▼
scheduler/（中心化调度器，纯代码驱动）
   ├─ db.py         SQLite 台账（session/subtask，调度器独占）
   ├─ leader.py     团长（限预算 Hermes Agent：出方案/聚合）
   ├─ executor.py   专家（限预算 Hermes Agent：--max-turns 10 --run-budget 180）
   ├─ engine.py     主循环（状态机/依赖/并发/多轮/看板单向回写）
   └─ api.py        HTTP 封装
   │
   ▼
Hermes Profiles（专家/团长，均为有界预算 Agent 实例）
```

## 快速开始（Codespace / Linux）

```bash
# 1. 启动前后端（首次会装前端依赖）
bash dev.sh

# 2. 浏览器打开
#    前端:  http://localhost:3000
#    后端:  http://localhost:8000/docs

# 3.（可选）加载预置的 4 个专家
bash scripts/bootstrap_experts.sh
```

## 使用流程

### 专家中心（首页 /experts）
- 查看专家卡片（头像/领域/技能/模型）
- 点卡片 → 专家详情 → 「召唤专家」→ 进入与该专家的多轮对话页
- 「+ 创建专家」填表 → 后端创建 Profile + SOUL.md + 绑定 skills

### 专家团中心（/teams）
- 团队卡片网格（展示主理人 + 成员）
- 「+ 创建专家团」→ 选主理人（团长，只调度）+ 成员
- 点团队卡片 → 团队详情 → 「召唤专家团」→ 进入团队对话页

### 专家团对话页（/chat/team/:id）
1. 输入需求 → 「🚀 提交需求」（创建调度会话）
2. 团长（限预算 Agent）制定方案 → **方案确认卡片**（确认执行 / 重新生成 / 编辑需求）
3. 确认后 → 调度器自动分配专家并行执行（每个专家一次限预算 Agent 调用）
4. 全部完成 → 团长聚合复审 → 最终报告
5. **不满意？** → 输入补充意见点「继续对话」→ 团长基于上轮报告+反馈规划新一轮（多轮迭代）

### 看板（/kanban）
- 全局视角：列视图 + DAG（由调度器单向回写，只读展示）
- SSE 自动实时刷新

## 与 LakeAgent 的关系

本项目的后端层（`backend/app/*.py` + `backend/scheduler/*`）抽取了与 LakeAgent 相同的接口模型：

- **专家 = Profile**：`experts.py` 映射 Hermes Profile 管理与 SOUL.md
- **看板 = kanban.db**：`kanban.py` 桥接 Hermes 原生 Kanban（调度器单向回写）
- **团队 = teams.json**：`team_store.py` 持久化团队（主理人/成员）
- **调度器 = scheduler/**：自研中心化调度（SQLite 台账 + 状态机引擎），Hermes 只作为限预算 Agent 调用源

迁移到 LakeAgent 时，仅需替换 `hermes_client.py` 中的 subprocess 调用为 LakeAgent 的 HTTP/内部 API，其余路由、前端与调度器可直接沿用。

## 目录结构

```
backend/
  app/
    main.py           # FastAPI 入口 + CORS + health + 调度引擎启动
    hermes_client.py  # Hermes CLI 封装（单点改动，含 chat_budgeted）
    schemas.py        # Pydantic 模型
    team_store.py     # 团队持久化（teams.json CRUD）
    experts.py        # 专家 CRUD + 专家对话（多轮会话）
    kanban.py         # 看板桥接 + SSE（只读展示）
    teams.py          # 专家团 CRUD（兼容旧 invoke，新流程走 scheduler）
  scheduler/
    db.py             # SQLite 台账（session/subtask）
    leader.py         # 团长（限预算 Agent：出方案/聚合复审）
    executor.py       # 专家（限预算 Agent 执行）
    engine.py         # 调度主循环（状态机/依赖/并发/多轮/看板回写）
    api.py            # 会话 API（create/confirm/resume）
    presets.py        # 预置专家定义
  tests/              # pytest（沙箱可跑，mock subprocess）
  requirements.txt
frontend/
  src/
    api/client.ts     # 类型化 REST + SSE client
    store.ts          # zustand 全局状态
    pages/            # 专家中心/详情/对话、团队中心/详情/对话、看板、配置
    components/       # ExpertCard/CreateExpertModal/CreateTeamModal/KanbanColumns/DAG/DetailDrawer
scripts/
  bootstrap_experts.sh # 预置专家一键加载
```

## 配置

| 项 | 默认 | 说明 |
|---|---|---|
| 模型 | `deepseek-chat` | `~/.hermes/.env` 已配置的 API key |
| 后端端口 | 8000 | `BACKEND_PORT` 环境变量 |
| 前端端口 | 3000 | `FRONTEND_PORT` 环境变量 |

## 测试

```bash
cd backend
python -m pytest tests/ -v
```

后端测试通过 mock `subprocess` 运行，不依赖真实 Hermes / 网络。

## 已知限制（MVP）

- 任务执行为手动触发模式（避免依赖 gateway dispatcher 稳定性），未来可将 `execute_kanban_task` 切换为 dispatcher 自动派发
- 专家创建为表单式（对齐 WorkBuddy 配置项），对话式引导留待二期
- 前端构建验证需在可访问 npm registry 的环境执行（本仓库已含 package.json/tsconfig/vite.config）