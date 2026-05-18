# Research: Current vs Target Parallel Registration

Date: 2026-05-18

## Local Baseline

- Current repo: `D:\Desktop\AutoTeam`
- Current branch after push: `main`
- Pushed commit: `5aff1af fix: 对齐注册轮转链路和 CloudMail 配置提示`
- Remote integrated first: `1060eb4 求赞QAQ`

## Current Repo Findings

- `src/autoteam/workspace_pool.py` implements Round 12 S7 workspace pool with `active`, `warm`, and `cold` tiers.
- The S7 invariant is failover-oriented: at most one workspace is active at a time. This is useful for high availability but does not satisfy multiple mother accounts running concurrently.
- `src/autoteam/admin_state.py` routes `get_admin_email()` and `get_chatgpt_account_id()` through `WorkspacePool.get_active()`.
- `src/autoteam/master_health.py` feeds health signals into `WorkspacePool` to mark the active workspace unhealthy and promote a candidate.
- `src/autoteam/manager.py` keeps the single-Team cap:
  - `TEAM_SEATS_MAX = 3`
  - `TEAM_SUB_ACCOUNT_HARD_CAP = 2`
  - `_clamp_team_target_seats(...)` clamps targets to the single Team cap.
- `src/autoteam/api.py` uses one global Playwright task lock:
  - `_playwright_lock`
  - `_current_task_id`
  - `_start_task(...)`
  - `_run_task(...)`
  This prevents two independent API mutation tasks from running concurrently, so multi-master parallelism should happen inside one orchestrated parent task with per-owner workers.
- `src/autoteam/accounts.py` already stores `workspace_account_id`, which can become the grouping key for per-owner account isolation.
- Current repo search did not find `DIRECT_REGISTER_PARALLEL`, `_direct_register_parallel_size`, or `_race_chatgpt_signup`.

## Target Repo Findings

- Target repo: `D:\Desktop\autoteam-1\AutoTeam`
- Target branch: `dev`, ahead of `origin/dev` by 6 at inspection time.
- Recent target commits:
  - `f120570 fix rotate post sync and cliproxy health`
  - `6f4d106 fix invite blank page recovery`
  - `15e50d6 Improve registration credential sync and diagnostics`
- Target repo includes direct signup parallel race:
  - `.env.example:78` `DIRECT_REGISTER_PARALLEL=1`
  - `src/autoteam/manager.py` `_direct_register_parallel_size()`
  - `src/autoteam/manager.py` `_cap_direct_register_parallel(...)`
  - `src/autoteam/manager.py` `_race_chatgpt_signup(...)`
  - `tests/unit/test_manager_auth_repair.py` memory downgrade test for `DIRECT_REGISTER_PARALLEL`.

## Design Implication

There are two separate forms of parallelism:

- Per-owner horizontal parallelism: several Team owners run independent fill / rotate workers at the same time.
- Per-registration race parallelism: a single owner worker can race several direct signup attempts for one account creation.

The MVP should combine them through one global budget. Without a global browser / worker budget, `owner_workers * direct_register_parallel` can multiply Playwright sessions and recreate the runtime-stall class of bugs this project just hardened.

## Recommendation

Start with imported existing Team owners. Do not include automatic mother-account creation in the first MVP unless the user explicitly accepts the larger scope. This keeps the first implementation focused on scheduler, isolation, status, and safe parallel registration rather than expanding the already fragile registration chain into owner creation.
