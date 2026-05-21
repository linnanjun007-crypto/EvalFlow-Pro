<script setup lang="ts">
import { onMounted, ref } from 'vue'
import PageHeader from '../../components/ef/PageHeader.vue'
import { listDownloads, type DownloadRecord } from '../../services/downloads'

const rows = ref<DownloadRecord[]>([])
const loading = ref(false)

function openDownload(url: string) {
  globalThis.open(url, '_blank')
}

async function refresh() {
  loading.value = true
  try {
    rows.value = await listDownloads()
  } finally {
    loading.value = false
  }
}

onMounted(refresh)
</script>

<template>
  <div class="page">
    <PageHeader title="全量下载" description="管理员按用户 / 项目查看和导出 zip 包。">
      <template #actions>
        <el-button @click="refresh" :loading="loading">刷新</el-button>
      </template>
    </PageHeader>

    <section class="ef-card card">
      <el-empty v-if="!rows.length && !loading" description="暂无下载任务" />
      <el-table v-else v-loading="loading" :data="rows" stripe style="width: 100%">
        <el-table-column prop="name" label="任务名称" min-width="200" />
        <el-table-column prop="status" label="状态" width="120">
          <template #default="{ row }">
            <el-tag :type="row.status === '可下载' ? 'success' : 'warning'">
              {{ row.status }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="created" label="创建时间" width="180" />
        <el-table-column prop="size" label="大小" width="100" />
        <el-table-column label="操作" width="120" fixed="right">
          <template #default="{ row }">
            <el-button
              v-if="row.download_url"
              link
              type="primary"
              size="small"
              @click="openDownload(row.download_url)"
            >
              下载
            </el-button>
            <span v-else class="muted">—</span>
          </template>
        </el-table-column>
      </el-table>
    </section>
  </div>
</template>

<style scoped>
.page { display: grid; gap: 12px; }
.card { padding: 14px; }
.muted { color: #94a3b8; font-size: 13px; }
</style>
