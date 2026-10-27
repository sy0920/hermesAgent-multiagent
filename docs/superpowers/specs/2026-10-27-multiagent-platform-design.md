# Hermes Multi-Agent 协作平台设计文档

创建日期：2026-10-27
项目：hermesAgent-multiagent（基于 Hermes Agent 的多 Agent 协作演示平台，后续移植到 LakeAgent）

## 1. 目标与背景

在 Hermes Agent v0.22.5（Codespace 已安装）之上构建一个多 Agent 协作平台，提供可视化 Kanban、专家（Expert）与专家团（Expert Team）能力，架构与 LakeAgent 对齐，便于后续将成果迁移回 LakeAgent/LakeAgentImage 生态。

关键用户诉求：
- 真实的 Hermes Agent 项目（非 bash 玩具脚本）
- 可视化 Kanban（列视图 + DAG 依赖图）
- 专家中心（专家即 Hermes Profile，含 Skill 绑定，可创建）
- 专家团（团长自动拆解 → 并行执行 → 整合交付）
- 前端可视化页面（React + Vite）

## 2. 总体架构

```
浏览器 (React + Vite / 单页 Tab)
  │  REST + SSE
  ▼
Backend (Python + FastAPI)
  ├─ experts 路由（专家=Profile CRUD）
  ├─ teams 路由（专家团编排）
  ├─ kanban 路由（看板桥接）
  └─ dispatcher（任务触发）
  │  subprocess / Python API
  ▼
Hermes Agent (~/.hermes)
  ├─ Profiles（专家：SOUL.md + model + skills）
  ├─ kanban.db（SQLite 任务树，含依赖）
  └─ gateway/dispatcher（自动派发，可选）
```

## 3. 数据模型

### 3.1 Expert（专家 = Hermes Profile 映射）

| 字段 | 类型 | 对应 Hermes 实现 |
|---|---|---|
| id | str | Profile 名（唯一） |
| display_name | str | 卡片显示名 |
| avatar | str | emoji / 首字母 |
| persona | str | SOUL.md 身份段 |
| expertise | str | SOUL.md 职责段 |
| prompt | str | SOUL.md 指令段 |
| model | str | config.yaml model |
| skills | list[str] | profile skills/ 目录 |
| status | str | running/parked |

Skill 绑定：profile 创建时 Hermes 自动 sync 82 个 bundled skills；创建专家时把表单多选的 skill 复制进 `profiles/<id>/skills/`。

### 3.2 Kanban Task（看板任务）

| 字段 | 类型 | 说明 |
|---|---|---|
| id | str | kanban.db task id |
| title / body | str | 任务内容 |
| assignee | str | 专家 profile 名 |
| status | str | todo/ready/doing/done/blocked |
| parents / children | list[str] | 依赖关系 |
| summary / metadata | str/dict | 交接信息 |

## 4. 专家团编排（混合方案）

- 团长：专用 profile（如 team-lead），SOUL.md 注入拆解-派发-整合方法论
- 任务树：团长用 `hermes kanban create` 建父子任务（parent→child）
- 执行：MVP 优先手动触发模式（POST /api/tasks/{id}/run 直接调专家 chat），自动派发（dispatcher）作为可选后补
- 整合：团长收集全部子任务 summary → 最终报告

## 5. API 一览

```
GET    /api/experts              # 专家列表
POST   /api/experts              # 创建专家（form → profile + SOUL.md + skills）
DELETE /api/experts/{id}         # 删除专家
GET    /api/skills               # Hermes 可用技能列表

GET    /api/teams                # 专家团列表
POST   /api/teams/{tid}/invoke   # 发起专家团任务
GET    /api/teams/{tid}/tasks    # 任务树
GET    /api/teams/{tid}/final    # 最终报告

GET    /api/kanban/tasks         # 全量任务（列视图 + DAG）
GET    /api/kanban/tasks/{id}    # 任务详情
POST   /api/tasks/{id}/run       # 手动触发专家执行
GET    /api/kanban/events        # SSE 实时状态
```

## 6. 前端

- React + Vite + TypeScript
- zustand 状态管理
- @xyflow/react DAG 图、dnd-kit 看板列
- 原生 EventSource 订阅 SSE
- 单页 4 Tab：专家中心 / 专家团 / 看板 / 配置

## 7. 运行方式

```bash
./dev.sh   # 后端 uvicorn :8000 + 前端 vite :3000（proxy /api → 8000）
```

## 8. 风险与规避

| 风险 | 规避 |
|---|---|
| gateway dispatcher 不稳定 | MVP 手动触发执行 |
| kanban.db 并发 | 后端串行 + CLI 原子命令 |
| SSE 断线 | EventSource 自动重连 |

## 9. 目录结构

```
backend/app/
  main.py           # FastAPI 入口 + SSE
  experts.py        # 专家 CRUD
  teams.py          # 专家团编排
  kanban.py         # 看板桥接
  hermes_client.py  # Hermes CLI 封装
frontend/src/
  App.tsx           # Tab 布局
  api/client.ts     # REST + SSE
  pages/ExpertCenter.tsx
  pages/ExpertTeam.tsx
  pages/KanbanBoard.tsx
  pages/Settings.tsx
```

## 10. 后续迁移到 LakeAgent

- 将以 Hermes Profile=专家、kanban.db=任务树为接口层，抽成独立 python 包
- 复用 LakeAgent 的 runtime 目录结构与 uv 打包方式