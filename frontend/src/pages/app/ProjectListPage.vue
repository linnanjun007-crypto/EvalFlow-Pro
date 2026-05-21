<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import PageHeader from '../../components/ef/PageHeader.vue'
import { listProjects, deleteProject, type ProjectResponse } from '../../services/projects'

const router = useRouter()
const keyword = ref('')
const loading = ref(false)
const rows = ref<ProjectResponse[]>([])
const filteredRows = computed(() => rows.value.filter((r) => !keyword.value || r.name.includes(keyword.value)))

async function refresh() {
  loading.value = true
  try {
    rows.value = await listProjects()
  } catch {
    rows.value = []
  } finally {
    loading.value = false
  }
}

onMounted(refresh)

function openProject(row: ProjectResponse) {
  router.push(`/app/projects/${row.id}/overview`)
}

function openWorkflow(row: ProjectResponse) {
  router.push(`/app/projects/${row.id}/workflow/1`)
}

async function removeProject(row: ProjectResponse) {
  await deleteProject(row.id)
  await refresh()
}
</script>

<template>
  <div class="page-wrap">
    <PageHeader title="项目列表" description="按项目管理 14 步工作流、历史版本与导出任务。">
      <template #actions>
        <el-button class="primary-btn" type="primary" @click="router.push('/app/projects/new')">新建项目</el-button>
      </template>
    </PageHeader>

    <div class="ef-card toolbar-card">
      <div class="toolbar-row">
        <el-input v-model="keyword" class="search" placeholder="搜索项目名称" clearable />
      </div>
    </div>

    <div class="ef-card table-card">
      <el-table v-loading="loading" :data="filteredRows" style="width: 100%">
        <el-table-column prop="name" label="项目名" min-width="260" />
        <el-table-column prop="description" label="简介" min-width="220" />
        <el-table-column prop="status" label="状态" width="110" />
        <el-table-column label="操作" width="260" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" size="small" @click="openProject(row)">总览</el-button>
            <el-button link type="primary" size="small" @click="openWorkflow(row)">继续工作</el-button>
            <el-button link type="danger" size="small" @click="removeProject(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </div>
  </div>
</template>
