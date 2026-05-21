<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import PageHeader from '../../components/ef/PageHeader.vue'
import { listChangeLogs, listAdminSteps, type ChangeLogRecord } from '../../services/admin'

const logs = ref<ChangeLogRecord[]>([])
const steps = ref<Array<{ code: string; name: string }>>([])
const loading = ref(false)
const filterStep = ref('')
const filterType = ref('')
const searchText = ref('')
const pageSize = ref(20)

const filteredLogs = computed(() => {
  let items = logs.value
  if (searchText.value) {
    const kw = searchText.value.toLowerCase()
    items = items.filter(
      (log) =>
        (log.actor_username || '').toLowerCase().includes(kw) ||
        (log.summary || '').toLowerCase().includes(kw) ||
        (log.action || '').toLowerCase().includes(kw),
    )
  }
  return items.slice(0, pageSize.value)
})

function formatTime(value?: string | null) {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString('zh-CN', { hour12: false })
}

function detailText(log: ChangeLogRecord) {
  if (log.summary) return log.summary
  const after = log.after_data || {}
  return `${log.action} · ${log.target_type}`
}

function tagType(targetType: string) {
  const map: Record<string, string> = {
    prompt: 'warning',
    kb: 'success',
    step_config: 'primary',
  }
  return map[targetType] || 'info'
}

function actionLabel(action: string) {
  const map: Record<string, string> = {
    create: '新增',
    update: '更新',
    delete: '删除',
    activate: '启用',
    publish: '发布',
    save_config: '保存配置',
  }
  return map[action] || action
}

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

watch([filterStep, filterType], () => {
  refresh()
})

onMounted(refresh)
</script>

<template>
  <div class="page">
    <PageHeader
      title="审计日志"
      description="记录管理端 Prompt、知识库与步骤配置的修改操作，包含操作人、时间、变更内容。"
    >
      <template #actions>
        <el-input
          v-model="searchText"
          placeholder="搜索操作人或摘要"
          style="width: 200px"
          clearable
        />
        <el-select
          v-model="filterStep"
          clearable
          placeholder="按步骤筛选"
          style="width: 200px"
        >
          <el-option
            v-for="step in steps"
            :key="step.code"
            :label="`${step.code} ${step.name}`"
            :value="step.code"
          />
        </el-select>
        <el-select
          v-model="filterType"
          clearable
          placeholder="对象类型"
          style="width: 130px"
        >
          <el-option label="Prompt" value="prompt" />
          <el-option label="知识库" value="kb" />
          <el-option label="步骤配置" value="step_config" />
        </el-select>
        <el-button @click="refresh">刷新</el-button>
      </template>
    </PageHeader>

    <section class="ef-card card" v-loading="loading">
      <el-empty v-if="!filteredLogs.length && !loading" description="暂无审计记录" />

      <el-timeline v-else>
        <el-timeline-item
          v-for="log in filteredLogs"
          :key="log.id"
          :timestamp="formatTime(log.created_at)"
          placement="top"
        >
          <el-card shadow="never" class="log-card">
            <div class="log-head">
              <span class="actor">{{ log.actor_username || log.actor_user_id }}</span>
              <el-tag size="small" :type="tagType(log.target_type)">
                {{ log.target_type }}
              </el-tag>
              <el-tag size="small" type="info">{{ actionLabel(log.action) }}</el-tag>
            </div>
            <p class="text">{{ detailText(log) }}</p>
          </el-card>
        </el-timeline-item>
      </el-timeline>

      <div v-if="logs.length > pageSize" class="load-more">
        <el-button text type="primary" @click="pageSize += 20">
          加载更多（已显示 {{ Math.min(pageSize, logs.length) }} / {{ logs.length }}）
        </el-button>
      </div>
    </section>
  </div>
</template>

<style scoped>
.page { display: grid; gap: 12px; }
.card { padding: 16px; }
.log-card { border: 1px solid #f1f5f9; }
.log-head {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  margin-bottom: 8px;
}
.actor {
  font-weight: 600;
  color: #0f172a;
}
.text {
  margin: 0;
  color: #475569;
  line-height: 1.6;
  font-size: 13px;
}
.load-more {
  margin-top: 16px;
  text-align: center;
}
</style>
