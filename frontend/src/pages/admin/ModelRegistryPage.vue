<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import PageHeader from '../../components/ef/PageHeader.vue'
import { createModel, deleteModel, listModels, setDefaultModel, toggleModel, updateModel, type ModelRecord } from '../../services/admin'

const rows = ref<ModelRecord[]>([])
const loading = ref(false)
const dialogOpen = ref(false)
const editMode = ref<'create' | 'edit'>('create')
const editingId = ref('')
const editKeyPreview = ref('')
const form = ref({ name: '', model_id: '', base_url: '', api_key: '', supports_vision: false, kind: 'chat' as 'chat' | 'embedding' | 'rerank', dimensions: 1536 })
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
  const payload: Record<string, unknown> = { ...form.value }
  if (form.value.kind !== 'embedding') {
    delete payload.dimensions
  }
  if (editMode.value === 'edit') {
    if (!payload.api_key) delete payload.api_key
    await updateModel(editingId.value, payload)
  } else {
    await createModel(payload)
  }
  dialogOpen.value = false
  form.value = { name: '', model_id: '', base_url: '', api_key: '', supports_vision: false, kind: 'chat', dimensions: 1536 }
  await refresh()
}

function openCreate() {
  editMode.value = 'create'
  editingId.value = ''
  editKeyPreview.value = ''
  form.value = { name: '', model_id: '', base_url: '', api_key: '', supports_vision: false, kind: 'chat', dimensions: 1536 }
  dialogOpen.value = true
}

function openEdit(row: ModelRecord) {
  editMode.value = 'edit'
  editingId.value = row.id
  editKeyPreview.value = row.api_key_preview || ''
  form.value = {
    name: row.name,
    model_id: row.model_id,
    base_url: row.base_url || '',
    api_key: '',
    supports_vision: row.supports_vision,
    kind: row.kind || 'chat',
    dimensions: row.dimensions || 1536,
  }
  dialogOpen.value = true
}

async function removeModel(id: string) {
  await deleteModel(id)
  await refresh()
}

async function switchModel(row: Record<string, unknown>) {
  await toggleModel(String(row.id), !Boolean(row.enabled))
  await refresh()
}

async function makeDefault(id: string) {
  await setDefaultModel(id)
  await refresh()
}

onMounted(refresh)
</script>

<template>
  <div class="page">
    <PageHeader title="模型配置" description="平台、Base URL、API Key 脱敏、模型 ID 与启停控制。">
      <template #actions>
        <el-button type="primary" @click="openCreate">新增模型</el-button>
      </template>
    </PageHeader>
    <section class="ef-card card">
      <el-input v-model="search" placeholder="搜索名称或模型 ID" style="margin-bottom: 12px; max-width: 320px" />
      <el-table v-loading="loading" :data="filteredRows" stripe style="width: 100%">
        <el-table-column prop="name" label="名称" width="140" />
        <el-table-column prop="model_id" label="模型 ID" width="160" />
        <el-table-column prop="kind" label="类型" width="100">
          <template #default="{ row }">
            <el-tag :type="row.kind === 'rerank' ? 'success' : row.kind === 'embedding' ? 'warning' : ''" size="small">{{ row.kind === 'rerank' ? 'Rerank' : row.kind === 'embedding' ? 'Embedding' : 'Chat' }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="base_url" label="Base URL" min-width="200" />
        <el-table-column label="API Key" width="140">
          <template #default="{ row }">
            <span v-if="row.api_key_preview" style="font-family: monospace; font-size: 12px">{{ row.api_key_preview }}</span>
            <span v-else style="color: var(--el-text-color-placeholder)">未配置</span>
          </template>
        </el-table-column>
        <el-table-column prop="enabled" label="启用" width="90" />
        <el-table-column label="默认" width="80">
          <template #default="{ row }">
            <el-tag v-if="row.is_default" type="success" size="small">默认</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="280" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" size="small" @click="openEdit(row)">编辑</el-button>
            <el-button link type="primary" size="small" @click="switchModel(row)">{{ row.enabled ? '禁用' : '启用' }}</el-button>
            <el-button v-if="!row.is_default" link type="success" size="small" @click="makeDefault(String(row.id))">设为默认</el-button>
            <el-button link type="danger" size="small" @click="removeModel(String(row.id))">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </section>

    <el-dialog v-model="dialogOpen" :title="editMode === 'edit' ? '编辑模型' : '新增模型'" width="520px">
      <el-form label-position="top">
        <el-form-item label="类型">
          <el-radio-group v-model="form.kind" :disabled="editMode === 'edit'">
            <el-radio value="chat">Chat（对话模型）</el-radio>
            <el-radio value="embedding">Embedding（向量模型）</el-radio>
            <el-radio value="rerank">Rerank（重排模型）</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="名称"><el-input v-model="form.name" /></el-form-item>
        <el-form-item label="模型 ID"><el-input v-model="form.model_id" /></el-form-item>
        <el-form-item label="Base URL"><el-input v-model="form.base_url" /></el-form-item>
        <el-form-item :label="editMode === 'edit' ? 'API Key（留空保持不变）' : 'API Key'">
          <el-input
            v-model="form.api_key"
            type="password"
            show-password
            :placeholder="editMode === 'edit' && editKeyPreview ? `当前：${editKeyPreview}（留空不修改）` : '请输入 API Key'"
          />
        </el-form-item>
        <el-form-item v-if="form.kind === 'chat'" label="视觉能力"><el-switch v-model="form.supports_vision" /></el-form-item>
        <el-form-item v-if="form.kind === 'embedding'" label="向量维度">
          <el-input-number v-model="form.dimensions" :min="128" :max="4096" :step="128" />
        </el-form-item>
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
