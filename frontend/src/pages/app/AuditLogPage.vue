<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import PageHeader from '../../components/ef/PageHeader.vue'
import { listChangeLogs, type ChangeLogRecord } from '../../services/admin'

const logs = ref<ChangeLogRecord[]>([])
const loading = ref(false)
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
  return `${log.action} · ${log.target_type}`
}

function tagType(targetType: string) {
  const map: Record<string, string> = { prompt: 'warning', kb: 'success', step_config: 'primary' }
  return map[targetType] || 'info'
}

function actionLabel(action: string) {
  const map: Record<string, string> = {
    create: '新增', update: '更新', delete: '删除',
    activate: '启用', publish: '发布', save_config: '保存配置',
  }
  return map[action] || action
}

async function refresh() {
  loading.value = true
  try {
    logs.value = await listChangeLogs({
      target_type: filterType.value || undefined,
      limit: 200,
    })
  } finally {
    loading.value = false
  }
}

watch(filterType, () => refresh())
onMounted(refresh)
</script>

<template>
  <div class="page">
    <PageHeader title="审计日志" description="查看登录、生成、导出、删除等关键操作的记录。">
      <template #actions>
        <el-input v-model="searchText" placeholder="搜索操作人或摘要" style="width: 220px" clearable />
        <el-select v-model="filterType" clearable placeholder="对象类型" style="width: 140px">
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
              <el-tag size="small" :type="tagType(log.target_type)">{{ log.target_type }}</el-tag>
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
.log-head { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; margin-bottom: 8px; }
.actor { font-weight: 600; color: #0f172a; }
.text { margin: 0; color: #475569; line-height: 1.6; font-size: 13px; }
.load-more { margin-top: 16px; text-align: center; }
</style>
