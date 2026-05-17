<!--
  MasterHealthBanner — F3 母号订阅健康度横幅,4 状态视觉
  spec:master-subscription-health.md v1.1 §6 (UI banner) + §13 (endpoint 守恒)

  Props:
    masterHealth: {healthy: bool, reason: string, evidence: object}
    minGraceUntil:  Optional<number>  集中显示"最近一个子号 grace 到期" 的 epoch
                                       从父级 status.accounts 派生最早 grace_until
  Emits:
    refresh: 立即重测按钮触发
-->
<template>
  <div v-if="visible" class="relative overflow-hidden rounded-lg border lift-hover shadow-card"
    :class="[tone.border, tone.bg]" role="alert">
    <!-- 角标 -->
    <div class="absolute top-0 right-0 px-3 py-1 text-[10px] font-mono uppercase tracking-widest rounded-bl-lg"
      :class="[tone.tagBg, tone.tagText]">
      {{ tone.tag }}
    </div>

    <div class="relative px-5 py-4">
      <div class="flex items-start gap-4">
        <!-- 图标 -->
        <div class="relative shrink-0 w-11 h-11 rounded-lg flex items-center justify-center"
          :class="tone.iconWrap">
          <AlertTriangle v-if="severity === 'critical'" class="w-5 h-5" :stroke-width="2" />
          <CircleAlert v-else-if="severity === 'warning'" class="w-5 h-5" :stroke-width="2" />
          <Info v-else-if="severity === 'info'" class="w-5 h-5" :stroke-width="2" />
          <Check v-else class="w-5 h-5" :stroke-width="2" />

          <span v-if="severity === 'critical'" class="absolute -top-0.5 -right-0.5 w-2.5 h-2.5 rounded-full bg-rose-400">
            <span class="absolute inset-0 rounded-full bg-rose-400 animate-ping opacity-75"></span>
          </span>
        </div>

        <!-- 文案 -->
        <div class="flex-1 min-w-0">
          <div class="flex items-center gap-3 flex-wrap">
            <h3 class="text-base font-bold" :class="tone.title">{{ title }}</h3>
            <span v-if="graceCountdown" class="font-mono text-xs px-2 py-0.5 rounded-md bg-surface border border-hairline"
              :class="graceCountdownColor">
              grace · {{ graceCountdown }}
            </span>
          </div>
          <p class="text-sm mt-1 leading-relaxed" :class="tone.body">{{ description }}</p>
          <div v-if="evidenceLine" class="text-[11px] font-mono mt-2 break-all opacity-70" :class="tone.body">
            {{ evidenceLine }}
          </div>
        </div>

        <!-- 操作 -->
        <div class="shrink-0 flex flex-col items-end gap-2">
          <button
            @click="$emit('refresh')"
            :disabled="loading"
            class="h-8 px-3 rounded-lg text-xs font-semibold border transition lift-hover focus-ring
                   disabled:opacity-50 disabled:cursor-not-allowed"
            :class="tone.btn">
            <span v-if="loading" class="inline-block w-3 h-3 mr-1.5 rounded-full border-2 border-current border-t-transparent animate-spin align-[-2px]"></span>
            {{ loading ? '检测中…' : '立即重测' }}
          </button>
          <span v-if="lastProbed" class="text-[10px] font-mono opacity-50" :class="tone.body">
            上次探测:{{ lastProbed }}{{ cached ? ' · cache' : '' }}
          </span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { formatGraceRemain, graceUrgencyClass, masterHealthSeverity } from '../composables/useStatus.js'
import { AlertTriangle, Check, CircleAlert, Info } from 'lucide-vue-next'

const props = defineProps({
  masterHealth: { type: Object, default: null },
  minGraceUntil: { type: [Number, null], default: null },
  loading: Boolean,
})
defineEmits(['refresh'])

// reason → severity 映射 (F3 PRD,Round 11 加 subscription_grace)
// spec:master-subscription-health.md v1.2 §14
//   subscription_grace                    → warning (healthy=True,但 grace 期内,黄色 + 倒计时)
//   subscription_cancelled (with grace)   → warning (旧兼容,子号 grace_until 仍未过期)
//   subscription_cancelled (no grace)     → critical (red)
//   workspace_missing / role_not_owner / auth_invalid → critical
//   network_error                          → info (gray, stale data)
//   active                                 → ok (green,微提示;visible=false)
const severity = computed(() => masterHealthSeverity(props.masterHealth, props.minGraceUntil))

const visible = computed(() => severity.value !== 'hidden')

const title = computed(() => {
  const r = props.masterHealth?.reason
  switch (severity.value) {
    case 'warning':
      // Round 11:subscription_grace 是 healthy=True 状态,文案区分于旧 subscription_cancelled+grace
      if (r === 'subscription_grace') return '母号订阅在 grace 期 · 仍可正常使用'
      return '母号订阅 grace 期 · 期限内仍可使用'
    case 'critical':
      if (r === 'subscription_cancelled') return '母号订阅已 cancel · 请续费或切换母号'
      if (r === 'workspace_missing') return 'Workspace 不存在 · account_id 漂移'
      if (r === 'role_not_owner') return '权限异常 · 当前角色非 owner/admin'
      if (r === 'auth_invalid') return '主号 session 失效 · 请重新登录'
      return '母号探针拒绝'
    case 'info':
      return '母号探针失败 · 数据可能 stale'
    default:
      return ''
  }
})

const description = computed(() => {
  const r = props.masterHealth?.reason
  switch (severity.value) {
    case 'warning':
      // Round 11:subscription_grace healthy=True,新 invite 仍能拿 plan_type=team
      if (r === 'subscription_grace') {
        return 'eligible_for_auto_reactivation=true 但订阅未到期,新 invite 仍能拿 plan_type=team。倒计时到期后自动转 cancelled,请提前续费或切换母号。'
      }
      return 'master 母号已 cancel_at_period_end,grace 期内子号 wham 仍 200 plan=team。fill 池不增量,但用户可继续消耗已有 quota。倒计时见右上角。'
    case 'critical':
      if (r === 'subscription_cancelled') return 'eligible_for_auto_reactivation=true,新 invite 必拿 plan_type=free。请续订或更换母号,fill-personal 入口已 503 拒绝。'
      if (r === 'workspace_missing') return '/backend-api/accounts items[] 中找不到目标 workspace,可能是 master 已切换。请重新核对 admin_state。'
      if (r === 'role_not_owner') return '当前用户角色不是 owner/admin,无法管理 workspace。请用正确账号重新登录。'
      if (r === 'auth_invalid') return 'master session 401/403,请到「设置」页清除登录态后重新导入 session_token。'
      return '请到「设置」页处理。'
    case 'info':
      return '/backend-api/accounts 网络抖动或 5xx,本次未拿到最新订阅状态。建议稍后重测。'
    default:
      return ''
  }
})

const evidenceLine = computed(() => {
  const ev = props.masterHealth?.evidence
  if (!ev) return ''
  const parts = []
  const accId = ev.account_id || ev.raw_account_item?.id
  if (accId) parts.push(`account_id=${accId}`)
  if (ev.current_user_role) parts.push(`role=${ev.current_user_role}`)
  if (ev.http_status) parts.push(`http=${ev.http_status}`)
  if (ev.detail) parts.push(`detail=${ev.detail}`)
  return parts.join(' · ')
})

const lastProbed = computed(() => {
  const ts = props.masterHealth?.evidence?.probed_at
  if (!ts) return ''
  const d = new Date(ts * 1000)
  const pad = (n) => String(n).padStart(2, '0')
  return `${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`
})

const cached = computed(() => props.masterHealth?.evidence?.cache_hit === true)

// Round 11:subscription_grace 的倒计时优先用 evidence.grace_until (master JWT 解析结果),
// 否则 fallback 到 minGraceUntil (子号 grace_until 派生)。
const effectiveGraceUntil = computed(() => {
  const evGrace = props.masterHealth?.evidence?.grace_until
  if (typeof evGrace === 'number' && evGrace > 0) return evGrace
  return props.minGraceUntil
})

const graceCountdown = computed(() => {
  if (severity.value !== 'warning') return ''
  return formatGraceRemain(effectiveGraceUntil.value) || ''
})
const graceCountdownColor = computed(() => graceUrgencyClass(effectiveGraceUntil.value))

// 配色三档
const tone = computed(() => {
  if (severity.value === 'warning') {
    return {
      tag: 'GRACE',
      tagBg: 'bg-amber-100',
      tagText: 'text-amber-800',
      bg: 'bg-amber-50',
      iconWrap: 'bg-amber-100 text-amber-700 border border-amber-200',
      title: 'text-amber-950',
      body: 'text-amber-800',
      border: 'border-amber-200',
      btn: 'bg-surface hover:bg-amber-100 text-amber-800 border-amber-200',
    }
  }
  if (severity.value === 'info') {
    return {
      tag: 'STALE',
      tagBg: 'bg-slate-100',
      tagText: 'text-slate-700',
      bg: 'bg-slate-50',
      iconWrap: 'bg-slate-100 text-slate-700 border border-slate-200',
      title: 'text-slate-950',
      body: 'text-slate-700',
      border: 'border-slate-200',
      btn: 'bg-surface hover:bg-slate-100 text-slate-700 border-slate-200',
    }
  }
  return {
    tag: 'ALERT',
    tagBg: 'bg-rose-100',
    tagText: 'text-rose-800',
    bg: 'bg-rose-50',
    iconWrap: 'bg-rose-100 text-rose-700 border border-rose-200',
    title: 'text-rose-950',
    body: 'text-rose-800',
    border: 'border-rose-200',
    btn: 'bg-surface hover:bg-rose-100 text-rose-800 border-rose-200',
  }
})
</script>
