---
phase: brainstorm
status: open
created: 2026-05-18
owner: codex
parent_task: null
linked_issue: null
---

# Task PRD: Multi-Master Team Parallel Registration

## Goal

把现有单 Team 自动注册 / 轮转链条扩展为多个 Team 母号并行工作。每个 Team 仍保持 `1 owner + 2 managed children = 3 seats` 的硬约束，通过多个独立母号水平扩展总吞吐，并把目标仓 `D:\Desktop\autoteam-1\AutoTeam` 中的 direct signup 并行尝试能力纳入可控调度。

## What I Already Know

- 当前已推送基线是 `5aff1af fix: 对齐注册轮转链路和 CloudMail 配置提示`，它是在远端 `1060eb4` 后 rebase 得到的新 hash。
- 当前版本已把 CloudMail / cf_temp_email 的 `CLOUDMAIL_BASE_URL` 指引改为必须包含 `/api`，这条配置提示需要在多母号场景继续保留。
- 当前 Team 运行契约仍是单 Team 最多 3 seats：`src/autoteam/manager.py` 中 `TEAM_SEATS_MAX = 3`，`TEAM_SUB_ACCOUNT_HARD_CAP = 2`，`AUTO_CHECK_TARGET_SEATS` 也被 clamp 到 `1..3`。
- 已有 `05-11-s7-multi-workspace-pool` 和 `src/autoteam/workspace_pool.py`，但它是冷备 / failover 模型：`workspaces[*].tier == "active"` 任意时刻至多 1 个；这不能满足多个母号同时并行工作。
- 当前 API 后台任务入口使用全局 `_playwright_lock` 和 `_current_task_id`，`/api/tasks/*` 在任一任务运行时会返回 409。这保证单任务安全，但会阻止多个 Team owner worker 以现有任务模型并行执行。
- 当前账号记录已经有 `workspace_account_id` 字段，用于识别账号属于哪个母号 workspace；这是多母号隔离和分组状态的基础。
- 当前仓尚未接入目标仓 direct signup race：本仓没有 `DIRECT_REGISTER_PARALLEL` / `_race_chatgpt_signup` / `_direct_register_parallel_size`；目标仓 `D:\Desktop\autoteam-1\AutoTeam` 的 `dev` 分支有这些配置和单测。
- 目标仓 direct signup 并行是同一注册目标的多个候选尝试 race；多母号并行是多个 owner / Team 维度的 worker 调度。两者需要组合，但不能简单把浏览器上下文跨线程共享。

## Problem

现在的吞吐瓶颈不只是注册步骤是否并发，而是整个系统仍围绕“一个当前 active 母号”设计：

- `WorkspacePool` 只能 active 一个 workspace，适合故障切换，不适合同时运行多个 Team。
- `cmd_rotate(target_seats=3)`、`cmd_fill(...)` 和自动巡检都默认操作当前母号，不能表达 `N 个 Team * 每 Team 2 个子号`。
- API 的全局任务锁把所有 Playwright 任务串行化，不能在多个母号之间做隔离并发。
- `/api/status`、Team 成员页、Pool 页和运行时 validation 都按单 Team 汇总，无法回答“哪个母号卡住、哪个母号可用、总共多少可用子号”。
- 如果直接把单 Team target_seats 提高到大于 3，会违反当前 license / seat contract，也会破坏已经修复的轮转准确性。

## Assumptions

- Decision from 2026-05-18 continuation: MVP uses imported existing Team owners first. Automatic Team mother-account creation stays out of scope for this first implementation slice.
- 推荐 MVP 先支持“导入多个现成 Team 母号并并行补齐子号”，不在第一版自动创建新的母号 Team。
- 每个母号独立持有 owner auth / workspace account id / Team 成员事实 / health state。
- 多母号并行调度必须有全局并发预算和 per-owner 并发预算，避免 `owner_count * direct_signup_parallel` 直接放大到失控的浏览器数量。
- 现有单母号模式必须零配置兼容：没有多母号配置时，行为等价于当前 `active` workspace。

## Requirements

- 保持单 Team seat cap：每个 Team 的 `target_seats` 最大仍为 3，子号 hard cap 仍为 2。
- 新增并行 Team owner 调度层，能对多个 owner 执行独立的 reconcile / fill / rotate 子任务。
- 每个 owner worker 必须使用自己的 ChatGPTTeamAPI session、Playwright context、owner auth 和 workspace id；不得共享非线程安全浏览器上下文。
- 全局任务模型需要支持一个“multi-master repair”任务内部启动多个 owner worker，而不是开放多个互相不可见的 API mutation task。
- 失败隔离：一个 owner 卡在 API / 注册 / OAuth / health degraded 时，不能阻塞其他 owner worker 完成。
- 调度必须组合 direct signup race：每个 owner worker 可使用 direct signup 并行尝试，但受全局浏览器预算限制。
- 状态必须按 owner 分组：`/api/status`、任务结果、validation、Team 成员视图至少能展示每个 Team 的 owner、children、invites、health、last_error 和 validation。
- 账号池必须按 `workspace_account_id` 聚合，避免 A Team 的子号被 B Team 的轮转 / cleanup / sync 误处理。
- CLIProxyAPI / CPA sync 只能同步已验证可用的本地 auth；任何多 owner sync 都必须保留现有 delete guard 和 read-only health 约束。
- CloudMail / mail provider 配置仍是共享资源；并行 worker 需要处理邮箱创建、验证码轮询和删除的 provider 限速 / 失败分类。

## Proposed MVP

- 后端引入 `MultiMasterTeamScheduler` 或等价服务，读取 `WorkspacePool.list_all()` 中标记为 `enabled` / `parallel` 的母号。
- 第一版只导入已有母号：支持从现有 admin login / session_token 导入多个 owner，并注册到 workspace pool；不自动创建新的 Team owner。
- 为每个 owner 计算局部目标：`owner_target_seats = 3`，`owner_child_target = 2`。
- 新增一个 API mutation：例如 `POST /api/tasks/multi-master/fill`，在单个全局任务里调度多个 owner worker，并返回 per-owner result。
- 多 owner worker 使用受控并发：`MULTI_MASTER_MAX_OWNER_WORKERS` 控制同时处理几个母号，`DIRECT_REGISTER_PARALLEL` 控制单个 direct signup race，最终用一个统一 browser budget 裁剪。
- `/api/status` 增加 additive 字段 `multi_master`，不删除现有字段；前端 Pool / Team 页再按 owner 分组展示。
- 老的单 active workspace 路径继续可用，默认不开启 multi-master。

## Acceptance Criteria

- 给定 2 个已导入 owner workspace，运行 multi-master fill 后，两个 owner 可以在同一个 API task 下并行补齐各自最多 2 个 managed children。
- 任意单 Team 的远端成员数不会超过 `1 owner + 2 managed children`，也不会用 create-before-remove 绕过 cap。
- owner A 卡住或 validation failed 时，owner B 的 worker 仍能完成，并在 task result 中标出 A failed / B completed。
- `/api/status` 同时展示 aggregate summary 和 per-owner diagnostics；单 owner 的旧字段保持兼容。
- `accounts.json` 中 active / standby / auth_invalid / personal 账号能按 `workspace_account_id` 正确分组，跨 owner 不互相 cleanup。
- direct signup parallel race 在高内存或浏览器预算不足时自动降级，不导致浏览器进程失控。
- 现有单母号测试继续通过；新增多母号 scheduler、per-owner lock、status aggregation、failure isolation、direct parallel budget 单测。

## Out Of Scope

- 第一版不自动创建新的 Team 母号，除非用户明确选择把“母号创建”纳入 MVP。
- 第一版不把单 Team seat cap 提高到 3 以上。
- 第一版不重写 mail provider 架构，只在现有 provider 上增加并发预算和错误归因。
- 第一版不做跨机器分布式调度；只处理本机多个 owner 并行。

## Open Questions

### Blocking Preference

第一版多母号来源怎么定：

- 推荐：先支持导入多个现成 Team 母号，然后并行补齐每个 Team 的 2 个子号。
- 扩大范围：同时自动注册 / 创建新的 Team 母号，再并行补齐子号。

### Deferred

- 前端第一版是否需要完整多 Team 管理界面，还是先做后端 API + 状态页最小展示。
- 多 owner 默认并发预算取值，例如 `max_owner_workers=2`、`direct_register_parallel=2` 是否足够保守。
- workspace pool 的 `active/warm/cold` 是否扩展为 `mode=primary|parallel|standby`，还是另建 parallel owner registry。

## Technical Notes

- Existing done task: `.trellis/tasks/05-11-s7-multi-workspace-pool/prd.md`
- Current owner pool implementation: `src/autoteam/workspace_pool.py`
- Current single-task lock: `src/autoteam/api.py` `_playwright_lock`, `_current_task_id`, `_start_task`, `_run_task`
- Current Team cap: `src/autoteam/manager.py` `TEAM_SEATS_MAX`, `TEAM_SUB_ACCOUNT_HARD_CAP`, `_clamp_team_target_seats`, `cmd_rotate`
- Current grouping hint: `src/autoteam/accounts.py` `workspace_account_id`
- Target repo verification: `D:\Desktop\autoteam-1\AutoTeam` `dev` branch has `DIRECT_REGISTER_PARALLEL`, `_direct_register_parallel_size`, `_race_chatgpt_signup`, and memory downgrade test.
- Research note: `.trellis/tasks/05-18-multi-master-parallel-registration/research/current-vs-target-parallel-registration.md`
