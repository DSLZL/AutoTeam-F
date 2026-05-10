# S4: 注册收尾双路径修复（round-11 痛点）

> 父任务: `05-11-upstream-align-register-multimail-frontend-refresh`
> 依赖: S2 (`fallback.py` + `addy_io.py` + `simplelogin.py`) + S3 (`ensure_account_mail`)
> 子任务 slug: `05-11-s4-register-dual-path-fix`

## Goal

围绕"子号注册新双路径"以及"免费号注册路径被 OpenAI 阻断"两个 round-11 痛点，
为 `manager.py` 注册链路接入：

1. **register-time provider rotation** — 当 OTP 超时 / 邀请链接抓不到 / 域名被 OpenAI 拒
   时，自动切到下一个 mail provider 重试，复用 S2 的 `_FailureTracker` 状态文件。
2. **alias + reader 配对**（`AliasWithReaderProvider`）— Addy.io / SimpleLogin 仅做
   alias 创建（拿到不在黑名单的邮箱），底层 reader provider（maillab / cf）查收
   转发邮件，覆盖 alias forwarding 服务无 inbox 的留白。
3. **入口适配** — `create_account_direct` / `create_new_account` / `_complete_registration`
   的 `mail_client` 入参改为可选，未提供时按 `MAIL_PROVIDER_CHAIN` 自动构造 fallback 链；
   同时支持 `acc` 路由（绑定了 `mail_provider` 字段的旧账号走对应 provider）。
4. **register_failures.json schema 兼容** — 不破坏现有 list-of-records，仅在 `**extra`
   中新增 `provider_chain_history` 字段（旧记录无该字段照样能读）。

## Decision (ADR-lite)

### Q1 ✓ 不复用 S2 FallbackMailProvider 做 register-level rotation

S2 的 `FallbackMailProvider` 是 **mail-API 级别**的 dispatch（每次方法调用都按链尝试）。
register-level rotation 是 **邮箱-粒度**的（一个邮箱注册 OTP 超时 / 域名被拒后，要换
到下一个 provider 创建新邮箱再重试整个流程）。两层语义不同，不应混用。

**决策**: 新建 `RegisterPathRotator`（`mail/register_dual_path.py`），编排"创建邮箱 →
执行注册动作 → 失败时切 provider"循环。复用 S2 `_FailureTracker` 的状态文件，避免再
开一个失败计数文件。

### Q2 ✓ 三类失败的分类器

`classify_register_failure(exc_or_msg) -> RegisterFailureType` 把异常/字符串映射到：

- `OTP_TIMEOUT` — `TimeoutError` 且消息含 `等待邮件超时` / `wait_for_email` 上下文
- `INVITE_LINK_MISSING` — `extract_invite_link` 返回 `None` 包装的逻辑失败
- `DOMAIN_REJECTED` — `RegisterBlocked` 且 reason 含 disposable / domain / not allowed 关键词
- `OTHER` — 其他异常归类，**不**触发 fallback（避免对偶发 Playwright 崩溃误判降级）

只有前三类触发 provider 切换；`OTHER` 由调用方按现有逻辑处理（重试 / 放弃）。

### Q3 ✓ AliasWithReaderProvider — 组合而非继承

```python
AliasWithReaderProvider(alias=AddyIoClient(), reader=MaillabClient())
```

实现 `MailProvider` ABC 的全部方法：
- 写入路径（`create_temp_email` / `delete_account` / `list_accounts`）→ `alias`
- 读取路径（`search_emails_by_recipient` / `list_emails` / `delete_emails_for` /
  `wait_for_email` / `get_latest_emails`）→ `reader`
- `login` 同时调用两者

**关键假设**: 用户已在 Addy.io 端配置 alias 转发到 reader 的真实邮箱（运维侧配置，
不在代码范围）。`provider_name = "alias_with_reader"`，cache_key 用 `alias.provider_name +
reader.provider_name`。

### Q4 ✓ register_failures.json schema 兼容

S2 PRD §Q3 已经把"失败计数"独立到 `mail_provider_state.json`，所以本任务**不动**
`register_failures.json` 的 list-of-records 主结构。

仅在 `record_failure(...)` 调用点的 `**extra` 中追加 `provider_chain_history`：

```python
record_failure(
    email,
    "mail_otp_timeout",
    "OTP 等待超时,自动切到下一 provider",
    provider_chain_history=[
        {"provider": "addy_io", "error_type": "OTP_TIMEOUT", "ts": 1715472000.0},
        {"provider": "maillab", "error_type": "OK", "ts": 1715472180.0},
    ],
)
```

旧记录无该字段，读路径不抛错（`r.get("provider_chain_history", [])` 即可）。

新增 categories（写入 `register_failures.py` 的 module 级常量供 grep）：
- `MAIL_OTP_TIMEOUT = "mail_otp_timeout"`
- `MAIL_INVITE_LINK_MISSING = "mail_invite_link_missing"`
- `MAIL_DOMAIN_REJECTED = "mail_domain_rejected"`

### Q5 ✓ create_account_direct 入参改造（向后兼容）

旧签名: `create_account_direct(mail_client, *, leave_workspace, out_outcome)`
新签名: `create_account_direct(mail_client=None, *, leave_workspace, out_outcome, acc=None)`

- `mail_client` is None 且 `acc` is None → 调用 `get_mail_client()`（按 env 决定单 / 多 provider）
- `mail_client` is None 且 `acc` 提供 → 调用模块级 helper `_get_mail_client_for_account(acc)`
  （从 `cmd_rotate.ensure_account_mail` 的逻辑提取出来）
- `mail_client` 显式传 → 完全保留旧行为

`create_new_account` / `_complete_registration` 同样处理。

### Q6 ✓ Rotator 落地到哪里

在 `create_account_direct` 入口增加一个 thin wrapper:

```python
def _try_register_with_rotation(mail_client, ...) -> tuple[bool, ...]:
    # 1. 如果 mail_client 是 FallbackMailProvider 且 chain 长度 > 1
    #    → 用 RegisterPathRotator(chain) 编排
    # 2. 否则单 provider → 直接调用（现有逻辑不变）
```

只在 chain 模式启用，单 provider 完全保留现有行为，零回归。

## Scope

### 必做

1. **新建** `src/autoteam/mail/alias_reader_pair.py`:
   - `AliasWithReaderProvider(MailProvider)` 完整 ABC 实现
   - 构造接收 `alias: MailProvider`, `reader: MailProvider` 两实例
   - 写方法 → alias / 读方法 → reader / `login` → 两者
   - `provider_name` 复合："alias_with_reader[<alias>+<reader>]"

2. **新建** `src/autoteam/mail/register_dual_path.py`:
   - `RegisterFailureType` 枚举（`OTP_TIMEOUT`, `INVITE_LINK_MISSING`, `DOMAIN_REJECTED`, `OTHER`）
   - `classify_register_failure(exc_or_text) -> RegisterFailureType`
   - `RegisterPathExhausted(Exception)` — 所有 path 都失败的聚合异常
   - `RegisterPathRotator(strategies: list[tuple[str, Callable[[], MailProvider]]], tracker=None)`:
     - `try_each(action: Callable[[MailProvider, str, dict], T]) -> T` — 编排循环；
       每次成功返回 T;失败按分类器决定是否切下一个 strategy
     - `provider_chain_history` 实例属性记录每次尝试的 (provider, error_type, ts)
     - 复用 S2 `_FailureTracker`,统一计数

3. **改** `src/autoteam/register_failures.py`:
   - 新增 module 级常量 `MAIL_OTP_TIMEOUT`, `MAIL_INVITE_LINK_MISSING`, `MAIL_DOMAIN_REJECTED`
   - 文档字符串中追加新 category 说明
   - 不动 schema / load / save 函数

4. **改** `src/autoteam/manager.py`:
   - 模块级 `_get_mail_client_for_account(acc) -> MailProvider`(从 cmd_rotate 闭包提取)
   - `_complete_registration` / `create_account_direct` / `create_new_account`:
     - `mail_client` 改为 `mail_client=None`,默认通过 `get_mail_client()` 构造
     - 新增可选 `acc=None` 参数,有 acc 时走 `_get_mail_client_for_account`
     - 向后兼容(显式传 mail_client 完全不影响旧行为)
   - 在 `create_account_direct` 中,如果 `mail_client` 是 `FallbackMailProvider` 且
     chain 长度 > 1 → 启用 `RegisterPathRotator` 路径切换

5. **测试** `tests/unit/test_round12_s4_register_dual_path.py`(>=15 case,全 mock):
   - `classify_register_failure`: 4 类映射(各 2-3 case)
   - `RegisterPathRotator`:
     - 单 provider 单次成功
     - 第一个 OTP_TIMEOUT → 切第二个成功
     - 全部 OTP_TIMEOUT → 抛 `RegisterPathExhausted`
     - DOMAIN_REJECTED 也触发切换
     - INVITE_LINK_MISSING 触发切换
     - OTHER 不切换(直接抛原异常)
     - `provider_chain_history` 字段累计正确
   - `AliasWithReaderProvider`:
     - `create_temp_email` 走 alias
     - `search_emails_by_recipient` 走 reader
     - `delete_account` 走 alias / `delete_emails_for` 走 reader
     - `login` 调用两者
   - `register_failures` 兼容性:
     - 旧记录无 `provider_chain_history` 字段读得出
     - 新记录带 history 字段读写一致

### 不做

- 不动 `src/autoteam/mail/{addy_io,simplelogin,fallback,maillab,cf_temp_email}.py`(S2 已稳)
- 不动 `account_state.py`(S1)
- 不实现真实 OpenAI 反爬规避(已固化为 subprocess 真实 Chrome,与本任务无关)
- 不动 `web/`(F2/F3 系列)
- 不真实 OpenAI 注册调用(无可用 team 母账号)
- 不修改 `register_failures.json` 主 schema(list-of-records 保持不变)

## Acceptance Criteria

- [ ] `ruff check src/autoteam/{manager,register_failures}.py src/autoteam/mail/{alias_reader_pair,register_dual_path}.py tests/unit/test_round12_s4_register_dual_path.py` 全绿
- [ ] `pytest tests/` >=624 passed(从 S3 baseline 无回归)
- [ ] `pytest tests/unit/test_round12_s4_register_dual_path.py -v` 全过且 >=15 case
- [ ] 新代码完整 type hints
- [ ] commit: `feat(round-12 S4): register dual-path with mail provider fallback`

## Definition of Done

- 上述 4 个文件落地(2 新 + 2 改)+ 1 新测试文件
- `_complete_registration` / `create_account_direct` / `create_new_account` 三个入口
  都接受 `mail_client=None` 与 `acc=None`,且不传 mail_client 时不抛错
- 单测覆盖 RegisterPathRotator 的 7+ 关键分支
- 无真实 OpenAI / Playwright 调用(全 mock)

## Out of Scope

- alias forwarding 真实 SMTP 转发配置(Addy.io 实例运维侧,不在代码内)
- 多 reader provider(本期 reader 与 alias 各 1 个,不嵌套链)
- 失败计数 UI 可视化(F2/F3 系列)
- mail.tm Tier 3 接入

## Research References

- 父 PRD: `.trellis/tasks/05-11-upstream-align-register-multimail-frontend-refresh/prd.md`
- S2 PRD §Q2/Q3: `.trellis/tasks/05-11-s2-mail-provider-fallback-gmx/prd.md`
- caveat-verified: `.trellis/tasks/05-11-upstream-align-register-multimail-frontend-refresh/research/caveat-verified-2026-05-11.md`
- 上游 baseline: `.upstream/manager.py:1225` (`_complete_registration`),
  `.upstream/manager.py:2030` (`create_account_direct`),
  `.upstream/manager.py:2106` (`create_new_account`)

## Technical Notes

- `RegisterFailureType.OTP_TIMEOUT` 关键 marker:
  - `TimeoutError` 且 `wait_for_email` 在 stack 上(via 文本匹配 `等待邮件超时` /
    `email timeout`)
- `RegisterFailureType.DOMAIN_REJECTED` 关键 marker:
  - `RegisterBlocked` 且消息含 `disposable` / `not allowed` / `please use a different`
  - 也包括 `email rejected` / `cannot use this email` / OpenAI 风控变体
- `_FailureTracker` 复用方式: `RegisterPathRotator(tracker=...)`;每次切 provider 前
  调 `tracker.record_failure(name, error_str)`,最后成功者调 `tracker.record_success(name)`
- 模块级 `_get_mail_client_for_account` 与 `cmd_rotate.ensure_account_mail` 的差异:
  前者每次调用都新建一个 mail client(无 reuse cache);后者在 cmd_rotate 闭包内有 cache。
  两者并行存在,本任务不动 cmd_rotate 闭包
