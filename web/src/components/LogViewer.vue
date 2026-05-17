<template>
  <div>
    <div class="flex items-center justify-between mb-6">
      <h2 class="text-xl font-bold text-ink-950">日志</h2>
      <div class="flex items-center gap-3">
        <span class="text-[11px] text-ink-500 hidden sm:inline">保留最新 1000 条，页面隐藏时暂停轮询</span>
        <label class="flex items-center gap-2 text-sm text-ink-600">
          <input type="checkbox" v-model="autoScroll" class="rounded border-hairline accent-indigo-600" />
          自动滚动
        </label>
        <AtButton variant="secondary" size="sm" :loading="loading" @click="fetchLogs">
          <template #icon>
            <RefreshCw class="w-3.5 h-3.5" :stroke-width="2" />
          </template>
          刷新
        </AtButton>
        <button @click="clearLogs"
          class="inline-flex items-center gap-1.5 px-3 py-1.5 bg-surface hover:bg-ink-100 text-sm rounded-lg border border-hairline transition text-ink-600 hover:text-ink-950 focus-ring">
          <Trash2 class="w-3.5 h-3.5" :stroke-width="2" />
          清空
        </button>
      </div>
    </div>

    <div ref="logContainer"
      class="bg-surface border border-hairline rounded-lg p-3 md:p-4 font-mono text-xs leading-relaxed h-[calc(100vh-200px)] md:h-[600px] overflow-y-auto">
      <div v-if="logs.length === 0" class="text-ink-400 text-center py-8">暂无日志</div>
      <div v-for="(log, i) in logs" :key="i"
        class="py-0.5 flex gap-3 hover:bg-ink-50">
        <span class="text-ink-500 shrink-0">{{ formatTime(log.time) }}</span>
        <span class="shrink-0 w-16"
          :class="{
            'text-rose-700': log.level === 'ERROR',
            'text-amber-700': log.level === 'WARNING',
            'text-sky-700': log.level === 'INFO',
            'text-ink-500': log.level === 'DEBUG',
          }">{{ log.level }}</span>
        <span class="text-ink-700 break-all">{{ log.message }}</span>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted, nextTick } from 'vue'
import { api } from '../api.js'
import AtButton from './AtButton.vue'
import { RefreshCw, Trash2 } from 'lucide-vue-next'

const logs = ref([])
const loading = ref(false)
const autoScroll = ref(true)
const logContainer = ref(null)
let pollTimer = null
let lastTime = 0
const LOG_RENDER_LIMIT = 1000

function formatTime(ts) {
  const d = new Date(ts * 1000)
  return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}:${String(d.getSeconds()).padStart(2, '0')}`
}

async function fetchLogs() {
  loading.value = true
  try {
    const result = await api.getLogs(500, lastTime)
    if (result.logs.length > 0) {
      if (lastTime === 0) {
        logs.value = result.logs
      } else {
        logs.value.push(...result.logs)
        // 保留最新 N 条
        if (logs.value.length > LOG_RENDER_LIMIT) {
          logs.value = logs.value.slice(-LOG_RENDER_LIMIT)
        }
      }
      lastTime = result.logs[result.logs.length - 1].time
      if (autoScroll.value) {
        nextTick(() => {
          if (logContainer.value) {
            logContainer.value.scrollTop = logContainer.value.scrollHeight
          }
        })
      }
    }
  } catch (e) {
    console.error('获取日志失败:', e)
  } finally {
    loading.value = false
  }
}

function clearLogs() {
  logs.value = []
  lastTime = 0
}

onMounted(() => {
  fetchLogs()
  pollTimer = setInterval(() => {
    if (!document.hidden) fetchLogs()
  }, 3000)
  document.addEventListener('visibilitychange', handleVisibility)
})

onUnmounted(() => {
  if (pollTimer) clearInterval(pollTimer)
  document.removeEventListener('visibilitychange', handleVisibility)
})

function handleVisibility() {
  if (!document.hidden) fetchLogs()
}
</script>
