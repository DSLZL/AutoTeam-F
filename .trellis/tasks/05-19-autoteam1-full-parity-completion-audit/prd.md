# autoteam-1 full parity completion audit

## Goal

Continue the long-running objective: absorb the good, proven ideas from
`D:\Desktop\autoteam-1\AutoTeam` into the current project at `D:\Desktop\AutoTeam`.

This task is not a blanket copy. The two repositories have diverged and the current
project already contains stronger local work in several areas. The work here is to
turn "all good points" into a concrete, evidence-backed checklist, identify the
remaining gaps, and then implement the next safe migration slice without disturbing
unrelated active work.

## Current Baseline

Recent current-repo commits already landed the largest seat-rotation slice:

* `05bf6da fix: harden seat rotation and direct signup race`
* `d8f55d5 chore(task): archive 05-19-autoteam1-seat-rotation-hardening-migration`
* `efad4b5 chore: record journal`

That prior slice covered `ROTATE_SKIP_REUSE`, remove-before-create replacement,
managed child validation, direct signup race wiring, multi-master direct parallel
propagation, auto-check cooldown/blocker handling, backend specs, and unit tests.

## Requirements

* Build a prompt-to-artifact checklist for the global objective, not just the last
  rotation task.
* Compare target-repo recent commits and target-only files against current code,
  tests, specs, and UI artifacts.
* Classify each target capability as:
  * absorbed with evidence,
  * partially absorbed and needing deeper audit,
  * not absorbed and worth migrating,
  * not worth migrating because current repo has a better/incompatible pattern.
* Preserve current repo advantages: multi-provider mail fallback, account-state
  machine, multi-master workspace pool, cleaner frontend design direction, CPA
  delete guard, and the 3-seat Team cap.
* Do not copy target files wholesale. Migrations must be adapted to current module
  boundaries and tested with current tests.
* Do not use `/api/sync` as a smoke test and do not restart live Docker during
  audit-only work.
* Do not include unrelated existing dirty files in commits.

## Acceptance Criteria

* [x] Research file contains a target-commit-to-current-evidence matrix for recent
  target commits.
* [x] Research file lists target-only source/UI/test files and states whether they
  are equivalent, superseded, or candidates for migration.
* [x] At least one concrete next implementation slice is selected, with explicit
  in-scope and out-of-scope boundaries.
* [x] If implementation is started, related tests are added or updated and `ruff`
  plus relevant `pytest` are run.
* [x] If no implementation is appropriate after audit, the audit explains why the
  global objective is still not complete or what evidence is needed before marking
  it complete.

## Initial Findings

See `research/autoteam1-full-parity-matrix.md`.

## Implemented Slices

* P1: Added a current-repo regression test for target-2 exhausted blocker removal
  with a stale remote overcount. The adapted current behavior remains
  remove-before-create rather than target-style preswitch.
* P2: Added read-only DNS diagnostics via `src/autoteam/dns_diagnostics.py` and
  `POST /api/setup/dns/check`. Mutating Cloudflare DNS upsert remains out of scope.
* P3: Migrated target `account_ops` Team-state parsing and deletion safeguards into
  current repo boundaries: nested Team member/invite helpers, readable auth/HTML
  failures, invite-delete fallback, configured CPA/Sub2API target cleanup, generic
  mail account deletion, local credential seat protection, and `/api/team/members`
  normalized rendering.
* P4: Migrated target `8f17448` CPA credential gate into current auto-check shape:
  read-only CLIProxyAPI provider-auth metadata can trigger the existing `auto-fill`
  path when Team is full, local active children are below target, and CPA has zero
  usable provider credentials. Management failure is not treated as zero.
* P5: Migrated reset-quota local recovery: `cmd_reset_quota_recovery`, CLI
  `reset-quota`, `POST /api/tasks/reset-quota`, and tests recover stale exhausted
  rows without touching Team, CPA, or Sub2API.
* P6: Migrated main-Codex after-admin improvements in current repo shape:
  local-only `MainCodexLoginFlow`, action-aware main-Codex status,
  `POST /api/main-codex/login`, sync-target preflight for
  `POST /api/main-codex/start`, and explicit remote deletion routes through
  `sync_targets.py`.
* P7: Migrated the safe auth-path subset from target auth-repair work:
  manager-level auth file resolution now handles host-absolute, `/app/...`
  container paths, project-relative `data/auths/...` / `auths/...`, and bare
  filenames across the current repo's auth search dirs. Team reconciliation now
  protects standby/auth-pending rows when a real local auth file exists and
  restores recovered Team auth rows with `protect_team_seat=True`.
* P8: Migrated target OAuth/auth-repair diagnostic labels and same-round delay
  helper for transient organization/region pages such as `oauth_timeout`,
  `unsupported_region`, `account_selection`, and `no_valid_organizations`.
* P9: Migrated target workspace-selection hardening in current repo shape:
  `chatgpt_api` now filters workspace candidate noise, waits for post-selection
  ChatGPT readiness, and shortcuts completed ChatGPT home states; `codex_auth`
  exposes compatibility wrappers to the existing shared `oauth_workspace.py`
  detectors/selectors.
* P11: Migrated the safe lightweight Codex OAuth helper subset from target
  `test_signup_flow_profiles.py`: API organization dropdown selection, account
  chooser selection, OAuth trace filtering/classification, timeout and
  `no_valid_organizations` retry-page recovery, login-challenge completion,
  OTP rejection cache hashing, and OTP submit acceptance of OAuth progress URLs.
* P12: Migrated split verification-code handling for direct and invite
  registration: delayed single-character input detection, single-input fallback,
  structured invite diagnostics, and shared submit helpers that wait for the
  registration step to advance.
* P13: Migrated the safe session fallback subset for Codex auth:
  `_fetch_team_session_bundle_from_context`, explicit
  `pre_signed_in_cookies`, and opt-in `return_result=True` wrapping. The default
  `login_codex_via_browser()` contract still returns the existing bundle/`None`
  shape.
* P14: Migrated the safe `_login_codex_with_result` subset from target
  auth-repair work. The helper normalizes explicit `return_result=True`, legacy
  bundle/`None`, retryable failures, and non-Team bundles into one result shape,
  while keeping it isolated from `cmd_check` and Team-seat release policy.
* P15: Migrated the safe `cmd_check` auth-repair entry subset from target:
  `force_auth_repair`, `preserve_low_active`, historical-low-quota handling when
  live quota returns `network_error`, auth-pending scanning, and per-account mail
  provider routing. This keeps the current persisted `auth_invalid` alias and
  does not change `_record_auth_repair_failure` release policy.
* P16: Migrated the low-risk `_record_auth_repair_failure` policy subset:
  repeated `email_verification` can release a Team blocker after retry budget is
  exhausted, missing-auth `login_state_lost` releases and retires the unusable
  row, released repair failures are marked disabled/reuse-disabled to avoid
  accidental standby reuse, and protected local credential seats are paused
  without release.
* P17: Migrated the Cloudflare temp-email compatibility facade and metadata
  extraction improvement: `autoteam.cloudflare_temp_email` remains a legacy
  import path, `normalize_cloudflare_temp_email_base_url()` strips `/admin`,
  `MailProvider` extract helpers prefer `metadata.ai_extract` before subject/body
  parsing, and target-style `test_cloudflare_temp_email.py` now passes against
  current repo.
* P18: Migrated the same real-time quota principle into CPA publish routing:
  `sync_to_cpa()` now re-checks active auths immediately before upload, keeps the
  remote copy on `network_error`, publishes only when `check_codex_quota()`
  returns `ok`, and deletes remote active files on exhausted/terminal failures.
  Tests cover the live keep-remote and delete-remote branches plus proxy refresh
  before upload.

## Open Decisions

* Target `ConfigPage.vue` exact migration is rejected for this task. Its grouping
  idea is useful, but the component depends on target-only `/api/config/runtime`
  and `/api/config/source` endpoints, keeps a raw `.env` editor, and reintroduces
  dark glass / emoji styling. A current-style runtime configuration page can be a
  separate frontend/API safety task, not a direct parity copy.
* Target `ThemeToggle.vue` remains rejected for this project because it reintroduces
  dark gradient / emoji styling that the current project intentionally moved away
  from.
* Target's old positional `SignupProfile("Name", year, month, day, age)` public
  constructor remains rejected. Current repo keeps the stronger immutable
  `SignupProfile(full_name, birthday, age=...)` snapshot contract; the underlying
  birthday/age/profile propagation behavior is covered by current tests.
* Remaining target auth-repair assertions after the migrated safe helper subsets
  are not a blanket migration target:
  * target's persisted `"auth_pending"` literal is intentionally rejected because
    current repo maps that lifecycle state to persisted `STATUS_AUTH_INVALID`
    (`"auth_invalid"`) and lets the account-state machine treat it as auth
    pending;
  * target's exact `update_account(email, {"status": ...})` call-shape assertions
    conflict with current `_reason`-carrying state-machine transition logging;
  * target's add-phone retry-disabled "pause without release" behavior is
    rejected for current automated provider children because it can leave an
    unrepairable child occupying one of the two managed seats under the hard
    Team cap. Current capacity-first release behavior is retained.

## Out of Scope For This Audit Pass

* Raising the Team seat cap above `1 owner + 2 managed children`.
* Resetting or cleaning the dirty worktree.
* Git commit and push are now in scope for the final repository handoff because
  the user explicitly requested them on 2026-05-20.
* Mutating live remote services such as CPA, Sub2API, Cloudflare DNS, or OpenAI
  Team.
