<!--
  ToastHost — toast 容器,挂在 App 顶层
-->
<template>
  <div class="fixed top-3 right-3 z-[100] space-y-2 max-w-sm pointer-events-none">
    <transition-group tag="div" class="space-y-2">
      <div v-for="t in state.items" :key="t.id"
        class="pointer-events-auto rounded-lg border bg-surface shadow-card px-4 py-3 flex items-start gap-3"
        :class="[toneClass(t.tone), t.leaving ? 'animate-toast-out' : 'animate-toast-in']"
        @click="dismiss(t.id)">
        <span class="shrink-0 mt-0.5">
          <Check v-if="t.tone === 'success'" class="w-4 h-4 text-emerald-700" :stroke-width="2" />
          <X v-else-if="t.tone === 'error'" class="w-4 h-4 text-rose-700" :stroke-width="2" />
          <TriangleAlert v-else-if="t.tone === 'warning'" class="w-4 h-4 text-amber-700" :stroke-width="2" />
          <Info v-else class="w-4 h-4 text-sky-700" :stroke-width="2" />
        </span>
        <div class="flex-1 min-w-0">
          <div class="text-sm font-semibold leading-tight" :class="titleColor(t.tone)">{{ t.text }}</div>
          <div v-if="t.detail" class="text-xs mt-1 opacity-70 break-all" :class="titleColor(t.tone)">{{ t.detail }}</div>
        </div>
      </div>
    </transition-group>
  </div>
</template>

<script setup>
import { useToast } from '../composables/useToast.js'
import { Check, Info, TriangleAlert, X } from 'lucide-vue-next'

const { state, dismiss } = useToast()

function toneClass(tone) {
  return {
    success: 'bg-emerald-50 border-emerald-200',
    error: 'bg-rose-50 border-rose-200',
    warning: 'bg-amber-50 border-amber-200',
    info: 'bg-sky-50 border-sky-200',
  }[tone] || 'bg-sky-50 border-sky-200'
}
function titleColor(tone) {
  return {
    success: 'text-emerald-900',
    error: 'text-rose-900',
    warning: 'text-amber-900',
    info: 'text-sky-900',
  }[tone] || 'text-sky-900'
}
</script>
