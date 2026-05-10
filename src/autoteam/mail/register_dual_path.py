"""Register-time mail provider rotation — 注册流程级别的双路径/多路径回退。

与 `fallback.py` 的区别(详见 S4 PRD §Q1):

- `FallbackMailProvider` 是 **mail-API 级**的 dispatch:每次单个方法调用尝试一条链,
  对单封邮件/单次查询的失败做降级。
- `RegisterPathRotator` 是 **邮箱-粒度**的:一个邮箱用 provider A 注册到一半,OTP 超时
  /域名被拒后,要整体切到 provider B 创建新邮箱再重试整个注册流程。

两层语义不同,不可互相替代。本模块复用 `fallback._FailureTracker` 的状态文件
(`mail_provider_state.json`),避免再开计数文件。

## 触发分类(S4 PRD §Q2)

`classify_register_failure(exc_or_text)` 把异常/字符串映射到 `RegisterFailureType`:

| 类型                  | 触发条件                                            | 是否切 provider |
|---------------------- |---------------------------------------------------- |---------------- |
| `OTP_TIMEOUT`         | `TimeoutError` + `等待邮件超时` / `email timeout`   | ✓               |
| `INVITE_LINK_MISSING` | 显式标记或文本含 `invite link not found`            | ✓               |
| `DOMAIN_REJECTED`     | `RegisterBlocked` + `disposable`/`not allowed`/...  | ✓               |
| `OTHER`               | 其他(Playwright 崩溃 / 网络抖动 / unknown)          | ✗(原样抛)       |

`OTHER` 不切 provider,避免对偶发性问题误判降级。
"""

from __future__ import annotations

import enum
import logging
import time
from collections.abc import Callable
from typing import Any, TypeVar

from autoteam.mail.base import MailProvider
from autoteam.mail.fallback import (
    MailProviderUnavailable,
    _FailureTracker,
)

logger = logging.getLogger(__name__)


T = TypeVar("T")


# ----------------------------------------------------------------- exceptions


class RegisterPathExhausted(Exception):
    """register-level 所有 strategy 都失败 — 业务层应直接放弃此账号。"""

    def __init__(
        self,
        message: str,
        history: list[dict[str, Any]] | None = None,
        last_error: Exception | None = None,
    ):
        super().__init__(message)
        self.history: list[dict[str, Any]] = history or []
        self.last_error: Exception | None = last_error


class InviteLinkMissingError(Exception):
    """显式标记类:`extract_invite_link` 返回 None / 邮件未到 / 链接抓不到。

    业务代码可主动抛此异常让分类器命中 `INVITE_LINK_MISSING`,无需依赖文本匹配。
    """


# ----------------------------------------------------------------- classifier


class RegisterFailureType(str, enum.Enum):
    OTP_TIMEOUT = "OTP_TIMEOUT"
    INVITE_LINK_MISSING = "INVITE_LINK_MISSING"
    DOMAIN_REJECTED = "DOMAIN_REJECTED"
    OTHER = "OTHER"


_OTP_TIMEOUT_TOKENS = (
    "等待邮件超时",
    "邮件超时",
    "email timeout",
    "otp timeout",
    "wait_for_email",
    "等待邮件",  # 覆盖 "等待邮件 X 秒超时" 变体
)

_INVITE_MISSING_TOKENS = (
    "invite link not found",
    "invite link missing",
    "extract_invite_link",
    "邀请链接抓不到",
    "邀请链接缺失",
    "no invite link",
)

# RegisterBlocked.reason / 页面文案 中的"域名被拒"信号
_DOMAIN_REJECTED_TOKENS = (
    "disposable",
    "not allowed",
    "please use a different email",
    "different email",
    "cannot use this email",
    "email rejected",
    "email is not allowed",
    "blocked email",
    "blocked domain",
    "该邮箱不允许",
    "请使用其他邮箱",
    "邮箱已被",  # OpenAI 风控变体
)


def _safe_lower(s: Any) -> str:
    try:
        return str(s).lower()
    except Exception:
        return ""


def classify_register_failure(exc_or_text: Any) -> RegisterFailureType:
    """把异常对象 / 字符串 映射到 `RegisterFailureType`。

    - 优先看显式类型(`TimeoutError` / `InviteLinkMissingError` /
      `RegisterBlocked`(via duck typing 检测 `is_phone` / `is_duplicate` 属性
      不存在,reason 文本匹配))
    - 兜底看文本(message / reason)
    """
    if exc_or_text is None:
        return RegisterFailureType.OTHER

    # 显式类型优先
    if isinstance(exc_or_text, InviteLinkMissingError):
        return RegisterFailureType.INVITE_LINK_MISSING

    if isinstance(exc_or_text, TimeoutError):
        return RegisterFailureType.OTP_TIMEOUT

    # 取可读文本(异常 message + RegisterBlocked.reason)
    parts: list[str] = []
    if isinstance(exc_or_text, BaseException):
        parts.append(_safe_lower(exc_or_text))
        reason = getattr(exc_or_text, "reason", None)
        if reason:
            parts.append(_safe_lower(reason))
        step = getattr(exc_or_text, "step", None)
        if step:
            parts.append(_safe_lower(step))
    else:
        parts.append(_safe_lower(exc_or_text))

    text = " | ".join(parts)

    # RegisterBlocked 且消息含域名信号
    if any(tok in text for tok in _DOMAIN_REJECTED_TOKENS):
        # 排除明显的"已被使用"(duplicate) — duplicate 不属于域名被拒,duplicate 应由
        # 上层走 RegisterBlocked.is_duplicate 路径换邮箱(不切 provider)。
        if "already" in text or "已被使用" in text or "已存在" in text:
            return RegisterFailureType.OTHER
        return RegisterFailureType.DOMAIN_REJECTED

    if any(tok in text for tok in _OTP_TIMEOUT_TOKENS):
        return RegisterFailureType.OTP_TIMEOUT

    if any(tok in text for tok in _INVITE_MISSING_TOKENS):
        return RegisterFailureType.INVITE_LINK_MISSING

    return RegisterFailureType.OTHER


# Triggers that cause provider rotation
_ROTATE_TRIGGERS = frozenset({
    RegisterFailureType.OTP_TIMEOUT,
    RegisterFailureType.INVITE_LINK_MISSING,
    RegisterFailureType.DOMAIN_REJECTED,
})


def should_rotate_on(failure_type: RegisterFailureType) -> bool:
    """三类失败触发 provider 切换;OTHER 不切。"""
    return failure_type in _ROTATE_TRIGGERS


# ----------------------------------------------------------------- rotator


# action 签名:
#   action(client: MailProvider, provider_name: str, ctx: dict) -> T
# action 应:
#   - 使用 client 创建邮箱并执行注册动作
#   - 把任何 RegisterBlocked / TimeoutError / InviteLinkMissingError 直接 raise,
#     不要 catch
#   - 成功时返回业务期望的 T(例如 email 字符串)
Action = Callable[[MailProvider, str, dict], T]


class RegisterPathRotator:
    """编排"创建邮箱 → 执行注册动作 → 失败时切下一个 provider"循环。

    Args:
        strategies: `[(name, factory), ...]`。factory 是 `Callable[[], MailProvider]`。
                    factory 抛 `MailProviderUnavailable` 时跳过该项(不计失败计数);
                    抛其他异常计入 tracker 失败计数。
        tracker:    复用 S2 `_FailureTracker`。None 时使用全局默认。

    Usage:
        rotator = RegisterPathRotator([
            ("addy_io", lambda: AddyIoClient()),
            ("maillab", lambda: MaillabClient()),
        ])

        def do_register(client, name, ctx):
            acc_id, email = client.create_temp_email()
            ctx["email"] = email
            ctx["account_id"] = acc_id
            # ... Playwright 走注册 / OAuth ...
            return email

        email = rotator.try_each(do_register)
    """

    def __init__(
        self,
        strategies: list[tuple[str, Callable[[], MailProvider]]],
        tracker: _FailureTracker | None = None,
    ):
        if not strategies:
            raise ValueError("RegisterPathRotator 至少需要一个 strategy")
        self._strategies: list[tuple[str, Callable[[], MailProvider]]] = list(strategies)
        self._tracker: _FailureTracker = tracker or _FailureTracker()
        # 每次 try_each 调用都会重置 + 累计
        self.provider_chain_history: list[dict[str, Any]] = []

    @property
    def configured_chain(self) -> list[str]:
        return [name for name, _ in self._strategies]

    def _record(self, provider: str, error_type: str, error: str | None = None) -> None:
        entry: dict[str, Any] = {
            "provider": provider,
            "error_type": error_type,
            "ts": time.time(),
        }
        if error:
            entry["error"] = error[:300]
        self.provider_chain_history.append(entry)

    def try_each(self, action: Action) -> T:
        """按优先级遍历 strategy,首个成功的返回 action 结果;全失败抛 RegisterPathExhausted。

        分类器返回 `OTHER` 时,**直接抛原异常**(不切 provider),由上层按原有逻辑处理。
        """
        self.provider_chain_history = []
        last_error: Exception | None = None

        for name, factory in self._strategies:
            # blocked 状态跳过(S2 _FailureTracker cooldown 24h 自动重置)
            if self._tracker.is_blocked(name):
                logger.info("[register-rotator] provider=%s blocked,跳过", name)
                self._record(name, "BLOCKED", error="provider blocked by failure tracker")
                continue

            try:
                client = factory()
            except MailProviderUnavailable as exc:
                logger.info("[register-rotator] provider=%s 配置不可用,跳过: %s", name, exc)
                self._record(name, "UNAVAILABLE", error=str(exc))
                continue
            except Exception as exc:
                self._tracker.record_failure(name, f"factory: {exc}")
                self._record(name, "FACTORY_ERROR", error=str(exc))
                last_error = exc
                continue

            logger.info("[register-rotator] 尝试 provider=%s", name)
            ctx: dict[str, Any] = {"provider": name, "history": self.provider_chain_history}
            try:
                result = action(client, name, ctx)
            except Exception as exc:
                ftype = classify_register_failure(exc)
                err_msg = f"{type(exc).__name__}: {exc}"
                if not should_rotate_on(ftype):
                    # OTHER:不切换,直接向上抛原异常(保留 traceback)
                    self._record(name, ftype.value, error=err_msg)
                    logger.warning(
                        "[register-rotator] provider=%s 失败类型=%s 不触发切换,抛原异常",
                        name,
                        ftype.value,
                    )
                    raise
                # 三类可切换失败:记账 + 切下一个
                self._tracker.record_failure(name, f"{ftype.value}: {exc}")
                self._record(name, ftype.value, error=err_msg)
                last_error = exc
                logger.warning(
                    "[register-rotator] provider=%s 失败类型=%s,切下一 provider",
                    name,
                    ftype.value,
                )
                continue

            # 成功
            self._tracker.record_success(name)
            self._record(name, "OK")
            logger.info("[register-rotator] provider=%s 成功", name)
            return result

        # 全失败
        msg = (
            f"register path exhausted: tried {len(self.provider_chain_history)} provider(s);"
            f" chain={self.configured_chain}; history={self.provider_chain_history}"
        )
        logger.error("[register-rotator] %s", msg)
        raise RegisterPathExhausted(
            msg,
            history=list(self.provider_chain_history),
            last_error=last_error,
        ) from last_error


__all__ = [
    "Action",
    "InviteLinkMissingError",
    "RegisterFailureType",
    "RegisterPathExhausted",
    "RegisterPathRotator",
    "classify_register_failure",
    "should_rotate_on",
]
