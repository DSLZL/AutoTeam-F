# F2+F3: rotate 实时进度 SSE + 切换/刷新交互优化

## Goal

补齐 round-12 父任务 (`05-11-upstream-align-register-multimail-frontend-refresh`) 中 F2+F3 子项:
把 S1 已就绪的 `default_machine.subscribe(callback)` 事件总线接到前端,做出"rotate 实时进度"
SSE 推送 + Bright Theme 浅色面板;同时把 F1 留下的 vue-query 注入升级为
真正的 `useQuery` 调用,让 useStatus 在 SSE 事件触发后立即 invalidate 重拉。

## Scope

### In

1. **后端 SSE 端点** `GET /api/rotate/stream` (FastAPI `StreamingResponse`):
   - 订阅 `default_machine.subscribe(cb)` (S1 commit `ef1637c`)
   - 每次 transition 推一行 `data: {...}\n\n`
   - 心跳 15s `: heartbeat` comment 行
   - 客户端断开时 unsubscribe (try/finally)
2. **前端 composable** `web/src/composables/useRotateStream.js`:
   - EventSource 包装 `/api/rotate/stream`
   - reactive `events` (最近 50 条) + `isConnected` + connect/disconnect
   - onMounted 自动 connect / onUnmounted disconnect
   - 重连失败 5 次后停止
3. **TaskPanel 集成**: rotate 操作按钮附近加"实时进度"折叠面板,显示最近 N 条
   transition,Lucide Activity/Check/AlertTriangle icon。
4. **useStatus.js 精细化**:
   - 新增 `useStatusQuery` 基于 `useQuery`,30s polling + refetchOnWindowFocus
   - SSE 事件 → `queryClient.invalidateQueries(['status'])`
   - 现有 utility 函数(STATUS_LABELS / computeUsability / 时间工具…) 全保留,
     不破坏 21 个组件的现有 import。
5. **F1 follow-up #1**: Settings.vue 硬编码 `bg-gray-(8|9)00` / `bg-slate-(8|9)00` /
   `text-white` 替换为 Bright theme 中性灰阶 (ink-* / surface / hairline)。

### Out (留给后续轮次)
- 不改 manager.py / 不实现预测式 rotate (S5+S6)
- 不实现 multi-workspace (S7)
- 不重写 21 组件全部 vue-query 迁移 — 只动 useStatus(导出复合 query 入口) +
  TaskPanel 集成。

## DoD
- `pytest tests/` 不退化
- `cd web && pnpm build` 无 warning
- `ruff check src/autoteam/api.py` 全绿
- 浏览器实测:`curl /api/rotate/stream` 看到心跳 + mock event 注入后看到 data 行;
  TaskPanel 实时进度面板在浏览器渲染。
- commit: `feat(round-12 F2+F3): rotate progress SSE + refresh polish + settings cleanup`

## Technical Notes
- FastAPI `StreamingResponse` + `media_type="text/event-stream"`
- 用 `queue.SimpleQueue` 把 subscribe 回调里的 transition 中转给 generator(线程安全)
- 心跳用 `queue.get(timeout=15)` 触发 `: heartbeat\n\n`
- 客户端断开:利用 `await request.is_disconnected()` 不通用(generator 是 sync),
  用 try/finally + StopIteration 兜底,FastAPI 关闭 generator 时自动触发
- EventSource 默认浏览器自带重连;手动 close 后 isConnected=false
