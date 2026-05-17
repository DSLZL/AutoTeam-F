<template>
  <div class="mt-6 space-y-6">
    <div class="glass rounded-lg p-4">
      <div class="flex items-center justify-between gap-4 mb-4">
        <div>
          <h2 class="text-lg font-semibold text-ink-950">OAuth 登录</h2>
          <p class="text-sm text-ink-500 mt-1">
            参考 CLIProxyAPI 的手动 OAuth 思路：系统先生成认证链接，你在浏览器中手动完成登录，最后把回调 URL 粘贴回来完成认证。
          </p>
        </div>
        <span
          class="min-w-[72px] px-3 py-1.5 rounded-full text-xs text-center whitespace-nowrap border"
          :class="manualAccountBusy
            ? 'bg-amber-50 text-amber-800 border-amber-200'
            : 'bg-ink-50 text-ink-600 border-hairline'"
        >
          {{ manualAccountBusy ? '进行中' : '空闲' }}
        </span>
      </div>

      <div v-if="message" class="mb-4 px-4 py-3 rounded-lg text-sm border" :class="messageClass">
        {{ message }}
      </div>

      <div
        v-if="manualAccountStatus?.status === 'completed' && manualAccountStatus?.account"
        class="mb-4 px-4 py-3 rounded-lg text-sm border bg-emerald-50 text-emerald-700 border-emerald-200"
      >
        {{ manualAccountStatus.message || `已添加账号 ${manualAccountStatus.account.email}` }}
      </div>

      <div
        v-else-if="manualAccountStatus?.status === 'error' && manualAccountStatus?.error"
        class="mb-4 px-4 py-3 rounded-lg text-sm border bg-rose-50 text-rose-700 border-rose-200"
      >
        {{ manualAccountStatus.error }}
      </div>

      <div v-if="!manualAccountBusy" class="flex flex-wrap gap-3">
        <button
          @click="startManualAccount"
          :disabled="manualSubmitting"
          class="px-4 py-2 bg-indigo-600 hover:bg-indigo-500 text-on-accent text-sm rounded-lg transition disabled:opacity-50 focus-ring"
        >
          {{ manualSubmitting ? '生成中...' : '生成 OAuth 链接' }}
        </button>
      </div>

      <div v-else class="space-y-4">
        <div class="text-sm text-ink-700">
          已生成 OAuth 链接。若当前机器可访问 <span class="font-mono">localhost:1455</span>，系统会自动接收回调；否则请手动粘贴最终回调 URL。
        </div>

        <div
          class="px-4 py-3 rounded-lg text-sm border"
          :class="manualAccountStatus?.auto_callback_available
            ? 'bg-blue-50 text-blue-700 border-blue-200'
            : 'bg-amber-50 text-amber-800 border-amber-200'"
        >
          {{
            manualAccountStatus?.auto_callback_available
              ? '本地自动回调服务已启动：OpenAI 跳回 localhost:1455 后会自动完成认证。'
              : `本地自动回调不可用：${manualAccountStatus?.auto_callback_error || '请改用手动粘贴回调 URL'}`
          }}
        </div>

        <div class="space-y-2">
          <div class="text-xs text-ink-500">OAuth 链接</div>
          <div class="p-3 bg-ink-50 border border-hairline rounded-lg text-xs font-mono break-all text-ink-700">
            {{ manualAccountStatus?.auth_url }}
          </div>
        </div>

        <div class="flex flex-wrap gap-3">
          <a
            :href="manualAccountStatus?.auth_url"
            target="_blank"
            rel="noopener noreferrer"
            class="px-4 py-2 bg-indigo-600 hover:bg-indigo-500 text-on-accent text-sm rounded-lg transition focus-ring"
          >
            打开 OAuth 链接
          </a>
        </div>

        <div
          v-if="manualAccountStatus?.callback_received"
          class="text-xs text-emerald-700"
        >
          已收到{{ manualAccountStatus?.callback_source === 'auto' ? '自动' : '手动' }}回调，刷新轮询中…
        </div>

        <div class="space-y-3">
          <input
            v-model.trim="manualCallbackUrl"
            type="text"
            placeholder="粘贴回调 URL，例如 http://localhost:1455/auth/callback?code=...&state=..."
            :disabled="manualSubmitting"
            class="w-full px-3 py-2 bg-surface border border-hairline rounded-lg text-sm text-ink-950 focus-ring"
          />
          <button
            @click="submitManualCallback"
            :disabled="manualSubmitting || !manualCallbackUrl"
            class="px-4 py-2 bg-indigo-600 hover:bg-indigo-500 text-on-accent text-sm rounded-lg transition disabled:opacity-50 focus-ring"
          >
            {{ manualSubmitting ? '提交中...' : '提交回调 URL' }}
          </button>
        </div>

        <div v-if="manualSubmitting && manualSubmittingHint" class="text-xs text-emerald-700">
          {{ manualSubmittingHint }}
        </div>

        <div class="flex justify-end">
          <button
            @click="cancelManualAccount"
            :disabled="manualSubmitting"
            class="px-4 py-2 bg-surface hover:bg-ink-100 text-sm text-ink-700 rounded-lg border border-hairline transition disabled:opacity-50 focus-ring"
          >
            取消 OAuth 登录
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { api } from '../api.js'

const props = defineProps({
  manualAccountStatus: {
    type: Object,
    default: null,
  },
})

const emit = defineEmits(['refresh', 'progress'])

const manualCallbackUrl = ref('')
const manualSubmitting = ref(false)
const manualSubmittingHint = ref('')
const message = ref('')
const messageClass = ref('')

const manualAccountBusy = computed(() => !!props.manualAccountStatus?.in_progress)

watch(
  () => props.manualAccountStatus,
  (next) => {
    if (!next?.in_progress) {
      manualCallbackUrl.value = ''
      manualSubmittingHint.value = ''
    }
  },
  { immediate: true },
)

function setMessage(text, type = 'success') {
  message.value = text
  messageClass.value = type === 'success'
    ? 'bg-emerald-50 text-emerald-700 border-emerald-200'
    : 'bg-rose-50 text-rose-700 border-rose-200'
  window.clearTimeout(setMessage._timer)
  setMessage._timer = window.setTimeout(() => {
    message.value = ''
  }, 8000)
}

async function startManualAccount() {
  manualSubmitting.value = true
  manualSubmittingHint.value = '正在生成 OAuth 链接...'
  try {
    const result = await api.startManualAccount()
    setMessage(result.auth_url ? 'OAuth 链接已生成，请完成登录后粘贴回调 URL' : '已开始 OAuth 登录流程')
    emit('progress')
  } catch (e) {
    setMessage(e.message, 'error')
  } finally {
    manualSubmitting.value = false
    manualSubmittingHint.value = ''
  }
}

async function submitManualCallback() {
  manualSubmitting.value = true
  manualSubmittingHint.value = '正在提交回调 URL 并交换 token...'
  try {
    const result = await api.submitManualAccountCallback(manualCallbackUrl.value)
    setMessage(result.status === 'completed' ? (result.message || '账号已添加') : '回调 URL 已提交')
    emit('progress')
  } catch (e) {
    setMessage(e.message, 'error')
  } finally {
    manualSubmitting.value = false
    manualSubmittingHint.value = ''
  }
}

async function cancelManualAccount() {
  manualSubmitting.value = true
  try {
    await api.cancelManualAccount()
    manualCallbackUrl.value = ''
    setMessage('OAuth 登录流程已取消')
    emit('refresh')
  } catch (e) {
    setMessage(e.message, 'error')
  } finally {
    manualSubmitting.value = false
  }
}
</script>
