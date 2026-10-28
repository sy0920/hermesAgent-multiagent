# WorkBuddy 式专家团中心 + 页面化重构 设计文档

创建日期：2026-10-27
项目：hermesAgent-multiagent（Hermes Agent 多 Agent 协作平台）
关联：docs/superpowers/specs/2026-10-27-multiagent-platform-design.md（前版）

## 1. 背景与目标

当前平台采用 4-Tab 平铺 + 单团写死（`_TEAM_DEFS`），无专家对话与建造团队能力。
本次按 WorkBuddy 模型重构：

- **专家团中心**：集中展示所有专家团（卡片网格），支持**创建专家团**
- **专家/专家团面板**：点击卡片进入详情，详情内有「召唤专家 / 召唤专家团」按钮
- **召唤后进入对话页**：专家 → 与专家多轮对话；专家团 → 专家团对话页（含按团过滤的看板 + DAG + 最终报告）
- **专家团组成**：多个专家 + 一个**主理人**（成员专家兼任团长，只调度不干执行活）

## 2. 关键设计决策（已与用户确认）

| # | 决策 |
|---|---|
| 1 | 主理人 = 团队内一名成员专家兼任团长，**只调度不实际执行** |
| 2 | 专家对话 = **完整多轮会话**（Hermes `--resume <session>` 保留上下文）|
| 3 | 导航 = **React Router 纯路由多页**（非 Tab 平铺）|
| 4 | 创建专家团表单：团名称/头像(自动)/能力介绍/擅长领域/主理人(单选)/团队成员(多选)|
| 5 | 团队持久化 = **`~/.hermes/teams.json`**（与 kanban.db 同目录）|
| 6 | 执行引擎复用现有 Planner/Executor：团长=该团 leader profile，assignee 白名单=该团 members |
| 7 | 看板/DAG 按团过滤：只显示 assignee ∈ 该团 members 的任务 |
| 8 | 首页 = **专家中心**（`/` 重定向 → `/experts`）|
| 9 | 旧 research 团 + team-lead **全部废弃**，无默认团，用户自行创建第一个团 |
| 10 | 团队 MVP 只做**创建 + 展示**（无编辑/删除）|
| 11 | 全局看板 `/kanban`、配置 `/settings` **保留** |

## 3. 架构

### 3.1 前端路由（React Router）

```
/                     → 重定向 /experts（首页）
/experts              专家中心：专家卡片网格 + 创建专家
/experts/:id          专家详情：人设/技能/模型/状态 + 「召唤专家」
/chat/expert/:id      专家对话页：多轮聊天（--resume 续聊）
/teams                专家团中心：团队卡片网格 + 创建专家团
/teams/:id            专家团详情：描述/主理人/成员 + 「召唤专家团」
/chat/team/:id        专家团对话页：需求输入 + 看板(按团过滤) + DAG + 最终报告
/kanban               全局看板（保留）
/settings             配置（保留）
```

Header 导航：`专家中心(/) | 专家团中心(/teams) | 看板(/kanban) | 配置(/settings)`

### 3.2 后端团队模型（teams.json）

```jsonc
{
  "teams": [
    {
      "id": "sql-team",
      "display_name": "SQL 优化团",
      "avatar": "🔧",                      // 自动生成（首个 emoji / 字符）
      "description": "擅长慢 SQL 诊断与性能优化",
      "leader": "sql",                      // 主理人（成员专家，兼任团长）
      "members": ["sql", "reviewer", "writer"],
      "created_at": "2026-10-27T..."
    }
  ]
}
```

- 存储 `~/.hermes/teams.json`；首次为空的团队列表（无默认团）
- 后端加载：读文件，不存在则返回空列表（不自动建默认团）

## 4. API 一览

### 团队（改造 + 新增）
```
GET    /api/teams            # 列表（读 teams.json）
POST   /api/teams            # 创建团（TeamCreate → JSON 落盘）
GET    /api/teams/{id}       # 团详情（含 leader/members/description）
```
（MVP 不做 PUT / DELETE）

### 专家对话（新增）
```
POST /api/experts/{id}/chat
  Body: { message: str, session_id?: str }
  → 无 session_id: hermes -p <id> chat -q "<message>"（新会话）
  → 有 session_id: hermes -p <id> chat --resume <sid> -q "<message>"（续聊）
  返回: { reply: str, session_id: str }
```

### 团队执行（改造，引擎复用）
```
POST /api/teams/{id}/invoke
  → 团长 = 该团 leader profile
  → assignee 白名单 = 该团 members
  → 复用现有 Planner/Executor + 推进循环 + 上下文移交 + 最终报告
```

## 5. 前端页面

### 5.1 /experts（专家中心，首页）
- 专家卡片网格
- 「+ 创建专家」按钮（复用现有 CreateExpertModal）
- 点卡片 → `/experts/:id`

### 5.2 /experts/:id（专家详情）
- 头像/显示名/人设/擅长领域/提示词/模型/状态
- 「召唤专家」按钮 → `/chat/expert/:id`

### 5.3 /chat/expert/:id（专家对话页）
- 聊天 UI：消息列表 + 输入框 + 发送
- 每轮调用 `POST /api/experts/{id}/chat`，维护 session_id（store/组件状态）
- 展示会话流式结果（一次性返回，不做流式）

### 5.4 /teams（专家团中心）
- 团卡片网格（团名/头像/主理人/成员 tag 缩略）
- 空态（无团）：居中提示 + 「创建第一个专家团」主按钮
- 右上角「+ 创建专家团」→ 表单弹窗：
  - 团名称（text）
  - 能力介绍（text，可选）
  - 擅长领域（text，可选）
  - 主理人（下拉，单选，从 /api/experts 选）
  - 团队成员（多选，从 /api/experts 选）
- 点卡片 → `/teams/:id`

### 5.5 /teams/:id（专家团详情）
- 描述 / 主理人 / 成员列表
- 「召唤专家团」按钮 → `/chat/team/:id`

### 5.6 /chat/team/:id（专家团对话页）
- 顶部：团名 + 主理人 + 成员 tag
- 需求输入框 + 「🚀 召唤专家团」按钮（POST invoke）
- 视图切换：看板列 | DAG
  - **仅显示 assignee ∈ 该团 members 的任务**（前端过滤）
- 全部 done 后「最终综合报告」自动出现（复用现有 report 逻辑）

### 5.7 保留
- /kanban 全局看板：4 列 + DAG，不做团过滤
- /settings 配置

## 6. 执行机制（复用，不改设计）

- 召唤团 → invoke → 团长（leader profile）输出 JSON 拆解计划
- 后端建 kanban 任务树（持久 workspace，`--workspace dir:`）
- 推进循环自动并行派发 ready 任务（assignee 白名单校验为该团 members）
- worker 用 kanban_complete 写 summary + metadata.final
- team_final 返回最终报告

## 7. 影响文件

```
后端：
  app/teams.py          团队模型 JSON 持久化 + CRUD + 移除 _TEAM_DEFS/team-lead
  app/experts.py        + POST /api/experts/{id}/chat
  app/schemas.py        + TeamCreate/TeamDetail/ChatRequest/ChatResponse
  app/hermes_client.py  + expert_chat(profile, msg, session_id=None)
  tests/                适配 + 新增 test_team_crud / test_expert_chat

前端：
  App.tsx               BrowserRouter + Routes + Header 链接
  store.ts              保持全局状态（专家/团队/任务）
  pages/ExpertCenter.tsx    首页网格（改为路由）
  pages/ExpertDetail.tsx    （新）
  pages/ExpertChat.tsx      （新）
  pages/TeamCenter.tsx      （新，原 ExpertTeam 拆出列表入口）
  pages/TeamDetail.tsx      （新）
  pages/TeamChat.tsx        （改造自 ExpertTeam，按团过滤+召唤）
  pages/KanbanBoard.tsx     （保留）
  pages/Settings.tsx        （保留）
  package.json          + react-router-dom
```

## 8. 测试策略

- 后端 pytest：
  - 团队 CRUD：POST 创建→teams.json 落盘；GET 列表/详情（mock Path.home）
  - 专家聊天：mock subprocess 验证 `--resume` 传参与 session_id 往返
  - invoke：团长=leader、白名单=members；无效成员回落模板
  - 现有推进循环/上下文移交/报告逻辑不回归
- 前端：构建 + import 完整性；路由跳转手测（Codespace）
- 端到端手测清单：创建团 → 召唤 → 输入需求 → 看板按团过滤 → 报告出现

## 9. bootstrap 调整

- `scripts/bootstrap_experts.sh` 不再创建 team-lead
- 保留 4 个默认专家（researcher-a/b/reviewer/writer），作为可用成员/主理人候选

## 10. 迁移

- 删除 `_TEAM_DEFS` 与 team-lead 相关逻辑与测试
- 前端删除 Tab 结构，路由化
- `docs/superpowers/plans/2026-10-27-multiagent-platform.md` 的旧计划不再适用（新计划另写）