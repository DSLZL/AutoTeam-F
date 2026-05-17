// round-12 F2 — useRotateStream
// 包装 EventSource 订阅 /api/rotate/stream,把后端 default_machine 的 transition
// 事件以 reactive ref 暴露给组件 (TaskPanel 实时进度面板)。
//
// 行为契约:
// - onMounted 自动 connect (除非传 { immediate: false });onUnmounted 自动 disconnect
// - events: 最近 N=50 条转移记录,数组首条 = 最新 (UI 直接 v-for 即可倒序)
// - isConnected: 反映 EventSource.readyState === OPEN
// - 重连失败 5 次后停止 (EventSource 浏览器内置自动重连;我们额外做计数兜底,
//   防止后端 5xx 死循环)
// - 通过 onTransition(cb) 注册外部副作用 (例如 vue-query invalidate)
//
// 后端 SSE schema (api.py _build_sse_event_stream):
//   { email, from, to, reason, ts, extra }

import { onMounted, onUnmounted, ref } from 'vue'
import { getApiKey } from '../api.js'

const DEFAULT_URL = '/api/rotate/stream'
const MAX_EVENTS = 50
const MAX_FAILURES = 5

export function useRotateStream(opts = {}) {
  const url = opts.url || DEFAULT_URL
  const max = opts.maxEvents ?? MAX_EVENTS
  const immediate = opts.immediate !== false

  const events = ref([])
  const isConnected = ref(false)
  const lastError = ref(null)

  let source = null
  let failureCount = 0
  let stoppedByQuota = false
  const transitionCallbacks = new Set()

  function urlWithAuthKey() {
    const key = getApiKey()
    if (!key) return url
    const target = new URL(url, window.location.origin)
    target.searchParams.set('key', key)
    return `${target.pathname}${target.search}`
  }

  function _push(payload) {
    // 首条 = 最新;超过 max 截尾
    events.value = [payload, ...events.value].slice(0, max)
    for (const cb of transitionCallbacks) {
      try {
        cb(payload)
      } catch (e) {
        // 不让一个 callback 阻塞其他订阅者
        console.warn('[useRotateStream] transition callback raised', e)
      }
    }
  }

  function connect() {
    if (source || stoppedByQuota) return
    try {
      source = new EventSource(urlWithAuthKey())
    } catch (e) {
      console.warn('[useRotateStream] EventSource ctor failed', e)
      lastError.value = e
      return
    }
    source.onopen = () => {
      isConnected.value = true
      failureCount = 0
    }
    source.onmessage = (ev) => {
      try {
        const data = JSON.parse(ev.data)
        _push(data)
      } catch (e) {
        console.warn('[useRotateStream] bad SSE payload', ev.data, e)
      }
    }
    source.onerror = (e) => {
      isConnected.value = false
      lastError.value = e
      failureCount += 1
      if (failureCount >= MAX_FAILURES) {
        console.warn(
          `[useRotateStream] giving up after ${MAX_FAILURES} reconnect failures`,
        )
        stoppedByQuota = true
        disconnect()
      }
      // 否则浏览器 EventSource 会自动重连,不要手动 close
    }
  }

  function disconnect() {
    if (source) {
      try {
        source.close()
      } catch (_) { /* noop */ }
      source = null
    }
    isConnected.value = false
  }

  function onTransition(cb) {
    transitionCallbacks.add(cb)
    return () => transitionCallbacks.delete(cb)
  }

  function reset() {
    events.value = []
    failureCount = 0
    stoppedByQuota = false
  }

  if (immediate) {
    onMounted(connect)
    onUnmounted(disconnect)
  }

  return {
    events,
    isConnected,
    lastError,
    connect,
    disconnect,
    reset,
    onTransition,
  }
}
