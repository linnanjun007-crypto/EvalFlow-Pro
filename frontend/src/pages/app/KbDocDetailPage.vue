<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import {
  exportKbDocumentChunks,
  getKb,
  getKbDocumentContent,
  getKbDocumentDetail,
  listKbDocumentChunks,
  type KbDocContent,
  type KbDocument,
  type UserKb,
} from '../../services/kbs'
import KbTuningWizard from '../../components/kb/KbTuningWizard.vue'

const route = useRoute()
const router = useRouter()

const kbId = computed(() => String(route.params.kbId || ''))
const docId = computed(() => String(route.params.docId || ''))

const kb = ref<UserKb | null>(null)
const doc = ref<KbDocument | null>(null)
const content = ref<KbDocContent | null>(null)
const chunkTotal = ref(0)
const loading = ref(false)
const searchKeyword = ref('')
const showRawDrawer = ref(false)
const tuningDialog = ref(false)

async function refresh() {
  if (!kbId.value || !docId.value) return
  loading.value = true
  try {
    const [kbRes, docRes, contentRes, chunksRes] = await Promise.all([
      getKb(kbId.value),
      getKbDocumentDetail(kbId.value, docId.value),
      getKbDocumentContent(kbId.value, docId.value),
      listKbDocumentChunks(kbId.value, docId.value, 0, 1),
    ])
    kb.value = kbRes
    doc.value = docRes
    content.value = contentRes
    chunkTotal.value = chunksRes.total
  } catch (e: any) {
    ElMessage.error(e.message || '加载文档失败')
  } finally {
    loading.value = false
  }
}

function goBack() {
  router.push({ name: 'personal-kbs' })
}

const filteredSections = computed(() => {
  if (!content.value) return []
  const kw = searchKeyword.value.trim().toLowerCase()
  if (!kw) return content.value.sections
  return content.value.sections.filter((s) => s.content.toLowerCase().includes(kw))
})

function highlight(text: string): string {
  const kw = searchKeyword.value.trim()
  if (!kw) return escapeHtml(text)
  const escaped = escapeHtml(text)
  const re = new RegExp(escapeRegex(kw), 'gi')
  return escaped.replace(re, (m) => `<mark>${m}</mark>`)
}

function escapeHtml(s: string): string {
  return s
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
}

function escapeRegex(s: string): string {
  return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

function formatSize(size?: number | null): string {
  if (!size && size !== 0) return '—'
  if (size < 1024) return `${size} B`
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`
  return `${(size / 1024 / 1024).toFixed(2)} MB`
}

function formatTime(value?: string | null): string {
  if (!value) return '—'
  const d = new Date(value)
  if (Number.isNaN(d.getTime())) return value
  return d.toLocaleString('zh-CN', { hour12: false })
}

async function exportChunks() {
  if (!doc.value) return
  try {
    const blob = await exportKbDocumentChunks(kbId.value, docId.value, 'md')
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `${doc.value.file_name}.chunks.md`
    a.click()
    URL.revokeObjectURL(url)
    ElMessage.success('已导出')
  } catch (e: any) {
    ElMessage.error(e.message || '导出失败')
  }
}

function openTuning() {
  tuningDialog.value = true
}

function onTuningApplied() {
  tuningDialog.value = false
  ElMessage.success('参数已保存，重建索引已在后台运行')
  refresh()
}

onMounted(refresh)
</script>

<template>
  <div class="kb-doc-detail" v-loading="loading">
    <header class="topbar">
      <div class="crumbs">
        <el-button link @click="goBack">← 返回</el-button>
        <span class="sep">/</span>
        <span class="kb-name">{{ kb?.name || '知识库' }}</span>
        <span class="sep">/</span>
        <span class="doc-name">{{ doc?.file_name || '...' }}</span>
      </div>
      <div class="actions">
        <el-button @click="exportChunks">导出分块</el-button>
        <el-button type="primary" @click="openTuning">调整训练参数</el-button>
      </div>
    </header>

    <div class="body">
      <section class="content-area">
        <div class="content-header">
          <el-input
            v-model="searchKeyword"
            placeholder="搜索文档内容..."
            clearable
            size="small"
            style="width: 280px"
          />
          <div class="stats">
            <el-tag size="small" type="info">{{ filteredSections.length }} 组数据</el-tag>
            <el-tag size="small" type="success">{{ chunkTotal }} 组索引</el-tag>
          </div>
        </div>

        <div class="sections">
          <article v-for="(sec, idx) in filteredSections" :key="idx" class="section-card">
            <div v-if="sec.heading_path?.length" class="sec-heading">
              {{ sec.heading_path.join(' / ') }}
            </div>
            <div class="sec-content" v-html="highlight(sec.content)" />
          </article>
          <el-empty v-if="!filteredSections.length && !loading" description="暂无内容" :image-size="80" />
        </div>

        <div class="content-footer">
          <el-button size="small" @click="showRawDrawer = true">查看原始内容</el-button>
          <span v-if="content?.truncated" class="trunc-tip">已截断展示，原文超过 1MB</span>
        </div>
      </section>

      <aside class="meta-panel">
        <h3>元数据</h3>
        <el-descriptions :column="1" size="small" border>
          <el-descriptions-item label="集合 ID">{{ kbId }}</el-descriptions-item>
          <el-descriptions-item label="数据来源">{{ doc?.source_type === 'upload' ? '直接上传' : doc?.source_type === 'project_file_promote' ? '项目导入' : doc?.source_type === 'copied' ? '复制' : doc?.source_type === 'migrated' ? '迁移' : doc?.source_type }}</el-descriptions-item>
          <el-descriptions-item label="数据集名称">{{ kb?.name }}</el-descriptions-item>
          <el-descriptions-item label="文件名">{{ doc?.file_name }}</el-descriptions-item>
          <el-descriptions-item label="文件类型">{{ doc?.file_type }}</el-descriptions-item>
          <el-descriptions-item label="来源大小">{{ formatSize(doc?.file_size) }}</el-descriptions-item>
          <el-descriptions-item label="创建时间">{{ formatTime(doc?.created_at) }}</el-descriptions-item>
          <el-descriptions-item label="索引时间">{{ formatTime(doc?.indexed_at) }}</el-descriptions-item>
          <el-descriptions-item label="PDF 增强解析">{{ kb?.pdf_enhanced_parse ? '是' : '否' }}</el-descriptions-item>
          <el-descriptions-item label="原文长度">{{ content?.total_length ?? '—' }} 字符</el-descriptions-item>
          <el-descriptions-item label="处理模式">{{ kb?.processing_mode === 'qa' ? '问答对提取' : '分块存储' }}</el-descriptions-item>
          <el-descriptions-item label="分块策略">{{ kb?.chunk_strategy || 'auto' }}</el-descriptions-item>
          <el-descriptions-item label="标题加入索引">{{ kb?.index_title ? '是' : '否' }}</el-descriptions-item>
          <el-descriptions-item label="图片索引">{{ kb?.index_image ? '是' : '否' }}</el-descriptions-item>
          <el-descriptions-item label="自动补充索引">{{ kb?.auto_supplement_index ? '是' : '否' }}</el-descriptions-item>
          <el-descriptions-item label="分块大小">{{ kb?.chunk_size }}</el-descriptions-item>
          <el-descriptions-item label="分块重叠">{{ kb?.chunk_overlap }}</el-descriptions-item>
          <el-descriptions-item label="索引大小">{{ chunkTotal }} 段</el-descriptions-item>
          <el-descriptions-item label="Embedding 维度">{{ kb?.embedding_dim }}</el-descriptions-item>
        </el-descriptions>
      </aside>
    </div>

    <el-drawer v-model="showRawDrawer" title="原始内容" size="60%" direction="rtl">
      <pre class="raw-text">{{ content?.raw_text }}</pre>
    </el-drawer>

    <KbTuningWizard
      v-if="tuningDialog && kb"
      v-model="tuningDialog"
      :kb="kb"
      :doc-id="docId"
      @applied="onTuningApplied"
    />
  </div>
</template>

<style scoped>
.kb-doc-detail {
  display: flex;
  flex-direction: column;
  height: calc(100vh - 96px);
  background: #f3f5f9;
}
.topbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 20px;
  background: #fff;
  border-bottom: 1px solid #e5e7eb;
}
.crumbs {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 14px;
  color: #374151;
}
.crumbs .sep {
  color: #d1d5db;
}
.crumbs .kb-name {
  color: #6b7280;
}
.crumbs .doc-name {
  font-weight: 500;
  color: #111827;
}
.actions {
  display: flex;
  gap: 8px;
}
.body {
  display: flex;
  gap: 16px;
  flex: 1;
  padding: 16px;
  overflow: hidden;
}
.content-area {
  flex: 1;
  background: #fff;
  border-radius: 8px;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.content-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  border-bottom: 1px solid #f3f4f6;
}
.stats {
  display: flex;
  gap: 8px;
}
.sections {
  flex: 1;
  overflow-y: auto;
  padding: 16px;
}
.section-card {
  margin-bottom: 16px;
  padding: 12px 16px;
  border-radius: 6px;
  border: 1px solid #f1f5f9;
  background: #fafbfc;
}
.section-card .sec-heading {
  font-weight: 600;
  font-size: 13px;
  color: #2563eb;
  background: #eff6ff;
  padding: 6px 10px;
  border-radius: 4px;
  margin-bottom: 8px;
  display: inline-block;
}
.sec-content {
  font-size: 14px;
  line-height: 1.7;
  color: #374151;
  white-space: pre-wrap;
  word-break: break-word;
}
.sec-content :deep(mark) {
  background: #fef08a;
  padding: 0 2px;
  border-radius: 2px;
}
.content-footer {
  padding: 10px 16px;
  border-top: 1px solid #f3f4f6;
  display: flex;
  align-items: center;
  gap: 12px;
}
.trunc-tip {
  font-size: 12px;
  color: #ef4444;
}
.meta-panel {
  width: 320px;
  flex-shrink: 0;
  background: #fff;
  border-radius: 8px;
  padding: 16px;
  overflow-y: auto;
}
.meta-panel h3 {
  margin: 0 0 12px;
  font-size: 14px;
  color: #111827;
}
.raw-text {
  font-family: monospace;
  font-size: 12px;
  white-space: pre-wrap;
  word-break: break-word;
  padding: 16px;
  margin: 0;
}
</style>
