<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import PageHeader from '../../components/ef/PageHeader.vue'
import { getDownload, listDownloads, type DownloadRecord } from '../../services/downloads'

const keyword = ref('')
const status = ref<'全部' | '生成中' | '可下载' | '失败'>('全部')
const loading = ref(false)
const rows = ref<DownloadRecord[]>([])
const detail = ref<DownloadRecord | null>(null)
const drawerOpen = ref(false)
const filteredRows = computed(() => rows.value.filter((row) => (!keyword.value || row.file_name.includes(keyword.value)) && (status.value === '全部' || row.status === status.value)))

async function refresh() {
  loading.value = true
  try {
    rows.value = await listDownloads()
  } finally {
    loading.value = false
  }
}

async function download(row: DownloadRecord) {
  detail.value = await getDownload(row.id)
  drawerOpen.value = true
  if (!detail.value.download_url) {
    ElMessage.info('当前任务暂无可用下载链接')
  }
}

async function copyDownloadUrl() {
  if (!detail.value?.download_url) return
  await navigator.clipboard.writeText(detail.value.download_url)
  ElMessage.success('下载链接已复制')
}

function openDownload() {
  if (!detail.value?.download_url) return
  window.open(detail.value.download_url, '_blank', 'noopener,noreferrer')
}

onMounted(refresh)
</script>

<template>
  <div class="page">
    <PageHeader title="导出任务" description="生成中、可下载、失败。" />

    <section class="ef-card filters">
      <el-input v-model="keyword" placeholder="搜索任务名" style="width: 240px" />
      <el-select v-model="status" style="width: 160px">
        <el-option label="全部" value="全部" />
        <el-option label="生成中" value="生成中" />
        <el-option label="可下载" value="可下载" />
        <el-option label="失败" value="失败" />
      </el-select>
      <el-button type="primary" @click="refresh">筛选</el-button>
    </section>

    <section class="ef-card card">
      <el-table v-loading="loading" :data="filteredRows" stripe style="width: 100%">
        <el-table-column prop="file_name" label="任务" min-width="240" />
        <el-table-column prop="status" label="状态" width="120" />
        <el-table-column prop="created_at" label="创建时间" width="180" />
        <el-table-column label="操作" width="180" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" size="small" @click="download(row)">查看详情</el-button>
            <el-button link type="success" size="small">下载</el-button>
          </template>
        </el-table-column>
      </el-table>
    </section>

    <el-drawer v-model="drawerOpen" title="下载详情" size="40%">
      <template v-if="detail">
        <div class="detail-head">
          <div />
          <div class="detail-actions">
            <el-button size="small" @click="copyDownloadUrl" :disabled="!detail.download_url">复制链接</el-button>
            <el-button size="small" type="primary" :disabled="!detail.download_url" @click="openDownload">打开下载</el-button>
          </div>
        </div>
        <el-descriptions :column="1" border>
          <el-descriptions-item label="文件名">{{ detail.file_name }}</el-descriptions-item>
          <el-descriptions-item label="状态">{{ detail.status }}</el-descriptions-item>
          <el-descriptions-item label="创建时间">{{ detail.created_at || '-' }}</el-descriptions-item>
          <el-descriptions-item label="文件 ID">{{ detail.file_id }}</el-descriptions-item>
          <el-descriptions-item label="下载地址">{{ detail.download_url || '暂无' }}</el-descriptions-item>
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
