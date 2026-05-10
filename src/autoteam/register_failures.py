"""注册失败明细日志（持久化到 register_failures.json）。

用户要求：失败账号不能污染账号列表，但失败原因必须能追溯 —— 比如 add-phone 触发了几次、
哪些临时邮箱在 OAuth 阶段挂了、哪些被判 duplicate。本模块单独存这类明细，不与 accounts.json 混。

记录只保留最近 N 条（RECORD_LIMIT），避免长期运行后文件膨胀。

并发：`_cmd_fill_personal` 等任务跑在 ThreadPoolExecutor 里，多个 worker 会同时命中
record_failure —— 无锁的读-改-写会互相覆盖导致丢记录。全部写入走 _LOCK 串行化。
"""

import json
import logging
import os
import threading
import time
from pathlib import Path

from autoteam.textio import read_text, write_text

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).parent.parent.parent
FAILURES_FILE = PROJECT_ROOT / "register_failures.json"
FAILURES_FILE_MODE = 0o666
RECORD_LIMIT = 500

_LOCK = threading.Lock()


# Round 8 — Master Team 订阅降级 + OAuth Personal Workspace 显式选择
# 详见 prompts/0426/spec/shared/master-subscription-health.md §7 + oauth-workspace-selection.md §2.3
MASTER_SUBSCRIPTION_DEGRADED = "master_subscription_degraded"
"""母号 ChatGPT Team 订阅 cancel(eligible_for_auto_reactivation=true)。M-T1 / M-T2 fail-fast。"""

OAUTH_WS_NO_PERSONAL = "oauth_workspace_select_no_personal"
"""workspaces[] 中找不到 personal 项 — user 在后端事实上只属于 Team。fail-fast,不重试。"""

OAUTH_WS_ENDPOINT_ERROR = "oauth_workspace_select_endpoint_error"
"""POST /api/accounts/workspace/select 4xx/5xx 且 UI fallback 失败。端点变更 / 反爬 / DOM 漂移。"""

OAUTH_PLAN_DRIFT_PERSISTENT = "oauth_plan_drift_persistent"
"""workspace/select 成功但 5 次 OAuth retry 后 bundle.plan_type 仍非 free — 后端最终一致性失败。"""


# Round 12 S4 — 注册收尾双路径:mail provider rotation 触发分类(详见
# `src/autoteam/mail/register_dual_path.py`)。三类失败会触发 RegisterPathRotator
# 切换到下一个 provider 重试,失败明细写入 register_failures.json,**extra 中带
# provider_chain_history 字段记录每个 provider 的尝试结果。
MAIL_OTP_TIMEOUT = "mail_otp_timeout"
"""注册时等待 OTP / 验证邮件超时 — 多见于 alias forwarding 链路转发延迟或 reader 失联。"""

MAIL_INVITE_LINK_MISSING = "mail_invite_link_missing"
"""邀请邮件已到但 extract_invite_link 抓不到链接 — 邮件模板变体 / HTML 损坏 / sender 异常。"""

MAIL_DOMAIN_REJECTED = "mail_domain_rejected"
"""OpenAI 拒绝当前 mail provider 的域名(disposable / not allowed) — 触发整体切到下一 provider。"""


def _load():
    if not FAILURES_FILE.exists():
        return []
    try:
        raw = read_text(FAILURES_FILE).strip()
        if not raw:
            return []
        data = json.loads(raw)
        return data if isinstance(data, list) else []
    except Exception as exc:
        # 不静默吞：文件损坏时保留原件便于人工排查,返回空让新一轮写入继续。
        corrupt_path = FAILURES_FILE.with_suffix(f".corrupt-{int(time.time())}.json")
        try:
            FAILURES_FILE.rename(corrupt_path)
            logger.error("[register_failures] 解析失败, 已保留原文件为 %s: %s", corrupt_path.name, exc)
        except Exception as rename_exc:
            logger.error("[register_failures] 解析失败且无法重命名 (%s): %s", exc, rename_exc)
        return []


def _save(records):
    records = records[-RECORD_LIMIT:]
    target = FAILURES_FILE.resolve()
    write_text(target, json.dumps(records, indent=2, ensure_ascii=False))
    try:
        os.chmod(target, FAILURES_FILE_MODE)
    except Exception:
        pass


def record_failure(email, category, reason="", **extra):
    """追加一条失败记录。

    category(原有):
        'phone_blocked' / 'duplicate_exhausted' / 'register_failed' / 'oauth_failed'
        / 'kick_failed' / 'team_oauth_failed' / 'exception'
    category(SPEC-2 新增 — 注册/邀请生命周期相关):
        'oauth_phone_blocked'        OAuth 阶段触发 add-phone / duplicate(invite.RegisterBlocked)
        'plan_unsupported'           plan_type 不在白名单(team/free/plus/pro)
        'no_quota_assigned'          OAuth 成功但后端没发配额(primary_total=0 或 rate_limit 全空)
        'plan_drift'                 reinvite 后 plan_type 漂移到非 team
        'auth_error_at_oauth'        post-register quota 探测返回 401/403
        'quota_probe_network_error'  post-register quota 探测网络错误(允许下次重试)
    category(Round 8 SPEC-2 v1.5 新增 — Master 订阅降级 / OAuth Workspace 显式选择):
        'master_subscription_degraded'         母号 Team 订阅已 cancel(M-T1 / M-T2 fail-fast)
        'oauth_workspace_select_no_personal'   OAuth session workspaces[] 中无 personal 项
        'oauth_workspace_select_endpoint_error' workspace/select 端点 + UI fallback 都失败
        'oauth_plan_drift_persistent'          5 次 OAuth retry 后 bundle.plan 仍非 free
    category(Round 12 S4 新增 — 注册双路径 mail provider rotation):
        'mail_otp_timeout'                     OTP/验证邮件等待超时 → 切下一 provider
        'mail_invite_link_missing'             邀请链接抓不到 → 切下一 provider
        'mail_domain_rejected'                 OpenAI 拒绝当前 provider 域名 → 切下一 provider

    reason: 面向人的简短描述,显示在日志和面板。可留空,从 extra.detail 取代。
    extra:  任意附加字段(attempts, duplicate_swaps, step, url, stage, detail ...)
            Round 12 S4 约定 extra 中可带:
              provider_chain_history: list[{provider, error_type, ts[, error]}]
              旧记录无此字段,读路径用 `r.get("provider_chain_history", [])` 兼容。
    """
    with _LOCK:
        records = _load()
        records.append(
            {
                "timestamp": time.time(),
                "email": email or "",
                "category": category,
                "reason": reason or extra.get("detail", "") or "",
                **extra,
            }
        )
        _save(records)


def list_failures(limit=50):
    with _LOCK:
        records = _load()
    return records[-limit:][::-1]


def count_by_category(since_ts=0):
    with _LOCK:
        records = _load()
    counts = {}
    for r in records:
        if r.get("timestamp", 0) < since_ts:
            continue
        cat = r.get("category", "unknown")
        counts[cat] = counts.get(cat, 0) + 1
    return counts
