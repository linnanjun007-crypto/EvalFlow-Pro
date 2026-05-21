<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import PageHeader from '../../components/ef/PageHeader.vue'
import { deleteFile, listFiles, createFileRecord, type FileRecord } from '../../services/files'

const route = useRoute()
const projectId = computed(() => String(route.params.projectId ?? ''))
const loading = ref(false)
const rows = ref<FileRecord[]>([])

async function refresh() {
  loading.value = true
  try {
    rows.value = await listFiles(projectId.value)
  } finally {
    loading.value = false
  }
}

async function addDemo() {
  await createFileRecord(projectId.value, { file_name: 'demo.xlsx', file_type: 'xlsx', storage_key: 'demo/demo.xlsx' })
  await refresh()
}

async function removeFile(id: string) {
  await deleteFile(projectId.value, id)
  await refresh()
}

watch(projectId, refresh, { immediate: true })
onMounted(refresh)
</script>

<template>
  <div class="page">
    <PageHeader title="文件管理" :description="`项目 ${projectId} 的文件列表与上传记录。`">
      <template #actions>
        <el-button @click="addDemo">模拟新增文件</el-button>
      </template>
    </PageHeader>

    <section class="ef-card card">
      <el-table v-loading="loading" :data="rows" stripe style="width: 100%">
        <el-table-column prop="file_name" label="文件名" min-width="220" />
        <el-table-column prop="file_type" label="类型" width="120" />
        <el-table-column prop="parse_status" label="解析状态" width="120" />
        <el-table-column label="操作" width="120">
          <template #default="{ row }">
            <el-button link type="danger" size="small" @click="removeFile(String(row.id))">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </section>
  </div>
</template>

<style scoped>
.page { display: grid; gap: 12px; }
.card { padding: 14px; }
</style>
