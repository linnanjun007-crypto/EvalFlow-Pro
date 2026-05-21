<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import PageHeader from '../../components/ef/PageHeader.vue'
import {
  activateKb,
  activatePrompt,
  createKb,
  createPrompt,
  deleteKb,
  deletePrompt,
  getActiveStepConfig,
  listAdminSteps,
  listChangeLogs,
  listKbs,
  listPrompts,
  saveStepConfig,
  updateModuleOrder,
  type AdminStepRecord,
  type ChangeLogRecord,
  type KbRecord,
  type PromptRecord,
} from '../../services/admin'

const steps = ref<AdminStepRecord[]>([])
const prompts = ref<PromptRecord[]>([])
const kbs = ref<KbRecord[]>([])
const recentLogs = ref<ChangeLogRecord[]>([])
const loading = ref(false)
const saving = ref(false)
const reordering = ref(false)
const activeStepCode = ref('step1')
const previewMarkdown = ref('')
const editorTab = ref<'prompt' | 'kb' | 'preview'>('prompt')

const editor = reactive({
  prompt_title: '',
  prompt_content: '',
  kb_name: '',
  kb_content: '',
})

const promptDialog = reactive({ open: false, title: '', content: '' })
const kbDialog = reactive({ open: false, name: '', storage_ref: '' })

const moduleOrderDraft = ref<string[]>([])
const newModuleName = ref('')

const activeStep = computed(() => steps.value.find((item) => item.code === activeStepCode.value))
const activePrompt = computed(() => prompts.value.find((item) => item.is_active))
const activeKb = computed(() => kbs.value.find((item) => item.is_active))

// 子 Prompt 视为以「二级指标:」为前缀的 PromptVersion 记录
const subPrompts = computed(() =>
  prompts.value.filter((p) => /^[^|]+::/.test(p.title) || p.title.startsWith('子:')),
)
const mainPrompts = computed(() =>
  prompts.value.filter((p) => !subPrompts.value.some((sub) => sub.id === p.id)),
)

async function refreshSteps() {
  steps.value = await listAdminSteps()
}

async function loadEditorFromActive() {
  const config = await getActiveStepConfig(activeStepCode.value)
  editor.prompt_title = config.prompt_title || ''
  editor.prompt_content = config.prompt_text || ''
  editor.kb_name = config.kb_name || ''
  editor.kb_content = config.knowledge_text || ''
}

async function refreshStepAssets() {
  loading.value = true
  try {
    const [promptItems, kbItems, logItems] = await Promise.all([
      listPrompts(activeStepCode.value),
      listKbs(activeStepCode.value),
      listChangeLogs({ step_code: activeStepCode.value, limit: 8 }),
    ])
    prompts.value = promptItems
    kbs.value = kbItems
    recentLogs.value = logItems
    await loadEditorFromActive()
  } finally {
    loading.value = false
  }
}

async function refresh() {
  await refreshSteps()
  await refreshStepAssets()
  syncModuleOrderDraft()
}

function syncModuleOrderDraft() {
  moduleOrderDraft.value = activeStep.value?.module_order
    ? [...activeStep.value.module_order]
    : []
}

async function selectStep(stepCode: string) {
  activeStepCode.value = stepCode
  previewMarkdown.value = ''
  editorTab.value = 'prompt'
  newModuleName.value = ''
  await refreshStepAssets()
  syncModuleOrderDraft()
}

async function submitPromptDraft() {
  if (!promptDialog.title.trim()) {
    ElMessage.warning('标题不能为空')
    return
  }
  await createPrompt({
    step_code: activeStepCode.value,
    title: promptDialog.title,
    content: promptDialog.content,
  })
  promptDialog.open = false
  promptDialog.title = ''
  promptDialog.content = ''
  ElMessage.success('已新增 Prompt 版本')
  await refresh()
}

async function submitKbDraft() {
  if (!kbDialog.name.trim()) {
    ElMessage.warning('名称不能为空')
    return
  }
  await createKb({
    step_code: activeStepCode.value,
    name: kbDialog.name,
    storage_ref: kbDialog.storage_ref,
  })
  kbDialog.open = false
  kbDialog.name = ''
  kbDialog.storage_ref = ''
  ElMessage.success('已新增知识库版本')
  await refresh()
}

async function setPromptActive(id: string) {
  await activatePrompt(id)
  ElMessage.success('已切换启用 Prompt')
  await refresh()
}

async function setKbActive(id: string) {
  await activateKb(id)
  ElMessage.success('已切换启用知识库')
  await refresh()
}

async function removePrompt(id: string) {
  await deletePrompt(id)
  ElMessage.success('已删除 Prompt 版本')
  await refresh()
}

async function removeKb(id: string) {
  await deleteKb(id)
  ElMessage.success('已删除知识库版本')
  await refresh()
}

async function runConfigAction(action: 'save' | 'preview') {
  saving.value = true
  try {
    const result = await saveStepConfig(activeStepCode.value, {
      prompt_title: editor.prompt_title,
      prompt_content: editor.prompt_content,
      kb_name: editor.kb_name,
      kb_content: editor.kb_content,
      action,
    })
    previewMarkdown.value = String(
      result.graph_result?.draft_markdown || result.graph_result?.final_markdown || '',
    )
    if (action === 'save') {
      ElMessage.success('配置已保存并生成新版本')
      await refresh()
    } else {
      ElMessage.info('预览已生成（未写入数据库）')
      editorTab.value = 'preview'
    }
  } catch (err) {
    ElMessage.error(err instanceof Error ? err.message : '保存失败')
  } finally {
    saving.value = false
  }
}

function moveModuleUp(index: number) {
  if (index <= 0) return
  const arr = moduleOrderDraft.value
  ;[arr[index - 1], arr[index]] = [arr[index], arr[index - 1]]
}

function moveModuleDown(index: number) {
  const arr = moduleOrderDraft.value
  if (index >= arr.length - 1) return
  ;[arr[index + 1], arr[index]] = [arr[index], arr[index + 1]]
}

function removeModule(index: number) {
  moduleOrderDraft.value.splice(index, 1)
}

function addModule() {
  const name = newModuleName.value.trim()
  if (!name) return
  if (moduleOrderDraft.value.includes(name)) {
    ElMessage.warning('模块已存在')
    return
  }
  moduleOrderDraft.value.push(name)
  newModuleName.value = ''
}

async function saveModuleOrder() {
  if (!moduleOrderDraft.value.length) {
    ElMessage.warning('模块顺序不能为空')
    return
  }
  reordering.value = true
  try {
    await updateModuleOrder(activeStepCode.value, moduleOrderDraft.value)
    ElMessage.success('模块顺序已保存')
    await refresh()
  } catch (err) {
    ElMessage.error(err instanceof Error ? err.message : '保存失败')
  } finally {
    reordering.value = false
  }
}

function resetModuleOrder() {
  syncModuleOrderDraft()
}

function formatLogTime(value?: string | null) {
  if (!value) return ''
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString('zh-CN', { hour12: false })
}

function stepFeatureTags(step: AdminStepRecord) {
  const tags: Array<{ label: string; type: '' | 'success' | 'warning' | 'info' | 'primary' | 'danger' }> = []
  if (step.supports_sub_prompts) tags.push({ label: '子', type: 'warning' })
  if (step.module_order_editable) tags.push({ label: '顺', type: 'primary' })
  return tags
}

watch(activeStepCode, () => {
  previewMarkdown.value = ''
})

onMounted(refresh)
</script>

<template>
  <div class="page">
    <PageHeader
      title="14 步配置中心"
      description="对应后端 14 步管理端配置：基础 Prompt / 知识库；部分步骤含子指标拆分或客户端模块顺序定义。"
    >
      <template #actions>
        <el-button @click="refresh">刷新</el-button>
        <el-button :loading="saving" @click="runConfigAction('preview')">预览</el-button>
        <el-button type="primary" :loading="saving" @click="runConfigAction('save')">
          保存并发布
        </el-button>
      </template>
    </PageHeader>

    <div class="layout">
      <!-- 左侧：14 步导航 -->
      <aside class="step-nav ef-card">
        <div class="nav-head">
          <span>14 步配置</span>
          <span class="muted">{{ steps.length }} / 14</span>
        </div>
        <div class="nav-list">
          <button
            v-for="step in steps"
            :key="step.code"
            class="step-row"
            :class="{ active: step.code === activeStepCode }"
            @click="selectStep(step.code)"
          >
            <span class="num">{{ step.order }}</span>
            <span class="info">
              <span class="name">{{ step.name }}</span>
              <span class="meta">
                <span>{{ step.prompt_count }}P · {{ step.kb_count }}K</span>
                <el-tag
                  v-for="tag in stepFeatureTags(step)"
                  :key="tag.label"
                  :type="tag.type"
                  size="small"
                  effect="plain"
                  class="feat-tag"
                >
                  {{ tag.label }}
                </el-tag>
              </span>
            </span>
          </button>
        </div>
        <div class="nav-legend">
          <span><el-tag size="small" effect="plain" type="warning">子</el-tag>支持二级指标拆分</span>
          <span><el-tag size="small" effect="plain" type="primary">顺</el-tag>支持模块顺序</span>
        </div>
      </aside>

      <!-- 右侧：工作区 -->
      <section class="workspace">
        <!-- 步骤摘要 -->
        <div v-if="activeStep" class="step-head ef-card">
          <div class="head-text">
            <div class="head-code">{{ activeStep.code }} · Step {{ activeStep.order }}</div>
            <h2 class="head-title">{{ activeStep.name }}</h2>
            <p v-if="activeStep.admin_focus" class="head-desc">{{ activeStep.admin_focus }}</p>
          </div>
          <div class="head-tags">
            <el-tag :type="activePrompt ? 'success' : 'warning'" size="small">
              {{ activePrompt ? `Prompt v${activePrompt.version}` : '未启用 Prompt' }}
            </el-tag>
            <el-tag :type="activeKb ? 'success' : 'info'" size="small">
              {{ activeKb ? `知识库 v${activeKb.version}` : '未启用知识库' }}
            </el-tag>
            <el-tag v-if="activeStep.supports_sub_prompts" type="warning" size="small">
              支持二级指标
            </el-tag>
            <el-tag v-if="activeStep.module_order_editable" type="primary" size="small">
              模块顺序可编辑
            </el-tag>
          </div>
        </div>

        <!-- 编辑器 -->
        <div class="ef-card editor" v-loading="loading">
          <el-tabs v-model="editorTab" class="editor-tabs">
            <el-tab-pane label="Prompt" name="prompt">
              <div class="field-group">
                <label class="field-label">标题</label>
                <el-input v-model="editor.prompt_title" placeholder="Prompt 标题" />
              </div>
              <div class="field-group">
                <label class="field-label">正文</label>
                <el-input
                  v-model="editor.prompt_content"
                  type="textarea"
                  :rows="14"
                  placeholder="角色、任务、输出结构、约束条件……"
                  resize="vertical"
                />
              </div>
            </el-tab-pane>

            <el-tab-pane label="知识库" name="kb">
              <div class="field-group">
                <label class="field-label">名称</label>
                <el-input v-model="editor.kb_name" placeholder="知识库名称" />
              </div>
              <div class="field-group">
                <label class="field-label">正文</label>
                <el-input
                  v-model="editor.kb_content"
                  type="textarea"
                  :rows="14"
                  placeholder="分类规则、样本说明、行业规范要点……"
                  resize="vertical"
                />
              </div>
            </el-tab-pane>

            <el-tab-pane label="预览" name="preview">
              <el-empty v-if="!previewMarkdown" description="点击「预览」生成实际效果" />
              <pre v-else class="preview-content">{{ previewMarkdown }}</pre>
            </el-tab-pane>
          </el-tabs>
        </div>

        <!-- step13/14：客户端模块顺序配置 -->
        <div v-if="activeStep?.module_order_editable" class="ef-card module-panel">
          <div class="card-head">
            <div>
              <h3>客户端模块顺序</h3>
              <p class="card-sub">客户端会按此顺序渲染该步骤的文本模块，影响最终报告结构。</p>
            </div>
            <div class="card-head-actions">
              <el-button size="small" :disabled="reordering" @click="resetModuleOrder">
                还原
              </el-button>
              <el-button
                size="small"
                type="primary"
                :loading="reordering"
                @click="saveModuleOrder"
              >
                保存顺序
              </el-button>
            </div>
          </div>

          <ol class="module-list" v-if="moduleOrderDraft.length">
            <li v-for="(mod, idx) in moduleOrderDraft" :key="`${mod}-${idx}`" class="module-row">
              <span class="module-index">{{ idx + 1 }}</span>
              <span class="module-name">{{ mod }}</span>
              <div class="module-actions">
                <el-button
                  size="small"
                  text
                  :disabled="idx === 0"
                  @click="moveModuleUp(idx)"
                >
                  ↑
                </el-button>
                <el-button
                  size="small"
                  text
                  :disabled="idx === moduleOrderDraft.length - 1"
                  @click="moveModuleDown(idx)"
                >
                  ↓
                </el-button>
                <el-button size="small" text type="danger" @click="removeModule(idx)">
                  删除
                </el-button>
              </div>
            </li>
          </ol>
          <el-empty v-else description="尚未配置模块顺序" :image-size="60" />

          <div class="module-add">
            <el-input
              v-model="newModuleName"
              placeholder="新增模块名称（如「绩效评价目的」）"
              size="default"
              @keyup.enter="addModule"
            >
              <template #append>
                <el-button @click="addModule">添加</el-button>
              </template>
            </el-input>
          </div>
        </div>

        <!-- step3/5/7/11：子指标 Prompt 说明面板 -->
        <div v-if="activeStep?.supports_sub_prompts" class="ef-card sub-panel">
          <div class="card-head">
            <div>
              <h3>二级指标子 Prompt</h3>
              <p class="card-sub">
                通过「新增 Prompt 版本」按命名约定保存：例如 <code>二级指标A::v1</code>，运行时按二级指标名匹配启用。
              </p>
            </div>
            <el-tag size="small" type="info" effect="plain">
              已发现 {{ subPrompts.length }} 个子 Prompt / {{ prompts.length }} 个总数
            </el-tag>
          </div>
          <el-table
            v-if="subPrompts.length"
            :data="subPrompts"
            size="small"
            empty-text="暂无子 Prompt"
          >
            <el-table-column prop="version" label="版本" width="64" align="center" />
            <el-table-column prop="title" label="标题（含二级指标名）" min-width="220" show-overflow-tooltip />
            <el-table-column label="状态" width="80" align="center">
              <template #default="{ row }">
                <el-tag :type="row.is_active ? 'success' : 'info'" size="small" effect="plain">
                  {{ row.is_active ? '启用' : '备用' }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column label="操作" width="140" align="center">
              <template #default="{ row }">
                <el-button
                  v-if="!row.is_active"
                  link
                  type="primary"
                  size="small"
                  @click="setPromptActive(String(row.id))"
                >
                  启用
                </el-button>
                <el-button link type="danger" size="small" @click="removePrompt(String(row.id))">
                  删除
                </el-button>
              </template>
            </el-table-column>
          </el-table>
          <div v-else class="sub-empty">
            尚未创建任何子 Prompt。在下方「Prompt 版本」中以
            <code>&lt;二级指标名&gt;::</code> 前缀命名即可被识别。
          </div>
        </div>

        <!-- 版本历史 -->
        <div class="version-grid">
          <div class="ef-card version-card">
            <div class="card-head">
              <h3>
                Prompt 版本
                <span class="card-count">{{ mainPrompts.length }}</span>
              </h3>
              <el-button size="small" type="primary" plain @click="promptDialog.open = true">
                新增
              </el-button>
            </div>
            <el-table
              v-loading="loading"
              :data="mainPrompts"
              size="small"
              empty-text="暂无版本"
            >
              <el-table-column prop="version" label="版本" width="64" align="center" />
              <el-table-column prop="title" label="标题" min-width="140" show-overflow-tooltip />
              <el-table-column label="状态" width="80" align="center">
                <template #default="{ row }">
                  <el-tag :type="row.is_active ? 'success' : 'info'" size="small" effect="plain">
                    {{ row.is_active ? '启用' : '备用' }}
                  </el-tag>
                </template>
              </el-table-column>
              <el-table-column label="操作" width="120" align="center">
                <template #default="{ row }">
                  <el-button
                    v-if="!row.is_active"
                    link
                    type="primary"
                    size="small"
                    @click="setPromptActive(String(row.id))"
                  >
                    启用
                  </el-button>
                  <el-button
                    link
                    type="danger"
                    size="small"
                    @click="removePrompt(String(row.id))"
                  >
                    删除
                  </el-button>
                </template>
              </el-table-column>
            </el-table>
          </div>

          <div class="ef-card version-card">
            <div class="card-head">
              <h3>
                知识库版本
                <span class="card-count">{{ kbs.length }}</span>
              </h3>
              <el-button size="small" type="primary" plain @click="kbDialog.open = true">
                新增
              </el-button>
            </div>
            <el-table
              v-loading="loading"
              :data="kbs"
              size="small"
              empty-text="暂无版本"
            >
              <el-table-column prop="version" label="版本" width="64" align="center" />
              <el-table-column prop="name" label="名称" min-width="140" show-overflow-tooltip />
              <el-table-column label="状态" width="80" align="center">
                <template #default="{ row }">
                  <el-tag :type="row.is_active ? 'success' : 'info'" size="small" effect="plain">
                    {{ row.is_active ? '启用' : '备用' }}
                  </el-tag>
                </template>
              </el-table-column>
              <el-table-column label="操作" width="120" align="center">
                <template #default="{ row }">
                  <el-button
                    v-if="!row.is_active"
                    link
                    type="primary"
                    size="small"
                    @click="setKbActive(String(row.id))"
                  >
                    启用
                  </el-button>
                  <el-button
                    link
                    type="danger"
                    size="small"
                    @click="removeKb(String(row.id))"
                  >
                    删除
                  </el-button>
                </template>
              </el-table-column>
            </el-table>
          </div>
        </div>

        <!-- 最近变更日志 -->
        <div class="ef-card logs">
          <div class="card-head">
            <h3>最近变更</h3>
            <router-link to="/admin/change-logs" class="link">查看全部 →</router-link>
          </div>
          <el-empty v-if="!recentLogs.length" description="暂无变更记录" :image-size="60" />
          <ul v-else class="log-list">
            <li v-for="log in recentLogs" :key="log.id" class="log-row">
              <span class="log-dot" />
              <span class="log-time">{{ formatLogTime(log.created_at) }}</span>
              <span class="log-actor">{{ log.actor_username || log.actor_user_id }}</span>
              <span class="log-summary">{{ log.summary || log.action }}</span>
            </li>
          </ul>
        </div>
      </section>
    </div>

    <!-- 新增 Prompt 对话框 -->
    <el-dialog
      v-model="promptDialog.open"
      title="新增 Prompt 版本"
      width="560px"
      align-center
    >
      <el-form label-position="top">
        <el-form-item label="标题" required>
          <el-input
            v-model="promptDialog.title"
            :placeholder="
              activeStep?.supports_sub_prompts
                ? '主版本直接命名；子版本用「<二级指标名>::」前缀'
                : '版本标题'
            "
          />
        </el-form-item>
        <el-form-item label="正文">
          <el-input
            v-model="promptDialog.content"
            type="textarea"
            :rows="8"
            placeholder="可从主编辑区复制粘贴"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="promptDialog.open = false">取消</el-button>
        <el-button type="primary" @click="submitPromptDraft">创建</el-button>
      </template>
    </el-dialog>

    <!-- 新增知识库对话框 -->
    <el-dialog
      v-model="kbDialog.open"
      title="新增知识库版本"
      width="560px"
      align-center
    >
      <el-form label-position="top">
        <el-form-item label="名称" required>
          <el-input v-model="kbDialog.name" placeholder="版本名称" />
        </el-form-item>
        <el-form-item label="内容摘要">
          <el-input
            v-model="kbDialog.storage_ref"
            type="textarea"
            :rows="8"
            placeholder="版本说明或内容引用"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="kbDialog.open = false">取消</el-button>
        <el-button type="primary" @click="submitKbDraft">创建</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.page { display: grid; gap: 14px; }

/* ── 主布局 ── */
.layout {
  display: grid;
  grid-template-columns: 280px minmax(0, 1fr);
  gap: 14px;
  align-items: start;
}

/* ── 步骤导航 ── */
.step-nav {
  padding: 10px;
  position: sticky;
  top: 14px;
  max-height: calc(100svh - 110px);
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.nav-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 6px 10px 10px;
  font-size: 12px;
  font-weight: 600;
  color: #64748b;
  letter-spacing: 0.04em;
  border-bottom: 1px solid #f1f5f9;
}

.muted { color: #cbd5e1; font-weight: 500; }

.nav-list {
  flex: 1;
  overflow: auto;
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 6px 0;
}

.nav-legend {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 10px 10px 4px;
  border-top: 1px solid #f1f5f9;
  font-size: 11px;
  color: #94a3b8;
}

.nav-legend span {
  display: flex;
  align-items: center;
  gap: 6px;
}

.step-row {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 10px;
  border: 1px solid transparent;
  border-radius: 8px;
  background: transparent;
  cursor: pointer;
  text-align: left;
  transition: background 0.15s ease, color 0.15s ease;
}

.step-row:hover {
  background: #f1f5f9;
}

.step-row.active {
  background: #eff6ff;
  border-color: #bfdbfe;
}

.num {
  flex-shrink: 0;
  display: grid;
  place-items: center;
  width: 24px;
  height: 24px;
  border-radius: 6px;
  background: #f1f5f9;
  color: #64748b;
  font-size: 12px;
  font-weight: 600;
}

.step-row.active .num {
  background: #1976ff;
  color: #fff;
}

.info {
  display: flex;
  flex-direction: column;
  min-width: 0;
  flex: 1;
}

.name {
  font-size: 13px;
  color: #1e293b;
  font-weight: 500;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.step-row.active .name { color: #1e3a8a; font-weight: 600; }

.meta {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 11px;
  color: #94a3b8;
  margin-top: 2px;
}

.feat-tag {
  margin-left: 4px;
  padding: 0 5px;
  font-size: 10px;
  line-height: 16px;
  height: 16px;
}

/* ── 工作区 ── */
.workspace {
  display: grid;
  gap: 14px;
  min-width: 0;
}

/* 步骤摘要 */
.step-head {
  padding: 18px 20px;
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 16px;
  flex-wrap: wrap;
}

.head-text { flex: 1; min-width: 0; }

.head-code {
  font-size: 11px;
  font-weight: 600;
  color: #1976ff;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  margin-bottom: 6px;
}

.head-title {
  margin: 0;
  font-size: 18px;
  font-weight: 600;
  color: #0f172a;
}

.head-desc {
  margin: 6px 0 0;
  font-size: 13px;
  color: #64748b;
  line-height: 1.5;
}

.head-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  align-items: center;
}

/* 编辑器 */
.editor { padding: 4px 18px 18px; }

.editor-tabs :deep(.el-tabs__nav-wrap::after) {
  height: 1px;
  background: #f1f5f9;
}

.editor-tabs :deep(.el-tabs__item) {
  font-size: 13px;
  font-weight: 500;
  padding: 0 18px;
  height: 42px;
}

.editor-tabs :deep(.el-tabs__active-bar) {
  background-color: #1976ff;
  height: 2px;
}

.field-group { display: grid; gap: 6px; margin-bottom: 14px; }
.field-group:last-child { margin-bottom: 0; }
.field-label { font-size: 12px; font-weight: 500; color: #64748b; }

.preview-content {
  margin: 0;
  padding: 14px;
  background: #f8fafc;
  border: 1px solid #f1f5f9;
  border-radius: 8px;
  white-space: pre-wrap;
  word-break: break-word;
  font-size: 12px;
  color: #334155;
  max-height: 460px;
  overflow: auto;
  font-family: 'SF Mono', Consolas, monospace;
  line-height: 1.6;
}

/* 模块顺序面板 */
.module-panel, .sub-panel { padding: 16px 18px; }

.card-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  margin-bottom: 12px;
  gap: 12px;
}

.card-head h3 {
  margin: 0;
  font-size: 14px;
  font-weight: 600;
  color: #0f172a;
  display: flex;
  align-items: center;
  gap: 6px;
}

.card-count {
  display: inline-grid;
  place-items: center;
  min-width: 20px;
  height: 18px;
  padding: 0 6px;
  border-radius: 9px;
  background: #f1f5f9;
  color: #64748b;
  font-size: 11px;
  font-weight: 500;
}

.card-sub {
  margin: 4px 0 0;
  font-size: 12px;
  color: #94a3b8;
  line-height: 1.5;
}

.card-sub code {
  background: #f1f5f9;
  padding: 1px 5px;
  border-radius: 3px;
  font-size: 11px;
  color: #1976ff;
}

.card-head-actions {
  display: flex;
  gap: 8px;
  flex-shrink: 0;
}

.module-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-bottom: 12px;
}

.module-row {
  display: grid;
  grid-template-columns: 28px 1fr auto;
  align-items: center;
  gap: 10px;
  padding: 8px 12px;
  background: #f8fafc;
  border: 1px solid #f1f5f9;
  border-radius: 8px;
  transition: background 0.15s ease;
}

.module-row:hover { background: #f1f5f9; }

.module-index {
  display: grid;
  place-items: center;
  width: 22px;
  height: 22px;
  border-radius: 50%;
  background: #1976ff;
  color: #fff;
  font-size: 11px;
  font-weight: 600;
}

.module-name {
  font-size: 13px;
  color: #1e293b;
  font-weight: 500;
}

.module-actions { display: flex; gap: 2px; }

.module-add { margin-top: 8px; }

/* 子 Prompt 面板 */
.sub-empty {
  font-size: 13px;
  color: #94a3b8;
  padding: 18px;
  background: #f8fafc;
  border-radius: 8px;
  text-align: center;
}

.sub-empty code {
  background: #fff;
  padding: 1px 6px;
  border-radius: 3px;
  color: #1976ff;
  border: 1px solid #e2e8f0;
}

/* 版本历史 */
.version-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 14px;
}

.version-card {
  padding: 16px 18px;
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.link {
  font-size: 12px;
  color: #1976ff;
  text-decoration: none;
}

.link:hover { text-decoration: underline; }

/* 日志 */
.logs { padding: 16px 18px; }

.log-list { list-style: none; margin: 0; padding: 0; }

.log-row {
  display: grid;
  grid-template-columns: 12px 140px 100px 1fr;
  gap: 10px;
  align-items: center;
  padding: 10px 4px;
  font-size: 13px;
  border-bottom: 1px solid #f8fafc;
}

.log-row:last-child { border-bottom: none; }

.log-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #1976ff;
  margin-left: 3px;
}

.log-time { color: #94a3b8; font-size: 12px; font-variant-numeric: tabular-nums; }
.log-actor { color: #0f172a; font-weight: 500; }
.log-summary { color: #475569; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

/* ── 响应式 ── */
@media (max-width: 1100px) {
  .layout { grid-template-columns: 1fr; }
  .step-nav { position: static; max-height: 320px; }
  .version-grid { grid-template-columns: 1fr; }
  .log-row {
    grid-template-columns: 12px 1fr;
    grid-template-areas:
      'dot time'
      'dot actor'
      'dot summary';
    row-gap: 2px;
  }
  .log-dot { grid-area: dot; }
  .log-time { grid-area: time; }
  .log-actor { grid-area: actor; }
  .log-summary { grid-area: summary; white-space: normal; }
}
</style>
