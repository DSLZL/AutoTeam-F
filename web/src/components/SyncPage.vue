<template>
  <div class="space-y-5">
    <div>
      <div class="text-[10px] uppercase tracking-[0.3em] text-indigo-700 mb-1">Sync Center</div>
      <h2 class="text-2xl font-extrabold text-ink-950 tracking-tight">同步中心</h2>
      <p class="text-sm text-ink-500 mt-1">本地账号池对账、同步到 CPA、从 CPA 反向拉取认证文件。</p>
    </div>
    <TaskPanel
      mode="sync"
      :running-task="runningTask"
      :admin-status="adminStatus"
      :rotate-stream="rotateStream"
      @task-started="$emit('task-started')"
      @refresh="$emit('refresh')"
    />
  </div>
</template>

<script setup>
import TaskPanel from './TaskPanel.vue'

defineProps({
  runningTask: Object,
  adminStatus: Object,
  rotateStream: { type: Object, default: null },
})

defineEmits(['task-started', 'refresh'])
</script>
