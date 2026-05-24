<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  createKb,
  deleteKb,
  deleteKbDocument,
  getKb,
  listKbDocuments,
  listKbs,
  migrateKbDocument,
  promoteProjectFileToKb,
  reindexKbDocument,
  searchKb,
  updateKb,
  uploadKbDocument,
  type KbDocument,
  type KbSearchResult,
  type UserKb,
} from '../../services/kbs'
import { listProjects, type ProjectResponse } from '../../services/projects'
import { listFiles, type FileRecord } from '../../services/files'

const router = useRouter()

const kbs = ref<UserKb[]>([])
const selectedKbId = ref<string | null>(null)
const selectedKb = ref<UserKb | null>(null)
const docs = ref<KbDocument[]>([])
const loading = ref(false)
const docsLoading = ref(false)

const editDialog = ref(false)
const editMode = ref<'create' | 'edit'>('create')
const editForm = ref({ id: '', name: '', description: '' })
const saving = ref(false)

const uploadInput = ref<HTMLInputElement | null>(null)
const uploading = ref(false)

const searchQuery = ref('')
const searchTopK = ref(5)
const searchResults = ref<KbSearchResult[]>([])
const searching = ref(false)

// 从项目导入
const importDialog = ref(false)
const projectsForImport = ref<ProjectResponse[]>([])
const selectedProjectId = ref('')
const projectFiles = ref<FileRecord[]>([])
const selectedFileIds = ref<string[]>([])
const importing = ref(false)
const loadingProjects = ref(false)
const loadingProjectFiles = ref(false)

// 文档迁移弹窗
const migrateDialog = ref(false)
const migrateDoc = ref<KbDocument | null>(null)
const migrateForm = ref({ targetKbId: '', mode: 'move' as 'move' | 'copy' })
const migrating = ref(false)

let pollTimer: ReturnType<typeof setInterval> | null = null

const hasPending = computed(() =>
  docs.value.some((d) => d.status === 'pending' || d.status === 'processing'),
)

async function loadKbs() {
  loading.value = true
  try {
    kbs.value = await listKbs()
    if (!selectedKbId.value && kbs.value.length) {
      selectKb(kbs.value[0].id)
    } else if (selectedKbId.value && !kbs.value.some((k) => k.id === selectedKbId.value)) {
      selectedKbId.value = kbs.value[0]?.id ?? null
      if (selectedKbId.value) selectKb(selectedKbId.value)
      else {
        selectedKb.value = null
        docs.value = []
      }
    }
  } catch (e: any) {
    ElMessage.error(e.message || '加载知识库失败')
  } finally {
    loading.value = false
  }
}

async function selectKb(kbId: string) {
  selectedKbId.value = kbId
  await Promise.all([loadKbDetail(kbId), loadDocs(kbId)])
}

async function loadKbDetail(kbId: string) {
  try {
    selectedKb.value = await getKb(kbId)
  } catch (e: any) {
    ElMessage.error(e.message || '加载知识库详情失败')
  }
}

async function loadDocs(kbId: string) {
  docsLoading.value = true
  try {
    docs.value = await listKbDocuments(kbId)
  } catch (e: any) {
    ElMessage.error(e.message || '加载文档失败')
  } finally {
    docsLoading.value = false
  }
}

function openCreate() {
  editMode.value = 'create'
  editForm.value = { id: '', name: '', description: '' }
  editDialog.value = true
}

function openEdit(kb: UserKb) {
  editMode.value = 'edit'
  editForm.value = { id: kb.id, name: kb.name, description: kb.description ?? '' }
  editDialog.value = true
}

async function submitEdit() {
  if (!editForm.value.name.trim()) {
    ElMessage.warning('请输入名称')
    return
  }
  saving.value = true
  try {
    if (editMode.value === 'create') {
      const kb = await createKb(editForm.value.name.trim(), editForm.value.description.trim())
      ElMessage.success('已创建')
      await loadKbs()
      selectedKbId.value = kb.id
      await selectKb(kb.id)
    } else {
      await updateKb(editForm.value.id, {
        name: editForm.value.name.trim(),
        description: editForm.value.description.trim(),
      })
      ElMessage.success('已保存')
      await loadKbs()
      if (selectedKbId.value === editForm.value.id) await loadKbDetail(editForm.value.id)
    }
    editDialog.value = false
  } catch (e: any) {
    ElMessage.error(e.message || '保存失败')
  } finally {
    saving.value = false
  }
}

async function confirmDelete(kb: UserKb) {
  try {
    await ElMessageBox.confirm(
      `确认删除知识库「${kb.name}」？此操作会删除其所有文档与索引。`,
      '删除确认',
      { type: 'warning' },
    )
  } catch {
    return
  }
  try {
    await deleteKb(kb.id)
    ElMessage.success('已删除')
    if (selectedKbId.value === kb.id) {
      selectedKbId.value = null
      selectedKb.value = null
      docs.value = []
    }
    await loadKbs()
  } catch (e: any) {
    ElMessage.error(e.message || '删除失败')
  }
}

function triggerUpload() {
  uploadInput.value?.click()
}

async function onFileChange(event: Event) {
  const target = event.target as HTMLInputElement
  if (!target.files?.length || !selectedKbId.value) return
  const files = Array.from(target.files)
  uploading.value = true
  try {
    for (const file of files) {
      await uploadKbDocument(selectedKbId.value, file)
    }
    ElMessage.success(`已上传 ${files.length} 个文件，正在后台索引`)
    await loadDocs(selectedKbId.value)
  } catch (e: any) {
    ElMessage.error(e.message || '上传失败')
  } finally {
    uploading.value = false
    target.value = ''
  }
}

async function onReindex(doc: KbDocument) {
  if (!selectedKbId.value) return
  try {
    await reindexKbDocument(selectedKbId.value, doc.id)
    ElMessage.success('已加入重建队列')
    await loadDocs(selectedKbId.value)
  } catch (e: any) {
    ElMessage.error(e.message || '重建失败')
  }
}

async function onDeleteDoc(doc: KbDocument) {
  if (!selectedKbId.value) return
  try {
    await ElMessageBox.confirm(`确认删除文档「${doc.file_name}」？`, '删除确认', { type: 'warning' })
  } catch {
    return
  }
  try {
    await deleteKbDocument(selectedKbId.value, doc.id)
    ElMessage.success('已删除')
    await loadDocs(selectedKbId.value)
    if (selectedKbId.value) await loadKbDetail(selectedKbId.value)
  } catch (e: any) {
    ElMessage.error(e.message || '删除失败')
  }
}

async function runSearch() {
  if (!selectedKbId.value || !searchQuery.value.trim()) {
    ElMessage.warning('请输入查询内容')
    return
  }
  searching.value = true
  try {
    const result = await searchKb(selectedKbId.value, searchQuery.value.trim(), searchTopK.value)
    searchResults.value = result.items
    if (!result.items.length) ElMessage.info('未召回任何片段')
  } catch (e: any) {
    ElMessage.error(e.message || '检索失败')
  } finally {
    searching.value = false
  }
}

async function openImportDialog() {
  importDialog.value = true
  selectedProjectId.value = ''
  projectFiles.value = []
  selectedFileIds.value = []
  loadingProjects.value = true
  try {
    projectsForImport.value = await listProjects()
  } catch (e: any) {
    ElMessage.error(e.message || '加载项目列表失败')
  } finally {
    loadingProjects.value = false
  }
}

async function onProjectSelect(projectId: string) {
  selectedProjectId.value = projectId
  selectedFileIds.value = []
  loadingProjectFiles.value = true
  try {
    projectFiles.value = await listFiles(projectId)
  } catch (e: any) {
    ElMessage.error(e.message || '加载文件列表失败')
  } finally {
    loadingProjectFiles.value = false
  }
}

async function doImportFiles() {
  if (!selectedKbId.value || !selectedFileIds.value.length) return
  importing.value = true
  try {
    for (const fileId of selectedFileIds.value) {
      await promoteProjectFileToKb(selectedKbId.value, fileId)
    }
    ElMessage.success(`已导入 ${selectedFileIds.value.length} 个文件，正在后台索引`)
    importDialog.value = false
    await loadDocs(selectedKbId.value)
  } catch (e: any) {
    ElMessage.error(e.message || '导入失败')
  } finally {
    importing.value = false
  }
}

function statusType(status: string) {
  return (
    {
      indexed: 'success',
      processing: 'warning',
      pending: 'info',
      failed: 'danger',
    }[status] ?? 'info'
  )
}

function statusLabel(status: string) {
  return (
    { indexed: '已索引', processing: '索引中', pending: '待处理', failed: '失败' }[status] ?? status
  )
}

function formatSize(bytes: number | null | undefined) {
  if (!bytes) return '—'
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1024 / 1024).toFixed(2)} MB`
}

function formatTime(value?: string | null) {
  if (!value) return '—'
  const d = new Date(value)
  if (Number.isNaN(d.getTime())) return value
  return d.toLocaleString('zh-CN', { hour12: false })
}

function openDocDetail(doc: KbDocument) {
  if (!selectedKbId.value) return
  router.push({
    name: 'kb-doc-detail',
    params: { kbId: selectedKbId.value, docId: doc.id },
  })
}

function openMigrate(doc: KbDocument) {
  migrateDoc.value = doc
  migrateForm.value = { targetKbId: '', mode: 'move' }
  migrateDialog.value = true
}

async function submitMigrate() {
  if (!selectedKbId.value || !migrateDoc.value) return
  if (!migrateForm.value.targetKbId) {
    ElMessage.warning('请选择目标知识库')
    return
  }
  migrating.value = true
  try {
    await migrateKbDocument(selectedKbId.value, migrateDoc.value.id, {
      target_kb_id: migrateForm.value.targetKbId,
      mode: migrateForm.value.mode,
    })
    ElMessage.success(migrateForm.value.mode === 'move' ? '已迁移' : '已复制')
    migrateDialog.value = false
    await loadDocs(selectedKbId.value)
    await loadKbDetail(selectedKbId.value)
  } catch (e: any) {
    ElMessage.error(e.message || '迁移失败')
  } finally {
    migrating.value = false
  }
}

const migrateTargetOptions = computed(() => kbs.value.filter((kb) => kb.id !== selectedKbId.value))

watch(hasPending, (v) => {
  if (v && !pollTimer) {
    pollTimer = setInterval(() => {
      if (selectedKbId.value) loadDocs(selectedKbId.value)
    }, 3000)
  }
  if (!v && pollTimer) {
    clearInterval(pollTimer)
    pollTimer = null
  }
})

onMounted(loadKbs)
onUnmounted(() => {
  if (pollTimer) clearInterval(pollTimer)
})
</script>

<template>
  <div class="kb-page">
    <div class="kb-sidebar">
      <div class="sidebar-header">
        <h3>知识库</h3>
        <el-button type="primary" size="small" @click="openCreate">新建</el-button>
      </div>
      <div v-loading="loading" class="kb-list">
        <div
          v-for="kb in kbs"
          :key="kb.id"
          class="kb-card"
          :class="{ active: selectedKbId === kb.id }"
          @click="selectKb(kb.id)"
        >
          <div class="kb-card-name">{{ kb.name }}</div>
          <div class="kb-card-meta">{{ formatTime(kb.updated_at) }}</div>
          <div class="kb-card-actions">
            <el-button link size="small" @click.stop="openEdit(kb)">编辑</el-button>
            <el-button link size="small" type="danger" @click.stop="confirmDelete(kb)">删除</el-button>
          </div>
        </div>
        <el-empty v-if="!loading && !kbs.length" description="暂无知识库" :image-size="60" />
      </div>
    </div>

    <div class="kb-main">
      <template v-if="selectedKb">
        <div class="main-header">
          <h2>{{ selectedKb.name }}</h2>
          <p v-if="selectedKb.description" class="desc">{{ selectedKb.description }}</p>
          <div class="stats">
            <el-tag size="small" type="info">文档 {{ selectedKb.doc_count ?? 0 }}</el-tag>
            <el-tag size="small" type="info">片段 {{ selectedKb.chunk_count ?? 0 }}</el-tag>
            <el-tag size="small">维度 {{ selectedKb.embedding_dim }}</el-tag>
          </div>
        </div>

        <el-divider />

        <div class="section-header">
          <h4>文档列表</h4>
          <div>
            <el-button type="primary" size="small" :loading="uploading" @click="triggerUpload">上传文件</el-button>
            <el-button size="small" @click="openImportDialog">从项目导入</el-button>
            <input
              ref="uploadInput"
              type="file"
              multiple
              accept=".pdf,.docx,.doc,.xlsx,.xls,.md,.txt,.csv"
              style="display: none"
              @change="onFileChange"
            />
          </div>
        </div>

        <el-table v-loading="docsLoading" :data="docs" stripe size="small" style="width: 100%">
          <el-table-column prop="file_name" label="文件名" min-width="180" show-overflow-tooltip />
          <el-table-column prop="file_type" label="类型" width="70" />
          <el-table-column label="大小" width="90">
            <template #default="{ row }">{{ formatSize(row.file_size) }}</template>
          </el-table-column>
          <el-table-column label="状态" width="90">
            <template #default="{ row }">
              <el-tag :type="statusType(row.status)" size="small">{{ statusLabel(row.status) }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="chunk_count" label="片段" width="70" />
          <el-table-column label="索引时间" width="160">
            <template #default="{ row }">{{ formatTime(row.indexed_at) }}</template>
          </el-table-column>
          <el-table-column label="操作" width="240" fixed="right">
            <template #default="{ row }">
              <el-button link size="small" type="primary" @click="openDocDetail(row)">详情</el-button>
              <el-button link size="small" @click="openMigrate(row)">迁移</el-button>
              <el-button link size="small" @click="onReindex(row)">重建</el-button>
              <el-button link size="small" type="danger" @click="onDeleteDoc(row)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>

        <el-divider />

        <div class="section-header">
          <h4>测试检索</h4>
        </div>
        <div class="search-bar">
          <el-input v-model="searchQuery" placeholder="输入查询内容..." clearable @keydown.enter="runSearch" />
          <el-input-number v-model="searchTopK" :min="1" :max="20" size="small" style="width: 100px" />
          <el-button type="primary" :loading="searching" @click="runSearch">检索</el-button>
        </div>
        <div v-if="searchResults.length" class="search-results">
          <div v-for="(item, idx) in searchResults" :key="item.id" class="result-card">
            <div class="result-header">
              <span class="result-idx">[{{ idx + 1 }}]</span>
              <span class="result-file">{{ item.file_name }} · 第{{ item.chunk_index }}段</span>
              <span class="result-score">{{ item.score.toFixed(4) }}</span>
            </div>
            <div class="result-content">{{ item.content }}</div>
          </div>
        </div>
      </template>
      <el-empty v-else description="请选择或新建一个知识库" :image-size="100" />
    </div>

    <el-dialog
      v-model="editDialog"
      :title="editMode === 'create' ? '新建知识库' : '编辑知识库'"
      width="420px"
    >
      <el-form label-width="80px">
        <el-form-item label="名称">
          <el-input v-model="editForm.name" placeholder="知识库名称" maxlength="100" />
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="editForm.description" type="textarea" :rows="3" placeholder="可选描述" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="editDialog = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="submitEdit">确定</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="importDialog" title="从项目导入文件" width="640px">
      <el-form label-width="80px">
        <el-form-item label="选择项目">
          <el-select
            :model-value="selectedProjectId"
            placeholder="请选择项目"
            style="width: 100%"
            :loading="loadingProjects"
            @change="onProjectSelect"
          >
            <el-option v-for="p in projectsForImport" :key="p.id" :label="p.name" :value="p.id" />
          </el-select>
        </el-form-item>
      </el-form>
      <div v-if="selectedProjectId" v-loading="loadingProjectFiles" class="import-file-list">
        <el-checkbox-group v-model="selectedFileIds">
          <div v-for="f in projectFiles" :key="f.id" class="import-file-item">
            <el-checkbox :value="f.id">
              {{ f.file_name }}
              <span class="import-file-meta">({{ f.file_type ?? '未知' }} · {{ formatSize(f.file_size) }})</span>
            </el-checkbox>
          </div>
        </el-checkbox-group>
        <el-empty v-if="!loadingProjectFiles && !projectFiles.length" description="该项目无可用文件" :image-size="60" />
      </div>
      <template #footer>
        <el-button @click="importDialog = false">取消</el-button>
        <el-button
          type="primary"
          :disabled="!selectedFileIds.length"
          :loading="importing"
          @click="doImportFiles"
        >
          导入 {{ selectedFileIds.length || '' }}
        </el-button>
      </template>
    </el-dialog>

    <!-- 文档迁移弹窗 -->
    <el-dialog v-model="migrateDialog" title="迁移文档" width="480px">
      <p style="margin-bottom: 12px; color: #666">
        将「{{ migrateDoc?.file_name }}」迁移到其他知识库
      </p>
      <el-form label-width="100px">
        <el-form-item label="目标知识库">
          <el-select v-model="migrateForm.targetKbId" placeholder="选择目标知识库" style="width: 100%">
            <el-option
              v-for="kb in migrateTargetOptions"
              :key="kb.id"
              :label="kb.name"
              :value="kb.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="迁移模式">
          <el-radio-group v-model="migrateForm.mode">
            <el-radio value="move">移动（原库不保留）</el-radio>
            <el-radio value="copy">复制（原库保留）</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-alert
          v-if="migrateForm.mode === 'move'"
          type="info"
          :closable="false"
          description="如果目标知识库使用不同的 Embedding 模型，文件将在目标库重新索引。"
          style="margin-top: 4px"
        />
      </el-form>
      <template #footer>
        <el-button @click="migrateDialog = false">取消</el-button>
        <el-button type="primary" :loading="migrating" @click="submitMigrate">确认迁移</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.kb-page {
  display: flex;
  gap: 16px;
  height: calc(100vh - 96px);
}
.kb-sidebar {
  width: 280px;
  flex-shrink: 0;
  background: #fff;
  border-radius: 8px;
  padding: 12px;
  display: flex;
  flex-direction: column;
}
.sidebar-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 10px;
}
.sidebar-header h3 {
  margin: 0;
  font-size: 15px;
}
.kb-list {
  flex: 1;
  overflow-y: auto;
}
.kb-card {
  padding: 10px;
  border-radius: 6px;
  border: 1px solid #e5e7eb;
  margin-bottom: 8px;
  cursor: pointer;
  transition: all 0.15s;
}
.kb-card:hover {
  border-color: #93c5fd;
  background: #f8fafc;
}
.kb-card.active {
  border-color: #3b82f6;
  background: #eff6ff;
}
.kb-card-name {
  font-weight: 600;
  font-size: 13px;
  margin-bottom: 4px;
}
.kb-card-meta {
  font-size: 11px;
  color: #94a3b8;
  margin-bottom: 6px;
}
.kb-card-actions {
  display: flex;
  gap: 4px;
}
.kb-main {
  flex: 1;
  background: #fff;
  border-radius: 8px;
  padding: 20px;
  overflow-y: auto;
}
.main-header h2 {
  margin: 0 0 6px;
  font-size: 18px;
}
.desc {
  color: #64748b;
  font-size: 13px;
  margin: 0 0 8px;
}
.stats {
  display: flex;
  gap: 8px;
  margin-top: 6px;
}
.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 10px;
}
.section-header h4 {
  margin: 0;
  font-size: 14px;
}
.search-bar {
  display: flex;
  gap: 8px;
  align-items: center;
  margin-bottom: 12px;
}
.search-results {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.result-card {
  padding: 10px 12px;
  border: 1px solid #e5e7eb;
  border-radius: 6px;
  background: #f9fafb;
}
.result-header {
  display: flex;
  gap: 8px;
  align-items: center;
  font-size: 12px;
  margin-bottom: 6px;
}
.result-idx {
  font-weight: 700;
  color: #3b82f6;
}
.result-file {
  color: #64748b;
  flex: 1;
}
.result-score {
  color: #94a3b8;
  font-family: monospace;
}
.result-content {
  font-size: 13px;
  line-height: 1.5;
  color: #1f2937;
  white-space: pre-wrap;
}
.import-file-list {
  max-height: 320px;
  overflow-y: auto;
  padding: 8px;
  border: 1px solid #e5e7eb;
  border-radius: 6px;
}
.import-file-item {
  padding: 4px 0;
}
.import-file-meta {
  margin-left: 6px;
  color: #94a3b8;
  font-size: 12px;
}
.detail-info {
  margin-bottom: 8px;
}
.detail-chunks-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 10px;
}
.detail-chunks-header h4 {
  margin: 0;
  font-size: 14px;
}
.detail-chunks-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  max-height: calc(100vh - 420px);
  overflow-y: auto;
}
.chunk-card {
  border: 1px solid #e5e7eb;
  border-radius: 6px;
  padding: 10px 12px;
  background: #f9fafb;
}
.chunk-header {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 12px;
  margin-bottom: 6px;
}
.chunk-idx {
  font-weight: 700;
  color: #3b82f6;
}
.chunk-chars {
  color: #94a3b8;
  font-family: monospace;
}
.chunk-content {
  font-size: 13px;
  line-height: 1.6;
  color: #1f2937;
  white-space: pre-wrap;
  max-height: 80px;
  overflow: hidden;
  position: relative;
}
.chunk-content::after {
  content: '';
  position: absolute;
  bottom: 0;
  left: 0;
  right: 0;
  height: 24px;
  background: linear-gradient(transparent, #f9fafb);
}
.chunk-content.expanded {
  max-height: none;
  overflow: visible;
}
.chunk-content.expanded::after {
  display: none;
}
.detail-pagination {
  margin-top: 12px;
  display: flex;
  justify-content: center;
}
</style>

