# Hermes 多 Agent 协作平台

基于 **Hermes Agent** 的多 Agent 协作平台原型，提供**可视化 Kanban**、**专家（Expert）** 与 **专家团（Expert Team）** 能力，架构与 LakeAgent 对齐，便于后续迁移回华为 LakeAgent 生态。

## 核心概念

| 平台概念 | Hermes 底盘 | 说明 |
|---|---|---|
| **专家** | Profile（SOUL.md + 独立模型 + skills） | 人设 + 方法论 + 工具链 |
| **可视化看板** | 原生 Kanban（SQLite 任务树 + 依赖） | 列视图 + DAG 依赖图 |
| **专家团** | orchestrator 人物 + kanban 任务分解 | 团长拆解 → 成员并行 → 综合交付 |

## 架构

```
浏览器 (React + Vite)
   │  REST + SSE
   ▼
Backend (Python + FastAPI)
   ├─ /api/experts        专家 = Profile CRUD（创建/列表/删除）
   ├─ /api/skills         方法论技能列表
   ├─ /api/teams          专家团编排（invoke/tasks/final）
   ├─ /api/kanban/*       看板桥接（列表/DAG/详情/解封）
   ├─ /api/tasks/{id}/run 手动触发专家执行
   └─ /api/kanban/events  SSE 实时推送
   │  subprocess
   ▼
Hermes Agent (~/.hermes)
   ├─ Profiles（专家）
   ├─ kanban.db（任务树）
   └─ skills（方法论）
```

## 快速开始（Codespace / Linux）

```bash
# 1. 启动前后端（首次会装前端依赖）
bash dev.sh

# 2. 浏览器打开
#    前端:  http://localhost:3000
#    后端:  http://localhost:8000/docs

# 3.（可选）加载预置的 4 个专家 + 1 个团长
bash scripts/bootstrap_experts.sh
```

## 使用流程

### 专家中心
- 查看专家卡片（头像/领域/技能/模型）
- 「+ 创建专家」填表 → 后端创建 Profile + SOUL.md + 绑定 skills

### 专家团
1. 输入需求（如"调研多智能体框架并输出报告"）
2. 团长（team-lead）自动拆解 → kanban 建任务树
3. 点「逐个执行待办任务」触发成员执行（MVP 手动模式）
4. 看 DAG/看板实时流转，全部 done 后显示综合报告

### 看板
- 列视图：todo / doing / done / blocked（按 assignee 着色）
- DAG 视图：依赖关系图（parent→child，状态着色）
- 点卡片：详情抽屉（body/summary/metadata/执行历史 + 运行/解封按钮）
- SSE 自动实时刷新

## 与 LakeAgent 的关系

本项目的后端层（`backend/app/*.py`）抽取了与 LakeAgent 相同的接口模型：

- **专家 = Profile**：`experts.py` 映射 Hermes Profile 管理与 SOUL.md
- **看板 = kanban.db**：`kanban.py` 桥接 Hermes 原生 Kanban
- **编排 = orchestrator + 任务树**：`teams.py` 复用 Hermes 拆解/依赖机制

迁移到 LakeAgent 时，仅需替换 `hermes_client.py` 中的 subprocess 调用为 LakeAgent 的 HTTP/内部 API，其余路由与前端可直接沿用。

## 目录结构

```
backend/
  app/
    main.py           # FastAPI 入口 + CORS + health
    hermes_client.py  # Hermes CLI 封装（单点改动）
    schemas.py        # Pydantic 模型
    experts.py        # 专家 CRUD
    kanban.py         # 看板桥接 + SSE
    teams.py          # 专家团编排
    presets.py        # 预置专家/团长定义
  tests/              # pytest（沙箱可跑，mock subprocess）
  requirements.txt
frontend/
  src/
    api/client.ts     # 类型化 REST + SSE client
    store.ts          # zustand 全局状态
    pages/            # 4 Tab：专家中心/专家团/看板/配置
    components/       # ExpertCard/Modal/KanbanColumns/DAG/DetailDrawer
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