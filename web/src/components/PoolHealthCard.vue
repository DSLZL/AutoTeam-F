<!--
  PoolHealthCard — F6 Dashboard 顶部账号池健康度卡片
  - 4 数字 (可用 / Grace / 待机 / 不可用)
  - 占比环形图 (Donut)
  - master_health inline 状态
-->
<template>
  <div class="glass rounded-lg p-5 lg:p-6 lift-hover relative overflow-hidden">
    <div class="relative flex flex-col lg:flex-row items-start lg:items-center gap-6">
      <!-- 左:donut + 中心总数 -->
      <div class="shrink-0">
        <HealthDonut
          :size="140"
          :thickness="14"
          :segments="segments"
          :center-value="counts.total"
          center-label="账号池"
          :center-hint="trendHint" />
      </div>

      <!-- 中:四档数字 -->
      <div class="flex-1 grid grid-cols-2 sm:grid-cols-4 gap-3 w-full">
        <div v-for="card in cards" :key="card.key"
          class="rounded-lg p-3 border bg-surface hover:bg-ink-50 transition-all"
          :class="card.borderClass">
          <div class="flex items-center gap-1.5 text-[10px] uppercase tracking-widest font-semibold"
            :class="card.labelClass">
            <span class="w-1.5 h-1.5 rounded-full" :style="{ background: card.color }"></span>
            {{ card.label }}
          </div>
          <div class="text-3xl font-bold tabular mt-1" :class="card.valueClass">
            {{ card.value }}
          </div>
          <div class="text-[10px] mt-0.5 opacity-60" :class="card.valueClass">
            {{ percent(card.value) }}
          </div>
        </div>
      </div>

      <!-- 右:master health inline -->
      <div class="shrink-0 lg:max-w-xs w-full lg:w-auto">
        <div class="rounded-lg border p-3 flex items-start gap-3"
          :class="masterTone.border" :style="{ background: masterTone.bg }">
          <div class="shrink-0 w-9 h-9 rounded-lg flex items-center justify-center"
            :class="masterTone.iconWrap">
            <ShieldCheck class="w-4 h-4" :stroke-width="2" />
          </div>
          <div class="min-w-0 flex-1">
            <div class="text-[10px] uppercase tracking-widest font-semibold opacity-70" :class="masterTone.text">
              母号订阅
            </div>
            <div class="text-sm font-bold leading-tight mt-0.5" :class="masterTone.text">
              {{ masterTitle }}
            </div>
            <div class="text-[10px] mt-0.5 opacity-70 truncate" :class="masterTone.text">
              {{ masterSubtitle }}
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import HealthDonut from './HealthDonut.vue'
import { computeUsability, formatGraceRemain } from '../composables/useStatus.js'
import { ShieldCheck } from 'lucide-vue-next'

const props = defineProps({
  accounts: { type: Array, default: () => [] },
  masterHealth: { type: Object, default: null },
  minGraceUntil: { type: [Number, null], default: null },
})

const counts = computed(() => {
  const c = { usable: 0, grace: 0, standby: 0, unusable: 0, total: 0 }
  for (const acc of props.accounts || []) {
    if (acc.is_main_account) continue
    const u = computeUsability(acc).kind
    if (u === 'usable') c.usable++
    else if (u === 'grace') c.grace++
    else if (u === 'standby') c.standby++
    else if (u === 'unusable') c.unusable++
    c.total++
  }
  return c
})

const cards = computed(() => [
  {
    key: 'usable', label: '可用', value: counts.value.usable,
    color: 'rgba(52, 211, 153, 1)',
    borderClass: 'border-emerald-500/20',
    labelClass: 'text-emerald-700',
    valueClass: 'text-emerald-700',
  },
  {
    key: 'grace', label: 'Grace', value: counts.value.grace,
    color: 'rgba(251, 146, 60, 1)',
    borderClass: 'border-orange-500/30',
    labelClass: 'text-orange-700',
    valueClass: 'text-orange-700',
  },
  {
    key: 'standby', label: '待机', value: counts.value.standby,
    color: 'rgba(251, 191, 36, 1)',
    borderClass: 'border-amber-500/20',
    labelClass: 'text-amber-700',
    valueClass: 'text-amber-700',
  },
  {
    key: 'unusable', label: '不可用', value: counts.value.unusable,
    color: 'rgba(244, 63, 94, 1)',
    borderClass: 'border-rose-500/20',
    labelClass: 'text-rose-700',
    valueClass: 'text-rose-700',
  },
])

const segments = computed(() =>
  cards.value.filter((c) => c.value > 0).map((c) => ({ key: c.key, value: c.value, color: c.color }))
)

const trendHint = computed(() => {
  const total = counts.value.total
  if (!total) return '无账号'
  const ratio = ((counts.value.usable / total) * 100).toFixed(0)
  return `${ratio}% 可用`
})

function percent(v) {
  if (!counts.value.total) return '0%'
  return `${((v / counts.value.total) * 100).toFixed(0)}%`
}

// 母号订阅 inline 状态
const masterTone = computed(() => {
  const m = props.masterHealth
  const r = m?.reason
  // Round 11:subscription_grace = healthy=True 但 grace 期内,渲染橙色提示 (而非 healthy 绿色)
  if (r === 'subscription_grace') {
    return {
      bg: '#fff7ed',
      border: 'border-orange-200',
      iconWrap: 'bg-orange-100 text-orange-700',
      text: 'text-orange-800',
    }
  }
  if (!m || m.healthy === true || r === 'active') {
    return {
      bg: '#ecfdf5',
      border: 'border-emerald-200',
      iconWrap: 'bg-emerald-100 text-emerald-700',
      text: 'text-emerald-800',
    }
  }
  if (r === 'subscription_cancelled') {
    return {
      bg: '#fff7ed',
      border: 'border-orange-200',
      iconWrap: 'bg-orange-100 text-orange-700',
      text: 'text-orange-800',
    }
  }
  if (r === 'network_error') {
    return {
      bg: '#f8fafc',
      border: 'border-slate-200',
      iconWrap: 'bg-slate-100 text-slate-700',
      text: 'text-slate-700',
    }
  }
  return {
    bg: '#fff1f2',
    border: 'border-rose-200',
    iconWrap: 'bg-rose-100 text-rose-700',
    text: 'text-rose-800',
  }
})

const masterTitle = computed(() => {
  const m = props.masterHealth
  if (!m) return '未探测'
  // Round 11:subscription_grace healthy=True,显示 "Grace 期内"
  if (m.reason === 'subscription_grace') return 'Grace 期内'
  if (m.healthy === true || m.reason === 'active') return 'Healthy'
  if (m.reason === 'subscription_cancelled') {
    if (props.minGraceUntil && props.minGraceUntil * 1000 > Date.now()) return 'Grace 期内'
    return 'Cancelled'
  }
  if (m.reason === 'workspace_missing') return 'Workspace 漂移'
  if (m.reason === 'role_not_owner') return '权限异常'
  if (m.reason === 'auth_invalid') return 'Session 失效'
  if (m.reason === 'network_error') return '网络抖动'
  return m.reason || '异常'
})

const masterSubtitle = computed(() => {
  const m = props.masterHealth
  if (!m) return '尚未拉取 / 设置 → 探测'
  // Round 11:subscription_grace 优先用 evidence.grace_until 显示倒计时
  if (m.reason === 'subscription_grace') {
    const evGrace = m.evidence?.grace_until
    const target = (typeof evGrace === 'number' && evGrace > 0) ? evGrace : props.minGraceUntil
    const r = formatGraceRemain(target)
    return r ? `grace 剩 ${r}` : '订阅 grace 期'
  }
  if (m.healthy === true || m.reason === 'active') return '订阅 active'
  if (m.reason === 'subscription_cancelled' && props.minGraceUntil) {
    const r = formatGraceRemain(props.minGraceUntil)
    return r ? `grace 剩 ${r}` : 'grace 已过期'
  }
  return m.evidence?.detail || ''
})
</script>
