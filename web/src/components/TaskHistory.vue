<template>
  <div class="mt-6 glass rounded-lg overflow-hidden">
    <div class="px-4 py-3 border-b border-hairline">
      <h2 class="text-lg font-semibold text-ink-950">任务历史</h2>
      <p v-if="hiddenTaskCount" class="text-xs text-ink-500 mt-1">
        仅显示最新 {{ visibleTasks.length }} 条，已隐藏 {{ hiddenTaskCount }} 条较早记录。
      </p>
    </div>

    <div v-if="tasks.length === 0" class="px-4 py-8 text-center text-gray-500 text-sm">
      暂无任务记录
    </div>

    <div v-else class="overflow-x-auto">
      <table class="w-full text-sm">
        <thead>
          <tr class="text-ink-500 text-left border-b border-hairline">
            <th class="px-4 py-3 font-medium">任务 ID</th>
            <th class="px-4 py-3 font-medium">命令</th>
            <th class="px-4 py-3 font-medium">参数</th>
            <th class="px-4 py-3 font-medium">状态</th>
            <th class="px-4 py-3 font-medium">创建时间</th>
            <th class="px-4 py-3 font-medium">耗时</th>
            <th class="px-4 py-3 font-medium">结果</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="task in visibleTasks" :key="task.task_id"
            class="border-b border-hairline hover:bg-ink-50 transition">
            <td class="px-4 py-3 font-mono text-xs text-ink-500">{{ task.task_id }}</td>
            <td class="px-4 py-3">
              <span class="px-2 py-0.5 bg-ink-50 rounded text-xs font-medium text-ink-700 border border-hairline">
                {{ task.command }}
              </span>
            </td>
            <td class="px-4 py-3 text-xs text-ink-500">{{ formatParams(task.params) }}</td>
            <td class="px-4 py-3">
              <span class="inline-flex items-center gap-1.5 text-xs font-medium" :class="taskStatusClass(task.status)">
                <span v-if="task.status === 'running'" class="animate-spin inline-block w-3 h-3 border-2 border-current border-t-transparent rounded-full"></span>
                <span v-else class="w-1.5 h-1.5 rounded-full" :class="taskDotClass(task.status)"></span>
                {{ taskStatusLabel(task.status) }}
              </span>
            </td>
            <td class="px-4 py-3 text-xs text-ink-500">{{ formatTime(task.created_at) }}</td>
            <td class="px-4 py-3 text-xs text-ink-500">{{ duration(task) }}</td>
            <td class="px-4 py-3 text-xs max-w-xs truncate" :class="task.error ? 'text-rose-700' : 'text-ink-500'">
              {{ task.error || formatResult(task.result) }}
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  tasks: { type: Array, default: () => [] },
})

const visibleTasks = computed(() => props.tasks.slice(0, 200))
const hiddenTaskCount = computed(() => Math.max(0, props.tasks.length - visibleTasks.value.length))

function taskStatusClass(s) {
  return {
    pending: 'text-ink-500',
    running: 'text-amber-700',
    completed: 'text-emerald-700',
    failed: 'text-rose-700',
  }[s] || 'text-ink-500'
}

function taskDotClass(s) {
  return {
    pending: 'bg-ink-400',
    completed: 'bg-emerald-500',
    failed: 'bg-rose-500',
  }[s] || 'bg-ink-400'
}

function taskStatusLabel(s) {
  return { pending: '等待中', running: '执行中', completed: '已完成', failed: '失败' }[s] || s
}

function formatTime(ts) {
  if (!ts) return '-'
  const d = new Date(ts * 1000)
  return `${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}:${String(d.getSeconds()).padStart(2, '0')}`
}

function duration(task) {
  const start = task.started_at || task.created_at
  const end = task.finished_at || (task.status === 'running' ? Date.now() / 1000 : null)
  if (!start || !end) return '-'
  const sec = Math.round(end - start)
  if (sec < 60) return `${sec}s`
  const min = Math.floor(sec / 60)
  return `${min}m ${sec % 60}s`
}

function formatParams(params) {
  if (!params || Object.keys(params).length === 0) return '-'
  return Object.entries(params).map(([k, v]) => `${k}=${v}`).join(', ')
}

function formatResult(result) {
  if (result === null || result === undefined) return '-'
  if (typeof result === 'string') return result
  return JSON.stringify(result)
}
</script>
