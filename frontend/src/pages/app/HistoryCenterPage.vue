<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import PageHeader from '../../components/ef/PageHeader.vue'
import { getHistory, listHistory, type HistoryRecord } from '../../services/history'

const router = useRouter()
const keyword = ref('')
const step = ref('全部')
const loading = ref(false)
const rows = ref<HistoryRecord[]>([])
const detail = ref<HistoryRecord | null>(null)
const drawerOpen = ref(false)
const filteredRows = computed(() => rows.value.filter((row) => (!keyword.value || row.project.includes(keyword.value) || row.summary.includes(keyword.value)) && (step.value === '全部' || row.step === step.value)))

async function refresh() {
  loading.value = true
  try {
    rows.value = await listHistory({ keyword: keyword.value || undefined })
  } finally {
    loading.value = false
  }
}

async function openDetail(row: HistoryRecord) {
  const result = await getHistory(row.project_id)
  detail.value = 'status' in result && result.status === 'not_found' ? row : (result as HistoryRecord)
  drawerOpen.value = true
}

async function copyContent() {
  if (!detail.value) return
  await navigator.clipboard.writeText(detail.value.content_text || detail.value.summary)
  ElMessage.success('内容已复制')
}

function goWorkflow() {
  if (!detail.value) return
  drawerOpen.value = false
  const match = String(detail.value.step).match(/\d+/)
  const stepNumber = match ? Number(match[0]) : 1
  router.push({ path: `/app/projects/${detail.value.project_id}/workflow/${stepNumber}`, query: { step: String(stepNumber) } })
}

onMounted(refresh)
</script>

<template>
  <div class="page">
    <PageHeader title="历史记录中心" description="按项目、步骤和时间查看历史输出。" />

    <section class="ef-card filters">
      <el-input v-model="keyword" placeholder="搜索项目或摘要" style="width: 240px" />
      <el-select v-model="step" style="width: 140px">
        <el-option label="全部" value="全部" />
        <el-option label="Step1" value="step1" />
        <el-option label="Step2" value="step2" />
        <el-option label="Step3" value="step3" />
      </el-select>
      <el-date-picker type="daterange" range-separator="至" start-placeholder="开始" end-placeholder="结束" />
      <el-button type="primary" @click="refresh">筛选</el-button>
    </section>

    <section class="ef-card card">
      <el-table v-loading="loading" :data="filteredRows" stripe style="width: 100%">
        <el-table-column prop="project" label="项目" min-width="240" />
        <el-table-column prop="step" label="步骤" width="100" />
        <el-table-column prop="summary" label="摘要" />
        <el-table-column label="操作" width="120" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" size="small" @click="openDetail(row)">查看</el-button>
          </template>
        </el-table-column>
      </el-table>
    </section>

    <el-drawer v-model="drawerOpen" title="历史详情" size="40%">
      <template v-if="detail">
        <div class="detail-head">
          <div />
          <div class="detail-actions">
            <el-button size="small" @click="copyContent">复制摘要</el-button>
            <el-button size="small" type="primary" @click="goWorkflow">跳转工作流</el-button>
          </div>
        </div>
        <el-descriptions :column="1" border>
          <el-descriptions-item label="项目">{{ detail.project }}</el-descriptions-item>
          <el-descriptions-item label="步骤">{{ detail.step }}</el-descriptions-item>
          <el-descriptions-item label="标题">{{ detail.title }}</el-descriptions-item>
          <el-descriptions-item label="内容">{{ detail.content_text || detail.summary }}</el-descriptions-item>
          <el-descriptions-item label="时间">{{ detail.time || '-' }}</el-descriptions-item>
        </el-descriptions>
      </template>
    </el-drawer>
  </div>
</template>

<style scoped>
.page { display: grid; gap: 12px; }
.filters { padding: 14px; display: flex; flex-wrap: wrap; gap: 10px; }
.card { padding: 14px; }
.detail-head { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-bottom: 12px; }
.detail-actions { display: flex; gap: 8px; flex-wrap: wrap; }
</style>
