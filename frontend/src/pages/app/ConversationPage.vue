<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import PageHeader from '../../components/ef/PageHeader.vue'
import { createConversation, getConversation, sendConversationMessage, type ConversationMessageRecord } from '../../services/conversations'

const route = useRoute()
const router = useRouter()
const projectId = computed(() => String(route.query.projectId ?? route.params.projectId ?? ''))
const stepCode = computed(() => String(route.query.stepCode ?? route.params.stepCode ?? 'step1'))
const conversationId = ref(String(route.query.conversationId ?? ''))
const loading = ref(false)
const sending = ref(false)
const input = ref('')
const messages = ref<ConversationMessageRecord[]>([])

async function ensureConversation() {
  if (!conversationId.value) {
    const created = await createConversation({ project_id: projectId.value, step_code: stepCode.value })
    conversationId.value = created.id
  }
}

async function loadConversation() {
  loading.value = true
  try {
    await ensureConversation()
    const data = await getConversation(conversationId.value)
    messages.value = data.messages
  } finally {
    loading.value = false
  }
}

async function send() {
  const text = input.value.trim()
  if (!text || sending.value) return
  sending.value = true
  try {
    await ensureConversation()
    const res = await sendConversationMessage(conversationId.value, text)
    messages.value = [...messages.value, { id: crypto.randomUUID(), conversation_id: conversationId.value, role: 'user', content: text }, { id: crypto.randomUUID(), conversation_id: conversationId.value, role: 'assistant', content: res.answer }]
    input.value = ''
  } finally {
    sending.value = false
  }
}

function back() {
  router.back()
}

onMounted(loadConversation)
</script>

<template>
  <div class="page">
    <PageHeader title="AI 对话" description="会话会持久化到数据库，支持多轮恢复。">
      <template #actions>
        <el-button @click="back">返回</el-button>
      </template>
    </PageHeader>

    <section class="ef-card chat-card">
      <div class="meta">项目 {{ projectId }} · 步骤 {{ stepCode }} · 会话 {{ conversationId || '创建中' }}</div>
      <div class="messages">
        <div v-for="msg in messages" :key="msg.id" class="bubble" :class="msg.role">
          <strong>{{ msg.role === 'user' ? '我' : '助手' }}</strong>
          <p>{{ msg.content }}</p>
        </div>
      </div>
      <div class="composer">
        <el-input v-model="input" type="textarea" :rows="4" placeholder="输入你的问题或修改要求" />
        <div class="actions">
          <el-button @click="loadConversation" :loading="loading">刷新会话</el-button>
          <el-button type="primary" :loading="sending" @click="send">发送</el-button>
        </div>
      </div>
    </section>
  </div>
</template>
