import { computed, onUnmounted, ref, watch } from 'vue'
import { useQuery, useQueryClient } from '@tanstack/vue-query'
import { api } from '../api.js'
import { useRotateStream } from './useRotateStream.js'

export const APP_QUERY_KEYS = {
  status: ['status'],
  tasks: ['tasks'],
  adminStatus: ['admin-status'],
  codexStatus: ['main-codex-status'],
  manualAccountStatus: ['manual-account-status'],
  registerFailures: ['register-failures'],
}

export const REFRESH_POLICY = {
  activeMs: 3000,
  idleMs: 120000,
  burstMs: 90000,
  staleMs: 5000,
}

function dataRef(query, fallback = null) {
  return computed(() => query.data.value ?? fallback)
}

function activeTask(tasks) {
  return (tasks || []).find(task => task.status === 'running' || task.status === 'pending') || null
}

export function useAppState(authenticated) {
  const queryClient = useQueryClient()
  const enabled = computed(() => !!authenticated.value)
  const burstUntil = ref(0)
  let activeTimer = null
  let burstTimer = null

  const statusQuery = useQuery({
    queryKey: APP_QUERY_KEYS.status,
    queryFn: () => api.getStatus(),
    enabled,
    staleTime: REFRESH_POLICY.staleMs,
    refetchInterval: computed(() => enabled.value ? REFRESH_POLICY.idleMs : false),
    refetchOnWindowFocus: true,
    keepPreviousData: true,
  })

  const tasksQuery = useQuery({
    queryKey: APP_QUERY_KEYS.tasks,
    queryFn: () => api.getTasks(),
    enabled,
    staleTime: REFRESH_POLICY.staleMs,
    refetchInterval: computed(() => enabled.value ? REFRESH_POLICY.idleMs : false),
    refetchOnWindowFocus: true,
    keepPreviousData: true,
  })

  const adminStatusQuery = useQuery({
    queryKey: APP_QUERY_KEYS.adminStatus,
    queryFn: () => api.getAdminStatus(),
    enabled,
    staleTime: REFRESH_POLICY.staleMs,
    refetchInterval: computed(() => enabled.value ? REFRESH_POLICY.idleMs : false),
    refetchOnWindowFocus: true,
    keepPreviousData: true,
  })

  const codexStatusQuery = useQuery({
    queryKey: APP_QUERY_KEYS.codexStatus,
    queryFn: () => api.getMainCodexStatus(),
    enabled,
    staleTime: REFRESH_POLICY.staleMs,
    refetchInterval: computed(() => enabled.value ? REFRESH_POLICY.idleMs : false),
    refetchOnWindowFocus: true,
    keepPreviousData: true,
  })

  const manualAccountStatusQuery = useQuery({
    queryKey: APP_QUERY_KEYS.manualAccountStatus,
    queryFn: () => api.getManualAccountStatus(),
    enabled,
    staleTime: REFRESH_POLICY.staleMs,
    refetchInterval: computed(() => enabled.value ? REFRESH_POLICY.idleMs : false),
    refetchOnWindowFocus: true,
    keepPreviousData: true,
  })

  const registerFailuresQuery = useQuery({
    queryKey: APP_QUERY_KEYS.registerFailures,
    queryFn: () => api.getRegisterFailures(50),
    enabled,
    staleTime: REFRESH_POLICY.staleMs,
    refetchInterval: computed(() => enabled.value ? REFRESH_POLICY.idleMs : false),
    refetchOnWindowFocus: true,
    keepPreviousData: true,
  })

  const status = dataRef(statusQuery)
  const tasks = dataRef(tasksQuery, [])
  const adminStatus = dataRef(adminStatusQuery)
  const codexStatus = dataRef(codexStatusQuery)
  const manualAccountStatus = dataRef(manualAccountStatusQuery)
  const registerFailures = dataRef(registerFailuresQuery)
  const runningTask = computed(() => activeTask(tasks.value))
  const busyTask = computed(() => {
    if (adminStatus.value?.login_in_progress) return { command: 'admin-login' }
    if (codexStatus.value?.in_progress) return { command: 'main-codex-sync' }
    return runningTask.value
  })
  const loading = computed(() => (
    statusQuery.isFetching.value
    || tasksQuery.isFetching.value
    || adminStatusQuery.isFetching.value
    || codexStatusQuery.isFetching.value
    || manualAccountStatusQuery.isFetching.value
    || registerFailuresQuery.isFetching.value
  ))
  const unauthorized = computed(() => [
    statusQuery.error.value,
    tasksQuery.error.value,
    adminStatusQuery.error.value,
    codexStatusQuery.error.value,
    manualAccountStatusQuery.error.value,
    registerFailuresQuery.error.value,
  ].some(error => error?.status === 401))
  const registerFailuresUnavailable = computed(() => {
    const error = registerFailuresQuery.error.value
    if (!error) return ''
    if (error.status === 404 || error.status === 405) {
      return '当前后端未提供注册失败明细 JSON 接口，前端已降级为空列表。'
    }
    return `获取注册失败明细失败: ${error.message || '未知错误'}`
  })
  const registerFailuresLoading = computed(() => registerFailuresQuery.isFetching.value)

  const rotateStream = useRotateStream({ immediate: false })
  const offTransition = rotateStream.onTransition(() => {
    refetchCore()
  })

  function invalidateCore() {
    for (const key of [
      APP_QUERY_KEYS.status,
      APP_QUERY_KEYS.tasks,
      APP_QUERY_KEYS.adminStatus,
      APP_QUERY_KEYS.codexStatus,
      APP_QUERY_KEYS.manualAccountStatus,
      APP_QUERY_KEYS.registerFailures,
    ]) {
      queryClient.invalidateQueries({ queryKey: key })
    }
  }

  function clearCoreCache() {
    for (const key of [
      APP_QUERY_KEYS.status,
      APP_QUERY_KEYS.tasks,
      APP_QUERY_KEYS.adminStatus,
      APP_QUERY_KEYS.codexStatus,
      APP_QUERY_KEYS.manualAccountStatus,
      APP_QUERY_KEYS.registerFailures,
    ]) {
      queryClient.removeQueries({ queryKey: key })
    }
  }

  async function refetchCore() {
    if (!enabled.value) return
    invalidateCore()
    await Promise.allSettled([
      queryClient.refetchQueries({ queryKey: APP_QUERY_KEYS.status, type: 'active' }),
      queryClient.refetchQueries({ queryKey: APP_QUERY_KEYS.tasks, type: 'active' }),
      queryClient.refetchQueries({ queryKey: APP_QUERY_KEYS.adminStatus, type: 'active' }),
      queryClient.refetchQueries({ queryKey: APP_QUERY_KEYS.codexStatus, type: 'active' }),
      queryClient.refetchQueries({ queryKey: APP_QUERY_KEYS.manualAccountStatus, type: 'active' }),
      queryClient.refetchQueries({ queryKey: APP_QUERY_KEYS.registerFailures, type: 'active' }),
    ])
  }

  function stopActiveRefresh() {
    if (activeTimer) {
      clearInterval(activeTimer)
      activeTimer = null
    }
  }

  function startActiveRefresh(durationMs = 0) {
    if (!enabled.value) return
    if (!activeTimer) {
      activeTimer = setInterval(refetchCore, REFRESH_POLICY.activeMs)
    }
    if (durationMs > 0) {
      burstUntil.value = Date.now() + durationMs
      clearTimeout(burstTimer)
      burstTimer = setTimeout(() => {
        burstUntil.value = 0
        if (!busyTask.value) stopActiveRefresh()
      }, durationMs)
    }
  }

  function notifyActionStarted() {
    startActiveRefresh(REFRESH_POLICY.burstMs)
    refetchCore()
  }

  async function refresh() {
    await refetchCore()
  }

  watch(enabled, (ok) => {
    if (ok) {
      rotateStream.connect()
      refetchCore()
      return
    }
    stopActiveRefresh()
    rotateStream.disconnect()
    clearCoreCache()
  }, { immediate: true })

  watch(unauthorized, (hit) => {
    if (hit) {
      authenticated.value = false
    }
  })

  watch(busyTask, (task) => {
    if (task) {
      startActiveRefresh()
      return
    }
    refetchCore()
    if (!burstUntil.value || Date.now() >= burstUntil.value) stopActiveRefresh()
  })

  onUnmounted(() => {
    stopActiveRefresh()
    clearTimeout(burstTimer)
    offTransition && offTransition()
    rotateStream.disconnect()
  })

  return {
    status,
    tasks,
    adminStatus,
    codexStatus,
    manualAccountStatus,
    registerFailures,
    registerFailuresLoading,
    registerFailuresUnavailable,
    runningTask,
    busyTask,
    loading,
    rotateStream,
    refresh,
    notifyActionStarted,
  }
}
