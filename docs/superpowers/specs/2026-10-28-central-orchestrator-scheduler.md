# 自研中心化团长调度器（方案 A）设计文档

创建日期：2026-10-28
项目：hermesAgent-multiagent（Hermes Agent 多 Agent 协作平台）
关联：docs/superpowers/specs/2026-10-27-workbuddy-teams-redesign.md

## 1. 背景与目标

当前平台使用"Hermes Kanban 共享看板 + llm_worker 单次调用"模式。本设计将编排层重构为**方案 A 的自研中心化团长调度器**（WorkBuddy 专家团同款范式）：

- 团长（Leader）= **限预算 Hermes Agent 实例**，只产出结构化任务方案 JSON
- 调度器（Scheduler）= **纯代码驱动**：解析方案、分配任务、等待依赖、并发控制、状态流转、聚合复审
- 专家（Expert）= **限预算 Hermes Agent 实例**，只收到被分配的指令 + 裁剪上下文，不碰看板、不抢任务
- 支持 **Plan 确认（HITL）** 与 **多轮增量迭代**（用户不满意 → 团长在上一轮基础上规划新一轮）

### 与现有实现的区别

| 维度 | 当前 | 方案 A |
|---|---|---|
| 任务台账 | Hermes kanban.db（看板共享）| 独立 subtask 表（调度器独占）|
| 分配方式 | 看板 ready + advance loop 派发 | 团长出 JSON 方案 → 调度器代码解析主动分配 |
| 执行者 | llm_worker 单次调用 | 专家 Hermes Agent（--max-turns --toolsets --run-budget）|
| Plan 确认 | 无 | enable_plan_confirm → 先方案后执行 |
| 上下文 | 任务 body 透传 | 团长为每个子任务裁剪专属上下文 |
| 汇总 | team_final 读 result 文件 | 团长限轮 Agent 聚合复审 |
| 并发 | 无限制 | 专家级 + 团级并发上限 |
| 失败 | 不重派 | 标记失败不重派（防 token 循环）|
| 多轮 | 无 | resuming → 增量迭代 |

## 2. 关键设计决策（已与用户确认）

| # | 决策 |
|---|---|
| 1 | **自研中心化调度器**（WorkBuddy 专家团范式，非 delegate_task 亦非 Kanban 抢单）|
| 2 | **专家 = Hermes Profile Agent 实例**，三层防护：`--max-turns N` + `--toolsets` 白名单 + `--run-budget SECONDS`（Hermes 原生支持，已验证）|
| 3 | **保留看板做只读展示**：调度器把 subtask 状态单向回写 kanban.db，前端看板/DAG 零改动 |
| 4 | **Plan 确认 = 整方案三按钮**（确认执行 / 重新生成 / 编辑需求），MVP 不做单任务细改 |
| 5 | **聚合复审 = 团长限轮 Agent**；子任务失败 → 标记不自动重派；团长出方案失败 → 重试 1 次 |
| 6 | **团长 = 限轮方案生成器**（出 JSON 方案即止,不自主调度）；`--stream-json` 桥接事件推送 |
| 7 | **多轮增量迭代**：用户不满意 → 团长以上轮 final_report + 反馈规划新一轮，增量执行 |
| 8 | 失败策略：专家失败标记不重派；聚合失败降级返回已收集结果 |

## 3. 架构

```
┌─────────────────────────────────────────────────────────────┐
│  前端（保留现有页面，看板/DAG 只读展示）                     │
│  专家团对话页：+ 方案确认卡片（确认/重新生成/编辑需求）       │
│               + 多轮迭代（继续对话/历史轮次）                │
└──────────────────────────┬──────────────────────────────────┘
                           │ REST + SSE 事件(stream-json 桥接)
┌──────────────────────────▼──────────────────────────────────┐
│             调度器（自研：scheduler，纯代码驱动）             │
│                                                              │
│  group_session 状态机：                                      │
│   submitting → planning → waiting_confirm → running          │
│    → aggregating → finished ─→ resuming → running(下一轮)    │
│                                                              │
│  subtask 台账（scheduler.db SQLite，调度器独占）：           │
│    pending/running/success/failed · dependencies             │
│    assigned_expert · instruction · input_context · output    │
│    round_no（多轮序号）                                       │
│                                                              │
│  核心循环：                                                  │
│   ① 扫描就绪子任务（deps 满足 + 并发未超）                    │
│   ② 实例化专家 Agent（Hermes -Q --max-turns --toolsets）     │
│   ③ 收结果 → 标记 success/失败(不重派)                        │
│   ④ 全完成 → 实例化团长 Agent 聚合复审 → 最终报告             │
│   ⑤ 用户不满意 → resuming，团长带反馈规划新一轮               │
└──────────┬──────────────────────────┬────────────────────────┘
           │ Hermes CLI(限预算调用)    │ 同步回写(单向) kanban.db
           ▼                          ▼
   Hermes Profiles(专家/团长)      Kanban(仅展示，调度器写)
```

## 4. 数据模型（scheduler.db SQLite）

### 4.1 expert（复用 Profile，不建表）

| 字段 | 来源 |
|---|---|
| id | Hermes Profile 名 |
| name/description/capability_tags | 现有 Profile SOUL 解析 |
| concurrency_limit | 默认 1（调度器配置）|
| timeout | 默认 180s |

### 4.2 expert_group（扩展 teams.json 或移入调度库）

| 字段 | 说明 |
|---|---|
| id / name / description | 现有 |
| member_expert_ids | 固定团员（团长只能从此选人）|
| leader_expert_id | 团长 Profile（主理人）|
| enable_plan_confirm | 是否开启方案确认 |
| max_parallel_tasks | 全局最大并行子任务数 |

### 4.3 group_session

| 字段 | 说明 |
|---|---|
| session_id | 主键 |
| group_id | 所属团 |
| status | submitting/planning/waiting_confirm/running/aggregating/finished/resuming/error |
| user_query | 用户原始需求 + 各轮反馈 |
| round_no | 当前轮次（从 1）|
| plan_json | 当前轮方案（子任务数组）|
| final_report | 最近一轮最终交付物 |
| created_at / updated_at | 时间戳 |

### 4.4 subtask

| 字段 | 说明 |
|---|---|
| subtask_id | 主键 |
| session_id / round_no | 归属会话与轮次 |
| expert_id | 执行人 |
| title / instruction | 指令 |
| input_context | 团长裁剪的专属上下文（非全量）|
| deps | 依赖的 subtask_id 数组 |
| status | pending/running/success/failed |
| output | 专家返回结果 |
| meta | 预留（retry_count 等）|

## 5. 调度器模块

```
scheduler/
  db.py            # SQLite 存取（subtask/session/expert_group）
  leader.py        # 团长：出方案 JSON / 聚合复审（Hermes -Q 限预算）
  executor.py      # 专家执行：Hermes -Q --max-turns N --toolsets 白名单
  engine.py        # 调度主循环（含多轮 resume）+ 看板单向回写
  events.py        # 事件总线：状态 → SSE 推前端；同步回写 kanban.db
```

### 5.1 leader.py（团长）

- **出方案**：输入 = 用户需求 + 花名册 + (多轮时: 上轮 final_report + 反馈)；`hermes -p <leader> chat -Q --max-turns 5 --run-budget 60 --stream-json -q "<prompt>"`；解析 JSON
- **聚合复审**：输入 = 全部子任务结果（裁剪合并）；`--max-turns 8 --run-budget 120`；输出 final_report
- **预算**：`--max-turns` 5（方案）/8（聚合）、`--run-budget` 60/120、toolsets 白名单 `["file", "skills"]`

### 5.2 executor.py（专家）

- 输入 = `instruction + input_context`（每任务裁剪）
- `hermes -p <expert> chat -Q --max-turns {MAX_TURNS} --run-budget {RUN_SECONDS} -t {白名单} -q "<prompt>"`
- 常量：`MAX_TURNS=10`、`RUN_SECONDS=180`、`TOOLSET_WHITELIST=["file", "skills", "terminal"]`（禁 delegate/kanban/send_message）
- **不自动重派**，失败即标记

### 5.3 engine.py（调度主循环）

```
每 3s 轮询：
  1. 找 waiting_confirm → plan_ready 事件（等用户）
  2. 找 running 会话 → 扫描就绪 subtask：
       status=pending & 所有 deps=success
       & 专家并发 < concurrency_limit
       & 全局并行 < max_parallel_tasks
     → 实例化专家 → subtask=running → expert_start 事件
  3. 找 finished 会话 → 若聚合完成 → 保持，等用户继续
  4. 找 resuming 会话 → 团长带反馈再出方案
  5. 所有 subtask 终态 → aggregating → 团长聚合 → finished
看板回写：subtask 状态 → kanban 任务（单向，仅 engine 写）
```

### 5.4 events.py（事件总线）

```
{type:"planning",   msg:"团长正在制定方案"}
{type:"plan_ready", plan:{...}}           ← 前端展示方案卡片
{type:"expert_start", expert_id, subtask_id}
{type:"expert_done",  expert_id, subtask_id, status}
{type:"aggregating",  msg:"团长正在聚合复审"}
{type:"finished",     final_report:"..."}
{type:"resuming",     round_no, msg:"基于上一轮结果继续规划"}
```

## 6. 状态机

```
submitting → planning → waiting_confirm ⇄ (重新生成 / 编辑需求)
          ↘ running → aggregating → finished
                                     ↘ resuming → running(下一轮) → aggregating → finished
                                     ↘ 用户满意 → 结束
可转 error：团长方案重试 1 次仍失败 / 调度异常
```

## 7. 多轮迭代规则（方案 A 增强）

- 每轮独立 subtask 集，挂同一 session 的 `round_no`
- 团长每轮规划输入 = `上轮 final_report + 用户反馈 + 花名册`（不含全量历史，防 token 膨胀）
- 增量执行：新方案只含要改/补的子任务；已完成的旧子任务不重复执行（结果保留在上轮报告）
- 每轮预算独立：完整"方案确认→执行→聚合"，token 按轮可控

## 8. Hermes 调用封装（hermes_client.chat_budgeted）

```python
def chat_budgeted(
    profile: str,
    message: str,
    *,
    max_turns: int = 10,
    run_budget: int = 180,
    toolsets: list[str] | None = None,
) -> str:
    args = ["-p", profile, "chat", "-Q", "--max-turns", str(max_turns),
            "--run-budget", str(run_budget)]
    if toolsets:
        args += ["-t", ",".join(toolsets)]
    args += ["-q", message]
    return run_hermes(args, timeout=run_budget + 30)
```

- **不回退到"非预算"通道**：所有团长/专家调用必须走 chat_budgeted
- `--stream-json` 用于事件桥接（可选，MVP 先用 -Q 一次性拿结果）

## 9. 前端变化

| 页面 | 变化 |
|---|---|
| TeamChat（团对话页）| + 方案确认卡片（确认/重新生成/编辑需求）|
|  | + 多轮迭代控件（"对这个结果不满意，继续对话"）|
|  | + 轮次历史（round 1/2/3 的结果可切换查看）|
| KanbanBoard / DAG | 数据源改为调度器回写（视觉不变）|
| client.ts | + session/subtask API 类型与函数 |

## 10. 影响文件

```
后端（新增）：scheduler/{db,leader,executor,engine,events}.py
后端（改造）：app/teams.py、app/kanban.py、app/hermes_client.py、app/main.py
后端（删除）：app/llm_worker.py（被 executor.py 取代）
前端：pages/TeamChat.tsx、components/SessionRunner.tsx（新）、api/client.ts
测试：新增 scheduler 各模块、改造 teams/kanban 关联测试
```

## 11. 测试策略

- pytest（mock Hermes）：状态机迁移全路径、依赖解析、并发上限、多轮 resume 上下文拼接、失败不重派、kanban 单向回写、预算参数组装
- 端到端（Codespace）：创建团 → 召唤 → 方案确认 → 执行 → 报告 → "不满意" → 第二轮增量 → 满意

## 12. 迁移与取舍

- 现有 `llm_worker.py` 退休，由 scheduler/executor.py 承担
- `invoke`/`advance_once`/`_invoke_windows` 逻辑并入调度引擎
- 看板/DAG 前端继续用（数据源换为调度器回写）
- 已知取舍：调度器无原生调试可视化/LangGraph 时间旅行（方案 A 固有）；状态枚举若随复杂分支增长需注意（MVP 约束在 8 态内）