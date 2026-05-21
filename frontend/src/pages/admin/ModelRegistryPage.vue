<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import PageHeader from '../../components/ef/PageHeader.vue'
import { createModel, deleteModel, listModels, toggleModel, type ModelRecord } from '../../services/admin'

const rows = ref<ModelRecord[]>([])
const loading = ref(false)
const dialogOpen = ref(false)
const form = ref({ name: '', model_id: '', base_url: '', api_key: '', supports_vision: false })
const search = ref('')
const filteredRows = computed(() => rows.value.filter((row) => !search.value || row.name.includes(search.value) || row.model_id.includes(search.value)))

async function refresh() {
  loading.value = true
  try {
    rows.value = await listModels()
  } finally {
    loading.value = false
  }
}

async function submit() {
  await createModel(form.value)
  dialogOpen.value = false
  await refresh()
}

async function removeModel(id: string) {
  await deleteModel(id)
  await refresh()
}

async function switchModel(row: Record<string, unknown>) {
  await toggleModel(String(row.id), !Boolean(row.enabled))
  await refresh()
}

onMounted(refresh)
</script>

<template>
  <div class="page">
    <PageHeader title="模型配置" description="平台、Base URL、API Key 脱敏、模型 ID 与启停控制。">
      <template #actions>
        <el-button type="primary" @click="dialogOpen = true">新增模型</el-button>
      </template>
    </PageHeader>
    <section class="ef-card card">
      <el-input v-model="search" placeholder="搜索名称或模型 ID" style="margin-bottom: 12px; max-width: 320px" />
      <el-table v-loading="loading" :data="filteredRows" stripe style="width: 100%">
        <el-table-column prop="name" label="名称" width="140" />
        <el-table-column prop="model_id" label="模型 ID" width="160" />
        <el-table-column prop="base_url" label="Base URL" min-width="200" />
        <el-table-column prop="enabled" label="启用" width="90" />
        <el-table-column label="操作" width="180" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" size="small" @click="switchModel(row)">{{ row.enabled ? '禁用' : '启用' }}</el-button>
            <el-button link type="danger" size="small" @click="removeModel(String(row.id))">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </section>

    <el-dialog v-model="dialogOpen" title="新增模型" width="520px">
      <el-form label-position="top">
        <el-form-item label="名称"><el-input v-model="form.name" /></el-form-item>
        <el-form-item label="模型 ID"><el-input v-model="form.model_id" /></el-form-item>
        <el-form-item label="Base URL"><el-input v-model="form.base_url" /></el-form-item>
        <el-form-item label="API Key"><el-input v-model="form.api_key" /></el-form-item>
        <el-form-item label="视觉能力"><el-switch v-model="form.supports_vision" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogOpen = false">取消</el-button>
        <el-button type="primary" @click="submit">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.page { display: grid; gap: 12px; }
.card { padding: 14px; }
</style>
