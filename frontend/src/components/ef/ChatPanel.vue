<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { sendChat, type ChatMessage } from '../../services/chat'

const props = defineProps<{
  projectId: string
  stepCode: string
  stepTitle?: string
  promptHint?: string
  threadId?: string
  workflowState?: Record<string, unknown>
}>()

const emit = defineEmits<{
  uiAction: [payload: { action: 'goto_step' | 'trigger_generate' | 'stop'; step?: number }]
}>()

const input = ref('')
const sending = ref(false)
const messages = ref<ChatMessage[]>([])
const messagesRef = ref<HTMLElement | null>(null)

function welcome(): ChatMessage[] {
  const lines = [
    '你好，我是工作流助手（Hybrid 模式）。',
    props.stepTitle ? `当前步骤：${props.stepTitle}` : '',
    props.promptHint ? `提示：${props.promptHint}` : '',
    '你可以直接说「跳到第3步」「开始生成」「停止」，或者就当前步骤提问。',
  ].filter(Boolean)
  return [{ role: 'assistant', content: lines.join('\n') }]
}

watch(
  () => [props.projectId, props.stepCode],
  () => {
    messages.value = welcome()
    input.value = ''
  },
  { immediate: true },
)

const CN_NUM: Record<string, number> = { 一: 1, 二: 2, 三: 3, 四: 4, 五: 5, 六: 6, 七: 7, 八: 8, 九: 9, 十: 10 }

function parseStepNumber(text: string): number | null {
  const m1 = text.match(/(?:第|step|步骤|第\s*)\s*(\d+)\s*(?:步|step)?/i)
  if (m1) {
    const n = Number(m1[1])
    if (n >= 1 && n <= 14) return n
  }
  const m2 = text.match(/第([一二三四五六七八九十]+)步/)
  if (m2) {
    const raw = m2[1]
    if (raw === '十') return 10
    if (raw.startsWith('十')) return 10 + (CN_NUM[raw.slice(1)] || 0)
    if (raw.endsWith('十')) return (CN_NUM[raw[0]] || 0) * 10
    if (raw.length === 1) return CN_NUM[raw] || null
    if (raw.length === 2 && raw[1] === '十') {
      const n = (CN_NUM[raw[0]] || 0) * 10
      return n >= 1 && n <= 14 ? n : null
    }
  }
  return null
}

function tryLocalIntent(text: string): { handled: boolean; reply?: string } {
  const trimmed = text.trim()
  if (/^(停止|stop|中止|取消生成)$/i.test(trimmed)) {
    emit('uiAction', { action: 'stop' })
    return { handled: true, reply: '好的，已发送停止指令。' }
  }
  if (/^(开始生成|生成|run|执行|跑一下|生成一下)$/i.test(trimmed) || /^(开始)?生成(吧|啊|一下)?$/.test(trimmed)) {
    emit('uiAction', { action: 'trigger_generate' })
    return { handled: true, reply: '好的，已触发本步骤生成。' }
  }
  if (/(跳到|切换到|进入|去|到).*?步/.test(trimmed) || /^step\s*\d+/i.test(trimmed)) {
    const n = parseStepNumber(trimmed)
    if (n) {
      emit('uiAction', { action: 'goto_step', step: n })
      return { handled: true, reply: `好的，正在切换到 Step ${n}。` }
    }
  }
  return { handled: false }
}

async function scrollToBottom() {
  await nextTick()
  const el = messagesRef.value
  if (el) el.scrollTop = el.scrollHeight
}

async function submit() {
  const text = input.value.trim()
  if (!text || sending.value) return

  messages.value.push({ role: 'user', content: text })
  input.value = ''
  await scrollToBottom()

  const localIntent = tryLocalIntent(text)
  if (localIntent.handled) {
    messages.value.push({ role: 'assistant', content: localIntent.reply || '已处理。' })
    await scrollToBottom()
    return
  }

  sending.value = true
  try {
    const res = await sendChat({
      project_id: props.projectId,
      step_code: props.stepCode,
      messages: messages.value.slice(-12),
      user_message: text,
      workflow_state: props.workflowState,
    })
    messages.value.push({ role: 'assistant', content: res.answer || '已收到。' })
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : '对话调用失败'
    ElMessage.error(msg)
    messages.value.push({ role: 'assistant', content: `（错误）${msg}` })
  } finally {
    sending.value = false
    await scrollToBottom()
  }
}

const stepProgressText = computed(() => `${props.stepCode}${props.stepTitle ? ` · ${props.stepTitle}` : ''}`)

function notifyFieldChange(payload: { field: string; value: unknown; label?: string }) {
  const display = typeof payload.value === 'object' ? JSON.stringify(payload.value) : String(payload.value)
  messages.value.push({ role: 'system', content: `[GUI] 用户已将 ${payload.label || payload.field} 设置为：${display}` })
  scrollToBottom()
}

defineExpose({ notifyFieldChange })
</script>

<template>
  <section class="chat-panel">
    <header class="chat-head">
      <div class="head-title">AI 对话 · {{ stepProgressText }}</div>
      <div class="ef-muted head-sub">支持「跳到第N步」「开始生成」「停止」等指令</div>
    </header>

    <div ref="messagesRef" class="messages">
      <div v-for="(msg, i) in messages" :key="i" class="msg" :class="`msg--${msg.role}`">
        <div class="msg-role">{{ msg.role === 'user' ? '你' : msg.role === 'system' ? '系统' : 'AI' }}</div>
        <div class="msg-content">{{ msg.content }}</div>
      </div>
    </div>

    <div class="composer">
      <el-input
        v-model="input"
        type="textarea"
        :rows="2"
        :placeholder="promptHint || '描述你想做的事…'"
        :disabled="sending"
        @keydown.enter.exact.prevent="submit"
      />
      <el-button type="primary" :loading="sending" @click="submit">发送</el-button>
    </div>
  </section>
</template>

<style scoped>
.chat-panel { display: flex; flex-direction: column; height: 100%; min-height: 0; }
.chat-head { padding: 8px 4px 12px; border-bottom: 1px solid var(--el-border-color-lighter); }
.head-title { font-weight: 600; font-size: 14px; }
.head-sub { font-size: 12px; margin-top: 2px; }
.messages { flex: 1; overflow-y: auto; padding: 12px 4px; display: flex; flex-direction: column; gap: 10px; min-height: 0; }
.msg { display: flex; flex-direction: column; gap: 4px; padding: 8px 10px; border-radius: 10px; }
.msg--user { background: var(--el-color-primary-light-9); align-self: flex-end; max-width: 85%; }
.msg--assistant { background: var(--el-bg-color-page); align-self: flex-start; max-width: 90%; }
.msg--system { background: var(--el-fill-color-lighter); align-self: stretch; font-size: 12px; color: var(--el-text-color-secondary); }
.msg-role { font-size: 11px; color: var(--el-text-color-secondary); }
.msg-content { font-size: 13px; white-space: pre-wrap; line-height: 1.5; }
.composer { display: flex; gap: 8px; padding-top: 10px; border-top: 1px solid var(--el-border-color-lighter); }
.composer .el-button { align-self: stretch; }
</style>
