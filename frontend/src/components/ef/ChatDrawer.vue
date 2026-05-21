<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { sendChat } from '../../services/chat'
import type { ChatMessage } from '../../services/chat'

const props = defineProps<{
  modelValue: boolean
  projectId: string
  stepCode: string
  stepTitle?: string
  promptHint?: string
  threadId?: string
  workflowState?: Record<string, unknown>
}>()

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  replaceDraft: [payload: { content: string; status: 'human_review' }]
}>()

const open = computed({
  get: () => props.modelValue,
  set: (value: boolean) => emit('update:modelValue', value),
})

const input = ref('')
const sending = ref(false)
const messages = ref<ChatMessage[]>([])
const messagesRef = ref<HTMLElement | null>(null)
const latestAssistantDraft = ref('')
const detailsOpen = ref(true)

const projectName = computed(() => String(props.workflowState?.project_name || props.projectId || '-'))
const activeModelName = computed(() => String(props.workflowState?.active_model_name || props.workflowState?.client_model_name || '-'))
const activeTemperature = computed(() => String(props.workflowState?.active_temperature ?? props.workflowState?.client_model_temperature ?? '-'))
const activeModelCount = computed(() => {
  const configs = props.workflowState?.active_model_configs
  return Array.isArray(configs) ? configs.length : (activeModelName.value === '-' ? 0 : 1)
})
const stepProgressText = computed(() => `${props.stepCode}${props.stepTitle ? ` · ${props.stepTitle}` : ''}`)

function createWelcomeMessage() {
  const lines = [
    '你好，我是工作流助手。你可以直接描述本步骤要生成或修改的内容。',
    props.stepTitle ? `当前步骤：${props.stepTitle}` : '',
    props.promptHint ? `提示：${props.promptHint}` : '',
    props.workflowState?.file_count !== undefined
      ? `当前文件：${props.workflowState.file_count}，图片/PDF：${props.workflowState.media_count ?? 0}，文档：${props.workflowState.document_count ?? 0}`
      : '',
  ].filter(Boolean)
  return [{ role: 'assistant', content: lines.join('\n') }]
}

watch(
  () => [props.projectId, props.stepCode, props.threadId, props.workflowState],
  () => {
    messages.value = createWelcomeMessage()
    input.value = ''
    latestAssistantDraft.value = ''
  },
  { immediate: true },
)

function extractAnswer(result: Record<string, unknown>) {
  const direct = result.answer ?? result.message ?? result.content
  if (typeof direct === 'string' && direct.trim()) return direct
  return '已收到请求，但未返回可展示的文本结果。'
}

function isDuplicateUserMessage(text: string) {
  const last = [...messages.value].reverse().find((item) => item.role === 'user')
  return Boolean(last && last.content.trim() === text.trim())
}

const replaceDraftLabel = computed(() => {
  if (props.stepCode === 'step3') return '替换当前三级指标草案'
  if (props.stepCode === 'step2') return '替换当前核心内容草稿'
  return '替换当前资料清单草稿'
})
const supportsReplaceDraft = computed(() => props.stepCode === 'step1' || props.stepCode === 'step2' || props.stepCode === 'step3')

function replaceCurrentDraft() {
  const content = latestAssistantDraft.value.trim()
  if (!content) {
    ElMessage.warning(props.stepCode === 'step2' ? '当前没有可替换的 AI 生成核心内容' : '当前没有可替换的 AI 生成资料清单')
    return
  }
  emit('replaceDraft', { content, status: 'human_review' })
  ElMessage.success('已用 AI 对话结果替换成品区草稿，请继续人工确认或修改')
}

async function scrollToBottom() {
  await nextTick()
  const el = messagesRef.value
  if (!el) return
  el.scrollTop = el.scrollHeight
}

async function submit() {
  const text = input.value.trim()
  if (!text || sending.value) return
  if (isDuplicateUserMessage(text)) {
    ElMessage.warning('与上一条用户消息重复，已忽略本次发送')
    return
  }

  const pendingMessage = { role: 'assistant', content: '正在处理中，请稍候…' } as ChatMessage
  const nextMessages = [...messages.value, { role: 'user', content: text } as ChatMessage]
  messages.value = [...nextMessages, pendingMessage]
  input.value = ''
  sending.value = true
  await scrollToBottom()

  try {
    const res = await sendChat({
      project_id: props.projectId,
      step_code: props.stepCode,
      user_message: text,
      messages: nextMessages,
      workflow_role: 'user',
      workflow_state: {
        ...(props.workflowState ?? {}),
        project_id: props.projectId,
        step_code: props.stepCode,
        thread_id: props.threadId,
        step_title: props.stepTitle,
        prompt_hint: props.promptHint,
        latest_user_message: text,
      },
    })

    const answer = extractAnswer(res as unknown as Record<string, unknown>)
    latestAssistantDraft.value = answer
    messages.value = [...nextMessages, { role: 'assistant', content: answer }]
    await scrollToBottom()
  } catch (error) {
    const errorText = error instanceof Error ? error.message : '发送失败，请稍后重试'
    ElMessage.error(errorText)
    messages.value = [...nextMessages, { role: 'assistant', content: `请求失败：${errorText}` }]
    await scrollToBottom()
  } finally {
    sending.value = false
  }
}
</script>

<template>
  <el-drawer v-model="open" title="AI 对话" size="46%" :destroy-on-close="false" class="ai-chat-drawer">
    <div class="chat-shell">
      <header class="chat-context-bar">
        <div class="context-main">
          <div class="context-title">{{ projectName }}</div>
          <div class="context-subtitle">正在进行：{{ stepProgressText }}</div>
        </div>
        <el-button size="small" text @click="detailsOpen = !detailsOpen">
          {{ detailsOpen ? '收起配置' : '查看配置' }}
        </el-button>
      </header>

      <section v-if="detailsOpen" class="context-panel">
        <div class="context-card">
          <span class="context-label">项目 ID</span>
          <strong>{{ projectId }}</strong>
        </div>
        <div class="context-card">
          <span class="context-label">当前 Step</span>
          <strong>{{ stepCode }}</strong>
        </div>
        <div class="context-card">
          <span class="context-label">生效模型</span>
          <strong>{{ activeModelName }}</strong>
        </div>
        <div class="context-card">
          <span class="context-label">模型数量 / 温度</span>
          <strong>{{ activeModelCount }} / {{ activeTemperature }}</strong>
        </div>
        <div class="context-card">
          <span class="context-label">文件</span>
          <strong>{{ workflowState?.file_count ?? 0 }} 份</strong>
        </div>
        <div class="context-card">
          <span class="context-label">图片/PDF · 文档</span>
          <strong>{{ workflowState?.media_count ?? 0 }} · {{ workflowState?.document_count ?? 0 }}</strong>
        </div>
        <div class="context-card">
          <span class="context-label">Step1 草稿</span>
          <strong>{{ workflowState?.has_step1_draft ? '已存在' : '无' }}</strong>
        </div>
        <div class="context-card">
          <span class="context-label">线程</span>
          <strong>{{ threadId || '-' }}</strong>
        </div>
      </section>

      <main ref="messagesRef" class="messages">
        <div v-for="(msg, idx) in messages" :key="idx" class="message-row" :class="msg.role">
          <div class="avatar">{{ msg.role === 'user' ? '我' : 'AI' }}</div>
          <div class="message-content">
            <div class="message-meta">{{ msg.role === 'user' ? '你' : '工作流助手' }}</div>
            <div class="bubble">{{ msg.content }}</div>
          </div>
        </div>
      </main>

      <footer class="composer">
        <div v-if="promptHint" class="hint-line">{{ promptHint }}</div>
        <el-input
          v-model="input"
          type="textarea"
          :rows="4"
          resize="none"
          placeholder="输入你的问题、修改要求或生成指令"
          @keydown.ctrl.enter.prevent="submit"
          @keydown.meta.enter.prevent="submit"
        />
        <div class="actions">
          <span class="send-tip">Ctrl / ⌘ + Enter 发送</span>
          <div class="action-buttons">
            <el-button @click="open = false">关闭</el-button>
            <el-button
              v-if="supportsReplaceDraft"
              type="success"
              plain
              :disabled="!latestAssistantDraft.trim() || sending"
              @click="replaceCurrentDraft"
            >
              {{ replaceDraftLabel }}
            </el-button>
            <el-button type="primary" :loading="sending" @click="submit">发送</el-button>
          </div>
        </div>
      </footer>
    </div>
  </el-drawer>
</template>

<style scoped>
:deep(.ai-chat-drawer .el-drawer__body) { padding: 0; }
.chat-shell { height: 100%; display: grid; grid-template-rows: auto auto minmax(0, 1fr) auto; background: var(--el-bg-color-page); }
.chat-context-bar { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 16px 20px; background: var(--el-bg-color); border-bottom: 1px solid var(--el-border-color-lighter); }
.context-title { font-weight: 700; color: var(--el-text-color-primary); font-size: 15px; }
.context-subtitle { color: var(--el-text-color-secondary); font-size: 12px; margin-top: 4px; }
.context-panel { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 10px; padding: 12px 20px; background: var(--el-fill-color-blank); border-bottom: 1px solid var(--el-border-color-lighter); }
.context-card { border: 1px solid var(--el-border-color-lighter); border-radius: 12px; padding: 10px 12px; background: var(--el-bg-color); min-width: 0; }
.context-label { display: block; font-size: 11px; color: var(--el-text-color-secondary); margin-bottom: 5px; }
.context-card strong { display: block; font-size: 13px; color: var(--el-text-color-primary); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.messages { overflow: auto; padding: 18px 20px; display: flex; flex-direction: column; gap: 16px; }
.message-row { display: flex; gap: 10px; align-items: flex-start; }
.message-row.user { flex-direction: row-reverse; }
.avatar { width: 34px; height: 34px; flex: 0 0 34px; border-radius: 50%; display: grid; place-items: center; font-size: 12px; font-weight: 700; background: var(--el-fill-color-dark); color: var(--el-text-color-regular); }
.message-row.user .avatar { background: var(--el-color-primary); color: #fff; }
.message-content { max-width: min(760px, 78%); display: grid; gap: 4px; }
.message-row.user .message-content { justify-items: end; }
.message-meta { font-size: 11px; color: var(--el-text-color-secondary); }
.bubble { white-space: pre-wrap; word-break: break-word; line-height: 1.65; border-radius: 16px; padding: 12px 14px; background: var(--el-bg-color); color: var(--el-text-color-primary); border: 1px solid var(--el-border-color-lighter); box-shadow: 0 6px 18px rgba(15, 23, 42, 0.04); }
.message-row.user .bubble { background: var(--el-color-primary); color: #fff; border-color: var(--el-color-primary); }
.composer { padding: 14px 20px 18px; background: var(--el-bg-color); border-top: 1px solid var(--el-border-color-lighter); display: grid; gap: 10px; }
.hint-line { color: var(--el-text-color-secondary); background: var(--el-fill-color-light); border-radius: 10px; padding: 8px 10px; font-size: 12px; }
.actions { display: flex; justify-content: space-between; align-items: center; gap: 12px; }
.action-buttons { display: flex; justify-content: flex-end; gap: 8px; flex-wrap: wrap; }
.send-tip { font-size: 12px; color: var(--el-text-color-secondary); }
@media (max-width: 1100px) { .context-panel { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
@media (max-width: 700px) { .context-panel { grid-template-columns: 1fr; } .message-content { max-width: 86%; } .actions { align-items: flex-start; flex-direction: column; } }
</style>
