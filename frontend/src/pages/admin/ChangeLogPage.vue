<script setup lang="ts">
import { onMounted, ref } from 'vue'
import PageHeader from '../../components/ef/PageHeader.vue'
import { listChangeLogs, listAdminSteps, type ChangeLogRecord } from '../../services/admin'

const logs = ref<ChangeLogRecord[]>([])
const steps = ref<Array<{ code: string; name: string }>>([])
const loading = ref(false)
const filterStep = ref('')
const filterType = ref('')

async function refresh() {
  loading.value = true
  try {
    const [logItems, stepItems] = await Promise.all([
      listChangeLogs({
        step_code: filterStep.value || undefined,
        target_type: filterType.value || undefined,
        limit: 200,
      }),
      listAdminSteps(),
    ])
    logs.value = logItems
    steps.value = stepItems.map((item) => ({ code: item.code, name: item.name }))
  } finally {
    loading.value = false
  }
}

function formatTime(value?: string | null) {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString('zh-CN', { hour12: false })
}

function detailText(log: ChangeLogRecord) {
  const after = log.after_data || {}
  const changes = (after.changes as Array<Record<string, unknown>> | undefined) || []
  if (changes.length) {
    return changes.map((item) => String(item.summary || '')).filter(Boolean).join('；')
  }
  return log.summary || `${log.action} · ${log.target_type}`
}

onMounted(refresh)
</script>

<template>
  <div class="page">
    <PageHeader title="变更日志" description="记录管理端 Prompt、知识库与步骤配置的修改：谁改的、什么时候改的、改了什么。客户端不可查看系统内置详细内容。">
      <template #actions>
        <el-select v-model="filterStep" clearable placeholder="按步骤筛选" style="width: 220px" @change="refresh">
          <el-option v-for="step in steps" :key="step.code" :label="`${step.code} ${step.name}`" :value="step.code" />
        </el-select>
        <el-select v-model="filterType" clearable placeholder="对象类型" style="width: 140px" @change="refresh">
          <el-option label="Prompt" value="prompt" />
          <el-option label="知识库" value="kb" />
          <el-option label="步骤配置" value="step_config" />
        </el-select>
        <el-button @click="refresh">刷新</el-button>
      </template>
    </PageHeader>

    <section class="ef-card card" v-loading="loading">
      <el-empty v-if="!logs.length" description="暂无变更记录" />
      <el-timeline v-else>
        <el-timeline-item
          v-for="log in logs"
          :key="log.id"
          :timestamp="formatTime(log.created_at)"
          placement="top"
        >
          <el-card shadow="never" class="log-card">
            <div class="log-head">
              <strong>{{ log.actor_username || log.actor_user_id }}</strong>
              <el-tag size="small" type="warning">{{ log.target_type }}</el-tag>
              <el-tag size="small">{{ log.action }}</el-tag>
            </div>
            <p class="text">{{ detailText(log) }}</p>
          </el-card>
        </el-timeline-item>
      </el-timeline>
    </section>
  </div>
</template>

<style scoped>
.page { display: grid; gap: 12px; }
.card { padding: 14px; }
.log-card { border: 1px solid #f1f5f9; }
.log-head { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; margin-bottom: 8px; }
.text { margin: 0; color: #475569; line-height: 1.6; }
</style>
