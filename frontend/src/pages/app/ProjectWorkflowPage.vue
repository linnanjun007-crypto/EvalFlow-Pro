<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch, watchEffect } from 'vue'
import Sortable from 'sortablejs'
import type { UploadFile, UploadProps } from 'element-plus'
import { useRoute, useRouter, onBeforeRouteLeave } from 'vue-router'
import { createMarkdown, renderSafe } from '../../utils/markdownConfig'
import PageHeader from '../../components/ef/PageHeader.vue'
import StepSidebar from '../../components/ef/StepSidebar.vue'
import GenerationPanel from '../../components/ef/GenerationPanel.vue'
import ModelCompareTabs from '../../components/ef/ModelCompareTabs.vue'
import ArtifactEditor from '../../components/ef/ArtifactEditor.vue'
import HistoryDrawer from '../../components/ef/HistoryDrawer.vue'
import ChatDrawer from '../../components/ef/ChatDrawer.vue'
import TaskProgress from '../../components/ef/TaskProgress.vue'
import Step1Analysis from '../../components/ef/Step1Analysis.vue'
import MarkdownDashboard from '../../components/ef/MarkdownDashboard.vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { cancelAgentRun, clearThreadState, getThreadState, runAgent, updateThreadState, type AgentRunResponse } from '../../services/agent'
import { useWorkflowBus } from '../../stores/workflowBus'

const props = withDefaults(defineProps<{ embeddedMode?: boolean }>(), { embeddedMode: false })

const workflowBus = useWorkflowBus()
import { downloadExportFile, exportStep1, exportStep2, exportStep14Word, type ExportFormat, type Step2FormatOptions } from '../../services/exports'
import { createFileRecord, deleteFile, isInputProjectFile, listFiles, uploadProjectFile, type FileRecord } from '../../services/files'
import { deleteStepHistory, getStepResult, getWorkflowStatus, listStepHistories, saveStepResult, type WorkflowStatusResponse } from '../../services/steps'

const route = useRoute()
const router = useRouter()
const projectId = computed(() => String(route.params.projectId ?? ''))
const stepId = computed(() => {
  const fromRoute = Number(route.params.stepId)
  const fromQuery = Number(route.query.step)
  return fromRoute || fromQuery || 1
})
const loading = ref(false)
const stopping = ref(false)
const activeRunId = ref('')
const activeRunAbortController = ref<AbortController | null>(null)
const saving = ref(false)
const uploading = ref(false)
const uploadingChannel = ref<'media' | 'documents'>('documents')
const uploadDialogVisible = ref(false)
const uploadQueue = ref<UploadFile[]>([])
const uploadPreviewText = computed(() => uploadQueue.value.map((item) => item.name).join('、'))
const inputProjectFiles = computed(() => projectFiles.value.filter(isInputProjectFile))
const step2Summary = computed(() => ({
  total: inputProjectFiles.value.length,
  media: mediaFiles.value.length,
  documents: documentFiles.value.length,
  ready: inputProjectFiles.value.length > 0,
}))
const resultText = ref('')
const error = ref('')
const historyOpen = ref(false)
const chatOpen = ref(false)
const step1ThreadId = computed(() => `step1:${projectId.value}`)
const workflowState = computed(() => ({
  project_id: projectId.value,
  project_name: projectName.value,
  step_id: stepId.value,
  step_code: stepCodeOf(),
  step_title: titleMap[stepId.value] ?? `Step ${stepId.value}`,
  prompt_hint: promptHintMap[stepId.value] ?? '输入本步骤补充指令或约束',
  file_count: inputProjectFiles.value.length,
  media_count: mediaFiles.value.length,
  document_count: documentFiles.value.length,
  has_step1_draft: Boolean(loadStep1DraftState()),
  current_result: currentResult.value,
  step3_state: step3State.value,
  client_model_provider: primaryActiveModelConfig.value.provider,
  client_model_name: primaryActiveModelConfig.value.model_name,
  client_model_base_url: primaryActiveModelConfig.value.base_url,
  client_model_api_key: primaryActiveModelConfig.value.api_key,
  client_model_temperature: primaryActiveModelConfig.value.temperature,
  active_model_provider: primaryActiveModelConfig.value.provider,
  active_model_name: primaryActiveModelConfig.value.model_name,
  active_base_url: primaryActiveModelConfig.value.base_url,
  active_api_key: primaryActiveModelConfig.value.api_key,
  active_temperature: primaryActiveModelConfig.value.temperature,
  active_model_configs: enabledActiveModelConfigs.value,
  client_model_configs: enabledActiveModelConfigs.value,
}))
const exportDialogVisible = ref(false)
const exportStyle = ref<'classic' | 'custom'>('classic')
const exportFormat = ref<ExportFormat>('markdown')
const exportCustomTitle = ref('')
const exportSaving = ref(false)
const lastExportUrl = ref('')
const lastExportFileName = ref('')
const exportPreviewMode = ref<'raw' | 'preview'>('raw')

const DEFAULT_STEP2_CATEGORIES = ['资金管理类', '预算管理类', '制度文件类', '项目实施类']
const REQUIRED_STEP2_DIMENSIONS = ['项目背景', '项目实施内容', '项目组织管理情况', '项目资金投入与支出情况', '项目绩效目标', '项目实际产出情况', '效益情况']
const step2DefaultCategories = ref<string[]>([...DEFAULT_STEP2_CATEGORIES])
const step2ExtraCategories = ref<string[]>([])
const step2NewCategoryInput = ref('')
const step2MediaModelId = ref('')
const step2DocsModelId = ref('')
const gapUploadPickerVisible = ref(false)
const gapUploadPickerMaterial = ref('')
const step2VerificationAck = ref(false)
const step2ReviewMode = ref<'approve' | 'modify'>('approve')
const step2ReviewFeedback = ref('')
const step2VerificationDigest = ref('')
const step2ParseWarnings = ref<string[]>([])
const step2ModelComparisons = ref<Array<{ model_name?: string; label?: string; provider?: string; channel?: string; temperature?: number; draft?: string; error?: string }>>([])
const step2SourceIndex = ref<Array<{ ref_id: string; source_name: string; channel: string; excerpt: string }>>([])
const step2MediaMetadata = ref<Array<Record<string, unknown>>>([])
const step2DocsMetadata = ref<Array<Record<string, unknown>>>([])
const step2StatusText = ref('')
const step2DraftDirty = ref(false)
const step2LastCommittedAt = ref<string | null>(null)
let step2WriteBackTimer: ReturnType<typeof setTimeout> | null = null
const step2DigestViewMode = ref<'raw' | 'preview'>('raw')
const step2ActiveCompareIndex = ref(0)
const step2CompareViewMode = ref<'raw' | 'preview'>('raw')
const step2ExportDialogVisible = ref(false)
const step2ExportStyle = ref<'classic' | 'custom'>('classic')
const step2ExportFormat = ref<ExportFormat>('markdown')
const step2ExportCustomTitle = ref('')
const step2ExportSaving = ref(false)
const lastStep2ExportUrl = ref('')
const lastStep2ExportFileName = ref('')
const step2ExportFormatOptions = ref<{
  font_family: string
  font_size_pt: number
  heading_font_size_pt: number
  line_spacing: number
  paragraph_spacing_pt: number
  first_line_indent_chars: number
}>({
  font_family: 'SimSun',
  font_size_pt: 12,
  heading_font_size_pt: 16,
  line_spacing: 1.5,
  paragraph_spacing_pt: 6,
  first_line_indent_chars: 2,
})
const step2ThreadId = computed(() => `step2:${projectId.value}`)
const step2MergedCategories = computed(() => {
  const seen = new Set<string>()
  const merged: string[] = []
  for (const item of [...step2DefaultCategories.value, ...step2ExtraCategories.value]) {
    const value = (item || '').trim()
    if (value && !seen.has(value)) {
      seen.add(value)
      merged.push(value)
    }
  }
  return merged
})
const step2VisionCapableModels = computed(() => enabledActiveModelConfigs.value.filter((item) => isVisionCapableModel(item)))
const step2ChannelModelOptions = computed(() => enabledActiveModelConfigs.value.map((item) => ({
  id: item.id,
  label: `${item.label || item.model_name}${isVisionCapableModel(item) ? ' · 多模态' : ''}`,
  vision: isVisionCapableModel(item),
})))
const step2MediaModelSupportsVision = computed(() => {
  if (!step2MediaModelId.value) return step2VisionCapableModels.value.length > 0
  const found = enabledActiveModelConfigs.value.find((item) => item.id === step2MediaModelId.value)
  return found ? isVisionCapableModel(found) : false
})
const step2HasFiles = computed(() => mediaFiles.value.length > 0 || documentFiles.value.length > 0)
const step2HasContent = computed(() => !isEditorEmpty(editor.value))
const step2CanRefine = computed(() => step2HasContent.value && step2ReviewFeedback.value.trim().length > 0)
const confirmDialogVisible = ref(false)
const confirmDialogTitle = ref('')
const confirmDialogMessage = ref('')
const confirmDialogType = ref<'warning' | 'danger' | 'info'>('warning')
const confirmDialogOkText = ref('确定')
const pendingConfirmAction = ref<null | (() => Promise<void> | void)>(null)
const editor = ref('')
const editorPlaceholder = '最终版本内容将在这里编辑。'
const step1DraftKey = computed(() => `ef_step1_draft:${projectId.value}:${step1ThreadId.value}`)
const step1DraftHistoryKey = computed(() => `ef_step1_draft_history:${projectId.value}:${step1ThreadId.value}`)
const step2DraftKey = computed(() => `ef_step2_draft:${projectId.value}:${step2ThreadId.value}`)
const step3DraftKey = computed(() => `ef_step3_draft:${projectId.value}`)
const currentResult = ref<Record<string, unknown> | null>(null)
const step1StructuredAnalysis = computed(() => {
  const sa = currentResult.value?.structured_analysis as Record<string, unknown> | undefined
  return {
    keyMetrics: (sa?.key_metrics ?? []) as Array<{ label: string; value: string; source: string }>,
    gapAnalysis: (sa?.gap_analysis ?? []) as Array<{ material: string; status: 'success' | 'error' | 'warning'; note: string }>,
    dataFlow: (sa?.data_flow ?? []) as Array<{ file_name: string; file_type: string; target_steps: string[] }>,
  }
})
const step1DraftHistory = ref<Array<{ id: string; title: string; content: string; source: string; created_at: string }>>([])
const step1DraftViewMode = ref<'edit' | 'preview'>('edit')
const step1ExpandDialog = ref(false)
const draftPreviewModes = ref<Record<string, 'raw' | 'preview'>>({})
const projectFiles = ref<FileRecord[]>([])
const projectName = ref(localStorage.getItem('ef_project_name') || '')
const historyItems = ref<Array<{ id: string; title: string; desc: string; content: string; content_json?: string }>>([])
const currentOutputs = ref<Array<{ title: string; desc: string; content: string }>>([])
const compareItems = ref<Array<{ label: string; content: string }>>([])
const placeholderEditorTexts = [editorPlaceholder, '最后版本内容将在这里编辑。']

function isEditorEmpty(value = editor.value) {
  const trimmed = (value || '').trim()
  return !trimmed || placeholderEditorTexts.includes(trimmed)
}
const step3State = ref<Record<string, unknown> | null>(null)
const step3Structured = ref<{ skeleton: Array<Record<string, unknown>>; level2Items: Array<Record<string, unknown>>; level3Items: Array<Record<string, unknown>> }>({
  skeleton: [],
  level2Items: [],
  level3Items: [],
})
const step3Config = ref({
  system_type: '项目支出指标体系',
  indicator_depth: 3,
  import_mode: 'none',
  imported_indicator_json: '',
  template_id: 'classic_performance_v1',
  skeleton_optimize_mode: 'none',
  per_optimize_level2_name: '',
  review_mode: 'approve',
  review_feedback: '',
})
// Step3 iterative state
interface Step3L2Task {
  level1_name: string
  level2_name: string
  target_l3_count: number
  l3_section_markdown: string
}
const step3SkeletonTasks = ref<Step3L2Task[]>([])
const step3ActiveL2Index = ref(0)
const step3ActiveL2Tab = computed({
  get: () => String(step3ActiveL2Index.value),
  set: (value: string) => {
    const idx = Number(value)
    if (Number.isFinite(idx)) selectStep3L2(idx)
  },
})
function onStep3TabChange(name: string | number) {
  const idx = Number(name)
  if (Number.isFinite(idx)) selectStep3L2(idx)
}
const step3L3Draft = ref('')
const step3L3Comparisons = ref<Array<{ model_name: string; label: string; draft: string; error: string }>>([])
const step3L3ReviewMode = ref<'approve' | 'modify'>('approve')
const step3L3Feedback = ref('')
const step3L3ViewMode = ref<'edit' | 'preview'>('edit')
const step3L3CompareViewMode = ref<'raw' | 'preview'>('raw')
const step3L3ActiveCompareIndex = ref(0)
const step3SkeletonPhase = ref<'config' | 'skeleton' | 'generating_l3' | 'completed'>('config')
const step3Templates: Array<{ id: string; name: string; tasks: Step3L2Task[] }> = [
  {
    id: 'classic_performance_v1',
    name: '经典绩效模板 v1',
    tasks: [
      { level1_name: '决策', level2_name: '依据充分与程序合规', target_l3_count: 3, l3_section_markdown: '' },
      { level1_name: '过程', level2_name: '资金管理与组织实施', target_l3_count: 3, l3_section_markdown: '' },
      { level1_name: '产出', level2_name: '产出数量与质量', target_l3_count: 3, l3_section_markdown: '' },
      { level1_name: '效益', level2_name: '经济、社会、环境效益', target_l3_count: 3, l3_section_markdown: '' },
    ],
  },
  {
    id: 'classic_procurement_v1',
    name: '经典采购模板 v1',
    tasks: [
      { level1_name: '决策', level2_name: '采购需求与审批', target_l3_count: 3, l3_section_markdown: '' },
      { level1_name: '过程', level2_name: '招标投标与合同履约', target_l3_count: 3, l3_section_markdown: '' },
      { level1_name: '产出', level2_name: '交付与验收', target_l3_count: 3, l3_section_markdown: '' },
      { level1_name: '效益', level2_name: '成本节约与满意度', target_l3_count: 3, l3_section_markdown: '' },
    ],
  },
]
const step3TemplatePreview = computed(() => {
  return step3Templates.find((t) => t.id === step3Config.value.template_id) || step3Templates[0]
})
const step3ActiveL2Task = computed(() => {
  return step3SkeletonTasks.value[step3ActiveL2Index.value] || null
})
const step3L2Progress = computed(() => {
  const total = step3SkeletonTasks.value.length
  const completed = step3SkeletonTasks.value.filter((t) => t.l3_section_markdown).length
  return { total, completed, percent: total ? Math.round((completed / total) * 100) : 0 }
})
const step3HasSkeleton = computed(() => step3SkeletonTasks.value.length > 0)
const step3HasStep2Core = computed(() => {
  const s = step3State.value
  if (!s) return false
  return Boolean(s.core_basis_digest || s.project_core_content || s.final_core_content || s.content_text || s.core_content_draft)
})
const step3CanGenerateL3 = computed(() => step3HasSkeleton.value && step3ActiveL2Task.value !== null)
const step3AllL2Completed = computed(() => {
  return step3SkeletonTasks.value.length > 0 && step3SkeletonTasks.value.every((t) => t.l3_section_markdown)
})
const step3GroupedL1 = computed(() => {
  const groups: Record<string, Step3L2Task[]> = {}
  for (const t of step3SkeletonTasks.value) {
    if (!groups[t.level1_name]) groups[t.level1_name] = []
    groups[t.level1_name].push(t)
  }
  return groups
})
const step3SkeletonEditDialogVisible = ref(false)
const step3SkeletonEditTarget = ref<{ level1_name: string; level2_name: string } | null>(null)
const step3SkeletonEditForm = ref({ level1_name: '', level2_name: '', target_l3_count: 3 })
const step3SkeletonAddL1DialogVisible = ref(false)
const step3SkeletonAddL2DialogVisible = ref(false)
const step3NewL1Name = ref('')
const step3NewL2Form = ref({ level1_name: '', level2_name: '', target_l3_count: 3 })

interface Step4ScoreItem {
  level1_name: string
  level2_name: string
  level3_name?: string
  weight?: number
  score?: number
  target_l3_count?: number
  l3_section_markdown?: string
}
const step4FlatL2Tasks = ref<Step4ScoreItem[]>([])
const step4ScoringMode = ref<'ai' | 'manual'>('ai')
const step4ManualScores = ref<Record<string, number>>({})
const step4ValidationErrors = ref<string[]>([])
const step4TotalScore = ref(100)
const step5ScoreSheet = ref('')
// step6：是否生成里克特满意度问卷 + 问卷反馈意见 + 后端返回的问卷草稿/条目快照
const step6QuestionnaireDecision = ref<'need' | 'skip'>('skip')
const step6QuestionnaireFeedback = ref('')
const step6QuestionnaireDraft = ref('')
interface Step6QItem {
  id: string
  indicator_id?: string
  indicator_name?: string
  question: string
  options: string[]
  source_note?: string
  model_name?: string
}
const step6QuestionnaireItems = ref<Step6QItem[]>([])
// step6 试填：本地 mock，不走后端
const step6RespondentRole = ref<'村民' | '村两委' | '镇政府' | '其他'>('村民')
const step6Answers = ref<Record<string, string>>({})
interface Step6ResponseRecord {
  version: number
  respondent_role: string
  answers: Record<string, string>
  submitted_at: string
}
const step6ResponseHistory = ref<Step6ResponseRecord[]>([])
const step6Exporting = ref(false)

// step6 拖拽：把 currentResult.scored_tree 拷贝成可编辑结构，拖拽后回写
interface Step6L3Node {
  id: string
  name: string
  score: number
  key_points?: string
  rubric?: Record<string, string>
}
interface Step6L2Node {
  name: string
  score: number
  level3: Step6L3Node[]
}
interface Step6L1Node {
  name: string
  score: number
  level2: Step6L2Node[]
}
const step6Tree = ref<Step6L1Node[]>([])
const step6TreeDirty = ref(false)
const step6L1ListRef = ref<HTMLElement | null>(null)
const step6L2ListRefs = ref<Record<string, HTMLElement | null>>({})
const step6L3ListRefs = ref<Record<string, HTMLElement | null>>({})
const step6SortableInstances: Sortable[] = []
function setStep6L2Ref(key: string, el: Element | null) {
  step6L2ListRefs.value[key] = (el as HTMLElement | null)
}
function setStep6L3Ref(key: string, el: Element | null) {
  step6L3ListRefs.value[key] = (el as HTMLElement | null)
}

// ===== Step 7: 指标体系分析与终审成果生成 =====
interface Step7PointSlot { key: string; label: string; hint?: string; suggested_score?: number }
interface Step7PointInput { key: string; label: string; plain_text: string; score: number; deduction_reason: string }
interface Step7IndicatorForm {
  id: string
  l1_name: string
  l2_name: string
  l3_name: string
  score: number
  tag?: string
  points: Step7PointSlot[]
  rubric?: Record<string, string>
}
interface Step7AnalysisRow {
  id: string
  l1_name: string
  l2_name: string
  l3_name: string
  score: number
  obtained_score: number
  score_rate: number
  deduction_reason: string
  analysis: string
  point_inputs?: Step7PointInput[]
  model_name?: string
}
interface Step7Comparison { model_name: string; label: string; draft: string; error?: string }
const step7Form = ref<Step7IndicatorForm[]>([])
const step7Inputs = ref<Record<string, Step7PointInput[]>>({})
const step7AnalysisRows = ref<Step7AnalysisRow[]>([])
const step7BlockMd = ref('')
const step7OverallMd = ref('')
const step7FinalMd = ref('')
const step7TotalScore = ref(0)
const step7TotalFull = ref(0)
const step7OverallRate = ref(0)
const step7Comparisons = ref<Step7Comparison[]>([])
const step7ReviewFeedback = ref('')
const step7SurveySample = ref<number | null>(null)
const step7SurveyRate = ref<number | null>(null)
const step7SurveySummary = ref('')
const step7Generating = ref(false)
const step7Reviewing = ref(false)
const step7Bootstrapping = ref(false)
const step7ExportFontFamily = ref('SimSun')
const step7ExportFontSize = ref(12)
const step7ExportLineHeight = ref(1.5)
const step7MarkdownRenderer = createMarkdown()
function renderMarkdown(src: string): string {
  if (!src) return ''
  try {
    return renderSafe(step7MarkdownRenderer, src)
  } catch {
    return ''
  }
}
function step7TotalUserSum(form: Step7IndicatorForm): number {
  const pts = step7Inputs.value[form.id] || []
  return Math.round(pts.reduce((s, p) => s + (Number(p.score) || 0), 0) * 100) / 100
}
function step7ClampPoint(form: Step7IndicatorForm, pt: Step7PointInput) {
  const max = Number(form.score) || 0
  if (!Number.isFinite(pt.score) || pt.score < 0) pt.score = 0
  // 限制单要点不超过该指标满分（更精细的"sum 不超满分"在 UI 用 step7TotalUserSum 显示）
  if (pt.score > max) pt.score = max
}
const step9StyleMode = ref<'neutral' | 'sharp' | 'gentle'>('neutral')
const step14ExportSaving = ref(false)
const step14ExportFormat = ref<ExportFormat>('markdown')
const step14ExportCustomTitle = ref('')
const prevStepContent = ref('')
const prevStepViewMode = ref<'raw' | 'preview'>('raw')
// 缓存上一步的结构化结果（如 step4 的 scored_tree、step3 的 flat_l2_tasks 等），
// 供 step5+ 构造 agent payload 时回传到后端 graph
const prevStepResult = ref<Record<string, unknown> | null>(null)

const workflowStatus = ref<WorkflowStatusResponse | null>(null)
type ClientModelConfig = {
  id: string
  label: string
  provider: string
  model_name: string
  base_url: string
  api_key: string
  temperature: number
  enabled: boolean
}
const modelPresets = [
  { label: 'OpenAI · GPT-4o', provider: 'openai-compatible', model_name: 'gpt-4o', base_url: 'https://api.openai.com/v1' },
  { label: 'OpenAI · GPT-4.1', provider: 'openai-compatible', model_name: 'gpt-4.1', base_url: 'https://api.openai.com/v1' },
  { label: 'OpenAI · o3', provider: 'openai-compatible', model_name: 'o3', base_url: 'https://api.openai.com/v1' },
  { label: 'Anthropic · Claude 3.7 Sonnet', provider: 'openai-compatible', model_name: 'claude-3-7-sonnet-latest', base_url: 'https://api.anthropic.com/v1' },
  { label: 'Anthropic · Claude 3.5 Sonnet', provider: 'openai-compatible', model_name: 'claude-3-5-sonnet-latest', base_url: 'https://api.anthropic.com/v1' },
  { label: 'Google · Gemini 2.5 Pro', provider: 'openai-compatible', model_name: 'gemini-2.5-pro', base_url: 'https://generativelanguage.googleapis.com/v1beta/openai' },
  { label: 'Google · Gemini 2.5 Flash', provider: 'openai-compatible', model_name: 'gemini-2.5-flash', base_url: 'https://generativelanguage.googleapis.com/v1beta/openai' },
  { label: 'DeepSeek · DeepSeek Chat', provider: 'openai-compatible', model_name: 'deepseek-chat', base_url: 'https://api.deepseek.com/v1' },
  { label: 'DeepSeek · DeepSeek Reasoner', provider: 'openai-compatible', model_name: 'deepseek-reasoner', base_url: 'https://api.deepseek.com/v1' },
  { label: 'Alibaba Cloud · Qwen Max', provider: 'openai-compatible', model_name: 'qwen-max', base_url: 'https://dashscope.aliyuncs.com/compatible-mode/v1' },
  { label: 'Alibaba Cloud · Qwen Plus', provider: 'openai-compatible', model_name: 'qwen-plus', base_url: 'https://dashscope.aliyuncs.com/compatible-mode/v1' },
  { label: 'Alibaba Cloud · Qwen Turbo', provider: 'openai-compatible', model_name: 'qwen-turbo', base_url: 'https://dashscope.aliyuncs.com/compatible-mode/v1' },
  { label: 'Moonshot · Kimi K2', provider: 'openai-compatible', model_name: 'kimi-k2-0711-preview', base_url: 'https://api.moonshot.cn/v1' },
  { label: 'Moonshot · Moonshot v1 128k', provider: 'openai-compatible', model_name: 'moonshot-v1-128k', base_url: 'https://api.moonshot.cn/v1' },
  { label: 'Zhipu AI · GLM-4 Plus', provider: 'openai-compatible', model_name: 'glm-4-plus', base_url: 'https://open.bigmodel.cn/api/paas/v4' },
  { label: 'Zhipu AI · GLM-4 Flash', provider: 'openai-compatible', model_name: 'glm-4-flash', base_url: 'https://open.bigmodel.cn/api/paas/v4' },
  { label: 'MiniMax · abab6.5s', provider: 'openai-compatible', model_name: 'abab6.5s-chat', base_url: 'https://api.minimax.chat/v1' },
  { label: 'Baichuan · Baichuan4', provider: 'openai-compatible', model_name: 'Baichuan4', base_url: 'https://api.baichuan-ai.com/v1' },
  { label: 'Tencent · Hunyuan Turbo', provider: 'openai-compatible', model_name: 'hunyuan-turbo', base_url: 'https://api.hunyuan.cloud.tencent.com/v1' },
  { label: 'Volcengine · Doubao Pro', provider: 'openai-compatible', model_name: 'doubao-pro-32k', base_url: 'https://ark.cn-beijing.volces.com/api/v3' },
  { label: '01.AI · Yi Large', provider: 'openai-compatible', model_name: 'yi-large', base_url: 'https://api.lingyiwanwu.com/v1' },
  { label: 'Groq · Llama 3.1 70B', provider: 'openai-compatible', model_name: 'llama-3.1-70b-versatile', base_url: 'https://api.groq.com/openai/v1' },
  { label: 'Mistral · Large', provider: 'openai-compatible', model_name: 'mistral-large-latest', base_url: 'https://api.mistral.ai/v1' },
  { label: 'OpenRouter · 自定义模型', provider: 'openai-compatible', model_name: 'openrouter/auto', base_url: 'https://openrouter.ai/api/v1' },
]
function createDefaultModelConfig(): ClientModelConfig {
  return {
    id: `${Date.now()}-${Math.random().toString(16).slice(2)}`,
    label: '模型配置 1',
    provider: 'openai-compatible',
    model_name: 'gpt-4o',
    base_url: '',
    api_key: '',
    temperature: 0.2,
    enabled: true,
  }
}

function normalizeModelConfig(item: Partial<ClientModelConfig>, index: number): ClientModelConfig {
  return {
    id: item.id || `${Date.now()}-${index}-${Math.random().toString(16).slice(2)}`,
    label: item.label || `模型配置 ${index + 1}`,
    provider: item.provider || 'openai-compatible',
    model_name: item.model_name || 'gpt-4o',
    base_url: item.base_url || '',
    api_key: item.api_key || '',
    temperature: Number.isFinite(Number(item.temperature)) ? Number(item.temperature) : 0.2,
    enabled: item.enabled !== false,
  }
}

function readSavedClientModelConfigs(): ClientModelConfig[] {
  const raw = localStorage.getItem('ef_client_model_configs')
  if (raw) {
    try {
      const parsed = JSON.parse(raw)
      if (Array.isArray(parsed) && parsed.length) return parsed.map((item, index) => normalizeModelConfig(item, index))
    } catch {
      // fallback to legacy single config
    }
  }
  return [normalizeModelConfig({
    label: '模型配置 1',
    provider: localStorage.getItem('ef_client_model_provider') || 'openai-compatible',
    model_name: localStorage.getItem('ef_client_model_name') || 'gpt-4o',
    base_url: localStorage.getItem('ef_client_model_base_url') || '',
    api_key: localStorage.getItem('ef_client_model_api_key') || '',
    temperature: Number(localStorage.getItem('ef_client_model_temperature') || '0.2'),
    enabled: true,
  }, 0)]
}

const activeClientModelConfigs = ref<ClientModelConfig[]>(readSavedClientModelConfigs())
const clientModelConfigs = ref<ClientModelConfig[]>(activeClientModelConfigs.value.map((item) => ({ ...item })))
const selectedModelPresets = ref<Record<string, string>>({})
const modelConfigPage = ref(1)
const modelConfigPageSize = ref(2)
const draftHistoryPage = ref(1)
const draftHistoryPageSize = ref(2)
const pagedModelConfigs = computed(() => {
  const start = (modelConfigPage.value - 1) * modelConfigPageSize.value
  return clientModelConfigs.value.slice(start, start + modelConfigPageSize.value).map((item, offset) => ({ item, index: start + offset }))
})
const pagedStep1DraftHistory = computed(() => {
  const start = (draftHistoryPage.value - 1) * draftHistoryPageSize.value
  return step1DraftHistory.value.slice(start, start + draftHistoryPageSize.value).map((item, offset) => ({ item, index: start + offset }))
})
const enabledActiveModelConfigs = computed(() => activeClientModelConfigs.value.filter((item) => item.enabled && item.base_url && item.api_key && item.model_name))
const primaryActiveModelConfig = computed(() => enabledActiveModelConfigs.value[0] ?? activeClientModelConfigs.value[0] ?? createDefaultModelConfig())
const hasUnsavedModelConfig = computed(() => JSON.stringify(clientModelConfigs.value) !== JSON.stringify(activeClientModelConfigs.value))
const activeModelSummary = computed(() => enabledActiveModelConfigs.value.length
  ? `当前生效 ${enabledActiveModelConfigs.value.length} 个模型：${enabledActiveModelConfigs.value.map((item) => `${item.label}/${item.model_name}(T=${item.temperature})`).join('；')}`
  : '尚未保存完整模型配置，生成前请至少启用并保存一个包含 Base URL、API Key、模型名和 Temperature 的模型。')
const steps = computed(() => Array.from({ length: workflowStatus.value?.total_steps ?? 14 }, (_, i) => {
  const id = i + 1
  const item = workflowStatus.value?.steps.find((statusItem) => statusItem.step_code === `step${id}`)
  const shortTitles: Record<number, string> = {
    1: '项目资料清单', 2: '有效项目资料', 3: '指标体系', 4: '生成分值',
    5: '评分标准', 6: '现场评价表', 7: '得分与分析', 8: '经验做法',
    9: '问题及原因', 10: '整改建议', 11: '综合分析', 12: '基础信息',
    13: '工作情况', 14: '评价报告',
  }
  return { id, title: shortTitles[id] ?? `Step ${id}`, done: Boolean(item?.done) }
}))
const taskProgress = computed(() => ({
  status: workflowStatus.value?.status ?? 'queued',
  percent: workflowStatus.value?.progress ?? 0,
  doneSteps: workflowStatus.value?.done_steps ?? 0,
  totalSteps: workflowStatus.value?.total_steps ?? 14,
}))
const canGenerate = computed(() => {
  if (!enabledActiveModelConfigs.value.length) return false
  if (stepId.value === 3) {
    const step2Core = step3State.value?.final_core_content ?? step3State.value?.content_text ?? step3State.value?.core_content_draft
    return typeof step2Core === 'string' && step2Core.trim().length > 0
  }
  if (stepId.value === 4) return step4FlatL2Tasks.value.length > 0
  if (stepId.value >= 5 && stepId.value <= 14) return prevStepContent.value.trim().length > 0 || !isEditorEmpty()
  return inputProjectFiles.value.length > 0
})
const mediaFiles = computed(() => inputProjectFiles.value.filter((item) => isMediaFile(item.file_type, item.file_name)))
const documentFiles = computed(() => inputProjectFiles.value.filter((item) => !isMediaFile(item.file_type, item.file_name)))
const promptHintMap: Record<number, string> = {
  1: '上传项目资料，系统会自动生成资料清单草稿',
  2: '资料上传后会自动区分图片/PDF 与 Word/Excel 两个通道，先确认资料识别结果，再生成有效项目资料',
  3: '输入体系类型、层级约束、模板要求',
  4: '输入总分、父子约束与校验规则',
  5: '输入评分口径、分档规则与描述风格',
  14: '输入报告结构、版式要求、章节顺序',
}

const titleMap: Record<number, string> = {
  1: 'Step1 · 项目资料清单',
  2: 'Step2 · 有效项目资料',
  3: 'Step3 · 指标体系',
  4: 'Step4 · 生成分值',
  5: 'Step5 · 评分标准',
  6: 'Step6 · 现场评价表',
  7: 'Step7 · 得分与分析',
  8: 'Step8 · 经验做法',
  9: 'Step9 · 问题及原因',
  10: 'Step10 · 整改建议',
  11: 'Step11 · 综合分析',
  12: 'Step12 · 基础信息',
  13: 'Step13 · 工作情况',
  14: 'Step14 · 评价报告',
}

function isMediaFile(fileType?: string, fileName = '') {
  const value = `${fileType || ''} ${fileName}`.toLowerCase()
  return ['.png', '.jpg', '.jpeg', '.webp', '.gif', '.bmp', '.tiff', '.pdf'].some((suffix) => value.endsWith(suffix) || value.includes(`${suffix} `) || value.includes(`.${suffix.replace('.', '')}`))
}

function isVisionCapableModel(config: { label?: string; model_name?: string }) {
  const blob = `${config.label || ''} ${config.model_name || ''}`.toLowerCase()
  const keywords = ['vision', 'vl', 'omni', 'multimodal', 'gpt-4o', 'gpt-4.1', 'claude-3', 'gemini', 'qwen-vl', 'yi-vl']
  return keywords.some((keyword) => blob.includes(keyword))
}

function goStep(n: number) {
  router.push({ path: `/app/projects/${projectId.value}/workflow/${n}`, query: { step: String(n) } })
}

const currentStepSections = computed<Array<{ id: string; label: string }>>(() => {
  const sid = stepId.value
  const common = [{ id: 'sec-model-config', label: '客户端模型配置' }]
  if (sid === 1) {
    return [
      ...common,
      { id: 'sec-step1-input', label: '输入资料与草稿' },
      { id: 'sec-step1-draft', label: '草稿编辑' },
      { id: 'sec-step1-analysis', label: '结构化分析' },
      { id: 'sec-step1-history', label: '草稿版本历史' },
      { id: 'sec-step1-export', label: '成果区与导出' },
      { id: 'sec-artifact-editor', label: '最终成品编辑' },
      { id: 'sec-backend-result', label: '后端结果' },
    ]
  }
  if (sid === 2) {
    return [
      ...common,
      { id: 'sec-step2-upload', label: '资料上传' },
      { id: 'sec-step2-categories', label: '资料分类管理' },
      { id: 'sec-step2-models', label: '通道模型选择' },
      { id: 'sec-step2-digest', label: '校验摘要' },
      { id: 'sec-step2-compare', label: '多模型对比' },
      { id: 'sec-step2-review', label: '复核与精修' },
      { id: 'sec-step2-export', label: '导出成品' },
      { id: 'sec-artifact-editor', label: '最终成品编辑' },
      { id: 'sec-backend-result', label: '后端结果' },
    ]
  }
  if (sid === 3) {
    const phase = step3SkeletonPhase.value
    const list = [...common]
    if (phase === 'config') list.push({ id: 'sec-step3-config', label: '指标体系配置' })
    if (phase === 'skeleton' || phase === 'generating_l3') list.push({ id: 'sec-step3-skeleton', label: '骨架管理' })
    if (phase === 'generating_l3') list.push({ id: 'sec-step3-l3', label: '三级指标生成' })
    if (phase === 'completed') list.push({ id: 'sec-step3-finalize', label: '收尾与定稿' })
    list.push({ id: 'sec-artifact-editor', label: '最终成品编辑' })
    list.push({ id: 'sec-backend-result', label: '后端结果' })
    return list
  }
  if (sid === 4) {
    return [
      ...common,
      { id: 'sec-step4-scoring', label: '分值配置' },
      { id: 'sec-artifact-editor', label: '最终成品编辑' },
      { id: 'sec-backend-result', label: '后端结果' },
    ]
  }
  if (sid === 9) {
    return [
      ...common,
      { id: 'sec-step9-style', label: '评价结论与语气' },
      { id: 'sec-artifact-editor', label: '最终成品编辑' },
      { id: 'sec-backend-result', label: '后端结果' },
    ]
  }
  if (sid === 14) {
    return [
      ...common,
      { id: 'sec-step14-export', label: '评价报告与导出' },
      { id: 'sec-artifact-editor', label: '最终成品编辑' },
      { id: 'sec-backend-result', label: '后端结果' },
    ]
  }
  return [
    ...common,
    { id: 'sec-stepN-prev', label: '上一步内容' },
    { id: 'sec-artifact-editor', label: '最终成品编辑' },
    { id: 'sec-backend-result', label: '后端结果' },
  ]
})

function scrollToSection(sectionId: string) {
  const el = document.getElementById(sectionId)
  if (!el) return
  const top = el.getBoundingClientRect().top + window.scrollY - 80
  window.scrollTo({ top, behavior: 'smooth' })
}

function stepCodeOf(value = stepId.value) {
  return `step${value}`
}

function extractResult(res: AgentRunResponse) {
  return res.result?.result ?? res.result
}

function getStep1ExportContent() {
  const candidates = [
    editor.value,
    typeof currentResult.value?.final_manifest === 'string' ? currentResult.value.final_manifest : '',
    typeof currentResult.value?.draft_manifest === 'string' ? currentResult.value.draft_manifest : '',
    typeof currentResult.value?.content_text === 'string' ? currentResult.value.content_text : '',
  ]
  return candidates.find((item) => item.trim() && !placeholderEditorTexts.includes(item.trim()))?.trim() || ''
}

function openStep1ExportDialog() {
  if (stepId.value !== 1) return
  const content = getStep1ExportContent()
  if (!content) {
    ElMessage.warning('当前没有可导出的 Step1 成果，请先生成资料清单或在成品区编辑真实内容')
    return
  }
  if (editor.value.trim() !== content) editor.value = content
  exportCustomTitle.value = `${getGlobalProjectName()}项目资料清单`
  lastExportUrl.value = ''
  lastExportFileName.value = ''
  exportDialogVisible.value = true
}

async function downloadLastStep1Export() {
  if (!lastExportUrl.value || !lastExportFileName.value) return
  try {
    await downloadExportFile(lastExportUrl.value, lastExportFileName.value)
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : '下载失败')
  }
}

async function submitStep1Export(downloadAfter = true) {
  const content = getStep1ExportContent()
  if (!content) {
    ElMessage.warning('当前没有可导出的 Step1 成果，请先生成资料清单或在成品区编辑真实内容')
    return
  }
  exportSaving.value = true
  try {
    const response = await exportStep1(projectId.value, {
      project_name: getGlobalProjectName(),
      thread_id: step1ThreadId.value,
      content_text: content,
      content_json: resultText.value,
      export_style: exportStyle.value,
      export_format: exportFormat.value,
      custom_title: exportCustomTitle.value,
      save_to_database: false,
    })
    lastExportUrl.value = response.download_url
    lastExportFileName.value = response.file_name
    if (downloadAfter) {
      await downloadExportFile(response.download_url, response.file_name)
      const tip = exportFormat.value === 'markdown' ? 'Markdown' : 'Word'
      ElMessage.success(`Step1 成果 ${tip} 已导出并开始下载`)
    } else {
      ElMessage.success('Step1 成果文件已生成，可点击「下载上次导出」')
    }
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : '导出失败')
  } finally {
    exportSaving.value = false
  }
}

function openConfirmDialog(options: {
  title: string
  message: string
  type?: 'warning' | 'danger' | 'info'
  okText?: string
  action: () => Promise<void> | void
}) {
  confirmDialogTitle.value = options.title
  confirmDialogMessage.value = options.message
  confirmDialogType.value = options.type ?? 'warning'
  confirmDialogOkText.value = options.okText ?? '确定'
  pendingConfirmAction.value = options.action
  confirmDialogVisible.value = true
}

async function runPendingConfirmAction() {
  const action = pendingConfirmAction.value
  confirmDialogVisible.value = false
  pendingConfirmAction.value = null
  if (action) await action()
}

function extractProjectNameFromFile(file: FileRecord) {
  const metadata = file.metadata_json ? parseMaybeJson(file.metadata_json) : null
  const candidates = [
    file.project_name,
    typeof metadata?.['project_name'] === 'string' ? metadata['project_name'] : '',
    typeof metadata?.['projectName'] === 'string' ? metadata['projectName'] : '',
    file.file_name,
  ]
  return candidates.find((item) => typeof item === 'string' && item.trim())?.trim() || ''
}

function setProjectName(name: string) {
  const value = name.trim()
  if (!value) return
  projectName.value = value
  localStorage.setItem('ef_project_name', value)
}

function genericStepDraftKey(stepCode: string) {
  return `ef_${stepCode}_draft:${projectId.value}:${stepCode}:${projectId.value}`
}

function saveGenericStepDraft(stepCode: string, draft: Record<string, unknown>) {
  if (!projectId.value || !stepCode) return
  try {
    localStorage.setItem(genericStepDraftKey(stepCode), JSON.stringify({ ...draft, _saved_at: Date.now() }))
  } catch { /* quota / serialize errors are non-fatal */ }
}

function loadGenericStepDraft(stepCode: string): Record<string, unknown> | null {
  if (!projectId.value || !stepCode) return null
  const raw = localStorage.getItem(genericStepDraftKey(stepCode))
  if (!raw) return null
  try {
    const parsed = JSON.parse(raw)
    return parsed && typeof parsed === 'object' && !Array.isArray(parsed) ? parsed as Record<string, unknown> : null
  } catch {
    return null
  }
}

function clearGenericStepDraft(stepCode: string) {
  if (!projectId.value || !stepCode) return
  localStorage.removeItem(genericStepDraftKey(stepCode))
}

async function clearStepShortTermMemory(stepCode: string, threadId?: string) {
  // 兜底清理：同时清掉前端 localStorage 通用草稿 + 后端 MemorySaver thread + memory_session 短期记录
  clearGenericStepDraft(stepCode)
  const tid = (threadId && threadId.trim()) || `${stepCode}:${projectId.value}`
  try {
    await clearThreadState({ step_code: stepCode, thread_id: tid, project_id: projectId.value, role: 'client' })
  } catch (e) {
    console.warn(`[step-memory] clear ${stepCode} thread failed`, e)
  }
}

function saveStep1DraftState(draft: Record<string, unknown>) {
  localStorage.setItem(step1DraftKey.value, JSON.stringify(draft))
}

function loadStep1DraftHistory() {
  const raw = localStorage.getItem(step1DraftHistoryKey.value)
  if (!raw) {
    step1DraftHistory.value = []
    return
  }
  try {
    const parsed = JSON.parse(raw)
    step1DraftHistory.value = Array.isArray(parsed) ? parsed.filter((item) => item && typeof item.content === 'string') : []
  } catch {
    step1DraftHistory.value = []
  }
}

function saveStep1DraftHistory() {
  localStorage.setItem(step1DraftHistoryKey.value, JSON.stringify(step1DraftHistory.value))
}

function pushStep1DraftSnapshot(content: string, source: string) {
  const value = content.trim()
  if (!value || placeholderEditorTexts.includes(value)) return
  const latest = step1DraftHistory.value[0]
  if (latest?.content.trim() === value) return
  step1DraftHistory.value = [
    {
      id: `${Date.now()}-${Math.random().toString(16).slice(2)}`,
      title: `未提交草稿 v${step1DraftHistory.value.length + 1}`,
      content: value,
      source,
      created_at: new Date().toISOString(),
    },
    ...step1DraftHistory.value,
  ].slice(0, 20)
  saveStep1DraftHistory()
}

function deleteStep1DraftSnapshot(index: number) {
  const item = step1DraftHistory.value[index]
  if (!item) return
  openConfirmDialog({
    title: '删除未提交草稿',
    message: `确定删除「${item.title}（${item.source}）」吗？该版本将从内存与本地缓存中移除。`,
    type: 'danger',
    okText: '删除',
    action: async () => {
      step1DraftHistory.value.splice(index, 1)
      delete draftPreviewModes.value[item.id]
      saveStep1DraftHistory()
      ElMessage.success('已删除该草稿版本')
    },
  })
}

function restoreStep1DraftSnapshot(index: number) {
  const item = step1DraftHistory.value[index]
  if (!item) return
  editor.value = item.content
  const nextResult = {
    ...(currentResult.value ?? {}),
    draft_manifest: item.content,
    final_manifest: item.content,
    status: 'human_review',
    review_mode: 'modify',
    approved: false,
    source: 'rollback_memory',
    restored_from: item.id,
    updated_at: new Date().toISOString(),
  }
  currentResult.value = nextResult
  resultText.value = JSON.stringify(nextResult, null, 2)
  saveStep1DraftState({
    project_id: projectId.value,
    thread_id: step1ThreadId.value,
    content_text: item.content,
    content_json: resultText.value,
    current_result: nextResult,
    project_name: projectName.value,
    project_files: inputProjectFiles.value,
    status: 'human_review',
    review_mode: 'modify',
    approved: false,
    updated_at: new Date().toISOString(),
  })
  ElMessage.success('已回滚到未提交草稿历史，当前仍处于人工复核状态')
}

function loadStep1DraftState() {
  const raw = localStorage.getItem(step1DraftKey.value)
  if (!raw) return null
  try {
    const parsed = JSON.parse(raw)
    return parsed && typeof parsed === 'object' ? parsed as Record<string, unknown> : null
  } catch {
    return null
  }
}

function clearStep1DraftState() {
  localStorage.removeItem(step1DraftKey.value)
  localStorage.removeItem(step1DraftHistoryKey.value)
  step1DraftHistory.value = []
}

function saveStep2DraftState() {
  const draft = {
    project_id: projectId.value,
    thread_id: step2ThreadId.value,
    editor: editor.value,
    result_text: resultText.value,
    current_result: currentResult.value,
    verification_digest: step2VerificationDigest.value,
    parse_warnings: step2ParseWarnings.value,
    model_comparisons: step2ModelComparisons.value,
    source_index: step2SourceIndex.value,
    media_metadata: step2MediaMetadata.value,
    docs_metadata: step2DocsMetadata.value,
    status_text: step2StatusText.value,
    default_categories: step2DefaultCategories.value,
    extra_categories: step2ExtraCategories.value,
    review_mode: step2ReviewMode.value,
    review_feedback: step2ReviewFeedback.value,
    verification_ack: step2VerificationAck.value,
    active_compare_index: step2ActiveCompareIndex.value,
    updated_at: new Date().toISOString(),
  }
  localStorage.setItem(step2DraftKey.value, JSON.stringify(draft))
}

function loadStep2DraftState(): Record<string, unknown> | null {
  const raw = localStorage.getItem(step2DraftKey.value)
  if (!raw) return null
  try {
    const parsed = JSON.parse(raw)
    return parsed && typeof parsed === 'object' ? parsed as Record<string, unknown> : null
  } catch {
    return null
  }
}

function restoreStep2DraftState(draft: Record<string, unknown>) {
  if (typeof draft.editor === 'string' && draft.editor.trim() && !placeholderEditorTexts.includes(draft.editor.trim())) {
    editor.value = draft.editor
  }
  if (typeof draft.result_text === 'string') resultText.value = draft.result_text
  if (draft.current_result && typeof draft.current_result === 'object') {
    currentResult.value = draft.current_result as Record<string, unknown>
  }
  if (typeof draft.verification_digest === 'string') step2VerificationDigest.value = draft.verification_digest
  if (Array.isArray(draft.parse_warnings)) step2ParseWarnings.value = draft.parse_warnings.map(String)
  if (Array.isArray(draft.model_comparisons)) step2ModelComparisons.value = draft.model_comparisons as typeof step2ModelComparisons.value
  if (Array.isArray(draft.source_index)) step2SourceIndex.value = draft.source_index as typeof step2SourceIndex.value
  if (Array.isArray(draft.media_metadata)) step2MediaMetadata.value = draft.media_metadata as typeof step2MediaMetadata.value
  if (Array.isArray(draft.docs_metadata)) step2DocsMetadata.value = draft.docs_metadata as typeof step2DocsMetadata.value
  if (typeof draft.status_text === 'string') step2StatusText.value = draft.status_text
  if (Array.isArray(draft.default_categories)) step2DefaultCategories.value = draft.default_categories.map(String)
  if (Array.isArray(draft.extra_categories)) step2ExtraCategories.value = draft.extra_categories.map(String)
  if (draft.review_mode === 'approve' || draft.review_mode === 'modify') step2ReviewMode.value = draft.review_mode
  if (typeof draft.review_feedback === 'string') step2ReviewFeedback.value = draft.review_feedback
  if (typeof draft.verification_ack === 'boolean') step2VerificationAck.value = draft.verification_ack
  if (typeof draft.active_compare_index === 'number') step2ActiveCompareIndex.value = draft.active_compare_index
}

function clearStep2DraftState() {
  localStorage.removeItem(step2DraftKey.value)
}

function saveStep3DraftState() {
  const draft = {
    project_id: projectId.value,
    skeleton_tasks: step3SkeletonTasks.value,
    active_l2_index: step3ActiveL2Index.value,
    l3_draft: step3L3Draft.value,
    skeleton_phase: step3SkeletonPhase.value,
    config: step3Config.value,
    updated_at: new Date().toISOString(),
  }
  localStorage.setItem(step3DraftKey.value, JSON.stringify(draft))
}

function loadStep3DraftState(): Record<string, unknown> | null {
  const raw = localStorage.getItem(step3DraftKey.value)
  if (!raw) return null
  try {
    const parsed = JSON.parse(raw)
    return parsed && typeof parsed === 'object' ? parsed as Record<string, unknown> : null
  } catch {
    return null
  }
}

function restoreStep3DraftState(draft: Record<string, unknown>) {
  if (Array.isArray(draft.skeleton_tasks) && draft.skeleton_tasks.length) {
    step3SkeletonTasks.value = draft.skeleton_tasks as typeof step3SkeletonTasks.value
  }
  if (typeof draft.active_l2_index === 'number') {
    step3ActiveL2Index.value = Math.max(0, Math.min(step3SkeletonTasks.value.length - 1, draft.active_l2_index))
  }
  if (typeof draft.l3_draft === 'string') {
    step3L3Draft.value = draft.l3_draft
  }
  const phase = draft.skeleton_phase
  if (phase === 'config' || phase === 'skeleton' || phase === 'generating_l3' || phase === 'completed') {
    step3SkeletonPhase.value = phase
  }
  if (draft.config && typeof draft.config === 'object') {
    const cfg = draft.config as Record<string, unknown>
    if (typeof cfg.system_type === 'string') step3Config.value.system_type = cfg.system_type
    if (typeof cfg.indicator_depth === 'number') step3Config.value.indicator_depth = cfg.indicator_depth as 3 | 4
    if (typeof cfg.import_mode === 'string') step3Config.value.import_mode = cfg.import_mode
    if (typeof cfg.template_id === 'string') step3Config.value.template_id = cfg.template_id
    if (typeof cfg.skeleton_optimize_mode === 'string') step3Config.value.skeleton_optimize_mode = cfg.skeleton_optimize_mode
  }
}

function clearStep3DraftState() {
  localStorage.removeItem(step3DraftKey.value)
}

async function loadProjectFiles() {
  if (!projectId.value) return
  try {
    projectFiles.value = await listFiles(projectId.value)
    const extracted = projectFiles.value.map(extractProjectNameFromFile).find((name) => Boolean(name))
    if (extracted) setProjectName(extracted)
  } catch {
    projectFiles.value = []
  }
}

function loadStep1DraftIntoEditor() {
  const draft = loadStep1DraftState()
  if (!draft) return
  const content = draft.content_text
  if (typeof content === 'string' && content.trim() && !placeholderEditorTexts.includes(content.trim())) {
    editor.value = content
    resultText.value = typeof draft.content_json === 'string' ? draft.content_json : resultText.value
    const savedResult = draft.current_result as Record<string, unknown> | null | undefined
    currentResult.value = savedResult && typeof savedResult === 'object' ? savedResult : draft
  }
}

function persistModelConfig() {
  const existed = Boolean(localStorage.getItem('ef_client_model_configs'))
  const normalized = clientModelConfigs.value.map((item, index) => normalizeModelConfig(item, index))
  clientModelConfigs.value = normalized.map((item) => ({ ...item }))
  activeClientModelConfigs.value = normalized.map((item) => ({ ...item }))
  localStorage.setItem('ef_client_model_configs', JSON.stringify(activeClientModelConfigs.value))
  const primary = primaryActiveModelConfig.value
  localStorage.setItem('ef_client_model_provider', primary.provider)
  localStorage.setItem('ef_client_model_name', primary.model_name)
  localStorage.setItem('ef_client_model_base_url', primary.base_url)
  localStorage.setItem('ef_client_model_api_key', primary.api_key)
  localStorage.setItem('ef_client_model_temperature', String(primary.temperature))
  ElMessage.success(existed ? '多模型配置已更新并生效' : '多模型配置已保存并生效')
}

function addModelConfig() {
  const next = createDefaultModelConfig()
  next.label = `模型配置 ${clientModelConfigs.value.length + 1}`
  clientModelConfigs.value.push(next)
  modelConfigPage.value = Math.ceil(clientModelConfigs.value.length / modelConfigPageSize.value)
}

function removeModelConfig(index: number) {
  if (clientModelConfigs.value.length <= 1) {
    ElMessage.warning('至少保留一个模型配置窗口')
    return
  }
  clientModelConfigs.value.splice(index, 1)
  modelConfigPage.value = Math.min(modelConfigPage.value, Math.max(1, Math.ceil(clientModelConfigs.value.length / modelConfigPageSize.value)))
}

function applyModelPreset(index: number, value: string) {
  selectedModelPresets.value[clientModelConfigs.value[index]?.id || String(index)] = value
  const preset = modelPresets.find((item) => item.model_name === value)
  const config = clientModelConfigs.value[index]
  if (!preset || !config) return
  config.label = preset.label
  config.provider = preset.provider
  config.model_name = preset.model_name
  config.base_url = preset.base_url
}

function setClientModelTemperature(index: number, value: number) {
  const config = clientModelConfigs.value[index]
  if (!config) return
  const normalized = Number.isFinite(value) ? Math.min(2, Math.max(0, value)) : 0.2
  config.temperature = Number(normalized.toFixed(2))
}

function openUploadDialog(channel: 'media' | 'documents') {
  uploadingChannel.value = channel
  uploadQueue.value = []
  uploadDialogVisible.value = true
}

function onRequestUpload(payload: { material: string }) {
  gapUploadPickerMaterial.value = payload.material
  gapUploadPickerVisible.value = true
}

function pickGapUploadChannel(channel: 'media' | 'documents') {
  gapUploadPickerVisible.value = false
  const channelLabel = channel === 'media' ? '图片 / PDF' : '文档'
  ElMessage.info(`补齐资料：${gapUploadPickerMaterial.value} → ${channelLabel}通道`)
  openUploadDialog(channel)
}

function clearUploadQueue() {
  uploadQueue.value = []
}

const handleUploadExceed: UploadProps['onExceed'] = () => {
  ElMessage.warning('已达到上传上限，请先删除部分文件')
}

function acceptTypes(channel: 'media' | 'documents') {
  return channel === 'media'
    ? '.png,.jpg,.jpeg,.webp,.gif,.bmp,.tiff,.pdf'
    : '.doc,.docx,.xls,.xlsx,.ppt,.pptx,.txt,.csv,.md,.pdf'
}

function beforeUpload(file: File) {
  const ext = `.${file.name.split('.').pop()?.toLowerCase() || ''}`
  if (uploadingChannel.value === 'media') {
    return ['.png', '.jpg', '.jpeg', '.webp', '.gif', '.bmp', '.tiff', '.pdf'].includes(ext)
  }
  return ['.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx', '.txt', '.csv', '.md', '.pdf'].includes(ext)
}

function inferProjectNameFromFileName(fileName: string) {
  const base = fileName.replace(/\.[^.]+$/, '').trim()
  if (!base) return ''
  const cleaned = base
    .replace(/^(项目|project|方案|资料|报告|附件)[_\-\s]*/i, '')
    .replace(/[_\-]+/g, ' ')
    .trim()
  return cleaned || base
}

async function uploadQueuedFiles() {
  if (!uploadQueue.value.length) {
    ElMessage.warning('请先选择要上传的文件')
    return
  }
  uploading.value = true
  try {
    for (const item of uploadQueue.value) {
      if (!item.raw) continue
      const uploaded = await uploadProjectFile(projectId.value, item.raw)
      ElMessage.success(`已上传：${uploaded.file_name}`)
      const candidateName =
        extractProjectNameFromFile(uploaded) ||
        inferProjectNameFromFileName(uploaded.file_name) ||
        inferProjectNameFromFileName(item.name)
      if (candidateName) setProjectName(candidateName)
    }
    uploadDialogVisible.value = false
    uploadQueue.value = []
    const draft = loadStep1DraftState()
    if (draft) {
      saveStep1DraftState({
        ...draft,
        upload_count: Array.isArray(draft.upload_count) ? draft.upload_count : undefined,
      })
    }
    await loadProjectFiles()
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : '上传失败')
  } finally {
    uploading.value = false
  }
}

function handleFileChange(uploadFile: UploadFile) {
  if (!uploadFile.raw) return
  const ok = beforeUpload(uploadFile.raw)
  if (!ok) {
    ElMessage.warning(uploadingChannel.value === 'media' ? '图片 / PDF 通道仅支持图片和 PDF 文件' : '文档通道仅支持 Word / Excel / 文本 / PDF 文件')
    uploadQueue.value = uploadQueue.value.filter((item) => item.uid !== uploadFile.uid)
    return
  }
  if (!uploadQueue.value.some((item) => item.uid === uploadFile.uid)) {
    uploadQueue.value.push(uploadFile)
  }
}

async function removeProjectFile(fileId: string, fileName = '') {
  openConfirmDialog({
    title: '删除 Step1 资料',
    message: fileName ? `确定删除资料「${fileName}」吗？删除后数据库记录也会同步移除。` : '确定删除这条资料记录吗？删除后数据库记录也会同步移除。',
    type: 'danger',
    okText: '删除',
    action: async () => {
      try {
        await deleteFile(projectId.value, fileId)
        ElMessage.success('资料记录已删除')
        await loadProjectFiles()
      } catch (e) {
        ElMessage.error(e instanceof Error ? e.message : '删除失败')
      }
    },
  })
}

async function loadHistories() {
  if (!projectId.value) return
  try {
    const items = await listStepHistories(stepCodeOf(), projectId.value)
    historyItems.value = items.map((item) => ({
      id: item.id,
      title: `${item.title} v${item.version}`,
      desc: item.is_final ? '最终版本' : '草稿',
      content: item.content_text || item.content_json || '',
      content_json: item.content_json || undefined,
    }))
  } catch {
    historyItems.value = []
  }
}

async function loadWorkflowStatus() {
  if (!projectId.value) return
  try {
    workflowStatus.value = await getWorkflowStatus(projectId.value)
    if (stepId.value === 2 && !inputProjectFiles.value.length) {
      ElMessage.warning('当前资料清单为空，请先上传资料后再生成 Step2')
    }
  } catch {
    workflowStatus.value = null
  }
}

async function loadResult() {
  await Promise.all([loadProjectFiles(), loadHistories(), loadWorkflowStatus()])
  if (stepId.value === 1) {
    loadStep1DraftHistory()
    loadStep1DraftIntoEditor()
    try {
      const files = await listFiles(projectId.value)
      const commits = files.filter((f) => f.source_type === 'step1_draft_commit')
      let committed: FileRecord | null = null
      let committedTime = ''
      for (const f of commits) {
        let ts = ''
        if (f.metadata_json) {
          try {
            const m = JSON.parse(f.metadata_json) as Record<string, unknown>
            if (typeof m.updated_at === 'string') ts = m.updated_at
          } catch {
            ts = ''
          }
        }
        if (!committed || ts > committedTime) {
          committed = f
          committedTime = ts
        }
      }
      if (committed?.metadata_json) {
        let metadata: Record<string, unknown> | null = null
        try {
          const parsed = JSON.parse(committed.metadata_json)
          if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
            metadata = parsed as Record<string, unknown>
          }
        } catch {
          metadata = null
        }
        if (metadata) {
          const savedResult = (metadata.current_result && typeof metadata.current_result === 'object')
            ? metadata.current_result as Record<string, unknown>
            : null
          const previousResult = (currentResult.value && typeof currentResult.value === 'object')
            ? currentResult.value as Record<string, unknown>
            : {}
          const merged: Record<string, unknown> = {
            ...(savedResult ?? {}),
            ...previousResult,
          }
          if (savedResult?.structured_analysis && !previousResult.structured_analysis) {
            merged.structured_analysis = savedResult.structured_analysis
          }
          currentResult.value = merged
          if (!editor.value.trim() && typeof metadata.content_text === 'string' && metadata.content_text.trim()) {
            editor.value = metadata.content_text
          }
          if (!resultText.value && typeof metadata.content_json === 'string') {
            resultText.value = metadata.content_json
          }
        }
      }
    } catch {
      // step1 not committed yet — keep localStorage-restored state
    }
  }
  if (stepId.value === 3) {
    try {
      const prevStep = await getStepResult('step2', projectId.value)
      const rawResult = (prevStep.result as Record<string, unknown>) || null
      let step2Full: Record<string, unknown> | null = null
      if (rawResult && typeof rawResult === 'object') {
        const cj = rawResult.content_json
        if (typeof cj === 'string' && cj.trim()) {
          try {
            const parsed = JSON.parse(cj)
            if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
              step2Full = parsed as Record<string, unknown>
            }
          } catch { /* ignore parse error */ }
        }
        if (!step2Full) {
          step2Full = rawResult
        }
        if (step2Full && !step2Full.content_text && rawResult.content_text) {
          step2Full.content_text = rawResult.content_text
        }
      }
      step3State.value = step2Full
    } catch {
      step3State.value = null
    }
    try {
      const res = await getStepResult(stepCodeOf(), projectId.value)
      const currentStepResult = (res.result as Record<string, unknown>) || null
      if (currentStepResult) {
        const core = currentStepResult.final_indicator_markdown || currentStepResult.content_text
        if (typeof core === 'string' && core.trim()) {
          editor.value = core
        }
        currentResult.value = currentStepResult
        resultText.value = JSON.stringify(currentStepResult, null, 2)
      }
    } catch {
      // ignore if step3 has not been generated yet
    }
  }
  if (stepId.value === 3 && !currentResult.value) {
    currentResult.value = step3State.value
  }
  if (stepId.value === 3) {
    if (currentResult.value) {
      syncStep3FromResult(currentResult.value)
    }
    // If backend has no step3 result yet, restore in-progress draft from localStorage.
    if (!step3SkeletonTasks.value.length) {
      const localDraft = loadStep3DraftState()
      if (localDraft) {
        restoreStep3DraftState(localDraft)
      }
    }
    finalizeStep3Workflow()
  } else if (stepId.value === 2) {
    let restoredFromBackend = false
    try {
      const res = await getStepResult('step2', projectId.value)
      const rawResult = (res.result as Record<string, unknown>) || null
      // Backend wraps actual agent payload in StepOutput row; unwrap content_json for full state.
      let step2Result: Record<string, unknown> | null = null
      if (rawResult && typeof rawResult === 'object') {
        const cj = rawResult.content_json
        if (typeof cj === 'string' && cj.trim()) {
          try {
            const parsed = JSON.parse(cj)
            if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
              step2Result = parsed as Record<string, unknown>
            }
          } catch {
            step2Result = null
          }
        }
        if (!step2Result && (rawResult.model_comparisons || rawResult.verification_digest)) {
          step2Result = rawResult
        }
        if (!step2Result && (rawResult.id || rawResult.content_text)) {
          // Fallback: only the StepOutput row was returned, treat content_text as final core content.
          step2Result = {
            content_text: rawResult.content_text,
            status: rawResult.status || 'saved',
          }
        }
      }
      if (step2Result) {
        currentResult.value = step2Result
        resultText.value = JSON.stringify(step2Result, null, 2)
        const comparisons = Array.isArray(step2Result.model_comparisons)
          ? (step2Result.model_comparisons as Array<{ model_name?: string; label?: string; provider?: string; channel?: string; temperature?: number; draft?: string; error?: string }>)
          : []
        extractStep2State(step2Result, comparisons)
        step2DraftDirty.value = false
        step2LastCommittedAt.value = (rawResult as { updated_at?: string } | null)?.updated_at || step2LastCommittedAt.value
        restoredFromBackend = comparisons.length > 0 || Boolean(step2Result.verification_digest)
      }
    } catch {
      // step2 not generated yet
    }
    if (!restoredFromBackend) {
      const localDraft = loadStep2DraftState()
      if (localDraft) restoreStep2DraftState(localDraft)
    }
    try {
      const step1Res = await getStepResult('step1', projectId.value)
      const step1Result = (step1Res.result as Record<string, unknown>) || null
      const step1Sa = step1Result?.structured_analysis
      if (step1Sa) {
        currentResult.value = {
          ...(currentResult.value ?? {}),
          structured_analysis: step1Sa,
        }
      }
    } catch { /* step1 not available */ }
  } else if (stepId.value !== 1) {
    if (stepId.value === 4) {
      try {
        const step3Res = await getStepResult('step3', projectId.value)
        const rawResult = (step3Res.result as Record<string, unknown>) || null
        if (rawResult && !rawResult.id && !rawResult.content_json && !rawResult.content_text) {
          console.warn('[Step4] Step3 result is empty — step3 may not have been saved yet.', step3Res)
        }
        let step3Result: Record<string, unknown> | null = null
        if (rawResult && typeof rawResult === 'object') {
          const cj = rawResult.content_json
          if (typeof cj === 'string' && cj.trim()) {
            try {
              const parsed = JSON.parse(cj)
              if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
                step3Result = parsed as Record<string, unknown>
              }
            } catch { /* ignore */ }
          }
          if (!step3Result) step3Result = rawResult
        }
        if (step3Result) {
          let tasks = step3Result.flat_l2_tasks
          // Fallback: derive from skeleton / level2_items if flat_l2_tasks is missing (old save format).
          if (!Array.isArray(tasks) || !tasks.length) {
            const skeleton = step3Result.skeleton
            if (Array.isArray(skeleton) && skeleton.length) {
              tasks = skeleton
            }
          }
          if (!Array.isArray(tasks) || !tasks.length) {
            const level2Items = step3Result.level2Items || step3Result.level2_items
            if (Array.isArray(level2Items) && level2Items.length) {
              tasks = level2Items
            }
          }
          // Final fallback: parse from content_text markdown (format: ### N. 一级：X ｜ 二级：Y)
          if (!Array.isArray(tasks) || !tasks.length) {
            const mdText = (step3Result.content_text || rawResult?.content_text || '') as string
            if (typeof mdText === 'string' && mdText.includes('一级：')) {
              const regex = /###\s*\d+\.\s*一级[：:]\s*(.+?)\s*[｜|]\s*二级[：:]\s*(.+)/g
              const extracted: Array<{ level1_name: string; level2_name: string }> = []
              let match: RegExpExecArray | null
              while ((match = regex.exec(mdText)) !== null) {
                extracted.push({ level1_name: match[1].trim(), level2_name: match[2].trim() })
              }
              if (extracted.length) tasks = extracted
            }
          }
          if (Array.isArray(tasks) && tasks.length) {
            step4FlatL2Tasks.value = tasks.map((t: any) => ({
              level1_name: String(t.level1_name || t.level1 || t.parent_name || ''),
              level2_name: String(t.level2_name || t.level2 || t.name || t.indicator_name || ''),
              level3_name: t.level3_name ? String(t.level3_name) : undefined,
              weight: typeof t.weight === 'number' ? t.weight : undefined,
              score: undefined,
              target_l3_count: typeof t.target_l3_count === 'number' ? t.target_l3_count : undefined,
              l3_section_markdown: typeof t.l3_section_markdown === 'string' ? t.l3_section_markdown : undefined,
            }))
          }
          // Also store step3 content_text for agent payload context.
          const step3Text = step3Result.content_text || step3Result.final_indicator_markdown || rawResult?.content_text
          if (typeof step3Text === 'string' && step3Text.trim()) {
            prevStepContent.value = step3Text
          }
        }
      } catch {
        step4FlatL2Tasks.value = []
      }
    } else if (stepId.value >= 5 && stepId.value <= 14) {
      try {
        const prevCode = `step${stepId.value - 1}`
        const prevRes = await getStepResult(prevCode, projectId.value)
        const rawResult = (prevRes.result as Record<string, unknown>) || null
        let prevResult: Record<string, unknown> | null = null
        if (rawResult && typeof rawResult === 'object') {
          const cj = rawResult.content_json
          if (typeof cj === 'string' && cj.trim()) {
            try {
              const parsed = JSON.parse(cj)
              if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
                prevResult = parsed as Record<string, unknown>
              }
            } catch { /* ignore */ }
          }
          if (!prevResult) prevResult = rawResult
          if (prevResult && !prevResult.content_text && rawResult.content_text) {
            prevResult.content_text = rawResult.content_text
          }
        }
        if (prevResult) {
          const text = prevResult.content_text || prevResult.final_core_content || prevResult.final_indicator_markdown || ''
          prevStepContent.value = typeof text === 'string' ? text : ''
          prevStepResult.value = prevResult
        }
        // step7+ 依赖 step4 的 scored_tree 与 step5 的 score_standards。
        // 如果 step6 保存时漏了这两份（旧版 step6 保存逻辑），这里回源到 step4/step5 补齐到 prevStepResult，
        // 让 buildGenericAgentPayload 的 pass-through 仍能拿到，避免 step7 graph 报"缺少第四步成果"。
        if (stepId.value >= 7) {
          const merged: Record<string, unknown> = (prevStepResult.value as Record<string, unknown>) ? { ...(prevStepResult.value as Record<string, unknown>) } : {}
          if (!Array.isArray(merged['scored_tree']) || !(merged['scored_tree'] as unknown[]).length) {
            try {
              const s4 = await getStepResult('step4', projectId.value)
              const s4Raw = (s4.result as Record<string, unknown>) || null
              if (s4Raw && typeof s4Raw.content_json === 'string') {
                const s4Parsed = JSON.parse(s4Raw.content_json)
                if (s4Parsed && Array.isArray(s4Parsed.scored_tree)) {
                  merged['scored_tree'] = s4Parsed.scored_tree
                }
                if (s4Parsed && typeof s4Parsed.project_core_content === 'string' && !merged['project_core_content']) {
                  merged['project_core_content'] = s4Parsed.project_core_content
                }
              }
            } catch { /* ignore */ }
          }
          if (!Array.isArray(merged['score_standards']) || !(merged['score_standards'] as unknown[]).length) {
            try {
              const s5 = await getStepResult('step5', projectId.value)
              const s5Raw = (s5.result as Record<string, unknown>) || null
              if (s5Raw && typeof s5Raw.content_json === 'string') {
                const s5Parsed = JSON.parse(s5Raw.content_json)
                if (s5Parsed && Array.isArray(s5Parsed.score_standards)) {
                  merged['score_standards'] = s5Parsed.score_standards
                }
                if (s5Parsed && Array.isArray(s5Parsed.scored_tree) && (!Array.isArray(merged['scored_tree']) || !(merged['scored_tree'] as unknown[]).length)) {
                  merged['scored_tree'] = s5Parsed.scored_tree
                }
              }
            } catch { /* ignore */ }
          }
          prevStepResult.value = { ...merged }
        }
      } catch {
        prevStepContent.value = ''
        prevStepResult.value = null
      }
    }
    try {
      const res = await getStepResult(stepCodeOf(), projectId.value)
      const saved = (res.result as Record<string, unknown>) || null
      if (saved) {
        // content_json 里封了 step 自己的结构化字段（scored_tree / questionnaire_items 等），
        // 必须反序列化合并回 currentResult，否则前端只能看到 content_text/version 这几个外壳字段
        let parsedContentJson: Record<string, unknown> | null = null
        if (typeof saved.content_json === 'string' && saved.content_json.trim()) {
          try {
            const parsed = JSON.parse(saved.content_json)
            if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
              parsedContentJson = parsed as Record<string, unknown>
            }
          } catch {
            parsedContentJson = null
          }
        }
        currentResult.value = parsedContentJson ? { ...saved, ...parsedContentJson } : saved
        resultText.value = JSON.stringify(currentResult.value, null, 2)
        const text = (saved.content_text as string) || readStep3FinishText(saved)
        if (typeof text === 'string' && text.trim()) editor.value = text
        // step6：从持久化的 content_json 把问卷 ref 回填，避免历史恢复后界面看不到问卷
        if (stepId.value === 6 && parsedContentJson) {
          const decision = parsedContentJson['questionnaire_decision']
          if (decision === 'need' || decision === 'skip') {
            step6QuestionnaireDecision.value = decision
          }
          const feedback = parsedContentJson['questionnaire_feedback']
          if (typeof feedback === 'string') step6QuestionnaireFeedback.value = feedback
          const qDraft = parsedContentJson['questionnaire_draft']
          if (typeof qDraft === 'string') step6QuestionnaireDraft.value = qDraft
          const qItems = parsedContentJson['questionnaire_items']
          if (Array.isArray(qItems)) step6QuestionnaireItems.value = qItems as Step6QItem[]
          loadStep6Responses()
        }
        // step4 刷新页面时从 saved 的 scored_tree 回填 score 到 step4FlatL2Tasks
        if (stepId.value === 4 && step4FlatL2Tasks.value.length) {
          const treeSource = (parsedContentJson && parsedContentJson['scored_tree']) ?? saved['scored_tree']
          const scoredTree = treeSource
          if (Array.isArray(scoredTree) && scoredTree.length) {
            const l2ScoreByKey: Record<string, number> = {}
            for (const l1 of scoredTree as any[]) {
              const l1Name = String(l1?.name ?? '')
              const level2List = Array.isArray(l1?.level2) ? l1.level2 : []
              for (const l2 of level2List) {
                const l2Name = String(l2?.name ?? '')
                const sc = typeof l2?.score === 'number' ? l2.score : Number(l2?.score)
                if (!Number.isNaN(sc)) l2ScoreByKey[`${l1Name}|${l2Name}`] = Number(sc)
              }
            }
            if (Object.keys(l2ScoreByKey).length) {
              step4FlatL2Tasks.value = step4FlatL2Tasks.value.map((row) => {
                const key = `${row.level1_name}|${row.level2_name}`
                const matched = l2ScoreByKey[key]
                return matched !== undefined ? { ...row, score: matched } : row
              })
              const scores: Record<string, number> = {}
              for (const t of step4FlatL2Tasks.value) {
                if (t.score !== undefined) scores[`${t.level1_name}|${t.level2_name}`] = t.score
              }
              if (Object.keys(scores).length > 0) step4ManualScores.value = scores
            }
          }
          if (typeof saved['total_score'] === 'number') {
            step4TotalScore.value = saved['total_score'] as number
          } else if (parsedContentJson && typeof parsedContentJson['total_score'] === 'number') {
            step4TotalScore.value = parsedContentJson['total_score'] as number
          }
        }
      } else if (stepId.value >= 4) {
        // 后端未提交版本时，回退读取 localStorage 短期草稿（双保险）
        const draft = loadGenericStepDraft(stepCodeOf())
        if (draft) {
          if (typeof draft.content_text === 'string') editor.value = draft.content_text
          if (typeof draft.content_json === 'string') resultText.value = draft.content_json
          if (draft.current_result && typeof draft.current_result === 'object') {
            currentResult.value = draft.current_result as Record<string, unknown>
          }
        }
      }
    } catch {
      // no saved result for this step yet
      if (stepId.value >= 4) {
        const draft = loadGenericStepDraft(stepCodeOf())
        if (draft) {
          if (typeof draft.content_text === 'string') editor.value = draft.content_text
          if (typeof draft.content_json === 'string') resultText.value = draft.content_json
          if (draft.current_result && typeof draft.current_result === 'object') {
            currentResult.value = draft.current_result as Record<string, unknown>
          }
        }
      }
    }
  }
}

function readStep3FinishText(source: Record<string, unknown> | null) {
  if (!source) return ''
  const candidates = [
    source['final_indicator_markdown'],
    source['indicator_markdown'],
    source['final_core_content'],
    source['content_text'],
    source['content_json'],
  ]
  for (const item of candidates) {
    if (typeof item === 'string' && item.trim()) return item
  }
  return ''
}

function parseMaybeJson(value: unknown): Record<string, unknown> | null {
  if (typeof value !== 'string') return null
  const text = value.trim()
  if (!text) return null
  try {
    const parsed = JSON.parse(text)
    return parsed && typeof parsed === 'object' ? parsed as Record<string, unknown> : null
  } catch {
    return null
  }
}

function toRecordArray(value: unknown): Array<Record<string, unknown>> {
  return Array.isArray(value) ? value.filter((item): item is Record<string, unknown> => Boolean(item) && typeof item === 'object') : []
}

function readStep3StructuredData(source: Record<string, unknown> | null): { skeleton: Array<Record<string, unknown>>; level2Items: Array<Record<string, unknown>>; level3Items: Array<Record<string, unknown>> } {
  if (!source) return { skeleton: [], level2Items: [], level3Items: [] }
  const raw = source['structure_json'] ?? source['indicator_tree'] ?? source['indicator_json'] ?? source['content_json']
  const parsed = typeof raw === 'string' ? parseMaybeJson(raw) : (raw && typeof raw === 'object' ? raw as Record<string, unknown> : null)
  const skeleton = toRecordArray(parsed?.skeleton ?? source['skeleton'])
  const level2Items = toRecordArray(parsed?.level2_items ?? source['level2_items'])
  const level3Items = toRecordArray(parsed?.level3_items ?? source['level3_items'])
  return { skeleton, level2Items, level3Items }
}

function toPrettyText(value: unknown) {
  if (typeof value === 'string') return value
  try {
    return JSON.stringify(value, null, 2)
  } catch {
    return String(value)
  }
}


function buildStep3CardContent(items: Array<Record<string, unknown>>, fallbackKey: string) {
  if (!items.length) return ''
  return items.map((item, index) => {
    const title = String(item.name ?? item.title ?? item.label ?? item.indicator_name ?? `${fallbackKey} ${index + 1}`)
    const content = Object.entries(item)
      .filter(([key]) => !['name', 'title', 'label', 'indicator_name'].includes(key))
      .map(([key, value]) => `- ${key}: ${toPrettyText(value)}`)
      .join('\n')
    return `${title}\n${content}`.trim()
  }).join('\n\n')
}

function extractStep2State(
  source: Record<string, unknown> | null,
  comparisons: Array<{ model_name?: string; label?: string; provider?: string; channel?: string; temperature?: number; draft?: string; error?: string }>,
) {
  if (!source) {
    step2VerificationDigest.value = ''
    step2ParseWarnings.value = []
    step2ModelComparisons.value = []
    step2SourceIndex.value = []
    step2MediaMetadata.value = []
    step2DocsMetadata.value = []
    step2StatusText.value = ''
    return
  }
  step2VerificationDigest.value = typeof source.verification_digest === 'string' ? String(source.verification_digest) : ''
  step2ParseWarnings.value = Array.isArray(source.parse_warnings) ? source.parse_warnings.map((item) => String(item)) : []
  step2ModelComparisons.value = comparisons
  step2ActiveCompareIndex.value = step2ModelComparisons.value.length ? 0 : 0
  step2SourceIndex.value = Array.isArray(source.source_index)
    ? (source.source_index as Array<Record<string, unknown>>).map((entry) => ({
        ref_id: String(entry.ref_id || ''),
        source_name: String(entry.source_name || ''),
        channel: String(entry.channel || ''),
        excerpt: String(entry.excerpt || ''),
      }))
    : []
  step2MediaMetadata.value = Array.isArray(source.media_metadata) ? (source.media_metadata as Array<Record<string, unknown>>) : []
  step2DocsMetadata.value = Array.isArray(source.text_doc_metadata) ? (source.text_doc_metadata as Array<Record<string, unknown>>) : []
  step2StatusText.value = typeof source.status === 'string' ? String(source.status) : ''

  // Sync core content into editor when fresh / approved drafts arrive.
  const candidates = [
    typeof source.final_core_content === 'string' ? String(source.final_core_content) : '',
    typeof source.core_content_draft === 'string' ? String(source.core_content_draft) : '',
    typeof source.content_text === 'string' ? String(source.content_text) : '',
  ]
  const next = candidates.find((item) => item && !placeholderEditorTexts.includes(item.trim()))
  if (next) editor.value = next

  // Sync categories from server if it returned them.
  const defaults = Array.isArray(source.default_categories) ? (source.default_categories as unknown[]).map((item) => String(item)) : []
  if (defaults.length) step2DefaultCategories.value = defaults
  const extras = Array.isArray(source.extra_categories) ? (source.extra_categories as unknown[]).map((item) => String(item)) : []
  if (extras.length) step2ExtraCategories.value = extras
}

function addStep2Category() {
  const value = step2NewCategoryInput.value.trim()
  if (!value) {
    ElMessage.warning('请输入要新增的分类名称')
    return
  }
  if (step2DefaultCategories.value.includes(value) || step2ExtraCategories.value.includes(value)) {
    ElMessage.info('该分类已经存在')
    return
  }
  step2ExtraCategories.value = [...step2ExtraCategories.value, value]
  step2NewCategoryInput.value = ''
}

function removeStep2ExtraCategory(index: number) {
  step2ExtraCategories.value = step2ExtraCategories.value.filter((_, idx) => idx !== index)
}

function toggleStep2DefaultCategory(category: string, enabled: boolean) {
  if (enabled) {
    if (!step2DefaultCategories.value.includes(category)) {
      step2DefaultCategories.value = [...step2DefaultCategories.value, category]
    }
  } else {
    step2DefaultCategories.value = step2DefaultCategories.value.filter((item) => item !== category)
  }
}

function applyStep2Comparison(index: number) {
  const item = step2ModelComparisons.value[index]
  if (!item || !item.draft) {
    ElMessage.warning('该模型暂未返回有效草稿，无法导入成品区')
    return
  }
  editor.value = item.draft
  step2ActiveCompareIndex.value = index
  saveStep2DraftState()
  ElMessage.success(`已把「${item.label || item.model_name || `模型 ${index + 1}`}」草稿导入成品区`)
}

async function submitStep2Refinement() {
  const feedback = step2ReviewFeedback.value.trim()
  if (!feedback) {
    ElMessage.warning('请填写要交给 AI 的修改意见，再发起优化')
    return
  }
  if (!step2HasContent.value) {
    ElMessage.warning('成品区暂无核心内容，请先生成草稿后再优化')
    return
  }
  step2ReviewMode.value = 'modify'
  await runStep('')
}

async function approveStep2() {
  if (!step2HasContent.value) {
    ElMessage.warning('请先生成或编辑 Step2 核心内容，再确认定稿')
    return
  }
  openConfirmDialog({
    title: '确认提交 Step2 核心内容',
    message: '是否确认把当前 Step2 核心内容提交为最终版本？提交后将写入数据库。',
    type: 'warning',
    okText: '确认提交',
    action: async () => {
      saving.value = true
      try {
        await updateThreadState({
          step_code: 'step2',
          thread_id: step2ThreadId.value,
          values: { final_core_content: editor.value, status: 'committed' },
        })
        const fullState = {
          ...(currentResult.value ?? {}),
          final_core_content: editor.value,
          content_text: editor.value,
          status: 'committed',
          model_comparisons: step2ModelComparisons.value,
          verification_digest: step2VerificationDigest.value,
          parse_warnings: step2ParseWarnings.value,
          source_index: step2SourceIndex.value,
          media_metadata: step2MediaMetadata.value,
          text_doc_metadata: step2DocsMetadata.value,
          default_categories: step2DefaultCategories.value,
          extra_categories: step2ExtraCategories.value,
        }
        await saveStepResult('step2', {
          project_id: projectId.value,
          title: titleMap[2],
          content_text: editor.value,
          content_json: JSON.stringify(fullState),
          model_name: 'manual-edit',
        })
        step2DraftDirty.value = false
        step2LastCommittedAt.value = new Date().toISOString()
        step2ReviewMode.value = 'approve'
        step2ReviewFeedback.value = ''
        clearStep2DraftState()
        await clearStepShortTermMemory('step2', step2ThreadId.value)
        await loadWorkflowStatus()
        ElMessage.success('Step2 核心内容已确认提交到数据库')
      } catch (e) {
        ElMessage.error(e instanceof Error ? e.message : '提交失败')
      } finally {
        saving.value = false
      }
    },
  })
}

function step2WriteBackToCheckpointer() {
  if (stepId.value !== 2) return
  if (step2WriteBackTimer) clearTimeout(step2WriteBackTimer)
  step2WriteBackTimer = setTimeout(async () => {
    if (stepId.value !== 2 || isEditorEmpty()) return
    saveStep2DraftState()
    try {
      await updateThreadState({
        step_code: 'step2',
        thread_id: step2ThreadId.value,
        values: { final_core_content: editor.value },
      })
    } catch { /* silent */ }
  }, 2000)
}

function getStep2ExportContent() {
  const candidates = [
    editor.value,
    typeof currentResult.value?.final_core_content === 'string' ? String(currentResult.value.final_core_content) : '',
    typeof currentResult.value?.core_content_draft === 'string' ? String(currentResult.value.core_content_draft) : '',
    typeof currentResult.value?.content_text === 'string' ? String(currentResult.value.content_text) : '',
  ]
  return candidates.find((item) => item.trim() && !placeholderEditorTexts.includes(item.trim()))?.trim() || ''
}

function openStep2ExportDialog() {
  if (stepId.value !== 2) return
  const content = getStep2ExportContent()
  if (!content) {
    ElMessage.warning('当前没有可导出的核心内容，请先生成或编辑后再导出')
    return
  }
  if ((editor.value || '').trim() !== content) editor.value = content
  step2ExportCustomTitle.value = `${getGlobalProjectName()}项目核心内容`
  lastStep2ExportUrl.value = ''
  lastStep2ExportFileName.value = ''
  step2ExportDialogVisible.value = true
}

async function downloadLastStep2Export() {
  if (!lastStep2ExportUrl.value || !lastStep2ExportFileName.value) return
  try {
    await downloadExportFile(lastStep2ExportUrl.value, lastStep2ExportFileName.value)
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : '下载失败')
  }
}

async function submitStep2Export(downloadAfter = true) {
  const content = getStep2ExportContent()
  if (!content) {
    ElMessage.warning('当前没有可导出的核心内容，请先生成或编辑后再导出')
    return
  }
  step2ExportSaving.value = true
  try {
    const formatOptions: Step2FormatOptions | null = step2ExportStyle.value === 'custom'
      ? { ...step2ExportFormatOptions.value }
      : null
    const response = await exportStep2(projectId.value, {
      project_name: getGlobalProjectName(),
      thread_id: step2ThreadId.value,
      content_text: content,
      content_json: resultText.value,
      export_style: step2ExportStyle.value,
      export_format: step2ExportFormat.value,
      custom_title: step2ExportCustomTitle.value,
      save_to_database: false,
      categories: step2MergedCategories.value,
      format_options: formatOptions,
    })
    lastStep2ExportUrl.value = response.download_url
    lastStep2ExportFileName.value = response.file_name
    if (downloadAfter) {
      await downloadExportFile(response.download_url, response.file_name)
      const tip = step2ExportFormat.value === 'markdown' ? 'Markdown' : 'Word'
      ElMessage.success(`Step2 核心内容 ${tip} 已导出并开始下载`)
    } else {
      ElMessage.success('Step2 核心内容文件已生成，可点击「下载上次导出」')
    }
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : '导出失败')
  } finally {
    step2ExportSaving.value = false
  }
}

function renderStep4ScoredMarkdown(scoredTree: any[], totalScore: number, project: string): string {
  const title = (project || '项目').trim()
  const fmtInt = (v: any) => {
    const n = Number(v)
    return Number.isFinite(n) ? String(Math.round(n)) : '0'
  }
  const esc = (s: any) => String(s ?? '').replace(/\|/g, '丨').replace(/\n/g, ' ').trim()

  const lines: string[] = []
  lines.push(`# 《${title} — 评估指标分值表》`)
  lines.push('')
  if (typeof totalScore === 'number' && !Number.isNaN(totalScore)) {
    lines.push(`> 总分：${fmtInt(totalScore)}`)
    lines.push('')
  }
  lines.push('| 一级指标 | 一级总分 | 二级指标 | 二级总分 | 具体观测点/三级指标 | 观测点分值 | 核心考核要点 |')
  lines.push('| --- | :---: | --- | :---: | --- | :---: | --- |')

  let grandL1 = 0
  let grandL2 = 0
  let grandL3 = 0

  for (const l1 of Array.isArray(scoredTree) ? scoredTree : []) {
    const l1Name = esc(l1?.name)
    const l1Score = fmtInt(l1?.score)
    grandL1 += Number(l1Score)
    let l1Emitted = false

    const l2List: any[] = Array.isArray(l1?.level2) ? l1.level2 : []
    if (!l2List.length) {
      lines.push(`| ${l1Name} | ${l1Score} | — | — | — | — | — |`)
      continue
    }

    for (const l2 of l2List) {
      const l2Name = esc(l2?.name)
      const l2Score = fmtInt(l2?.score)
      grandL2 += Number(l2Score)
      let l2Emitted = false

      const l3List: any[] = Array.isArray(l2?.level3) ? l2.level3 : []
      if (!l3List.length) {
        const leftL1 = l1Emitted ? '' : l1Name
        const leftL1Score = l1Emitted ? '' : l1Score
        lines.push(`| ${leftL1} | ${leftL1Score} | ${l2Name} | ${l2Score} | — | — | — |`)
        l1Emitted = true
        continue
      }

      for (const l3 of l3List) {
        const l3Name = esc(l3?.name)
        const l3Score = fmtInt(l3?.score)
        grandL3 += Number(l3Score)
        const kp = esc(l3?.key_points || l3?.description || '')
        const leftL1 = l1Emitted ? '' : l1Name
        const leftL1Score = l1Emitted ? '' : l1Score
        const leftL2 = l2Emitted ? '' : l2Name
        const leftL2Score = l2Emitted ? '' : l2Score
        lines.push(`| ${leftL1} | ${leftL1Score} | ${leftL2} | ${leftL2Score} | ${l3Name} | ${l3Score} | ${kp} |`)
        l1Emitted = true
        l2Emitted = true
      }
    }
  }

  lines.push(`| **合计** | **${grandL1}** | — | **${grandL2}** | — | **${grandL3}** | — |`)
  lines.push('')
  return lines.join('\n').replace(/\n{3,}/g, '\n\n').trim() + '\n'
}

function applyAgentResult(res: AgentRunResponse) {
  const payload = extractResult(res)
  currentResult.value = payload && typeof payload === 'object' ? payload as Record<string, unknown> : null
  resultText.value = JSON.stringify(payload, null, 2)

  const finishText = readStep3FinishText(currentResult.value)
  if (finishText) {
    editor.value = finishText
  }

  const structuredData = readStep3StructuredData(currentResult.value)
  step3Structured.value = structuredData
  const comparisonsSource = currentResult.value as Record<string, unknown> | null
  const comparisons = Array.isArray(comparisonsSource?.['model_comparisons'])
    ? (comparisonsSource['model_comparisons'] as Array<{ model_name?: string; label?: string; provider?: string; channel?: string; temperature?: number; draft?: string; error?: string }>)
    : []
  compareItems.value = comparisons.map((item) => ({
    label: item.label || item.model_name || '模型',
    content: item.draft || (item.error ? `（调用失败：${item.error}）` : ''),
  }))
  if (stepId.value === 2) {
    extractStep2State(currentResult.value, comparisons)
    step2DraftDirty.value = true
    saveStep2DraftState()
  }

  if (stepId.value === 4 && currentResult.value) {
    const tasks = currentResult.value['flat_l2_tasks']
    if (Array.isArray(tasks) && tasks.length) {
      step4FlatL2Tasks.value = tasks.map((t: any) => ({
        level1_name: String(t.level1_name || ''),
        level2_name: String(t.level2_name || ''),
        level3_name: t.level3_name ? String(t.level3_name) : undefined,
        weight: typeof t.weight === 'number' ? t.weight : undefined,
        score: typeof t.score === 'number' ? t.score : undefined,
        target_l3_count: typeof t.target_l3_count === 'number' ? t.target_l3_count : undefined,
        l3_section_markdown: typeof t.l3_section_markdown === 'string' ? t.l3_section_markdown : undefined,
      }))
    }
    // 后端 step4 实际产出的是 scored_tree（L1 -> L2 -> L3 的分层树），需要展平回 L2 名 -> 分值
    const scoredTree = currentResult.value['scored_tree']
    if (Array.isArray(scoredTree) && scoredTree.length && step4FlatL2Tasks.value.length) {
      const l2ScoreByKey: Record<string, number> = {}
      for (const l1 of scoredTree as any[]) {
        const l1Name = String(l1?.name ?? '')
        const level2List = Array.isArray(l1?.level2) ? l1.level2 : []
        for (const l2 of level2List) {
          const l2Name = String(l2?.name ?? '')
          const sc = typeof l2?.score === 'number' ? l2.score : Number(l2?.score)
          if (!Number.isNaN(sc)) {
            l2ScoreByKey[`${l1Name}|${l2Name}`] = Number(sc)
          }
        }
      }
      if (Object.keys(l2ScoreByKey).length) {
        step4FlatL2Tasks.value = step4FlatL2Tasks.value.map((row) => {
          const key = `${row.level1_name}|${row.level2_name}`
          const matched = l2ScoreByKey[key]
          return matched !== undefined ? { ...row, score: matched } : row
        })
      }
    }
    const scores: Record<string, number> = {}
    for (const t of step4FlatL2Tasks.value) {
      if (t.score !== undefined) {
        scores[`${t.level1_name}|${t.level2_name}`] = t.score
      }
    }
    if (Object.keys(scores).length > 0) step4ManualScores.value = scores
    if (typeof currentResult.value['total_score'] === 'number') {
      step4TotalScore.value = currentResult.value['total_score'] as number
    }

    // 将分值合并进介质文本：优先用后端 final_scores_markdown，否则按 scored_tree 自渲染一份带分值的 Markdown 写回 editor
    const backendFinalMd = currentResult.value['final_scores_markdown']
    if (typeof backendFinalMd === 'string' && backendFinalMd.trim()) {
      editor.value = backendFinalMd
    } else if (Array.isArray(scoredTree) && scoredTree.length) {
      editor.value = renderStep4ScoredMarkdown(scoredTree as any[], step4TotalScore.value, projectName.value)
    }
  }

  if (stepId.value === 5 && currentResult.value) {
    // step5：评分标准 markdown 优先取 final_rubrics_markdown，未定稿时取 draft_rubrics_markdown
    const finalRubric = currentResult.value['final_rubrics_markdown']
    const draftRubric = currentResult.value['draft_rubrics_markdown']
    const contentText = currentResult.value['content_text']
    const md = (typeof finalRubric === 'string' && finalRubric.trim())
      ? finalRubric
      : (typeof draftRubric === 'string' && draftRubric.trim())
        ? draftRubric
        : (typeof contentText === 'string' ? contentText : '')
    if (md && md.trim()) {
      editor.value = md
    }
  }

  if (stepId.value === 6 && currentResult.value) {
    // step6：指标体系 markdown + 可选问卷草稿
    const frameworkMd = currentResult.value['final_indicator_framework_markdown']
    const exportPayload = currentResult.value['export_payload']
    const contentText = currentResult.value['content_text']
    const baseMd = (typeof frameworkMd === 'string' && frameworkMd.trim())
      ? frameworkMd
      : (typeof exportPayload === 'string' && exportPayload.trim())
        ? exportPayload
        : (typeof contentText === 'string' ? contentText : '')
    if (baseMd && baseMd.trim()) {
      editor.value = baseMd
    }
    const qDraft = currentResult.value['questionnaire_draft']
    step6QuestionnaireDraft.value = typeof qDraft === 'string' ? qDraft : ''
    const qItems = currentResult.value['questionnaire_items']
    step6QuestionnaireItems.value = Array.isArray(qItems) ? qItems as Step6QItem[] : []
    // 解析 scored_tree → 拖拽 ref，并在 DOM 渲染后挂载 sortable
    parseScoredTreeIntoStep6Tree()
    nextTick(() => mountStep6Sortables())
  }

  const structuredSummaries = [
    {
      title: '指标骨架',
      desc: `共 ${structuredData.skeleton.length} 项`,
      content: buildStep3CardContent(structuredData.skeleton, '骨架'),
    },
    {
      title: '二级指标',
      desc: `共 ${structuredData.level2Items.length} 项`,
      content: buildStep3CardContent(structuredData.level2Items, '二级指标'),
    },
    {
      title: '三级指标',
      desc: `共 ${structuredData.level3Items.length} 项`,
      content: buildStep3CardContent(structuredData.level3Items, '三级指标'),
    },
  ]

  currentOutputs.value = [
    {
      title: `Step ${stepId.value} 当前结果`,
      desc: currentResult.value?.status ? String(currentResult.value.status) : '已加载',
      content: finishText || resultText.value,
    },
    ...structuredSummaries,
    ...compareItems.value.map((item) => ({
      title: item.label,
      desc: '模型对比草稿',
      content: item.content,
    })),
  ]
}

async function saveCurrentStep() {
  if (stepId.value === 1) {
    if (isEditorEmpty()) {
      ElMessage.warning('成品区内容为空，无法保存 Step1 草稿')
      return
    }
    openConfirmDialog({
      title: '确认提交 Step1 草稿',
      message: '是否确认把当前 Step1 草稿提交为最终资料清单？提交后将写入数据库文件表。',
      type: 'warning',
      okText: '提交',
      action: async () => {
        saving.value = true
        try {
          await createFileRecord(projectId.value, {
            project_name: projectName.value,
            file_name: `${projectName.value || `项目 ${projectId.value}`} Step1 草稿`,
            file_type: 'draft-json',
            storage_key: `drafts/${projectId.value}/${step1ThreadId.value}.json`,
            source_type: 'step1_draft_commit',
            metadata_json: JSON.stringify({
              thread_id: step1ThreadId.value,
              project_id: projectId.value,
              content_text: editor.value,
              content_json: resultText.value,
              current_result: currentResult.value,
              project_files: inputProjectFiles.value,
              updated_at: new Date().toISOString(),
              confirmed: true,
            }),
            draft_thread_id: step1ThreadId.value,
            draft_payload: {
              thread_id: step1ThreadId.value,
              content_text: editor.value,
              content_json: resultText.value,
              current_result: currentResult.value,
              project_name: projectName.value,
              project_files: inputProjectFiles.value,
              confirmed: true,
            },
          })
          clearStep1DraftState()
          await loadProjectFiles()
          // Also persist as StepOutput so workflow progress reflects step1 completion.
          try {
            await saveStepResult('step1', {
              project_id: projectId.value,
              title: titleMap[1] ?? 'Step1 · 项目资料清单',
              content_text: editor.value,
              content_json: resultText.value || '{}',
              model_name: 'manual-edit',
            })
            await clearStepShortTermMemory('step1', step1ThreadId.value)
          } catch (e) {
            console.warn('saveStepResult step1 failed', e)
          }
          await loadWorkflowStatus()
          ElMessage.success('Step1 草稿已确认并完成提交')
        } catch (e) {
          ElMessage.error(e instanceof Error ? e.message : '提交失败')
        } finally {
          saving.value = false
        }
      },
    })
    return
  }
  if (isEditorEmpty()) {
    ElMessage.warning('成品区内容为空，无法保存')
    return
  }
  openConfirmDialog({
    title: '保存最终版本',
    message: '是否确定保存当前最终版本？保存后会写入新的最终版本记录。',
    type: 'warning',
    okText: '保存',
    action: async () => {
      saving.value = true
      try {
        const step3Json = stepId.value === 3
          ? JSON.stringify({
              ...step3Structured.value,
              flat_l2_tasks: step3SkeletonTasks.value,
              review_mode: step3Config.value.review_mode,
              review_feedback: step3Config.value.review_feedback,
              system_type: step3Config.value.system_type,
              indicator_depth: step3Config.value.indicator_depth,
              import_mode: step3Config.value.import_mode,
              template_id: step3Config.value.template_id,
              skeleton_optimize_mode: step3Config.value.skeleton_optimize_mode,
              per_optimize_level2_name: step3Config.value.per_optimize_level2_name,
            }, null, 2)
          : stepId.value === 4
            ? JSON.stringify({
                flat_l2_tasks: step4FlatL2Tasks.value.map((t) => ({
                  level1_name: t.level1_name,
                  level2_name: t.level2_name,
                  target_l3_count: t.target_l3_count ?? 1,
                  l3_section_markdown: t.l3_section_markdown ?? '',
                  score: typeof t.score === 'number' ? t.score : undefined,
                })),
                assign_mode: step4ScoringMode.value === 'ai' ? 'llm' : 'manual',
                manual_l3_scores: step4ManualScores.value,
                total_score: step4TotalScore.value,
                // 关键：把后端 step4 graph 产出的 scored_tree 一并持久化，否则历史恢复后 score 字段全部丢失，
                // 同时 step5 也拿不到 scored_tree 会直接报错
                scored_tree: (currentResult.value && Array.isArray((currentResult.value as Record<string, unknown>)['scored_tree']))
                  ? (currentResult.value as Record<string, unknown>)['scored_tree']
                  : [],
                final_indicator_markdown: (currentResult.value && typeof (currentResult.value as Record<string, unknown>)['final_indicator_markdown'] === 'string')
                  ? (currentResult.value as Record<string, unknown>)['final_indicator_markdown']
                  : (prevStepContent.value || ''),
              }, null, 2)
            : stepId.value === 6
              ? JSON.stringify({
                  // step6 现场评价表 + 满意度问卷一并落库，否则历史恢复后问卷与指标体系都会丢失
                  final_indicator_framework_markdown:
                    (currentResult.value && typeof (currentResult.value as Record<string, unknown>)['final_indicator_framework_markdown'] === 'string')
                      ? (currentResult.value as Record<string, unknown>)['final_indicator_framework_markdown']
                      : (editor.value || ''),
                  questionnaire_decision: step6QuestionnaireDecision.value,
                  questionnaire_feedback: step6QuestionnaireFeedback.value,
                  questionnaire_draft: step6QuestionnaireDraft.value,
                  questionnaire_items: step6QuestionnaireItems.value,
                  compressed_rubrics:
                    (currentResult.value && typeof (currentResult.value as Record<string, unknown>)['compressed_rubrics'] === 'object')
                      ? (currentResult.value as Record<string, unknown>)['compressed_rubrics']
                      : {},
                  export_payload:
                    (currentResult.value && typeof (currentResult.value as Record<string, unknown>)['export_payload'] === 'string')
                      ? (currentResult.value as Record<string, unknown>)['export_payload']
                      : '',
                  // 关键：step7+ 依赖 step4 的 scored_tree 与 step5 的 score_standards，
                  // step6 保存时必须把这两份一并落库，否则后续 step 的 prev pass-through 拿不到，会直接报"缺少第四步成果"
                  scored_tree:
                    (currentResult.value && Array.isArray((currentResult.value as Record<string, unknown>)['scored_tree']))
                      ? (currentResult.value as Record<string, unknown>)['scored_tree']
                      : ((prevStepResult.value && Array.isArray((prevStepResult.value as Record<string, unknown>)['scored_tree']))
                        ? (prevStepResult.value as Record<string, unknown>)['scored_tree']
                        : []),
                  score_standards:
                    (currentResult.value && Array.isArray((currentResult.value as Record<string, unknown>)['score_standards']))
                      ? (currentResult.value as Record<string, unknown>)['score_standards']
                      : ((prevStepResult.value && Array.isArray((prevStepResult.value as Record<string, unknown>)['score_standards']))
                        ? (prevStepResult.value as Record<string, unknown>)['score_standards']
                        : []),
                  project_core_content:
                    (currentResult.value && typeof (currentResult.value as Record<string, unknown>)['project_core_content'] === 'string')
                      ? (currentResult.value as Record<string, unknown>)['project_core_content']
                      : ((prevStepResult.value && typeof (prevStepResult.value as Record<string, unknown>)['project_core_content'] === 'string')
                        ? (prevStepResult.value as Record<string, unknown>)['project_core_content']
                        : ''),
                }, null, 2)
            : stepId.value === 7
              ? JSON.stringify({
                  // step7 指标体系分析与得分表：分析行 + 4 块 5 列表 + 总评分表 6 列 + 级联得分
                  indicator_form: step7Form.value,
                  indicator_inputs: step7Inputs.value,
                  analysis_rows: step7AnalysisRows.value,
                  block_tables_markdown: step7BlockMd.value,
                  overall_score_table_markdown: step7OverallMd.value,
                  total_score: step7TotalScore.value,
                  total_full_score: step7TotalFull.value,
                  overall_score_rate: step7OverallRate.value,
                  survey_summary: step7SurveySummary.value,
                  survey_sample_size: step7SurveySample.value,
                  survey_satisfaction_rate: step7SurveyRate.value,
                  export_font_family: step7ExportFontFamily.value,
                  export_font_size: step7ExportFontSize.value,
                  export_line_height: step7ExportLineHeight.value,
                  // 把上游字段一并保留，供 step8+ pass-through 使用
                  scored_tree:
                    (prevStepResult.value && Array.isArray((prevStepResult.value as Record<string, unknown>)['scored_tree']))
                      ? (prevStepResult.value as Record<string, unknown>)['scored_tree']
                      : [],
                  score_standards:
                    (prevStepResult.value && Array.isArray((prevStepResult.value as Record<string, unknown>)['score_standards']))
                      ? (prevStepResult.value as Record<string, unknown>)['score_standards']
                      : [],
                  project_core_content:
                    (prevStepResult.value && typeof (prevStepResult.value as Record<string, unknown>)['project_core_content'] === 'string')
                      ? (prevStepResult.value as Record<string, unknown>)['project_core_content']
                      : '',
                  final_score_sheet_markdown: editor.value,
                }, null, 2)
              : resultText.value || '{}'
        const saved = await saveStepResult(stepCodeOf(), {
          project_id: projectId.value,
          title: titleMap[stepId.value] ?? `Step ${stepId.value} 输出`,
          content_text: editor.value,
          content_json: step3Json,
          model_name: 'manual-edit',
        })
        let restoredFromSavedJson: Record<string, unknown> | null = null
        if (typeof saved.content_json === 'string' && saved.content_json.trim()) {
          try {
            const parsed = JSON.parse(saved.content_json)
            if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
              restoredFromSavedJson = parsed as Record<string, unknown>
            }
          } catch {
            restoredFromSavedJson = null
          }
        }
        const previousResult = (currentResult.value && typeof currentResult.value === 'object')
          ? currentResult.value as Record<string, unknown>
          : {}
        currentResult.value = {
          ...previousResult,
          ...(restoredFromSavedJson ?? {}),
          status: 'saved',
          content_text: saved.content_text,
          version: saved.version,
        }
        resultText.value = saved.content_json || saved.content_text
        currentOutputs.value = [{
          title: `Step ${stepId.value} 当前结果`,
          desc: 'saved',
          content: saved.content_text,
        }]
        ElMessage.success(`已保存最终版本 v${saved.version}`)
        if (stepId.value === 3) clearStep3DraftState()
        if (stepId.value === 7) clearStep7DraftState()
        await clearStepShortTermMemory(stepCodeOf(), `${stepCodeOf()}:${projectId.value}`)
        await Promise.all([loadHistories(), loadWorkflowStatus()])
      } catch (e) {
        ElMessage.error(e instanceof Error ? e.message : '保存失败')
      } finally {
        saving.value = false
      }
    },
  })
}

async function finalizeStep3Workflow() {
  if (stepId.value !== 3) return
  if (!currentResult.value && step3State.value) {
    currentResult.value = step3State.value
  }

  // Build final markdown from skeleton tasks
  const markdown = buildStep3FinalMarkdown()
  if (markdown) {
    editor.value = markdown
  }

  const finishText = readStep3FinishText(currentResult.value)
  if (finishText && !markdown) {
    editor.value = finishText
  }

  if (finishText && !markdown) {
    resultText.value = currentResult.value?.content_json && typeof currentResult.value.content_json === 'string'
      ? String(currentResult.value.content_json)
      : resultText.value || finishText
  }

  const statusText = currentResult.value?.status ? String(currentResult.value.status) : '已就绪'
  const summaryLines = [
    `收尾状态：${statusText}`,
    `体系类型：${step3Config.value.system_type}`,
    `指标深度：${step3Config.value.indicator_depth} 级`,
    `导入模式：${step3Config.value.import_mode}`,
    `骨架优化：${step3Config.value.skeleton_optimize_mode}`,
    `审核模式：${step3Config.value.review_mode}`,
  ]
  if (step3Config.value.review_feedback.trim()) {
    summaryLines.push(`修订意见：${step3Config.value.review_feedback.trim()}`)
  }
  if (step3State.value?.core_basis_digest) {
    summaryLines.push(`Step2 核心摘要：${String(step3State.value.core_basis_digest)}`)
  }
  summaryLines.push(`骨架二级指标：${step3SkeletonTasks.value.length} 项`)
  summaryLines.push(`已完成三级指标：${step3L2Progress.value.completed}/${step3L2Progress.value.total} 项`)

  currentOutputs.value = [
    {
      title: 'Step3 收尾摘要',
      desc: 'finalized',
      content: summaryLines.join('\n'),
    },
  ]
}

function restoreHistory(idx: number) {
  const item = historyItems.value[idx]
  if (!item) return
  editor.value = item.content
  resultText.value = item.content_json || item.content
  historyOpen.value = false

  // step4 恢复时从 content_json 回填 scored_tree → score 到表格
  if (stepId.value === 4 && item.content_json) {
    try {
      const parsed = JSON.parse(item.content_json)
      if (parsed && typeof parsed === 'object') {
        currentResult.value = parsed as Record<string, unknown>
        // 从 flat_l2_tasks 恢复 score
        const tasks = parsed.flat_l2_tasks
        if (Array.isArray(tasks) && tasks.length) {
          step4FlatL2Tasks.value = tasks.map((t: any) => ({
            level1_name: String(t.level1_name || ''),
            level2_name: String(t.level2_name || ''),
            level3_name: t.level3_name ? String(t.level3_name) : undefined,
            weight: typeof t.weight === 'number' ? t.weight : undefined,
            score: typeof t.score === 'number' ? t.score : undefined,
            target_l3_count: typeof t.target_l3_count === 'number' ? t.target_l3_count : undefined,
            l3_section_markdown: typeof t.l3_section_markdown === 'string' ? t.l3_section_markdown : undefined,
          }))
        }
        // 从 scored_tree 展平回填 score（优先级高于 flat_l2_tasks 里的 score）
        const scoredTree = parsed.scored_tree
        if (Array.isArray(scoredTree) && scoredTree.length && step4FlatL2Tasks.value.length) {
          const l2ScoreByKey: Record<string, number> = {}
          for (const l1 of scoredTree) {
            const l1Name = String(l1?.name ?? '')
            const level2List = Array.isArray(l1?.level2) ? l1.level2 : []
            for (const l2 of level2List) {
              const l2Name = String(l2?.name ?? '')
              const sc = typeof l2?.score === 'number' ? l2.score : Number(l2?.score)
              if (!Number.isNaN(sc)) l2ScoreByKey[`${l1Name}|${l2Name}`] = Number(sc)
            }
          }
          if (Object.keys(l2ScoreByKey).length) {
            step4FlatL2Tasks.value = step4FlatL2Tasks.value.map((row) => {
              const key = `${row.level1_name}|${row.level2_name}`
              const matched = l2ScoreByKey[key]
              return matched !== undefined ? { ...row, score: matched } : row
            })
          }
        }
        // 同步 manualScores
        const scores: Record<string, number> = {}
        for (const t of step4FlatL2Tasks.value) {
          if (t.score !== undefined) scores[`${t.level1_name}|${t.level2_name}`] = t.score
        }
        if (Object.keys(scores).length > 0) step4ManualScores.value = scores
        if (typeof parsed.total_score === 'number') step4TotalScore.value = parsed.total_score
      }
    } catch { /* ignore parse errors */ }
  }

  ElMessage.success('已恢复到成品区')
}

async function deleteHistory(idx: number) {
  const item = historyItems.value[idx]
  if (!item) return
  openConfirmDialog({
    title: '删除历史版本',
    message: `确定删除历史版本「${item.title}」吗？此操作会同时删除数据库中的最终版本记录。`,
    type: 'danger',
    okText: '删除',
    action: async () => {
      try {
        await deleteStepHistory(stepCodeOf(), projectId.value, item.id)
        ElMessage.success('历史版本已删除')
        await loadHistories()
        await loadWorkflowStatus()
      } catch (e) {
        ElMessage.error(e instanceof Error ? e.message : '删除失败')
      }
    },
  })
}

function buildAgentPayloadFiles() {
  return inputProjectFiles.value.map((item) => item.storage_key || item.file_name).filter(Boolean)
}

function getGlobalProjectName() {
  return projectName.value.trim() || projectFiles.value.map(extractProjectNameFromFile).find((name) => Boolean(name)) || `项目 ${projectId.value}`
}

function buildStep1AgentPayload() {
  const files = buildAgentPayloadFiles()
  return {
    project_id: projectId.value,
    step_code: 'step1',
    title: titleMap[1],
    file_paths: files,
    project_files: inputProjectFiles.value.map((item) => ({
      id: item.id,
      file_name: item.file_name,
      file_type: item.file_type,
      storage_key: item.storage_key,
      parse_status: item.parse_status,
    })),
    project_name: getGlobalProjectName(),
    thread_id: step1ThreadId.value,
    has_step1_draft: Boolean(loadStep1DraftState()),
  }
}

function buildStep2AgentPayload() {
  const files = buildAgentPayloadFiles()
  return {
    project_id: projectId.value,
    step_code: `step${stepId.value}`,
    title: titleMap[stepId.value] ?? `Step ${stepId.value}`,
    file_paths: files,
    media_file_paths: mediaFiles.value.map((item) => item.storage_key || item.file_name),
    text_doc_file_paths: documentFiles.value.map((item) => item.storage_key || item.file_name),
    project_files: inputProjectFiles.value.map((item) => ({
      id: item.id,
      file_name: item.file_name,
      file_type: item.file_type,
      storage_key: item.storage_key,
      parse_status: item.parse_status,
    })),
    project_name: getGlobalProjectName(),
    review_mode: step2ReviewMode.value,
    review_feedback: step2ReviewMode.value === 'modify' ? step2ReviewFeedback.value.trim() : '',
    default_categories: step2DefaultCategories.value,
    extra_categories: step2ExtraCategories.value.filter((item) => item && item.trim()),
    verification_acknowledged: step2VerificationAck.value,
    final_core_content: stepId.value === 2 && step2HasContent.value ? editor.value : '',
    thread_id: step2ThreadId.value,
  }
}

function buildStep3AgentPayload() {
  const step2Core = step3State.value?.final_core_content || step3State.value?.content_text || currentResult.value?.final_core_content || currentResult.value?.content_text || ''
  const flattenedFiles = inputProjectFiles.value.map((item) => ({
    id: item.id,
    file_name: item.file_name,
    file_type: item.file_type,
    storage_key: item.storage_key,
    parse_status: item.parse_status,
  }))
  return {
    project_id: projectId.value,
    step_code: `step${stepId.value}`,
    title: titleMap[stepId.value] ?? `Step ${stepId.value}`,
    project_name: getGlobalProjectName(),
    project_core_content: typeof step2Core === 'string' ? step2Core : '',
    final_core_content: typeof step2Core === 'string' ? step2Core : '',
    system_type: step3Config.value.system_type,
    indicator_depth: step3Config.value.indicator_depth,
    import_mode: step3Config.value.import_mode,
    imported_indicator_json: step3Config.value.imported_indicator_json,
    template_id: step3Config.value.template_id,
    skeleton_optimize_mode: step3Config.value.skeleton_optimize_mode,
    per_optimize_level2_name: step3Config.value.per_optimize_level2_name,
    review_mode: step3SkeletonPhase.value === 'generating_l3' ? step3L3ReviewMode.value : step3Config.value.review_mode,
    review_feedback: step3SkeletonPhase.value === 'generating_l3'
      ? (step3L3ReviewMode.value === 'modify' ? step3L3Feedback.value : '')
      : step3Config.value.review_feedback,
    flat_l2_tasks: step3SkeletonTasks.value,
    active_l2_index: step3ActiveL2Index.value,
    l3_active_draft: step3L3Draft.value,
    project_files: flattenedFiles,
  }
}

function buildGenericAgentPayload() {
  const files = buildAgentPayloadFiles()
  // 把上一步的结构化结果（如 step4 的 scored_tree、step5 的 score_standards 等）透传给当前 step graph，
  // 避免 stepN 因找不到 stepN-1 在 state 里的关键字段而报错。仅保留可序列化字段。
  const prev = prevStepResult.value || {}
  const prevPassThrough: Record<string, unknown> = {}
  if (prev && typeof prev === 'object') {
    for (const key of Object.keys(prev)) {
      if (key === 'messages' || key === 'content_json') continue
      const val = (prev as Record<string, unknown>)[key]
      if (val === null || val === undefined) continue
      if (typeof val === 'function') continue
      prevPassThrough[key] = val
    }
  }
  return {
    ...prevPassThrough,
    project_id: projectId.value,
    step_code: stepCodeOf(),
    title: titleMap[stepId.value] ?? `Step ${stepId.value}`,
    project_name: getGlobalProjectName(),
    file_paths: files,
    project_files: inputProjectFiles.value.map((item) => ({
      id: item.id,
      file_name: item.file_name,
      file_type: item.file_type,
      storage_key: item.storage_key,
      parse_status: item.parse_status,
    })),
    content_text: editor.value,
  }
}

// ===== Step 7 业务方法 =====
function step7DraftKey() {
  return `ef_step7_draft:${projectId.value}:step7:${projectId.value}`
}

function saveStep7DraftState() {
  if (!projectId.value) return
  try {
    localStorage.setItem(step7DraftKey(), JSON.stringify({
      indicator_form: step7Form.value,
      indicator_inputs: step7Inputs.value,
      analysis_rows: step7AnalysisRows.value,
      block_md: step7BlockMd.value,
      overall_md: step7OverallMd.value,
      final_md: step7FinalMd.value,
      total_score: step7TotalScore.value,
      total_full: step7TotalFull.value,
      overall_rate: step7OverallRate.value,
      review_feedback: step7ReviewFeedback.value,
      survey_sample: step7SurveySample.value,
      survey_rate: step7SurveyRate.value,
      survey_summary: step7SurveySummary.value,
      export_font_family: step7ExportFontFamily.value,
      export_font_size: step7ExportFontSize.value,
      export_line_height: step7ExportLineHeight.value,
      _saved_at: Date.now(),
    }))
  } catch { /* ignore quota */ }
}

function loadStep7DraftState(): boolean {
  if (!projectId.value) return false
  const raw = localStorage.getItem(step7DraftKey())
  if (!raw) return false
  try {
    const d = JSON.parse(raw)
    if (Array.isArray(d.indicator_form)) step7Form.value = d.indicator_form
    if (d.indicator_inputs && typeof d.indicator_inputs === 'object') step7Inputs.value = d.indicator_inputs
    if (Array.isArray(d.analysis_rows)) step7AnalysisRows.value = d.analysis_rows
    if (typeof d.block_md === 'string') step7BlockMd.value = d.block_md
    if (typeof d.overall_md === 'string') step7OverallMd.value = d.overall_md
    if (typeof d.final_md === 'string') step7FinalMd.value = d.final_md
    if (typeof d.total_score === 'number') step7TotalScore.value = d.total_score
    if (typeof d.total_full === 'number') step7TotalFull.value = d.total_full
    if (typeof d.overall_rate === 'number') step7OverallRate.value = d.overall_rate
    if (typeof d.review_feedback === 'string') step7ReviewFeedback.value = d.review_feedback
    if (typeof d.survey_sample === 'number') step7SurveySample.value = d.survey_sample
    if (typeof d.survey_rate === 'number') step7SurveyRate.value = d.survey_rate
    if (typeof d.survey_summary === 'string') step7SurveySummary.value = d.survey_summary
    if (typeof d.export_font_family === 'string') step7ExportFontFamily.value = d.export_font_family
    if (typeof d.export_font_size === 'number') step7ExportFontSize.value = d.export_font_size
    if (typeof d.export_line_height === 'number') step7ExportLineHeight.value = d.export_line_height
    return true
  } catch {
    return false
  }
}

function clearStep7DraftState() {
  if (!projectId.value) return
  localStorage.removeItem(step7DraftKey())
}

function step7BuildFormFromUpstream(): Step7IndicatorForm[] {
  // 兜底：当后端 expand_points 还没返回时（首次进入），先在前端按相同规则展开 form schema
  const prev = (prevStepResult.value || {}) as Record<string, unknown>
  const tree = Array.isArray(prev['scored_tree']) ? prev['scored_tree'] as any[] : []
  const stds = Array.isArray(prev['score_standards']) ? prev['score_standards'] as any[] : []
  const stdById: Record<string, any> = {}
  for (const s of stds) { if (s && s.id) stdById[String(s.id)] = s }
  const splitRe = /[；;\n、]+/
  const bulletRe = /^\s*(?:[-•·●▪◆◇○*]|\d+[\.\)、])\s*/
  const forms: Step7IndicatorForm[] = []
  for (const l1 of tree) {
    for (const l2 of (l1?.level2 || [])) {
      for (const l3 of (l2?.level3 || [])) {
        const id = String(l3?.id || '')
        const std = stdById[id] || {}
        const score = Number(l3?.score || 0)
        const kp = String(std.key_points || l3?.key_points || '')
        const rubric = (std.rubric || l3?.rubric || {}) as Record<string, string>
        const labels = (kp.split(splitRe).map((p: string) => p.replace(bulletRe, '').replace(/[：:。.，, ]+$/g, '').trim()).filter(Boolean))
        const finalLabels = labels.length ? labels : ['整体执行情况']
        const avg = Math.round((score / Math.max(finalLabels.length, 1)) * 100) / 100
        const points: Step7PointSlot[] = finalLabels.map((label: string, idx: number) => ({
          key: `P${idx + 1}`,
          label,
          hint: ((rubric['良好'] || rubric['合格'] || '') + '').slice(0, 120),
          suggested_score: avg,
        }))
        forms.push({
          id, l1_name: String(l1?.name || ''), l2_name: String(l2?.name || ''), l3_name: String(l3?.name || ''),
          score, tag: String(l3?.tag || std.tag || '其他'), points, rubric,
        })
      }
    }
  }
  return forms
}

function step7EnsureForm() {
  if (!step7Form.value.length) {
    step7Form.value = step7BuildFormFromUpstream()
  }
  // 同步 inputs：保留已填值，按 form 的 points 顺序补齐缺位
  const next: Record<string, Step7PointInput[]> = {}
  for (const form of step7Form.value) {
    const old = step7Inputs.value[form.id] || []
    const byKey: Record<string, Step7PointInput> = {}
    for (const p of old) byKey[p.key] = p
    next[form.id] = form.points.map((slot) => byKey[slot.key] || ({
      key: slot.key, label: slot.label, plain_text: '', score: 0, deduction_reason: '',
    }))
  }
  step7Inputs.value = next
}

async function step7BootstrapForm() {
  if (step7Bootstrapping.value) return
  step7Bootstrapping.value = true
  try {
    const cur: Record<string, unknown> = (prevStepResult.value as Record<string, unknown>)
      ? { ...(prevStepResult.value as Record<string, unknown>) } : {}
    const needTree = () => !Array.isArray(cur['scored_tree']) || !(cur['scored_tree'] as unknown[]).length
    const needStds = () => !Array.isArray(cur['score_standards']) || !(cur['score_standards'] as unknown[]).length

    // 1) 优先从持久化 step_output 取（用户已 save final 的情况）
    if (needTree() && projectId.value) {
      try {
        const s4 = await getStepResult('step4', projectId.value)
        const raw = (s4.result as Record<string, unknown>) || null
        if (raw && typeof raw.content_json === 'string') {
          const parsed = JSON.parse(raw.content_json)
          if (parsed && Array.isArray(parsed.scored_tree)) cur['scored_tree'] = parsed.scored_tree
          if (parsed && typeof parsed.project_core_content === 'string' && !cur['project_core_content']) {
            cur['project_core_content'] = parsed.project_core_content
          }
        }
      } catch { /* ignore */ }
    }
    if (needStds() && projectId.value) {
      try {
        const s5 = await getStepResult('step5', projectId.value)
        const raw = (s5.result as Record<string, unknown>) || null
        if (raw && typeof raw.content_json === 'string') {
          const parsed = JSON.parse(raw.content_json)
          if (parsed && Array.isArray(parsed.score_standards)) cur['score_standards'] = parsed.score_standards
          if (parsed && Array.isArray(parsed.scored_tree) && needTree()) {
            cur['scored_tree'] = parsed.scored_tree
          }
        }
      } catch { /* ignore */ }
    }

    // 2) fallback 去 LangGraph MemorySaver 短期记忆 thread 找草稿
    //    （CLAUDE.md：step4/step5 未确认提交时只放短期记忆，step_output 是空的）
    if (needTree() && projectId.value) {
      try {
        const t4 = await getThreadState({ step_code: 'step4', thread_id: `step4:${projectId.value}` })
        const st4 = (t4?.state || {}) as Record<string, unknown>
        if (Array.isArray(st4['scored_tree']) && (st4['scored_tree'] as unknown[]).length) {
          cur['scored_tree'] = st4['scored_tree']
        }
        if (typeof st4['project_core_content'] === 'string' && !cur['project_core_content']) {
          cur['project_core_content'] = st4['project_core_content']
        }
      } catch { /* ignore */ }
    }
    if (needStds() && projectId.value) {
      try {
        const t5 = await getThreadState({ step_code: 'step5', thread_id: `step5:${projectId.value}` })
        const st5 = (t5?.state || {}) as Record<string, unknown>
        if (Array.isArray(st5['score_standards']) && (st5['score_standards'] as unknown[]).length) {
          cur['score_standards'] = st5['score_standards']
        }
        if (Array.isArray(st5['scored_tree']) && needTree()) {
          cur['scored_tree'] = st5['scored_tree']
        }
      } catch { /* ignore */ }
    }

    prevStepResult.value = { ...cur }
    step7Form.value = step7BuildFormFromUpstream()
    step7EnsureForm()
    if (!step7Form.value.length) {
      ElMessage.warning('未识别到三级指标，请确认 Step 4 / Step 5 已生成（保存草稿或最终版本均可）。')
    } else {
      saveStep7DraftState()
      ElMessage.success(`已构造 ${step7Form.value.length} 条三级指标录入表单。`)
    }
  } finally {
    step7Bootstrapping.value = false
  }
}

async function generateStep7Analysis() {
  if (step7Generating.value) return
  // 1) 先确保 prev 拥有 step4(scored_tree) + step5(score_standards)；缺哪一项就实时回源补齐。
  const ensurePrev = async () => {
    const cur: Record<string, unknown> = (prevStepResult.value as Record<string, unknown>) ? { ...(prevStepResult.value as Record<string, unknown>) } : {}
    const needTree = !Array.isArray(cur['scored_tree']) || !(cur['scored_tree'] as unknown[]).length
    const needStds = !Array.isArray(cur['score_standards']) || !(cur['score_standards'] as unknown[]).length
    if (needTree) {
      try {
        const s4 = await getStepResult('step4', projectId.value)
        const raw = (s4.result as Record<string, unknown>) || null
        if (raw && typeof raw.content_json === 'string') {
          const parsed = JSON.parse(raw.content_json)
          if (parsed && Array.isArray(parsed.scored_tree)) cur['scored_tree'] = parsed.scored_tree
          if (parsed && typeof parsed.project_core_content === 'string' && !cur['project_core_content']) cur['project_core_content'] = parsed.project_core_content
        }
      } catch { /* ignore */ }
    }
    if (needStds) {
      try {
        const s5 = await getStepResult('step5', projectId.value)
        const raw = (s5.result as Record<string, unknown>) || null
        if (raw && typeof raw.content_json === 'string') {
          const parsed = JSON.parse(raw.content_json)
          if (parsed && Array.isArray(parsed.score_standards)) cur['score_standards'] = parsed.score_standards
          if (parsed && Array.isArray(parsed.scored_tree) && (!Array.isArray(cur['scored_tree']) || !(cur['scored_tree'] as unknown[]).length)) cur['scored_tree'] = parsed.scored_tree
        }
      } catch { /* ignore */ }
    }
    prevStepResult.value = { ...cur }
    return cur
  }
  const prev = await ensurePrev()
  const treeOk = Array.isArray(prev['scored_tree']) && (prev['scored_tree'] as unknown[]).length > 0
  const stdsOk = Array.isArray(prev['score_standards']) && (prev['score_standards'] as unknown[]).length > 0
  if (!treeOk || !stdsOk) {
    ElMessage.error(`无法生成：${!treeOk ? '缺少第四步定稿分值（scored_tree）' : ''}${!treeOk && !stdsOk ? '；' : ''}${!stdsOk ? '缺少第五步评分标准（score_standards）' : ''}。请先回到对应步骤完成并保存。`)
    return
  }
  step7EnsureForm()
  if (!step7Form.value.length) {
    ElMessage.warning('未识别到三级指标，请确认 step4 / step5 是否已生成。')
    return
  }
  step7Generating.value = true
  try {
    const base = buildGenericAgentPayload()
    const surveySummary = step7SurveySummary.value
      || ((step7SurveySample.value ? `有效样本量：${step7SurveySample.value}；` : '')
        + (step7SurveyRate.value ? `综合满意率：${(step7SurveyRate.value * 100).toFixed(2)}%` : '')).trim()
    const res = await runAgent<Record<string, unknown>>({
      step_code: 'step7',
      payload: {
        ...base,
        indicator_form: step7Form.value,
        indicator_inputs: step7Inputs.value,
        survey_summary: surveySummary,
        survey_sample_size: step7SurveySample.value || 0,
        survey_satisfaction_rate: step7SurveyRate.value || 0,
        review_feedback: step7ReviewFeedback.value,
      },
    })
    const r = (res?.result || {}) as Record<string, unknown>
    if (Array.isArray(r['indicator_form']) && (r['indicator_form'] as unknown[]).length) {
      step7Form.value = r['indicator_form'] as Step7IndicatorForm[]
      step7EnsureForm()
    }
    if (Array.isArray(r['analysis_rows'])) step7AnalysisRows.value = r['analysis_rows'] as Step7AnalysisRow[]
    if (typeof r['block_tables_markdown'] === 'string') step7BlockMd.value = r['block_tables_markdown'] as string
    if (typeof r['overall_score_table_markdown'] === 'string') step7OverallMd.value = r['overall_score_table_markdown'] as string
    if (typeof r['total_score'] === 'number') step7TotalScore.value = r['total_score'] as number
    if (typeof r['total_full_score'] === 'number') step7TotalFull.value = r['total_full_score'] as number
    if (typeof r['overall_score_rate'] === 'number') step7OverallRate.value = r['overall_score_rate'] as number
    if (Array.isArray(r['model_comparisons'])) step7Comparisons.value = r['model_comparisons'] as Step7Comparison[]
    if (typeof r['final_score_sheet_markdown'] === 'string') {
      step7FinalMd.value = r['final_score_sheet_markdown'] as string
      editor.value = step7FinalMd.value
      resultText.value = editor.value
    } else if (typeof r['analysis_draft_markdown'] === 'string') {
      editor.value = r['analysis_draft_markdown'] as string
      resultText.value = editor.value
    }
    currentResult.value = r
    saveStep7DraftState()
    ElMessage.success('指标分析已生成（草稿仅在短期记忆，未持久化）。')
  } catch (e: any) {
    ElMessage.error(`生成失败：${e?.response?.data?.detail || e?.message || e}`)
  } finally {
    step7Generating.value = false
  }
}

async function reviewStep7Analysis() {
  if (step7Reviewing.value) return
  if (!step7ReviewFeedback.value.trim()) {
    ElMessage.warning('请先填写人工修改意见后再进行软磨润色。')
    return
  }
  step7Reviewing.value = true
  try {
    await generateStep7Analysis()
  } finally {
    step7Reviewing.value = false
  }
}

function step7AdoptComparison(c: Step7Comparison) {
  if (!c?.draft) return
  try {
    // 解析模型 JSON，把它的 analysis 应用到当前 rows
    const parsed = JSON.parse(c.draft.replace(/^```(?:json)?/, '').replace(/```$/, ''))
    const items = Array.isArray(parsed?.rows) ? parsed.rows : []
    const byId: Record<string, any> = {}
    for (const it of items) { if (it?.id) byId[String(it.id)] = it }
    step7AnalysisRows.value = step7AnalysisRows.value.map((row) => {
      const it = byId[row.id]
      if (!it) return row
      const userSum = (step7Inputs.value[row.id] || []).reduce((s, p) => s + (Number(p.score) || 0), 0)
      const obtained = userSum > 0 ? userSum : Number(it.obtained_score || row.obtained_score || 0)
      const clamped = Math.max(0, Math.min(row.score, Math.round(obtained * 100) / 100))
      return {
        ...row,
        obtained_score: clamped,
        score_rate: row.score ? clamped / row.score : 0,
        deduction_reason: String(it.deduction_reason || row.deduction_reason || ''),
        analysis: String(it.analysis || row.analysis || ''),
        model_name: c.model_name,
      }
    })
    saveStep7DraftState()
    // 采用某模型后，"终审定稿成果"也用当前 rows 即时重拼一份，保证 UI 终审区与 rows 同步。
    try { step7FinalMd.value = buildStep7CombinedMarkdown() } catch { /* ignore */ }
    ElMessage.success(`已采用 ${c.label || c.model_name} 的分析结果。`)
  } catch {
    ElMessage.error('该模型返回内容解析失败，无法直接采用。')
  }
}

function buildStep7CombinedMarkdown(): string {
  const parts: string[] = []
  const safeName = (projectName.value || '未命名项目').replace(/[\\/:*?"<>|]/g, '_')
  parts.push(`# 《${safeName}项目绩效评价指标体系得分表》`)
  parts.push('')
  parts.push(
    `<!-- 个性化导出参数：font-family=${step7ExportFontFamily.value}; font-size=${step7ExportFontSize.value}pt; line-height=${step7ExportLineHeight.value} -->`,
  )
  parts.push('')
  parts.push(`> 项目核心：${(prevStepResult.value as any)?.project_core_content || '（暂无）'}`)
  parts.push(
    `> 抽样规模：${step7SurveySample.value || 0}；问卷回收率：${((step7SurveyRate.value ?? 0) * 100).toFixed(1)}%；满意度概览：${step7SurveySummary.value || '（无）'}`,
  )
  parts.push('')
  parts.push(`> 总得分：${step7TotalScore.value} / ${step7TotalFull.value}（综合得分率 ${(step7OverallRate.value * 100).toFixed(2)}%）`)
  parts.push('')
  if (step7BlockMd.value && step7BlockMd.value.trim()) {
    parts.push('## 一、四大板块明细（决策 / 过程 / 产出 / 效益）')
    parts.push('')
    parts.push(step7BlockMd.value.trim())
    parts.push('')
  }
  if (step7OverallMd.value && step7OverallMd.value.trim()) {
    parts.push('## 二、总评分表（合并指标层级 + 加权得分）')
    parts.push('')
    parts.push(step7OverallMd.value.trim())
    parts.push('')
  }
  if (step7AnalysisRows.value.length) {
    parts.push('## 三、AI 事实级深度分析（逐三级指标）')
    parts.push('')
    for (const row of step7AnalysisRows.value) {
      parts.push(`### ${row.l1_name} / ${row.l2_name} / ${row.l3_name}（${row.obtained_score}/${row.score}，得分率 ${(row.score_rate * 100).toFixed(1)}%）`)
      if (row.deduction_reason) parts.push(`- 扣分原因：${row.deduction_reason}`)
      if (row.analysis) {
        parts.push('')
        parts.push(row.analysis)
      }
      parts.push('')
    }
  }
  return parts.join('\n')
}

function exportStep7Document() {
  if (!step7AnalysisRows.value.length && !step7BlockMd.value && !step7OverallMd.value) {
    ElMessage.warning('当前没有可导出的指标体系分析，请先生成内容。')
    return
  }
  try {
    const md = buildStep7CombinedMarkdown()
    const safeName = (projectName.value || '未命名项目').replace(/[\\/:*?"<>|]/g, '_')
    const blob = new Blob([md], { type: 'text/markdown;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `${safeName}项目绩效评价指标体系得分表.md`
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
    ElMessage.success(`已导出《${safeName}项目绩效评价指标体系得分表.md》`)
  } catch (err) {
    console.error(err)
    ElMessage.error('导出失败，请重试。')
  }
}

function buildStep4AgentPayload() {
  const base = buildGenericAgentPayload()
  const prev = prevStepResult.value || {}
  return {
    ...base,
    flat_l2_tasks: step4FlatL2Tasks.value.map((t) => ({
      level1_name: t.level1_name,
      level2_name: t.level2_name,
      target_l3_count: t.target_l3_count ?? 1,
      l3_section_markdown: t.l3_section_markdown ?? '',
    })),
    assign_mode: step4ScoringMode.value === 'ai' ? 'llm' : 'manual',
    manual_l3_scores: step4ScoringMode.value === 'manual' ? step4ManualScores.value : {},
    total_score: step4TotalScore.value,
    project_core_content:
      typeof prev['project_core_content'] === 'string'
        ? prev['project_core_content']
        : (typeof prev['final_core_content'] === 'string' ? prev['final_core_content'] : ''),
  }
}

function buildStep5AgentPayload() {
  const base = buildGenericAgentPayload()
  const prev = prevStepResult.value || {}
  const scoredTree = Array.isArray(prev['scored_tree']) ? prev['scored_tree'] : []
  return {
    ...base,
    score_sheet: step5ScoreSheet.value,
    scored_tree: scoredTree,
    total_score: typeof prev['total_score'] === 'number' ? prev['total_score'] : step4TotalScore.value,
    final_indicator_markdown: typeof prev['final_indicator_markdown'] === 'string' ? prev['final_indicator_markdown'] : prevStepContent.value,
    project_core_content: typeof prev['project_core_content'] === 'string' ? prev['project_core_content'] : '',
    content_text: prevStepContent.value || editor.value,
  }
}

function buildStep6AgentPayload() {
  const base = buildGenericAgentPayload()
  const prev = prevStepResult.value || {}
  // step6 验收要求 scored_tree（来自 step4） + score_standards（来自 step5）。step5 的 prev 里同时也带着这两份。
  const scoredTree = Array.isArray(prev['scored_tree']) ? prev['scored_tree'] : []
  const scoreStandards = Array.isArray(prev['score_standards']) ? prev['score_standards'] : []
  return {
    ...base,
    scored_tree: scoredTree,
    score_standards: scoreStandards,
    project_core_content: typeof prev['project_core_content'] === 'string' ? prev['project_core_content'] : '',
    questionnaire_decision: step6QuestionnaireDecision.value,
    review_feedback: step6QuestionnaireFeedback.value,
    content_text: prevStepContent.value || editor.value,
  }
}

// ==================== step6 指标拖拽：解析/序列化 ====================
function step6MdEscape(text: string): string {
  return String(text || '').replace(/\|/g, '/').replace(/\n/g, '<br/>').replace(/\r/g, '')
}

function step6ShortRubric(text: string, limit = 36): string {
  const t = String(text || '').trim().replace(/\n/g, ' ')
  return t.length <= limit ? t : t.slice(0, limit - 1) + '…'
}

function step6LocalCompressRubric(rubric: Record<string, string> | undefined, score: number): string {
  const r = rubric || {}
  const f = (v: number) => v.toFixed(0)
  return (
    `优≥${f(score * 0.9)}分:${step6ShortRubric(r['优秀'] || '')};`
    + `良${f(score * 0.75)}-${f(score * 0.89)}:${step6ShortRubric(r['良好'] || '')};`
    + `合${f(score * 0.6)}-${f(score * 0.74)}:${step6ShortRubric(r['合格'] || '')};`
    + `差≤${f(score * 0.59)}:${step6ShortRubric(r['不合格'] || '')}`
  )
}

function nowIsoCN(): string {
  return new Date().toISOString().replace('T', ' ').slice(0, 19)
}

function rebuildFrameworkMarkdownFromTree(
  projectName: string,
  tree: Step6L1Node[],
  standards: Array<Record<string, unknown>>,
  compressedRubrics: Record<string, string>,
): string {
  const explanationIndex: Record<string, string> = {}
  const rubricIndex: Record<string, Record<string, string>> = {}
  for (const s of standards || []) {
    const id = String((s as Record<string, unknown>)['id'] || '')
    if (!id) continue
    explanationIndex[id] = String((s as Record<string, unknown>)['key_points'] || '')
    const rb = (s as Record<string, unknown>)['rubric']
    if (rb && typeof rb === 'object') rubricIndex[id] = rb as Record<string, string>
  }
  const lines: string[] = [
    `# 《${projectName} — 绩效评价指标体系》`,
    '',
    `- 生成时间：${nowIsoCN()}`,
    '',
    '## 指标体系表',
    '',
    '| 一级指标 | 二级指标 | 三级指标 | 分值 | 指标解释 | 评分标准 |',
    '| --- | --- | --- | --- | --- | --- |',
  ]
  let lastL1 = ''
  let lastL2 = ''
  for (const l1 of tree) {
    const l1Score = Number(l1.score) || 0
    const l1Name = String(l1.name || '')
    const l1Label = `${l1Name}（${l1Score.toFixed(0)} 分）`
    for (const l2 of l1.level2 || []) {
      const l2Score = Number(l2.score) || 0
      const l2Name = String(l2.name || '')
      const l2Label = `${l2Name}（${l2Score.toFixed(0)} 分）`
      const l3List = l2.level3 || []
      if (!l3List.length) continue
      for (const l3 of l3List) {
        const rowId = String(l3.id || '')
        const l3Name = String(l3.name || '')
        const l3Score = Number(l3.score) || 0
        const explanation = explanationIndex[rowId] || String(l3.key_points || '')
        const rubricDict = rubricIndex[rowId] || l3.rubric || {}
        const rubricText = compressedRubrics[rowId]
          ? compressedRubrics[rowId]
          : step6LocalCompressRubric(rubricDict, l3Score)
        const l1Cell = l1Name !== lastL1 ? l1Label : ''
        const l2Cell = (l2Name !== lastL2 || l1Name !== lastL1) ? l2Label : ''
        lastL1 = l1Name
        lastL2 = l2Name
        lines.push(
          `| ${step6MdEscape(l1Cell)} | ${step6MdEscape(l2Cell)} | ${step6MdEscape(l3Name)} | ${l3Score.toFixed(0)} | ${step6MdEscape(explanation || '（暂无解释）')} | ${step6MdEscape(rubricText)} |`
        )
      }
    }
  }
  lines.push('')
  return lines.join('\n')
}

function parseScoredTreeIntoStep6Tree() {
  const raw = currentResult.value?.['scored_tree']
  if (!Array.isArray(raw)) {
    step6Tree.value = []
    return
  }
  // 深拷贝，避免拖拽直接改到原 currentResult，确认提交前都只在拷贝里编辑
  const cloned: Step6L1Node[] = []
  for (const l1 of raw as any[]) {
    const level2: Step6L2Node[] = []
    for (const l2 of (l1?.level2 || []) as any[]) {
      const level3: Step6L3Node[] = []
      for (const l3 of (l2?.level3 || []) as any[]) {
        level3.push({
          id: String(l3?.id ?? ''),
          name: String(l3?.name ?? ''),
          score: Number(l3?.score) || 0,
          key_points: typeof l3?.key_points === 'string' ? l3.key_points : '',
          rubric: l3?.rubric && typeof l3.rubric === 'object' ? { ...l3.rubric } : {},
        })
      }
      level2.push({
        name: String(l2?.name ?? ''),
        score: Number(l2?.score) || 0,
        level3,
      })
    }
    cloned.push({
      name: String(l1?.name ?? ''),
      score: Number(l1?.score) || 0,
      level2,
    })
  }
  step6Tree.value = cloned
  step6TreeDirty.value = false
}

function applyStep6TreeBackToResult() {
  if (!currentResult.value || !Array.isArray(step6Tree.value) || !step6Tree.value.length) return
  const standards = Array.isArray(currentResult.value['score_standards'])
    ? (currentResult.value['score_standards'] as Array<Record<string, unknown>>)
    : []
  const compressed = (currentResult.value['compressed_rubrics'] && typeof currentResult.value['compressed_rubrics'] === 'object')
    ? (currentResult.value['compressed_rubrics'] as Record<string, string>)
    : {}
  const md = rebuildFrameworkMarkdownFromTree(
    projectName.value || '未命名项目',
    step6Tree.value,
    standards,
    compressed,
  )
  // 写回纯数据 scored_tree 供 step7+ 复用
  const newTree = step6Tree.value.map((l1) => ({
    name: l1.name,
    score: l1.score,
    level2: l1.level2.map((l2) => ({
      name: l2.name,
      score: l2.score,
      level3: l2.level3.map((l3) => ({
        id: l3.id,
        name: l3.name,
        score: l3.score,
        key_points: l3.key_points || '',
        rubric: l3.rubric || {},
      })),
    })),
  }))
  currentResult.value = {
    ...currentResult.value,
    scored_tree: newTree,
    final_indicator_framework_markdown: md,
  }
  editor.value = md
  resultText.value = JSON.stringify(currentResult.value, null, 2)
  if (projectId.value) {
    saveGenericStepDraft(stepCodeOf(), {
      project_id: projectId.value,
      thread_id: `step6:${projectId.value}`,
      content_text: editor.value,
      content_json: resultText.value,
      current_result: currentResult.value,
    })
  }
}

function destroyStep6Sortables() {
  while (step6SortableInstances.length) {
    const inst = step6SortableInstances.pop()
    try { inst?.destroy() } catch { /* noop */ }
  }
}

function mountStep6Sortables() {
  destroyStep6Sortables()
  if (!step6Tree.value.length) return
  const onEnd = () => {
    step6TreeDirty.value = true
    applyStep6TreeBackToResult()
  }
  // L1 之间允许整组拖动
  if (step6L1ListRef.value) {
    step6SortableInstances.push(new Sortable(step6L1ListRef.value, {
      group: 'step6-l1',
      animation: 150,
      handle: '.step6-drag-handle',
      onEnd: (evt) => {
        if (evt.oldIndex === evt.newIndex) return
        const arr = step6Tree.value
        const [moved] = arr.splice(evt.oldIndex!, 1)
        arr.splice(evt.newIndex!, 0, moved)
        onEnd()
      },
    }))
  }
  // L2 仅在同一 L1 内允许重排
  step6Tree.value.forEach((l1, l1Idx) => {
    const key = `l2-${l1Idx}`
    const el = step6L2ListRefs.value[key]
    if (!el) return
    step6SortableInstances.push(new Sortable(el, {
      group: { name: `step6-l2-${l1Idx}`, pull: false, put: false },
      animation: 150,
      handle: '.step6-drag-handle',
      onEnd: (evt) => {
        if (evt.oldIndex === evt.newIndex) return
        const arr = l1.level2
        const [moved] = arr.splice(evt.oldIndex!, 1)
        arr.splice(evt.newIndex!, 0, moved)
        onEnd()
      },
    }))
    // L3 仅在同一 L2 内允许重排
    l1.level2.forEach((l2, l2Idx) => {
      const key3 = `l3-${l1Idx}-${l2Idx}`
      const el3 = step6L3ListRefs.value[key3]
      if (!el3) return
      step6SortableInstances.push(new Sortable(el3, {
        group: { name: `step6-l3-${l1Idx}-${l2Idx}`, pull: false, put: false },
        animation: 150,
        handle: '.step6-drag-handle',
        onEnd: (evt) => {
          if (evt.oldIndex === evt.newIndex) return
          const arr = l2.level3
          const [moved] = arr.splice(evt.oldIndex!, 1)
          arr.splice(evt.newIndex!, 0, moved)
          onEnd()
        },
      }))
    })
  })
}

watch(
  () => [stepId.value, currentResult.value?.['scored_tree']],
  async () => {
    if (stepId.value === 6) {
      parseScoredTreeIntoStep6Tree()
      await nextTick()
      mountStep6Sortables()
    } else {
      destroyStep6Sortables()
      step6Tree.value = []
    }
    if (stepId.value === 7) {
      // 优先 localStorage 草稿，没有再按上游构建 form
      if (!loadStep7DraftState()) {
        step7Form.value = step7BuildFormFromUpstream()
        step7AnalysisRows.value = []
        step7BlockMd.value = ''
        step7OverallMd.value = ''
        step7FinalMd.value = ''
        step7TotalScore.value = 0
        step7TotalFull.value = 0
        step7OverallRate.value = 0
        step7Comparisons.value = []
      }
      step7EnsureForm()
      // 进入 step7 时若 prev 还没回源完成（首次进入或刷新），form 会是空的，
      // 这里自动走一次 bootstrap，去 step4/step5 直接拉数据补齐，避免空状态死锁。
      if (!step7Form.value.length && projectId.value) {
        await step7BootstrapForm()
      }
    }
  },
  { immediate: true, deep: false },
)

// step7 表单 / inputs / 反馈 / 问卷数据变化 → 自动写入 localStorage 短期记忆（CLAUDE.md 双层缓存兜底）
watch(
  () => [stepId.value, step7Inputs.value, step7AnalysisRows.value, step7ReviewFeedback.value,
         step7SurveySample.value, step7SurveyRate.value, step7SurveySummary.value,
         step7ExportFontFamily.value, step7ExportFontSize.value, step7ExportLineHeight.value],
  () => {
    if (stepId.value === 7 && projectId.value) saveStep7DraftState()
  },
  { deep: true },
)

// prevStepResult 异步回源完成后（首次进入 step7 时上游 step4/step5 数据可能还在路上），
// 若此时 step7Form 仍为空，立即按上游构造一遍，避免用户看到永远的空状态。
watch(
  () => prevStepResult.value,
  () => {
    if (stepId.value !== 7) return
    if (step7Form.value.length) return
    const built = step7BuildFormFromUpstream()
    if (built.length) {
      step7Form.value = built
      step7EnsureForm()
    }
  },
  { deep: true },
)

function buildStep6QuestionnaireMarkdown(): string {
  if (!step6QuestionnaireItems.value.length) return step6QuestionnaireDraft.value || ''
  const lines: string[] = ['# 里克特 5 级满意度问卷']
  step6QuestionnaireItems.value.forEach((q, idx) => {
    lines.push('')
    lines.push(`## ${idx + 1}. ${q.question}`)
    if (q.indicator_name) lines.push(`> 关联指标：${q.indicator_name}`)
    q.options.forEach((opt) => lines.push(`- [ ] ${opt}`))
  })
  return lines.join('\n')
}

function buildStep6CombinedMarkdown(): string {
  const framework = (currentResult.value
    && typeof (currentResult.value as Record<string, unknown>)['final_indicator_framework_markdown'] === 'string'
    ? ((currentResult.value as Record<string, unknown>)['final_indicator_framework_markdown'] as string)
    : '') || editor.value || ''
  const questionnaire = buildStep6QuestionnaireMarkdown()
  const blocks: string[] = []
  if (framework.trim()) blocks.push('# 绩效评价指标体系（现场评分表）', '', framework.trim())
  if (questionnaire.trim()) blocks.push('', '---', '', questionnaire.trim())
  return blocks.join('\n')
}

async function copyToClipboard(text: string) {
  if (!text) return
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text)
    } else {
      const ta = document.createElement('textarea')
      ta.value = text
      ta.style.position = 'fixed'
      ta.style.left = '-9999px'
      document.body.appendChild(ta)
      ta.select()
      document.execCommand('copy')
      document.body.removeChild(ta)
    }
    ElMessage.success('已复制到剪贴板')
  } catch {
    ElMessage.warning('复制失败，请手动选中文本')
  }
}

function downloadStep6Markdown() {
  const md = buildStep6CombinedMarkdown()
  if (!md.trim()) {
    ElMessage.warning('当前没有可导出的内容，请先生成指标体系或问卷。')
    return
  }
  step6Exporting.value = true
  try {
    const safeName = (projectName.value || '未命名项目').replace(/[\\/:*?"<>|]/g, '_')
    const blob = new Blob([md], { type: 'text/markdown;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `${safeName}_step6_指标体系与问卷.md`
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
    ElMessage.success('已下载 Markdown')
  } finally {
    step6Exporting.value = false
  }
}

function step6ResponsesKey(pid: string) {
  return `ef_q_responses:${pid}`
}

function loadStep6Responses() {
  if (!projectId.value) return
  try {
    const raw = localStorage.getItem(step6ResponsesKey(projectId.value))
    if (!raw) {
      step6ResponseHistory.value = []
      return
    }
    const arr = JSON.parse(raw)
    step6ResponseHistory.value = Array.isArray(arr) ? (arr as Step6ResponseRecord[]) : []
  } catch {
    step6ResponseHistory.value = []
  }
}

function submitStep6Response() {
  if (!projectId.value) return
  if (!step6QuestionnaireItems.value.length) {
    ElMessage.warning('当前没有可提交的问卷题目。')
    return
  }
  const unanswered = step6QuestionnaireItems.value.filter((q) => !step6Answers.value[q.id])
  if (unanswered.length) {
    ElMessage.warning(`还有 ${unanswered.length} 题未作答`)
    return
  }
  const record: Step6ResponseRecord = {
    version: typeof (currentResult.value as Record<string, unknown> | null)?.['version'] === 'number'
      ? ((currentResult.value as Record<string, unknown>)['version'] as number)
      : 0,
    respondent_role: step6RespondentRole.value,
    answers: { ...step6Answers.value },
    submitted_at: new Date().toISOString(),
  }
  loadStep6Responses()
  step6ResponseHistory.value = [...step6ResponseHistory.value, record]
  try {
    localStorage.setItem(
      step6ResponsesKey(projectId.value),
      JSON.stringify(step6ResponseHistory.value),
    )
    ElMessage.success(`已提交 1 份问卷（角色：${record.respondent_role}）`)
    step6Answers.value = {}
  } catch (e) {
    ElMessage.error('保存到本地失败：' + (e instanceof Error ? e.message : String(e)))
  }
}

function clearStep6Responses() {
  if (!projectId.value) return
  localStorage.removeItem(step6ResponsesKey(projectId.value))
  step6ResponseHistory.value = []
  ElMessage.success('已清空本地问卷答案')
}

function buildStep9AgentPayload() {
  const base = buildGenericAgentPayload()
  return {
    ...base,
    style_mode: step9StyleMode.value,
    content_text: prevStepContent.value || editor.value,
  }
}

function buildStep14AgentPayload() {
  const base = buildGenericAgentPayload()
  return {
    ...base,
    content_text: prevStepContent.value || editor.value,
    custom_title: step14ExportCustomTitle.value || null,
  }
}

function buildAgentPayloadByStep() {
  if (stepId.value === 1) return buildStep1AgentPayload()
  if (stepId.value === 2) return buildStep2AgentPayload()
  if (stepId.value === 3) return buildStep3AgentPayload()
  if (stepId.value === 4) return buildStep4AgentPayload()
  if (stepId.value === 5) return buildStep5AgentPayload()
  if (stepId.value === 6) return buildStep6AgentPayload()
  if (stepId.value === 9) return buildStep9AgentPayload()
  if (stepId.value === 14) return buildStep14AgentPayload()
  if (stepId.value >= 6 && stepId.value <= 13) {
    const base = buildGenericAgentPayload()
    return { ...base, content_text: prevStepContent.value || editor.value }
  }
  return buildGenericAgentPayload()
}

function validateStep4Scores(): { errors: string[]; warnings: string[] } {
  const errors: string[] = []
  const warnings: string[] = []
  const items = step4FlatL2Tasks.value
  const scores = step4ManualScores.value

  if (step4ScoringMode.value === 'manual') {
    let total = 0
    for (const item of items) {
      const key = `${item.level1_name}|${item.level2_name}`
      const score = scores[key] ?? item.score ?? 0
      if (score < 0 || score > 100) {
        errors.push(`「${item.level2_name}」分值 ${score} 超出 [0, 100] 范围`)
      }
      total += score
    }
    if (Math.abs(total - step4TotalScore.value) > 0.01) {
      errors.push(`各项分值之和 ${total.toFixed(2)} ≠ 总分 ${step4TotalScore.value}`)
    }

    const l1Groups: Record<string, number[]> = {}
    for (const item of items) {
      const key = `${item.level1_name}|${item.level2_name}`
      const score = scores[key] ?? item.score ?? 0
      if (!l1Groups[item.level1_name]) l1Groups[item.level1_name] = []
      l1Groups[item.level1_name].push(score)
    }
    for (const [l1, childScores] of Object.entries(l1Groups)) {
      const childSum = childScores.reduce((a, b) => a + b, 0)
      const parentWeight = items.find((i) => i.level1_name === l1)?.weight
      if (parentWeight !== undefined && Math.abs(childSum - parentWeight) > 0.01) {
        errors.push(`一级「${l1}」子项合计 ${childSum.toFixed(2)} ≠ 父级权重 ${parentWeight}`)
      }
    }

    const hasOutputBenefit = items.some(
      (i) => /产出|效益/.test(i.level1_name) || /产出|效益/.test(i.level2_name || '')
    )
    if (!hasOutputBenefit) {
      warnings.push('指标体系中未包含「产出」或「效益」相关指标，建议检查')
    }
  }

  step4ValidationErrors.value = errors
  return { errors, warnings }
}

function replaceStep1DraftFromChat(payload: { content: string; status: 'human_review' }) {
  const content = payload.content.trim()
  if (!content) return
  if (stepId.value === 3) {
    step3L3Draft.value = content
    ElMessage.success('已用 AI 对话结果更新当前三级指标草案，请继续审阅')
    return
  }
  if (stepId.value === 2) {
    editor.value = content
    const nextResult = {
      ...(currentResult.value ?? {}),
      core_content_draft: content,
      final_core_content: content,
      status: 'chat_replaced',
      review_mode: 'modify',
      source: 'chat_replace',
      updated_at: new Date().toISOString(),
    }
    currentResult.value = nextResult
    resultText.value = JSON.stringify(nextResult, null, 2)
    step2ReviewMode.value = 'modify'
    ElMessage.success('已替换为 AI 对话生成的核心内容，当前仍处于人机交互修改状态')
    return
  }
  if (stepId.value !== 1) return
  pushStep1DraftSnapshot(editor.value, 'before_chat_replace')
  editor.value = content
  const nextResult = {
    ...(currentResult.value ?? {}),
    draft_manifest: content,
    final_manifest: content,
    status: payload.status,
    review_mode: 'modify',
    approved: false,
    source: 'chat_replace',
    updated_at: new Date().toISOString(),
  }
  currentResult.value = nextResult
  resultText.value = JSON.stringify(nextResult, null, 2)
  saveStep1DraftState({
    project_id: projectId.value,
    thread_id: step1ThreadId.value,
    content_text: content,
    content_json: resultText.value,
    current_result: nextResult,
    project_name: projectName.value,
    project_files: inputProjectFiles.value,
    status: payload.status,
    review_mode: 'modify',
    approved: false,
    updated_at: new Date().toISOString(),
  })
  pushStep1DraftSnapshot(content, 'chat_replace')
  ElMessage.success('已替换为 AI 对话生成的资料清单草稿，当前仍处于人机交互修改状态')
}

// ---- Step3 specific functions ----

function parseStep3FlatL2Tasks(source: Record<string, unknown> | null): Step3L2Task[] {
  if (!source) return []
  const tasks = source['flat_l2_tasks']
  if (!Array.isArray(tasks)) return []
  return tasks
    .filter((item): item is Record<string, unknown> => Boolean(item) && typeof item === 'object')
    .map((row) => ({
      level1_name: String(row.level1_name || row.level1 || ''),
      level2_name: String(row.level2_name || row.level2 || ''),
      target_l3_count: Math.max(1, Math.min(20, Number(row.target_l3_count) || 3)),
      l3_section_markdown: String(row.l3_section_markdown || ''),
    }))
    .filter((task) => task.level1_name.trim() && task.level2_name.trim())
}

function parseStep3L3Comparisons(source: Record<string, unknown> | null): Array<{ model_name: string; label: string; draft: string; error: string }> {
  if (!source) return []
  const comparisons = source['l3_model_comparisons'] || source['model_comparisons']
  if (Array.isArray(comparisons)) {
    return comparisons.filter((c): c is { model_name: string; label: string; draft: string; error: string } => Boolean(c) && typeof c === 'object')
  }
  return []
}

function syncStep3FromResult(result: Record<string, unknown> | null) {
  if (!result) return

  const tasks = parseStep3FlatL2Tasks(result)
  if (tasks.length) {
    if (step3SkeletonTasks.value.length === 0) {
      step3SkeletonTasks.value = tasks
    } else {
      // Merge: preserve existing l3_section_markdown if backend returns empty for that task.
      const merged = tasks.map((incoming) => {
        const existing = step3SkeletonTasks.value.find(
          (t) => t.level1_name === incoming.level1_name && t.level2_name === incoming.level2_name,
        )
        if (existing && existing.l3_section_markdown && !incoming.l3_section_markdown) {
          return { ...incoming, l3_section_markdown: existing.l3_section_markdown }
        }
        return incoming
      })
      step3SkeletonTasks.value = merged
    }
  }

  if (typeof result.active_l2_index === 'number' && Number.isFinite(result.active_l2_index)) {
    // Only apply backend's index hint during initial load (no tasks yet), not during active generation.
    if (!step3SkeletonTasks.value.length) {
      step3ActiveL2Index.value = Math.max(0, Math.min(tasks.length - 1, result.active_l2_index as number))
    }
  }

  const draft = result.l3_active_draft
  if (typeof draft === 'string') {
    step3L3Draft.value = draft
  } else if (step3ActiveL2Task.value?.l3_section_markdown) {
    step3L3Draft.value = step3ActiveL2Task.value.l3_section_markdown
  }

  const comparisons = parseStep3L3Comparisons(result)
  if (comparisons.length) {
    step3L3Comparisons.value = comparisons
    compareItems.value = comparisons.map((item) => ({
      label: item.label || item.model_name || '模型',
      content: item.draft || (item.error ? `（调用失败：${item.error}）` : ''),
    }))
  }

  if (typeof result.system_type === 'string' && result.system_type.trim()) {
    step3Config.value.system_type = result.system_type
  }
  if (typeof result.indicator_depth === 'number') {
    step3Config.value.indicator_depth = result.indicator_depth as 3 | 4
  }

  const status = String(result.status || '')
  if (status === 'completed') {
    step3SkeletonPhase.value = 'completed'
    const finishText = readStep3FinishText(result)
    if (finishText) editor.value = finishText
  } else if (status === 'l3_draft_ready' || status === 'l3_refined' || status === 'l3_level_saved') {
    step3SkeletonPhase.value = 'generating_l3'
  } else if (status === 'skeleton_ready' || tasks.length > 0) {
    const allDone = tasks.length > 0 && tasks.every((t) => t.l3_section_markdown)
    const someDone = tasks.some((t) => t.l3_section_markdown)
    const hasDraft = Boolean(step3L3Draft.value)
    if (allDone) {
      step3SkeletonPhase.value = 'completed'
    } else if (someDone || hasDraft || step3SkeletonPhase.value === 'generating_l3') {
      step3SkeletonPhase.value = 'generating_l3'
    } else {
      step3SkeletonPhase.value = 'skeleton'
    }
  }

  currentResult.value = result
  resultText.value = JSON.stringify(result, null, 2)
}

function applyStep3Result(res: AgentRunResponse) {
  const payload = extractResult(res)
  const result = (payload && typeof payload === 'object' ? payload as Record<string, unknown> : null)
  syncStep3FromResult(result)
}

async function runStep3BuildSkeleton() {
  if (!step3HasStep2Core.value) {
    ElMessage.warning('请先确保 Step2 已定稿并保存核心内容')
    return
  }
  loading.value = true
  error.value = ''
  step3Config.value.review_mode = 'approve'
  step3Config.value.review_feedback = ''
  const runId = `step3:${projectId.value}:${Date.now()}:${Math.random().toString(16).slice(2)}`
  activeRunId.value = runId
  try {
    const payload = buildStep3AgentPayload()
    const primary = enabledActiveModelConfigs.value[0] ?? primaryActiveModelConfig.value
    const res = await runAgent({
      workflow_role: 'client',
      step_code: 'step3',
      payload: { ...payload, run_id: runId, model_configs: enabledActiveModelConfigs.value, temperature: primary.temperature },
      context: {
        project_id: projectId.value,
        thread_id: `step3:${projectId.value}`,
        workflow_role: 'client',
        run_id: runId,
        model_provider: primary.provider,
        model_name: primary.model_name,
        base_url: primary.base_url,
        api_key: primary.api_key,
        temperature: primary.temperature,
        active_model_name: primary.model_name,
        active_base_url: primary.base_url,
        active_api_key: primary.api_key,
        active_temperature: primary.temperature,
        active_model_configs: enabledActiveModelConfigs.value,
        compare_models: enabledActiveModelConfigs.value.map((m) => m.model_name),
        enable_multi_model: enabledActiveModelConfigs.value.length > 1,
      },
    })
    applyStep3Result(res)
    if (step3SkeletonTasks.value.length > 0 && step3SkeletonPhase.value !== 'completed') {
      step3SkeletonPhase.value = 'generating_l3'
    }
    saveStep3DraftState()
    ElMessage.success('指标体系骨架已构建，正在逐个生成三级指标，请审阅当前结果')
  } catch (e) {
    error.value = e instanceof Error ? e.message : '构建骨架失败'
  } finally {
    loading.value = false
    if (activeRunId.value === runId) activeRunId.value = ''
  }
}

async function runStep3Continue() {
  step3SkeletonPhase.value = 'generating_l3'
  loading.value = true
  error.value = ''
  const targetIndex = step3ActiveL2Index.value
  const runId = `step3:${projectId.value}:${Date.now()}:${Math.random().toString(16).slice(2)}`
  activeRunId.value = runId
  try {
    const payload = buildStep3AgentPayload()
    payload.review_mode = step3L3ReviewMode.value
    payload.review_feedback = step3L3ReviewMode.value === 'modify' ? step3L3Feedback.value : ''
    const primary = enabledActiveModelConfigs.value[0] ?? primaryActiveModelConfig.value
    const res = await runAgent({
      workflow_role: 'client',
      step_code: 'step3',
      payload: { ...payload, run_id: runId, model_configs: enabledActiveModelConfigs.value, temperature: primary.temperature },
      context: {
        project_id: projectId.value,
        thread_id: `step3:${projectId.value}`,
        workflow_role: 'client',
        run_id: runId,
        model_provider: primary.provider,
        model_name: primary.model_name,
        base_url: primary.base_url,
        api_key: primary.api_key,
        temperature: primary.temperature,
        active_model_name: primary.model_name,
        active_base_url: primary.base_url,
        active_api_key: primary.api_key,
        active_temperature: primary.temperature,
        active_model_configs: enabledActiveModelConfigs.value,
        compare_models: enabledActiveModelConfigs.value.map((m) => m.model_name),
        enable_multi_model: enabledActiveModelConfigs.value.length > 1,
      },
    })
    applyStep3Result(res)
    // Restore the user's selected tab — backend may return a different active_l2_index.
    if (targetIndex >= 0 && targetIndex < step3SkeletonTasks.value.length) {
      step3ActiveL2Index.value = targetIndex
      // Ensure the draft content is associated with the correct task.
      const returnedDraft = step3L3Draft.value
      if (returnedDraft && returnedDraft.trim()) {
        step3SkeletonTasks.value[targetIndex] = {
          ...step3SkeletonTasks.value[targetIndex],
          l3_section_markdown: returnedDraft,
        }
      }
      // Re-read draft from the target task to keep display in sync.
      step3L3Draft.value = step3SkeletonTasks.value[targetIndex].l3_section_markdown || returnedDraft || ''
    }
    if (step3SkeletonPhase.value !== 'completed') {
      step3SkeletonPhase.value = 'generating_l3'
    }
    if (step3L3ReviewMode.value === 'approve') {
      step3L3Feedback.value = ''
      if (step3SkeletonPhase.value === 'generating_l3') {
        ElMessage.success(`「${step3SkeletonTasks.value[targetIndex]?.level2_name || ''}」三级指标已生成`)
      } else if (step3SkeletonPhase.value === 'completed') {
        ElMessage.success('全部二级指标已处理完毕，指标体系定稿完成！')
      }
    } else {
      ElMessage.success('已根据修改意见重新生成，请审阅')
    }
    saveStep3DraftState()
  } catch (e) {
    error.value = e instanceof Error ? e.message : '操作失败'
  } finally {
    loading.value = false
    if (activeRunId.value === runId) activeRunId.value = ''
  }
}

function openSkeletonEditDialog(task: Step3L2Task) {
  step3SkeletonEditTarget.value = { level1_name: task.level1_name, level2_name: task.level2_name }
  step3SkeletonEditForm.value = {
    level1_name: task.level1_name,
    level2_name: task.level2_name,
    target_l3_count: task.target_l3_count,
  }
  step3SkeletonEditDialogVisible.value = true
}

function saveSkeletonEdit() {
  const target = step3SkeletonEditTarget.value
  if (!target) return
  const form = step3SkeletonEditForm.value
  const idx = step3SkeletonTasks.value.findIndex(
    (t) => t.level1_name === target.level1_name && t.level2_name === target.level2_name
  )
  if (idx >= 0) {
    step3SkeletonTasks.value[idx] = {
      ...step3SkeletonTasks.value[idx],
      level1_name: form.level1_name,
      level2_name: form.level2_name,
      target_l3_count: Math.max(1, Math.min(20, form.target_l3_count)),
    }
  }
  step3SkeletonEditDialogVisible.value = false
  ElMessage.success('骨架指标已更新')
}

function removeSkeletonTask(task: Step3L2Task) {
  step3SkeletonTasks.value = step3SkeletonTasks.value.filter(
    (t) => !(t.level1_name === task.level1_name && t.level2_name === task.level2_name)
  )
  ElMessage.success('已删除该指标')
}

function addSkeletonL1() {
  const name = step3NewL1Name.value.trim()
  if (!name) {
    ElMessage.warning('请输入一级指标名称')
    return
  }
  step3SkeletonTasks.value.push({
    level1_name: name,
    level2_name: '待定义二级指标',
    target_l3_count: 3,
    l3_section_markdown: '',
  })
  step3NewL1Name.value = ''
  step3SkeletonAddL1DialogVisible.value = false
  ElMessage.success('已添加一级指标')
}

function addSkeletonL2() {
  const form = step3NewL2Form.value
  const l1 = form.level1_name.trim()
  const l2 = form.level2_name.trim()
  if (!l1 || !l2) {
    ElMessage.warning('请输入一级和二级指标名称')
    return
  }
  step3SkeletonTasks.value.push({
    level1_name: l1,
    level2_name: l2,
    target_l3_count: Math.max(1, Math.min(20, form.target_l3_count)),
    l3_section_markdown: '',
  })
  step3NewL2Form.value = { level1_name: '', level2_name: '', target_l3_count: 3 }
  step3SkeletonAddL2DialogVisible.value = false
  ElMessage.success('已添加二级指标')
}

function handleStep3ImportJsonFile(file: File) {
  const reader = new FileReader()
  reader.onload = (e) => {
    try {
      const text = String(e.target?.result || '')
      const data = JSON.parse(text)
      const tasks: Step3L2Task[] = []
      const arr = data.tasks || (Array.isArray(data) ? data : [])
      if (Array.isArray(arr)) {
        for (const row of arr) {
          if (row && typeof row === 'object') {
            tasks.push({
              level1_name: String(row.level1 || row.l1 || row['一级'] || ''),
              level2_name: String(row.level2 || row.l2 || row['二级'] || ''),
              target_l3_count: Math.max(1, Math.min(20, Number(row.target_l3_count || row.n || 3))),
              l3_section_markdown: '',
            })
          }
        }
      }
      if (tasks.length) {
        step3SkeletonTasks.value = tasks
        step3Config.value.imported_indicator_json = text
        step3SkeletonPhase.value = 'skeleton'
        ElMessage.success(`已导入 ${tasks.length} 个二级指标`)
      } else {
        ElMessage.warning('未能从文件中解析出有效的指标数据')
      }
    } catch {
      ElMessage.error('JSON 文件解析失败，请检查文件格式')
    }
  }
  reader.readAsText(file)
}

function applyStep3Template() {
  const tpl = step3TemplatePreview.value
  if (tpl) {
    step3SkeletonTasks.value = tpl.tasks.map((t) => ({ ...t }))
    step3SkeletonPhase.value = 'skeleton'
    ElMessage.success(`已导入模板「${tpl.name}」，共 ${tpl.tasks.length} 个二级指标`)
  }
}

function syncCurrentL3DraftToTask() {
  const idx = step3ActiveL2Index.value
  if (idx < 0 || idx >= step3SkeletonTasks.value.length) return
  const draft = (step3L3Draft.value || '').trim()
  if (!draft) return
  step3SkeletonTasks.value[idx] = {
    ...step3SkeletonTasks.value[idx],
    l3_section_markdown: step3L3Draft.value,
  }
}

function selectStep3L2(index: number) {
  if (index < 0 || index >= step3SkeletonTasks.value.length) return
  if (index === step3ActiveL2Index.value) return
  syncCurrentL3DraftToTask()
  step3ActiveL2Index.value = index
  const task = step3SkeletonTasks.value[index]
  step3L3Draft.value = task.l3_section_markdown || ''
  step3L3Comparisons.value = []
  step3L3Feedback.value = ''
  saveStep3DraftState()
}

function applyL3Comparison(index: number) {
  const item = step3L3Comparisons.value[index]
  if (!item || !item.draft) {
    ElMessage.warning('该模型暂未返回有效草稿')
    return
  }
  step3L3Draft.value = item.draft
  ElMessage.success(`已将「${item.label || item.model_name}」的草案设为当前审阅版本`)
}

function approveL3AndNext() {
  if (!step3ActiveL2Task.value) return
  step3SkeletonTasks.value[step3ActiveL2Index.value] = {
    ...step3SkeletonTasks.value[step3ActiveL2Index.value],
    l3_section_markdown: step3L3Draft.value,
  }
  if (step3ActiveL2Index.value + 1 < step3SkeletonTasks.value.length) {
    step3ActiveL2Index.value++
    step3L3Draft.value = step3SkeletonTasks.value[step3ActiveL2Index.value].l3_section_markdown || ''
    step3L3Comparisons.value = []
    step3L3Feedback.value = ''
    ElMessage.success(`已保存，进入第 ${step3ActiveL2Index.value + 1} 个二级指标`)
  } else {
    step3SkeletonPhase.value = 'completed'
    ElMessage.success('全部二级指标已完成！可点击"完成 Step3 收尾并保存"定稿')
  }
  saveStep3DraftState()
}

function manualSaveCurrentL3() {
  if (!step3ActiveL2Task.value) return
  step3SkeletonTasks.value[step3ActiveL2Index.value] = {
    ...step3SkeletonTasks.value[step3ActiveL2Index.value],
    l3_section_markdown: step3L3Draft.value,
  }
  saveStep3DraftState()
  ElMessage.success('当前三级指标已手动保存')
}

function buildStep3FinalMarkdown(): string {
  const name = getGlobalProjectName()
  const tasks = step3SkeletonTasks.value
  const lines = [
    `# 《${name} — 指标体系（${step3Config.value.system_type}）》`,
    '',
    `- 生成时间：${new Date().toISOString()}`,
    `- 指标深度：${step3Config.value.indicator_depth} 级`,
    '- **依据**：第二步项目核心内容',
    '',
    '## 指标体系全表',
    '',
  ]
  for (let idx = 0; idx < tasks.length; idx++) {
    const t = tasks[idx]
    lines.push(`### ${idx + 1}. 一级：${t.level1_name} ｜ 二级：${t.level2_name}`)
    lines.push('')
    lines.push(t.l3_section_markdown || '_（该二级下三级指标尚未完成）_')
    lines.push('')
  }
  lines.push('---')
  lines.push('')
  lines.push('*定稿后可用于第四步赋分等环节。*')
  return lines.join('\n')
}

const step14ExportDialogVisible = ref(false)
const lastStep14ExportUrl = ref('')
const lastStep14ExportFileName = ref('')

function openStep14ExportDialog() {
  step14ExportDialogVisible.value = true
}

async function submitStep14Export() {
  if (isEditorEmpty()) {
    ElMessage.warning('成品区内容为空，无法导出')
    return
  }
  step14ExportSaving.value = true
  try {
    const res = await exportStep14Word(projectId.value, {
      project_name: getGlobalProjectName(),
      content_text: editor.value,
      custom_title: step14ExportCustomTitle.value || null,
      export_format: step14ExportFormat.value,
    })
    lastStep14ExportUrl.value = res.download_url
    lastStep14ExportFileName.value = res.file_name
    await downloadExportFile(res.download_url, res.file_name)
    const tip = step14ExportFormat.value === 'markdown' ? 'Markdown' : 'Word'
    ElMessage.success(`Step14 评价报告 ${tip} 已导出并下载`)
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : '导出失败')
  } finally {
    step14ExportSaving.value = false
  }
}

async function downloadLastStep14Export() {
  if (!lastStep14ExportUrl.value) return
  try {
    await downloadExportFile(lastStep14ExportUrl.value, lastStep14ExportFileName.value)
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : '下载失败')
  }
}

async function stopCurrentRun() {
  if (!activeRunId.value && !loading.value) {
    ElMessage.warning('当前没有正在运行的生成任务')
    return
  }
  stopping.value = true
  const runId = activeRunId.value
  try {
    activeRunAbortController.value?.abort()
    if (runId) {
      const res = await cancelAgentRun(runId)
      if (res.cancelled) {
        ElMessage.success('已发送停止指令，正在取消当前生成任务')
      } else {
        ElMessage.info('任务可能已结束，状态将自动刷新')
      }
    } else {
      ElMessage.success('已停止当前生成请求')
    }
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : '停止失败')
  } finally {
    loading.value = false
    stopping.value = false
    activeRunId.value = ''
    activeRunAbortController.value = null
  }
}

async function runStep(prompt = '', options: { models?: string[] } = {}) {
  activeRunAbortController.value?.abort()
  const abortController = new AbortController()
  activeRunAbortController.value = abortController
  loading.value = true
  stopping.value = false
  error.value = ''
  const runId = `${stepCodeOf()}:${projectId.value}:${Date.now()}:${Math.random().toString(16).slice(2)}`
  activeRunId.value = runId
  // step4 的图带 interrupt_after，旧 thread 会让图从断点恢复并复用旧 scored_tree（旧观测点/旧分值）。
  // 每次生成前先丢弃 MemorySaver 检查点，强制图从 START 重跑，确保用上最新模板与考核要点。
  if (stepId.value === 4 && projectId.value) {
    try {
      await clearThreadState({
        step_code: 'step4',
        thread_id: `step4:${projectId.value}`,
        project_id: projectId.value,
        role: 'client',
      })
    } catch (e) {
      console.warn('[step4] clear thread before generate failed', e)
    }
  }
  // step5 同理：MemorySaver 中残留的旧 score_standards（旧 l3_name / 旧分值 / 缺 key_points）
  // 会让"重新生成"形同虚设，强制从 START 重跑以基于最新 scored_tree 构造评分标准。
  if (stepId.value === 5 && projectId.value) {
    try {
      await clearThreadState({
        step_code: 'step5',
        thread_id: `step5:${projectId.value}`,
        project_id: projectId.value,
        role: 'client',
      })
    } catch (e) {
      console.warn('[step5] clear thread before generate failed', e)
    }
  }
  // step6 同理：旧 thread 会带回上一次的 questionnaire_items / final_indicator_framework_markdown，
  // 导致用户切换"是否需要问卷"或修改 step3~5 后再来 step6 拿到的还是旧体系/旧问卷。
  if (stepId.value === 6 && projectId.value) {
    try {
      await clearThreadState({
        step_code: 'step6',
        thread_id: `step6:${projectId.value}`,
        project_id: projectId.value,
        role: 'client',
      })
    } catch (e) {
      console.warn('[step6] clear thread before generate failed', e)
    }
  }
  try {
    const payload = buildAgentPayloadByStep()
    const selectedNames = options.models?.length ? new Set(options.models) : null
    const modelConfigs = enabledActiveModelConfigs.value.filter((item) => !selectedNames || selectedNames.has(item.model_name))
    const effectiveModelConfigs = modelConfigs.length ? modelConfigs : enabledActiveModelConfigs.value
    const primary = effectiveModelConfigs[0] ?? primaryActiveModelConfig.value
    const modelNames = effectiveModelConfigs.map((item) => item.model_name)
    const res = await runAgent({
      workflow_role: 'client',
      step_code: stepCodeOf(),
      payload: { ...payload, prompt, run_id: runId, model_configs: effectiveModelConfigs, temperature: primary.temperature },
      context: {
        project_id: projectId.value,
        thread_id: stepId.value === 1 ? step1ThreadId.value : (stepId.value === 3 ? `step3:${projectId.value}` : undefined),
        workflow_role: 'client',
        run_id: runId,
        model_provider: primary.provider,
        model_name: primary.model_name,
        base_url: primary.base_url,
        api_key: primary.api_key,
        temperature: primary.temperature,
        active_model_provider: primary.provider,
        active_model_name: primary.model_name,
        active_base_url: primary.base_url,
        active_api_key: primary.api_key,
        active_temperature: primary.temperature,
        active_model_configs: effectiveModelConfigs,
        model_configs: effectiveModelConfigs,
        model_name_media: (effectiveModelConfigs.find((item) => item.id === step2MediaModelId.value)?.model_name) || primary.model_name,
        model_name_documents: (effectiveModelConfigs.find((item) => item.id === step2DocsModelId.value)?.model_name) || primary.model_name,
        media_model_config_id: step2MediaModelId.value,
        documents_model_config_id: step2DocsModelId.value,
        media_model_supports_pdf_image: step2MediaModelSupportsVision.value,
        compare_models: modelNames,
        enable_multi_model: effectiveModelConfigs.length > 1,
        recent_messages: [],
        memory_scope: 'short_and_long',
      },
    }, { signal: abortController.signal })
    if (stepId.value === 1) {
      pushStep1DraftSnapshot(editor.value, 'before_generate')
    }
    if (stepId.value === 3) {
      applyStep3Result(res)
    } else {
      applyAgentResult(res)
    }
    const resultPayload = res.result as Record<string, unknown> | null
    const resultError = typeof resultPayload?.error === 'string' ? resultPayload.error : ''
    const resultStatus = typeof resultPayload?.status === 'string' ? resultPayload.status : ''
    if (resultError && (resultStatus.includes('model_failed') || resultError.includes('Unauthorized') || resultError.includes('401') || resultError.includes('api_key') || resultError.includes('API Key'))) {
      error.value = resultError
      ElMessage.error({ message: `模型调用失败：${resultError.length > 120 ? resultError.slice(0, 120) + '…' : resultError}`, duration: 8000 })
    } else if (resultError) {
      error.value = resultError
      ElMessage.warning({ message: resultError.length > 120 ? resultError.slice(0, 120) + '…' : resultError, duration: 6000 })
    }
    if (stepId.value === 1) {
      pushStep1DraftSnapshot(editor.value, 'generate')
      saveStep1DraftState({
        project_id: projectId.value,
        thread_id: step1ThreadId.value,
        content_text: editor.value,
        content_json: resultText.value,
        current_result: currentResult.value,
        project_name: projectName.value,
        project_files: inputProjectFiles.value,
        updated_at: new Date().toISOString(),
      })
    } else if (stepId.value >= 4) {
      // step4-step14 通用 localStorage 双保险（step1/2/3 已有专用 draft state）
      saveGenericStepDraft(stepCodeOf(), {
        project_id: projectId.value,
        thread_id: `${stepCodeOf()}:${projectId.value}`,
        content_text: editor.value,
        content_json: resultText.value,
        current_result: currentResult.value,
      })
    }
    await loadWorkflowStatus()
  } catch (e) {
    const aborted = abortController.signal.aborted
      || (e instanceof Error && (e.name === 'CanceledError' || e.message.includes('canceled') || e.message.includes('aborted')))
    if (aborted) {
      error.value = '生成任务已取消'
      ElMessage.info('生成任务已停止')
    } else if (e instanceof Error && (e.message.includes('499') || e.message.includes('cancelled') || e.message.includes('cancel'))) {
      error.value = '生成任务已取消'
      ElMessage.info('生成任务已停止')
    } else {
      error.value = e instanceof Error ? e.message : '生成失败'
    }
  } finally {
    loading.value = false
    stopping.value = false
    if (activeRunId.value === runId) activeRunId.value = ''
    if (activeRunAbortController.value === abortController) activeRunAbortController.value = null
  }
}

watch(stepId, async () => {
  await loadResult()
}, { immediate: true })

watch(editor, (val) => {
  if (stepId.value === 2 && !isEditorEmpty(val)) {
    step2DraftDirty.value = true
    step2WriteBackToCheckpointer()
  }
  if (stepId.value >= 4 && !isEditorEmpty(val)) {
    saveGenericStepDraft(stepCodeOf(), {
      project_id: projectId.value,
      thread_id: `${stepCodeOf()}:${projectId.value}`,
      content_text: val,
      content_json: resultText.value,
      current_result: currentResult.value,
    })
  }
})

onMounted(() => {
  loadResult()
  loadStep1DraftIntoEditor()
  window.addEventListener('beforeunload', onBeforeUnloadGuard)
})

onBeforeUnmount(() => {
  window.removeEventListener('beforeunload', onBeforeUnloadGuard)
  if (step2WriteBackTimer) clearTimeout(step2WriteBackTimer)
  destroyStep6Sortables()
})

function onBeforeUnloadGuard(e: BeforeUnloadEvent) {
  if (stepId.value === 2 && step2DraftDirty.value) {
    e.preventDefault()
    e.returnValue = ''
  }
}

onBeforeRouteLeave(async () => {
  if (stepId.value !== 2 || !step2DraftDirty.value) return true
  try {
    await ElMessageBox.confirm(
      '当前 Step2 内容仅存于 LangGraph 短期记忆，未提交到数据库。离开后下次回到本步骤可继续编辑，但未确认前不会出现在历史版本中。',
      'Step2 草稿未提交',
      { confirmButtonText: '仍然离开', cancelButtonText: '留下继续编辑', type: 'warning' },
    )
    return true
  } catch {
    return false
  }
})

watchEffect(() => {
  workflowBus.currentStepId = stepId.value
  workflowBus.isLoading = loading.value
  workflowBus.currentProjectId = projectId.value
})

watch(() => workflowBus.pendingCommand, (cmd) => {
  if (!cmd) return
  const consumed = workflowBus.consume()
  if (!consumed) return
  if (consumed.action === 'goto_step' && consumed.step) {
    goStep(consumed.step)
  } else if (consumed.action === 'trigger_generate') {
    runStep('')
  } else if (consumed.action === 'stop') {
    stopCurrentRun()
  }
})
</script>

<template>
  <div class="workflow" :class="{ 'workflow--embedded': props.embeddedMode }">
    <PageHeader v-if="!props.embeddedMode" :title="`工作台 · Step ${stepId}`" :description="`项目 ${projectId} · 生成区 / 成品区 / 历史区三栏布局`">
      <template #actions>
        <el-button @click="router.push(`/app/projects/${projectId}/overview`)">回总览</el-button>
        <el-button @click="historyOpen = true">历史</el-button>
        <el-button :loading="saving" type="success" @click="saveCurrentStep">保存最终版本</el-button>
        <el-button type="primary" @click="chatOpen = true">AI 对话</el-button>
      </template>
    </PageHeader>

    <div class="layout" :class="{ 'layout--no-sidebar': props.embeddedMode }">
      <StepSidebar v-if="!props.embeddedMode" :steps="steps" :active-step="stepId" :sections="currentStepSections" @select="goStep" @scroll-to="scrollToSection" />

      <div class="center">
        <el-alert v-if="error" :title="error" type="error" :closable="false" show-icon class="mb" />
        <div class="stack">
          <GenerationPanel
            :title="titleMap[stepId] ?? `Step ${stepId}`"
            :loading="loading"
            :stoppable="Boolean(activeRunId)"
            :stopping="stopping"
            @generate="() => canGenerate ? runStep('') : undefined"
            @stop="stopCurrentRun"
          />

          <el-card id="sec-model-config" shadow="never">
            <template #header>客户端模型配置</template>
            <el-alert
              type="success"
              :closable="false"
              show-icon
              class="mb"
              :title="activeModelSummary"
            />
            <el-alert
              v-if="hasUnsavedModelConfig"
              type="warning"
              :closable="false"
              show-icon
              class="mb"
              title="你已修改模型配置或 Temperature，但尚未保存；生成时仍会使用上方提示中的当前生效配置。"
            />
            <div class="model-config-list">
              <el-card v-for="entry in pagedModelConfigs" :key="entry.item.id" shadow="never" class="model-config-card">
                <template #header>
                  <div class="model-config-card-header">
                    <span>{{ entry.item.label || `模型配置 ${entry.index + 1}` }}</span>
                    <div class="model-config-card-actions">
                      <el-tag size="small" type="info">{{ entry.index + 1 }} / {{ clientModelConfigs.length }}</el-tag>
                      <el-switch v-model="entry.item.enabled" active-text="启用" inactive-text="停用" />
                      <el-button size="small" type="danger" plain @click="removeModelConfig(entry.index)">删除</el-button>
                    </div>
                  </div>
                </template>
                <el-form label-width="110px">
                  <el-form-item label="显示名称">
                    <el-input v-model="entry.item.label" placeholder="例如 OpenAI 严谨版 / Qwen 发散版" />
                  </el-form-item>
                  <el-form-item label="模型预设">
                    <el-select
                      :model-value="selectedModelPresets[entry.item.id]"
                      filterable
                      clearable
                      placeholder="选择模型预设，自动填充模型名和 Base URL"
                      @change="(value) => applyModelPreset(entry.index, String(value || ''))"
                    >
                      <el-option v-for="item in modelPresets" :key="item.model_name" :label="item.label" :value="item.model_name" />
                    </el-select>
                  </el-form-item>
                  <el-form-item label="Provider">
                    <el-input v-model="entry.item.provider" placeholder="openai-compatible" />
                  </el-form-item>
                  <el-form-item label="Base URL">
                    <el-input v-model="entry.item.base_url" placeholder="例如 https://api.openai.com/v1 或兼容服务地址" />
                  </el-form-item>
                  <el-form-item label="API Key">
                    <el-input v-model="entry.item.api_key" type="password" show-password placeholder="这个模型自己的 API Key" />
                  </el-form-item>
                  <el-form-item label="模型名">
                    <el-input v-model="entry.item.model_name" placeholder="例如 gpt-4o / qwen-max / deepseek-chat" />
                  </el-form-item>
                  <el-form-item label="Temperature">
                    <el-slider
                      :model-value="entry.item.temperature"
                      :min="0"
                      :max="2"
                      :step="0.1"
                      show-input
                      @update:model-value="(value) => setClientModelTemperature(entry.index, Number(value))"
                    />
                  </el-form-item>
                </el-form>
              </el-card>
            </div>
            <div class="pagination-row">
              <el-pagination
                v-model:current-page="modelConfigPage"
                v-model:page-size="modelConfigPageSize"
                :total="clientModelConfigs.length"
                :page-sizes="[1, 2, 3, 5]"
                layout="total, sizes, prev, pager, next, jumper"
                small
              />
            </div>
            <div class="upload-toolbar">
              <el-button @click="addModelConfig">新增模型配置窗口</el-button>
              <el-button type="primary" @click="persistModelConfig">保存全部模型配置并生效</el-button>
            </div>
          </el-card>

          <el-alert v-if="!canGenerate" type="warning" :closable="false" show-icon title="请先上传项目资料，并配置客户端模型 API Key、Base URL 和模型名。" />

          <el-card id="sec-step1-input" v-if="stepId === 1" shadow="never">
            <template #header>Step1 输入资料与草稿</template>
            <el-alert
              type="info"
              :closable="false"
              show-icon
              class="mb"
              title="Step1 现在采用草稿 + 确认提交模式：先生成并编辑草稿，确认后才会落库为最终资料清单。"
            />
            <div class="upload-toolbar">
              <el-button type="primary" @click="openUploadDialog('documents')">打开资料上传窗口</el-button>
              <el-button @click="loadStep1DraftIntoEditor">恢复当前草稿</el-button>
            </div>
            <el-alert v-if="!inputProjectFiles.length" type="warning" :closable="false" show-icon title="当前资料清单为空，先上传资料再做 Step1 草稿生成。" />
            <el-table v-else :data="inputProjectFiles" size="small">
              <el-table-column prop="file_name" label="文件名" min-width="180" />
              <el-table-column prop="file_type" label="类型" width="120" />
              <el-table-column prop="parse_status" label="解析状态" width="120" />
              <el-table-column prop="storage_key" label="存储路径" min-width="220" show-overflow-tooltip />
              <el-table-column label="操作" width="100">
                <template #default="{ row }">
                  <el-button size="small" type="danger" plain @click="removeProjectFile(row.id, row.file_name)">删除</el-button>
                </template>
              </el-table-column>
            </el-table>
          </el-card>

          <el-card id="sec-step1-draft" v-if="stepId === 1" shadow="never">
            <template #header>
              <div class="card-head-with-toggle">
                <span>Step1 草稿编辑</span>
                <el-radio-group v-model="step1DraftViewMode" size="small">
                  <el-radio-button value="edit">编辑</el-radio-button>
                  <el-radio-button value="preview">看板预览</el-radio-button>
                </el-radio-group>
              </div>
            </template>
            <template v-if="step1DraftViewMode === 'edit'">
              <el-alert
                type="success"
                :closable="false"
                show-icon
                class="mb"
                :title="step1ThreadId ? `当前草稿线程：${step1ThreadId}` : '当前尚未创建线程。'"
              />
              <el-form label-width="110px">
                <el-form-item label="项目名称">
                  <el-input v-model="projectName" placeholder="系统会自动识别，也可以手工调整" />
                </el-form-item>
                <el-form-item label="草稿内容">
                  <div class="draft-editor-wrap">
                    <el-input v-model="editor" type="textarea" :rows="10" :placeholder="editorPlaceholder" />
                    <el-button class="draft-editor-expand" size="small" plain @click="step1ExpandDialog = true">放大编辑</el-button>
                  </div>
                </el-form-item>
              </el-form>
              <div class="upload-toolbar">
                <el-button type="primary" :loading="loading" @click="runStep('')">生成 / 刷新 Step1 草稿</el-button>
                <el-button type="success" :loading="saving" @click="saveCurrentStep">确认提交 Step1 草稿</el-button>
                <el-button type="warning" :loading="exportSaving" @click="openStep1ExportDialog">成果导出</el-button>
              </div>
            </template>
            <MarkdownDashboard
              v-else
              :source="(currentResult?.final_manifest as string) || (currentResult?.draft_manifest as string) || editor"
              :key-metrics="step1StructuredAnalysis.keyMetrics"
              :gap-items="step1StructuredAnalysis.gapAnalysis"
              @request-upload="onRequestUpload"
              @step-click="goStep"
            />
          </el-card>

          <el-card id="sec-step1-analysis" v-if="stepId === 1" shadow="never">
            <template #header>Step1 结构化分析（三表视图）</template>
            <Step1Analysis
              :key-metrics="step1StructuredAnalysis.keyMetrics"
              :gap-analysis="step1StructuredAnalysis.gapAnalysis"
              :data-flow="step1StructuredAnalysis.dataFlow"
            />
          </el-card>

          <el-card id="sec-step1-history" v-if="stepId === 1" shadow="never">
            <template #header>Step1 未提交资料清单版本</template>
            <el-alert
              type="info"
              :closable="false"
              show-icon
              class="mb"
              title="这些版本只保存在本次草稿内存/本地缓存中，确认提交到数据库后会自动清空。"
            />
            <el-empty v-if="!step1DraftHistory.length" description="还没有生成过未提交资料清单。点击生成后，每一版都会出现在这里。" />
            <template v-else>
              <div class="draft-memory-list">
                <div v-for="entry in pagedStep1DraftHistory" :key="entry.item.id" class="draft-memory-item">
                  <div class="draft-memory-main">
                    <div class="draft-memory-title">
                      <span>{{ entry.item.title }} · {{ entry.item.source }}</span>
                      <el-radio-group
                        :model-value="draftPreviewModes[entry.item.id] || 'raw'"
                        size="small"
                        class="draft-memory-toggle"
                        @update:model-value="(v: string | number | boolean | undefined) => (draftPreviewModes[entry.item.id] = (v as 'raw' | 'preview'))"
                      >
                        <el-radio-button value="raw">原文</el-radio-button>
                        <el-radio-button value="preview">看板</el-radio-button>
                      </el-radio-group>
                    </div>
                    <div class="draft-memory-desc">{{ entry.item.created_at }} · 第 {{ entry.index + 1 }} / {{ step1DraftHistory.length }} 版</div>
                    <pre v-if="(draftPreviewModes[entry.item.id] || 'raw') === 'raw'" class="draft-memory-preview">{{ entry.item.content }}</pre>
                    <MarkdownDashboard v-else :source="entry.item.content" />
                  </div>
                  <div class="draft-memory-actions">
                    <el-button size="small" type="primary" plain @click="restoreStep1DraftSnapshot(entry.index)">回滚</el-button>
                    <el-button size="small" type="danger" plain @click="deleteStep1DraftSnapshot(entry.index)">删除</el-button>
                  </div>
                </div>
              </div>
              <div class="pagination-row">
                <el-pagination
                  v-model:current-page="draftHistoryPage"
                  v-model:page-size="draftHistoryPageSize"
                  :total="step1DraftHistory.length"
                  :page-sizes="[1, 2, 3, 5, 10]"
                  layout="total, sizes, prev, pager, next, jumper"
                  small
                />
              </div>
            </template>
          </el-card>

          <el-alert
            v-if="stepId === 2 && step2HasContent"
            :type="step2DraftDirty ? 'warning' : 'success'"
            :closable="false"
            show-icon
            class="mb"
          >
            <template #title>
              <span v-if="step2DraftDirty">Step2 草稿已生成 · 暂存于 LangGraph 短期记忆 · 未提交到数据库</span>
              <span v-else>Step2 内容已提交到数据库<span v-if="step2LastCommittedAt">（{{ new Date(step2LastCommittedAt).toLocaleString('zh-CN') }}）</span></span>
            </template>
          </el-alert>

          <el-card id="sec-step2-upload" v-if="stepId === 2" shadow="never">
            <template #header>Step2 资料上传窗口与通道确认</template>
            <el-alert
              type="info"
              :closable="false"
              show-icon
              class="mb"
              title="Step2 会按上传资料自动分成图片 / PDF 通道和文档通道，并把两路文件一并发给后端与 agent。"
            />
            <div class="step-card-grid">
              <div class="step-card">
                <div class="upload-title">双通道资料概览</div>
                <div class="upload-summary">
                  <div>总计 {{ step2Summary.total }} 份资料</div>
                  <div>图片 / PDF：{{ step2Summary.media }} 份</div>
                  <div>文档：{{ step2Summary.documents }} 份</div>
                  <div>资料状态：{{ step2Summary.ready ? '可生成' : '待上传' }}</div>
                </div>
                <div class="upload-desc">确认资料已按通道分配后，再开始生成核心内容。</div>
              </div>
              <div class="step-card">
                <div class="upload-title">Step2 操作</div>
                <div class="upload-desc">先打开对应通道上传窗口，完成资料上传后点击一键生成。</div>
                <div class="upload-toolbar">
                  <el-button :loading="uploading" @click="openUploadDialog('media')">上传图片 / PDF</el-button>
                  <el-button :loading="uploading" @click="openUploadDialog('documents')">上传文档</el-button>
                </div>
              </div>
            </div>
            <el-alert v-if="!step2HasFiles" type="warning" :closable="false" show-icon title="请先上传资料，再执行 Step2 生成。" />
          </el-card>

          <el-card id="sec-step2-models" v-if="stepId === 2" shadow="never">
            <template #header>Step2 每通道模型绑定</template>
            <el-alert
              type="info"
              :closable="false"
              show-icon
              class="mb"
              title="可以为「图片 / PDF」与「文档」两个通道分别绑定一个已保存的模型。绑定为空时默认按全部已启用模型并行调用、对比草稿。"
            />
            <el-alert
              v-if="mediaFiles.length && !step2MediaModelSupportsVision"
              type="warning"
              :closable="false"
              show-icon
              class="mb"
              title="当前图片 / PDF 通道未绑定多模态模型，识别结果可能不完整。请在「资料识别结果」中务必人工校验，或切换到带 vision / vl / gpt-4o / claude-3 / gemini 等关键字的模型。"
            />
            <el-form label-width="170px">
              <el-form-item label="图片 / PDF 通道模型">
                <el-select v-model="step2MediaModelId" clearable placeholder="不绑定时全部已启用模型参与">
                  <el-option v-for="option in step2ChannelModelOptions" :key="option.id" :label="option.label" :value="option.id" />
                </el-select>
              </el-form-item>
              <el-form-item label="Word / Excel 通道模型">
                <el-select v-model="step2DocsModelId" clearable placeholder="不绑定时全部已启用模型参与">
                  <el-option v-for="option in step2ChannelModelOptions" :key="option.id" :label="option.label" :value="option.id" />
                </el-select>
              </el-form-item>
            </el-form>
          </el-card>

          <el-card id="sec-step2-categories" v-if="stepId === 2" shadow="never">
            <template #header>Step2 分类管理</template>
            <el-alert
              type="info"
              :closable="false"
              show-icon
              class="mb"
              title="核心内容会按下列分类组织。默认包含资金管理、预算管理、制度文件、项目实施四类，可以勾选保留或新增自定义分类（例如「采购合同类」「绩效目标类」等）。"
            />
            <div class="step2-category-row">
              <el-checkbox
                v-for="category in DEFAULT_STEP2_CATEGORIES"
                :key="category"
                :model-value="step2DefaultCategories.includes(category)"
                @update:model-value="(value) => toggleStep2DefaultCategory(category, value === true)"
              >
                {{ category }}
              </el-checkbox>
            </div>
            <div class="step2-category-row step2-extra-row">
              <el-tag
                v-for="(item, idx) in step2ExtraCategories"
                :key="`${item}-${idx}`"
                closable
                type="success"
                @close="removeStep2ExtraCategory(idx)"
              >
                {{ item }}
              </el-tag>
              <el-input
                v-model="step2NewCategoryInput"
                placeholder="新增分类名称，例如「采购合同类」"
                style="max-width: 240px"
                @keyup.enter="addStep2Category"
              />
              <el-button type="primary" plain @click="addStep2Category">新增分类</el-button>
            </div>
            <el-alert
              type="success"
              :closable="false"
              show-icon
              class="mb"
              :title="`将按以下分类生成核心内容：${step2MergedCategories.join('、') || '暂未选择任何分类'}`"
            />
            <el-alert
              type="info"
              :closable="false"
              show-icon
              :title="`必备维度自动覆盖：${REQUIRED_STEP2_DIMENSIONS.join('、')}`"
            />
          </el-card>

          <el-card id="sec-step2-digest" v-if="stepId === 2 && (step2VerificationDigest || step2ParseWarnings.length || step2MediaMetadata.length || step2DocsMetadata.length)" shadow="never">
            <template #header>Step2 资料识别校验</template>
            <el-alert
              v-for="(item, idx) in step2ParseWarnings"
              :key="`warn-${idx}`"
              type="warning"
              :closable="false"
              show-icon
              class="mb"
              :title="item"
            />
            <el-tabs class="mb">
              <el-tab-pane :label="`图片 / PDF（${step2MediaMetadata.length}）`">
                <el-empty v-if="!step2MediaMetadata.length" description="本通道暂无识别结果" />
                <el-table v-else :data="step2MediaMetadata" size="small">
                  <el-table-column prop="name" label="文件名" min-width="180" />
                  <el-table-column prop="type" label="类型" width="120" />
                  <el-table-column prop="page_count" label="页/规模" width="100" />
                  <el-table-column prop="content_summary" label="识别摘录" min-width="320" show-overflow-tooltip />
                </el-table>
              </el-tab-pane>
              <el-tab-pane :label="`Word / Excel（${step2DocsMetadata.length}）`">
                <el-empty v-if="!step2DocsMetadata.length" description="本通道暂无识别结果" />
                <el-table v-else :data="step2DocsMetadata" size="small">
                  <el-table-column prop="name" label="文件名" min-width="180" />
                  <el-table-column prop="type" label="类型" width="120" />
                  <el-table-column prop="page_count" label="页/规模" width="100" />
                  <el-table-column prop="content_summary" label="识别摘录" min-width="320" show-overflow-tooltip />
                </el-table>
              </el-tab-pane>
              <el-tab-pane label="原文摘录索引">
                <el-empty v-if="!step2SourceIndex.length" description="暂无索引条目" />
                <el-table v-else :data="step2SourceIndex" size="small">
                  <el-table-column prop="ref_id" label="索引号" width="100" />
                  <el-table-column prop="source_name" label="来源文件" min-width="200" />
                  <el-table-column prop="channel" label="通道" width="120" />
                  <el-table-column prop="excerpt" label="摘录" min-width="320" show-overflow-tooltip />
                </el-table>
              </el-tab-pane>
              <el-tab-pane label="识别摘要文本">
                <div style="display: flex; justify-content: flex-end; margin-bottom: 8px;">
                  <el-radio-group v-model="step2DigestViewMode" size="small">
                    <el-radio-button value="raw">原文</el-radio-button>
                    <el-radio-button value="preview">看板</el-radio-button>
                  </el-radio-group>
                </div>
                <pre v-if="step2DigestViewMode === 'raw'" class="result">{{ step2VerificationDigest || '暂无摘要文本' }}</pre>
                <MarkdownDashboard v-else :source="step2VerificationDigest || ''" :source-index="step2SourceIndex" />
              </el-tab-pane>
            </el-tabs>
            <el-checkbox v-model="step2VerificationAck">已逐条对比原件，确认识别结果与上传资料一致</el-checkbox>
            <div class="upload-desc">未勾选时仍可继续，但生成的核心内容会带有「待复核」语义，建议先确认再生成。</div>
          </el-card>

          <ModelCompareTabs v-if="stepId === 2 && compareItems.length" :items="compareItems" />

          <el-card id="sec-step2-compare" v-if="stepId === 2 && step2ModelComparisons.length" shadow="never">
            <template #header>Step2 多模型对比</template>
            <el-alert
              type="info"
              :closable="false"
              show-icon
              class="mb"
              title="左侧列表展示每个模型的草稿，可整体导入到下方成品区，再通过手工编辑或多轮对话进一步优化。"
            />
            <div class="step2-compare-layout">
              <div class="step2-compare-list">
                <div
                  v-for="(item, idx) in step2ModelComparisons"
                  :key="`cmp-${idx}-${item.model_name}`"
                  class="step2-compare-card"
                  :class="{ active: idx === step2ActiveCompareIndex }"
                  @click="step2ActiveCompareIndex = idx"
                >
                  <div class="step2-compare-title">{{ item.label || item.model_name || `模型 ${idx + 1}` }}</div>
                  <div class="step2-compare-meta">
                    {{ item.provider || 'openai-compatible' }} · T={{ item.temperature ?? '-' }} · {{ item.channel || 'combined' }}
                  </div>
                  <el-tag v-if="item.error" type="danger" size="small">调用失败</el-tag>
                  <el-tag v-else-if="!item.draft" size="small">空响应</el-tag>
                  <el-tag v-else type="success" size="small">{{ (item.draft || '').length }} 字</el-tag>
                </div>
              </div>
              <div class="step2-compare-detail">
                <div v-if="step2ModelComparisons[step2ActiveCompareIndex]">
                  <div class="step2-compare-detail-title" style="display: flex; align-items: center; justify-content: space-between; gap: 8px;">
                    <span>{{ step2ModelComparisons[step2ActiveCompareIndex].label || step2ModelComparisons[step2ActiveCompareIndex].model_name }}</span>
                    <el-radio-group v-model="step2CompareViewMode" size="small">
                      <el-radio-button value="raw">原文</el-radio-button>
                      <el-radio-button value="preview">看板</el-radio-button>
                    </el-radio-group>
                  </div>
                  <pre v-if="step2CompareViewMode === 'raw'" class="result">{{ step2ModelComparisons[step2ActiveCompareIndex].draft || (step2ModelComparisons[step2ActiveCompareIndex].error ? `调用失败：${step2ModelComparisons[step2ActiveCompareIndex].error}` : '空响应') }}</pre>
                  <MarkdownDashboard v-else :source="step2ModelComparisons[step2ActiveCompareIndex].draft || ''" :source-index="step2SourceIndex" />
                  <div class="upload-toolbar">
                    <el-button type="primary" :disabled="!step2ModelComparisons[step2ActiveCompareIndex].draft" @click="applyStep2Comparison(step2ActiveCompareIndex)">把该草稿导入成品区</el-button>
                  </div>
                </div>
              </div>
            </div>
          </el-card>

          <el-card id="sec-step2-review" v-if="stepId === 2" shadow="never">
            <template #header>Step2 人机交互精修</template>
            <el-alert
              type="info"
              :closable="false"
              show-icon
              class="mb"
              title="支持两种精修方式：①直接在下方成品区手工编辑；②写下修改意见，点击「让 AI 重新打磨」，会按当前模型重写并保留索引引用。多轮重复，直到满意为止。"
            />
            <el-form label-width="110px">
              <el-form-item label="审核模式">
                <el-radio-group v-model="step2ReviewMode">
                  <el-radio label="modify">人机协同修改</el-radio>
                  <el-radio label="approve">已满意，提交定稿</el-radio>
                </el-radio-group>
              </el-form-item>
              <el-form-item label="修订意见">
                <el-input v-model="step2ReviewFeedback" type="textarea" :rows="4" placeholder="例如：加强项目背景与政策依据的衔接；将资金支出按类别小计；为每条核心结论补充 [S?] 索引引用。" />
              </el-form-item>
            </el-form>
            <div class="upload-toolbar">
              <el-button type="primary" :loading="loading" :disabled="!step2CanRefine" @click="submitStep2Refinement">让 AI 重新打磨核心内容</el-button>
              <el-button type="success" :loading="saving" @click="approveStep2">确认提交到数据库</el-button>
              <el-button @click="chatOpen = true">打开 AI 对话深度精修</el-button>
            </div>
            <el-alert
              v-if="step2StatusText"
              type="success"
              :closable="false"
              show-icon
              class="mb"
              :title="`当前状态：${step2StatusText}`"
            />
          </el-card>

          <el-card id="sec-step2-export" v-if="stepId === 2" shadow="never">
            <template #header>Step2 成果区与导出</template>
            <el-alert
              type="success"
              :closable="false"
              show-icon
              class="mb"
              title="下方为核心内容成品区。确认后默认以 Markdown 一键导出，亦可切换为 Word；自定义排版支持字体、字号、行距、段距与首行缩进。"
            />
            <div class="upload-toolbar">
              <el-button type="warning" :loading="step2ExportSaving" @click="openStep2ExportDialog">导出 Step2 成果（Markdown / Word）</el-button>
              <el-button v-if="lastStep2ExportUrl" @click="downloadLastStep2Export">下载上次导出</el-button>
            </div>
          </el-card>

          <ModelCompareTabs v-if="compareItems.length && stepId === 3" :items="compareItems" />
          <!-- Step3: 配置阶段 -->
          <el-card id="sec-step3-config" v-if="stepId === 3 && step3SkeletonPhase === 'config'" shadow="never">
            <template #header>Step3 · 指标体系配置</template>
            <el-alert v-if="!step3HasStep2Core" type="warning" :closable="false" show-icon title="当前尚未读取到 Step2 核心内容，请先确保 Step2 已定稿并保存。" />
            <el-alert v-else type="success" :closable="false" show-icon class="mb" title="已读取 Step2 核心内容，下方配置完成后即可构建指标体系。" />
            <el-form label-width="120px">
              <el-form-item label="体系类型">
                <el-select v-model="step3Config.system_type" style="width: 100%" @change="step3SkeletonTasks = []">
                  <el-option label="项目支出指标体系" value="项目支出指标体系" />
                  <el-option label="部门整体指标体系" value="部门整体指标体系" />
                  <el-option label="下级政府整体运行指标体系" value="下级政府整体运行指标体系" />
                  <el-option label="专项债指标体系" value="专项债指标体系" />
                  <el-option label="社保基金指标体系" value="社保基金指标体系" />
                  <el-option label="自定义（LLM 自动生成）" value="自定义" />
                </el-select>
              </el-form-item>
              <el-form-item label="指标深度">
                <el-radio-group v-model="step3Config.indicator_depth">
                  <el-radio :label="3">3 级（标准）</el-radio>
                  <el-radio :label="4">4 级（含四级细项）</el-radio>
                </el-radio-group>
              </el-form-item>
              <el-form-item label="导入模式">
                <el-radio-group v-model="step3Config.import_mode" @change="() => { step3SkeletonTasks = []; step3Config.imported_indicator_json = ''; }">
                  <el-radio label="none">不导入（按类型自动生成）</el-radio>
                  <el-radio label="template">模板库一键导入</el-radio>
                  <el-radio label="own">自有 JSON 导入</el-radio>
                </el-radio-group>
              </el-form-item>
              <el-form-item v-if="step3Config.import_mode === 'template'" label="选择模板">
                <div style="display: flex; gap: 10px; align-items: center; width: 100%;">
                  <el-select v-model="step3Config.template_id" style="flex: 1">
                    <el-option v-for="tpl in step3Templates" :key="tpl.id" :label="tpl.name" :value="tpl.id" />
                  </el-select>
                  <el-button @click="applyStep3Template">应用模板</el-button>
                </div>
                <el-card v-if="step3TemplatePreview" shadow="never" style="margin-top: 8px; background: var(--el-fill-color-lighter);">
                  <template #header>模板预览：{{ step3TemplatePreview.name }}</template>
                  <div v-for="t in step3TemplatePreview.tasks" :key="t.level1_name + t.level2_name" style="padding: 2px 0; font-size: 13px;">
                    {{ t.level1_name }} → {{ t.level2_name }}（三级数量：{{ t.target_l3_count }}）
                  </div>
                </el-card>
              </el-form-item>
              <el-form-item v-if="step3Config.import_mode === 'own'" label="导入方式">
                <div style="display: flex; gap: 10px; align-items: center; flex-wrap: wrap;">
                  <el-upload
                    :auto-upload="false"
                    :show-file-list="false"
                    :limit="1"
                    accept=".json"
                    :on-change="(file: UploadFile) => file.raw && handleStep3ImportJsonFile(file.raw)"
                  >
                    <el-button>上传 JSON 文件</el-button>
                  </el-upload>
                  <span style="color: var(--el-text-color-secondary); font-size: 12px;">或手动粘贴</span>
                </div>
                <el-input
                  v-model="step3Config.imported_indicator_json"
                  type="textarea"
                  :rows="6"
                  placeholder='格式：{"tasks":[{"level1":"决策","level2":"依据充分","target_l3_count":3}]}'
                  style="margin-top: 8px;"
                  @blur="() => {
                    if (step3Config.imported_indicator_json.trim()) {
                      try {
                        const data = JSON.parse(step3Config.imported_indicator_json)
                        const arr = data.tasks || (Array.isArray(data) ? data : [])
                        if (arr.length) {
                          step3SkeletonTasks = arr.filter((r: any) => r && typeof r === 'object').map((r: any) => ({
                            level1_name: String(r.level1 || r.l1 || ''),
                            level2_name: String(r.level2 || r.l2 || ''),
                            target_l3_count: Math.max(1, Math.min(20, Number(r.target_l3_count || r.n || 3))),
                            l3_section_markdown: '',
                          }))
                        }
                      } catch {}
                    }
                  }"
                />
              </el-form-item>
              <el-form-item label="骨架优化">
                <el-radio-group v-model="step3Config.skeleton_optimize_mode">
                  <el-radio label="none">不优化</el-radio>
                  <el-radio label="one_click">一键优化（LLM 对照核心内容）</el-radio>
                  <el-radio label="per_level2">按二级指标逐个优化</el-radio>
                </el-radio-group>
              </el-form-item>
              <el-form-item v-if="step3Config.skeleton_optimize_mode === 'per_level2'" label="优化目标">
                <el-input v-model="step3Config.per_optimize_level2_name" placeholder="输入要优化的二级指标名称" />
              </el-form-item>
            </el-form>
            <el-alert type="info" :closable="false" show-icon class="mb" title="点击下方按钮，系统将根据配置构建指标体系骨架，并逐个二级指标生成三级指标与解释。" />
            <div class="upload-toolbar">
              <el-button type="primary" size="large" :loading="loading" @click="runStep3BuildSkeleton" :disabled="!step3HasStep2Core">
                构建指标体系骨架
              </el-button>
            </div>
          </el-card>

          <!-- Step3: 骨架编辑 & L3 生成阶段 -->
          <el-card id="sec-step3-skeleton" v-if="stepId === 3 && step3SkeletonPhase !== 'config'" shadow="never">
            <template #header>Step3 · 指标体系骨架管理</template>
            <el-alert type="success" :closable="false" show-icon class="mb" title="骨架已就绪，可增删改一级/二级指标，调整三级数量，然后逐个生成三级指标与解释。" />
            <el-alert
              v-if="Object.keys(step3GroupedL1).length"
              type="info"
              :closable="false"
              show-icon
              class="mb"
              :title="`骨架概览：${Object.keys(step3GroupedL1).length} 个一级指标，${step3SkeletonTasks.length} 个二级指标（${step3L2Progress.completed}/${step3L2Progress.total} 项三级已完成）`"
            />
            <div style="margin-bottom: 12px; display: flex; gap: 10px; flex-wrap: wrap;">
              <el-button size="small" type="primary" @click="step3SkeletonAddL1DialogVisible = true">+ 新增一级指标</el-button>
              <el-button size="small" type="success" @click="step3SkeletonAddL2DialogVisible = true">+ 新增二级指标</el-button>
            </div>
            <el-table :data="step3SkeletonTasks" size="small" stripe max-height="360">
              <el-table-column label="序号" type="index" width="60" />
              <el-table-column label="一级指标" prop="level1_name" min-width="140">
                <template #default="{ row }">
                  <el-tag>{{ row.level1_name }}</el-tag>
                </template>
              </el-table-column>
              <el-table-column label="二级指标" prop="level2_name" min-width="180" />
              <el-table-column label="三级数量" prop="target_l3_count" width="100" align="center">
                <template #default="{ row }">
                  <el-input-number
                    :model-value="row.target_l3_count"
                    :min="1"
                    :max="20"
                    size="small"
                    controls-position="right"
                    style="width: 80px"
                    @update:model-value="(val) => { if (typeof val === 'number') row.target_l3_count = val }"
                  />
                </template>
              </el-table-column>
              <el-table-column label="三级状态" width="120" align="center">
                <template #default="{ row }">
                  <el-tag v-if="row.l3_section_markdown" type="success" size="small">已完成</el-tag>
                  <el-tag v-else-if="step3ActiveL2Task && step3ActiveL2Task.level1_name === row.level1_name && step3ActiveL2Task.level2_name === row.level2_name" type="warning" size="small">进行中</el-tag>
                  <el-tag v-else type="info" size="small">待处理</el-tag>
                </template>
              </el-table-column>
              <el-table-column label="操作" width="200" align="center">
                <template #default="{ row, $index }">
                  <el-button size="small" @click="openSkeletonEditDialog(row)">编辑</el-button>
                  <el-button size="small" type="danger" plain @click="removeSkeletonTask(row)">删除</el-button>
                  <el-button size="small" type="primary" plain @click="selectStep3L2($index)">处理</el-button>
                </template>
              </el-table-column>
            </el-table>
            <div class="upload-toolbar" style="margin-top: 12px;">
              <el-button type="primary" :loading="loading" @click="runStep3BuildSkeleton">重新构建骨架</el-button>
              <el-button @click="step3Config.skeleton_optimize_mode = 'one_click'; runStep3BuildSkeleton()">一键优化骨架</el-button>
            </div>
          </el-card>

          <!-- Step3: 逐个二级指标生成三级指标 -->
          <el-card id="sec-step3-l3" v-if="stepId === 3 && step3SkeletonPhase !== 'config' && step3SkeletonTasks.length" shadow="never">
            <template #header>
              Step3 · 三级指标生成（共 {{ step3SkeletonTasks.length }} 个二级指标）
            </template>
            <el-progress :percentage="step3L2Progress.percent" :text-inside="true" :stroke-width="20" style="margin-bottom: 12px;" />
            <el-alert
              v-if="step3AllL2Completed"
              type="success"
              :closable="false"
              show-icon
              class="mb"
              title="全部二级指标的三级内容已就绪，可点击「完成 Step3 收尾并保存」定稿。"
            />

            <el-tabs v-model="step3ActiveL2Tab" type="card" @tab-change="onStep3TabChange">
              <el-tab-pane
                v-for="(task, idx) in step3SkeletonTasks"
                :key="`l3-tab-${idx}`"
                :name="String(idx)"
              >
                <template #label>
                  <span :style="{ color: task.l3_section_markdown ? 'var(--el-color-success)' : undefined }">
                    {{ task.level1_name }} → {{ task.level2_name }}
                    {{ task.l3_section_markdown ? ' ✓' : '' }}
                  </span>
                </template>

                <div v-if="idx === step3ActiveL2Index">
                  <div class="step3-summary-grid" style="margin-bottom: 12px;">
                    <div class="step3-summary-card">
                      <div class="step3-summary-title">一级指标</div>
                      <div class="step3-summary-value">{{ task.level1_name }}</div>
                    </div>
                    <div class="step3-summary-card">
                      <div class="step3-summary-title">二级指标</div>
                      <div class="step3-summary-value">{{ task.level2_name }}</div>
                    </div>
                    <div class="step3-summary-card">
                      <div class="step3-summary-title">需要三级指标数</div>
                      <div class="step3-summary-value">{{ task.target_l3_count }} 个</div>
                    </div>
                    <div class="step3-summary-card">
                      <div class="step3-summary-title">状态</div>
                      <div class="step3-summary-value">{{ task.l3_section_markdown ? '已完成' : '待生成' }}</div>
                    </div>
                  </div>

                  <!-- 生成按钮 -->
                  <div class="upload-toolbar" style="margin-bottom: 12px;">
                    <el-button type="primary" :loading="loading" :disabled="!step3CanGenerateL3" @click="step3L3ReviewMode = 'approve'; runStep3Continue()">生成三级指标</el-button>
                    <el-button @click="chatOpen = true">通过 AI 对话生成</el-button>
                  </div>

                  <!-- 多模型对比 -->
                  <el-card v-if="step3L3Comparisons.length > 1" shadow="never" style="margin-bottom: 12px; background: var(--el-fill-color-lighter);">
                    <template #header>
                      <div style="display: flex; align-items: center; justify-content: space-between; gap: 8px;">
                        <span>多模型对比（共 {{ step3L3Comparisons.length }} 个模型）</span>
                        <el-radio-group v-model="step3L3CompareViewMode" size="small">
                          <el-radio-button value="raw">原文</el-radio-button>
                          <el-radio-button value="preview">看板</el-radio-button>
                        </el-radio-group>
                      </div>
                    </template>
                    <div class="step2-compare-layout">
                      <div class="step2-compare-list">
                        <div
                          v-for="(item, cmpIdx) in step3L3Comparisons"
                          :key="`l3-cmp-${cmpIdx}`"
                          class="step2-compare-card"
                          :class="{ active: cmpIdx === step3L3ActiveCompareIndex }"
                          style="cursor: pointer;"
                          @click="step3L3ActiveCompareIndex = cmpIdx"
                        >
                          <div class="step2-compare-title">{{ item.label || item.model_name }}</div>
                          <el-tag v-if="item.error" type="danger" size="small">调用失败</el-tag>
                          <el-tag v-else type="success" size="small">{{ (item.draft || '').length }} 字</el-tag>
                        </div>
                      </div>
                      <div class="step2-compare-detail">
                        <div v-if="step3L3Comparisons[step3L3ActiveCompareIndex]">
                          <pre v-if="step3L3CompareViewMode === 'raw'" class="result">{{ step3L3Comparisons[step3L3ActiveCompareIndex].draft || (step3L3Comparisons[step3L3ActiveCompareIndex].error ? `调用失败：${step3L3Comparisons[step3L3ActiveCompareIndex].error}` : '空响应') }}</pre>
                          <MarkdownDashboard v-else :source="step3L3Comparisons[step3L3ActiveCompareIndex].draft || ''" />
                          <div class="upload-toolbar">
                            <el-button type="primary" :disabled="!step3L3Comparisons[step3L3ActiveCompareIndex].draft" @click="applyL3Comparison(step3L3ActiveCompareIndex)">导入为当前草案</el-button>
                          </div>
                        </div>
                      </div>
                    </div>
                  </el-card>

                  <!-- 当前三级指标草案 -->
                  <el-form label-width="110px">
                    <el-form-item label="三级指标草案">
                      <div style="width: 100%;">
                        <div style="display: flex; justify-content: flex-end; margin-bottom: 6px;">
                          <el-radio-group v-model="step3L3ViewMode" size="small">
                            <el-radio-button value="edit">编辑</el-radio-button>
                            <el-radio-button value="preview">看板</el-radio-button>
                          </el-radio-group>
                        </div>
                        <el-input v-if="step3L3ViewMode === 'edit'" v-model="step3L3Draft" type="textarea" :rows="12" placeholder="三级指标草案将显示在这里，支持直接编辑" />
                        <MarkdownDashboard v-else :source="step3L3Draft || ''" />
                      </div>
                    </el-form-item>
                    <el-form-item label="修改意见">
                      <el-input v-model="step3L3Feedback" type="textarea" :rows="3" placeholder="输入修改意见，让大模型根据意见重新生成（可选）" />
                    </el-form-item>
                  </el-form>

                  <!-- 操作按钮 -->
                  <div class="upload-toolbar">
                    <el-button type="primary" :loading="loading" @click="manualSaveCurrentL3">保存当前草案</el-button>
                    <el-button type="success" :loading="loading" @click="approveL3AndNext">
                      {{ step3ActiveL2Index + 1 < step3SkeletonTasks.length ? '保存并进入下一个' : '保存并完成全部' }}
                    </el-button>
                    <el-button v-if="step3L3Feedback.trim()" type="warning" :loading="loading" @click="step3L3ReviewMode = 'modify'; runStep3Continue()">
                      提交修改意见重新生成
                    </el-button>
                    <el-button @click="chatOpen = true">通过对话修改</el-button>
                  </div>
                </div>
                <div v-else class="step3-l3-tab-preview">
                  <pre v-if="task.l3_section_markdown" class="result" style="max-height: 300px; overflow: auto;">{{ task.l3_section_markdown }}</pre>
                  <el-empty v-else description="该二级指标尚未生成三级内容，点击此 Tab 后可操作生成" />
                </div>
              </el-tab-pane>
            </el-tabs>
          </el-card>

          <!-- Step3: 完成阶段 -->
          <el-card id="sec-step3-finalize" v-if="stepId === 3 && step3SkeletonPhase === 'completed'" shadow="never">
            <template #header>Step3 · 指标体系已完成</template>
            <el-alert type="success" :closable="false" show-icon class="mb" title="全部二级指标的三级指标与解释已处理完毕，可进入定稿环节。" />
            <div class="step3-summary-grid">
              <div class="step3-summary-card">
                <div class="step3-summary-title">体系类型</div>
                <div class="step3-summary-value">{{ step3Config.system_type }}</div>
              </div>
              <div class="step3-summary-card">
                <div class="step3-summary-title">指标深度</div>
                <div class="step3-summary-value">{{ step3Config.indicator_depth }} 级</div>
              </div>
              <div class="step3-summary-card">
                <div class="step3-summary-title">二级指标总数</div>
                <div class="step3-summary-value">{{ step3SkeletonTasks.length }} 个</div>
              </div>
              <div class="step3-summary-card">
                <div class="step3-summary-title">已完成三级</div>
                <div class="step3-summary-value">{{ step3L2Progress.completed }} / {{ step3L2Progress.total }}</div>
              </div>
            </div>
            <el-alert
              type="success"
              :closable="false"
              show-icon
              :title="`已聚合 ${step3SkeletonTasks.length} 项二级指标。点击「完成 Step3 收尾并保存」即可一次性定稿，成品区将展示完整的指标体系。`"
            />
          </el-card>

          <!-- 骨架编辑对话框 -->
          <el-dialog v-model="step3SkeletonEditDialogVisible" title="编辑指标" width="500px">
            <el-form label-width="120px">
              <el-form-item label="一级指标名称">
                <el-input v-model="step3SkeletonEditForm.level1_name" />
              </el-form-item>
              <el-form-item label="二级指标名称">
                <el-input v-model="step3SkeletonEditForm.level2_name" />
              </el-form-item>
              <el-form-item label="三级指标数量">
                <el-input-number v-model="step3SkeletonEditForm.target_l3_count" :min="1" :max="20" />
              </el-form-item>
            </el-form>
            <template #footer>
              <el-button @click="step3SkeletonEditDialogVisible = false">取消</el-button>
              <el-button type="primary" @click="saveSkeletonEdit">保存</el-button>
            </template>
          </el-dialog>

          <!-- 新增一级指标对话框 -->
          <el-dialog v-model="step3SkeletonAddL1DialogVisible" title="新增一级指标" width="450px">
            <el-form label-width="120px">
              <el-form-item label="一级指标名称">
                <el-input v-model="step3NewL1Name" placeholder="例如：决策环节" />
              </el-form-item>
            </el-form>
            <template #footer>
              <el-button @click="step3SkeletonAddL1DialogVisible = false">取消</el-button>
              <el-button type="primary" @click="addSkeletonL1">添加</el-button>
            </template>
          </el-dialog>

          <!-- 新增二级指标对话框 -->
          <el-dialog v-model="step3SkeletonAddL2DialogVisible" title="新增二级指标" width="500px">
            <el-form label-width="120px">
              <el-form-item label="所属一级指标">
                <el-input v-model="step3NewL2Form.level1_name" placeholder="一级指标名称" />
              </el-form-item>
              <el-form-item label="二级指标名称">
                <el-input v-model="step3NewL2Form.level2_name" placeholder="例如：预算编制规范性" />
              </el-form-item>
              <el-form-item label="三级指标数量">
                <el-input-number v-model="step3NewL2Form.target_l3_count" :min="1" :max="20" />
              </el-form-item>
            </el-form>
            <template #footer>
              <el-button @click="step3SkeletonAddL2DialogVisible = false">取消</el-button>
              <el-button type="primary" @click="addSkeletonL2">添加</el-button>
            </template>
          </el-dialog>

          <!-- Step4: 赋分 -->
          <el-card id="sec-step4-scoring" v-if="stepId === 4" shadow="never">
            <template #header>Step4 · 生成分值</template>
            <el-alert v-if="!step4FlatL2Tasks.length" type="warning" :closable="false" show-icon title="未读取到 Step3 指标体系数据，请确保 Step3 已完成并保存。" />
            <template v-else>
              <el-alert type="info" :closable="false" show-icon class="mb" :title="`共加载 ${step4FlatL2Tasks.length} 项指标，总分 ${step4TotalScore}`" />
              <el-form label-width="110px" class="mb">
                <el-form-item label="赋分模式">
                  <el-radio-group v-model="step4ScoringMode">
                    <el-radio label="ai">AI 自动赋分</el-radio>
                    <el-radio label="manual">人工赋分</el-radio>
                  </el-radio-group>
                </el-form-item>
                <el-form-item label="总分设置">
                  <el-input-number v-model="step4TotalScore" :min="1" :max="1000" :step="10" />
                </el-form-item>
              </el-form>
              <el-table :data="step4FlatL2Tasks" size="small" stripe max-height="400">
                <el-table-column label="序号" type="index" width="60" />
                <el-table-column label="一级指标" prop="level1_name" min-width="140">
                  <template #default="{ row }">
                    <el-tag>{{ row.level1_name }}</el-tag>
                  </template>
                </el-table-column>
                <el-table-column label="二级指标" prop="level2_name" min-width="180" />
                <el-table-column v-if="step4ScoringMode === 'manual'" label="分值" width="140" align="center">
                  <template #default="{ row }">
                    <el-input-number
                      :model-value="step4ManualScores[`${row.level1_name}|${row.level2_name}`] ?? row.score ?? 0"
                      :min="0"
                      :max="100"
                      :step="1"
                      size="small"
                      controls-position="right"
                      style="width: 110px"
                      @update:model-value="(val) => { step4ManualScores[`${row.level1_name}|${row.level2_name}`] = Number(val ?? 0) }"
                    />
                  </template>
                </el-table-column>
                <el-table-column v-if="step4ScoringMode === 'ai'" label="AI 分值" prop="score" width="100" align="center">
                  <template #default="{ row }">
                    {{ row.score ?? '-' }}
                  </template>
                </el-table-column>
              </el-table>
              <el-alert
                v-for="(err, idx) in step4ValidationErrors"
                :key="`v4err-${idx}`"
                type="error"
                :closable="false"
                show-icon
                class="mb"
                :title="err"
                style="margin-top: 8px;"
              />
              <div class="upload-toolbar">
                <el-button v-if="step4ScoringMode === 'manual'" type="warning" @click="validateStep4Scores">校验分值</el-button>
                <el-button type="primary" :loading="loading" :disabled="!canGenerate" @click="runStep('')">
                  {{ step4ScoringMode === 'ai' ? 'AI 自动赋分' : '提交人工分值并生成' }}
                </el-button>
              </div>
            </template>
          </el-card>

          <!-- Step5: 评分标准 -->
          <el-card id="sec-stepN-prev" v-if="stepId === 5" shadow="never">
            <template #header>Step5 · 评分标准</template>
            <el-alert v-if="!prevStepContent && !editor" type="warning" :closable="false" show-icon title="未读取到 Step4 赋分结果，请确保 Step4 已完成并保存。" />
            <el-alert v-else type="info" :closable="false" show-icon class="mb" title="基于 Step4 赋分结果，生成各指标的详细评分标准。" />
            <el-form label-width="110px" class="mb">
              <el-form-item label="评分表备注">
                <el-input v-model="step5ScoreSheet" type="textarea" :rows="4" placeholder="补充评分标准要求或约束（可选）" />
              </el-form-item>
            </el-form>
            <div class="upload-toolbar">
              <el-button type="primary" :loading="loading" :disabled="!canGenerate" @click="runStep('')">生成评分标准</el-button>
            </div>
          </el-card>

          <!-- Step6: 绩效评价指标体系 + 可选里克特问卷 -->
          <el-card id="sec-step6-framework" v-if="stepId === 6" shadow="never">
            <template #header>Step6 · 绩效评价指标体系</template>
            <el-alert v-if="!prevStepContent && !editor" type="warning" :closable="false" show-icon title="未读取到 Step5 评分标准结果，请确保上一步已完成并保存。" />
            <el-alert v-else type="info" :closable="false" show-icon class="mb" title="基于 Step3 指标骨架、Step4 分值、Step5 评分标准生成完整指标体系；可选附里克特 5 级满意度问卷。" />
            <el-form label-width="140px" class="mb">
              <el-form-item label="是否生成问卷">
                <el-radio-group v-model="step6QuestionnaireDecision">
                  <el-radio label="skip">不需要</el-radio>
                  <el-radio label="need">需要（里克特 5 级）</el-radio>
                </el-radio-group>
              </el-form-item>
              <el-form-item v-if="step6QuestionnaireDecision === 'need'" label="问卷修改意见">
                <el-input v-model="step6QuestionnaireFeedback" type="textarea" :rows="3" placeholder="如需重做问卷，可在此处填入修改意见；首次生成可留空" />
              </el-form-item>
            </el-form>
            <div class="upload-toolbar">
              <el-button type="primary" :loading="loading" :disabled="!canGenerate" @click="runStep('')">生成指标体系</el-button>
              <el-button :loading="step6Exporting" :disabled="!step6QuestionnaireDraft && !editor" @click="downloadStep6Markdown">导出指标体系 + 问卷 (.md)</el-button>
              <el-button :disabled="!step6QuestionnaireDraft && !editor" @click="copyToClipboard(buildStep6CombinedMarkdown())">复制全部 Markdown</el-button>
            </div>

            <el-divider v-if="step6Tree.length" />
            <div v-if="step6Tree.length" class="step6-tree-wrap">
              <div class="step6-tree-head">
                <div style="font-weight:600;">指标层级可视化（拖拽排序）</div>
                <div class="step6-tree-tip">支持同级拖拽：L1 之间整组移动；L2 仅同 L1 内重排；L3 仅同 L2 内重排。分值/解释/评分标准随节点同步。</div>
              </div>
              <div ref="step6L1ListRef" class="step6-l1-list">
                <div v-for="(l1, l1Idx) in step6Tree" :key="`l1-${l1Idx}-${l1.name}`" class="step6-l1-row">
                  <div class="step6-l1-head">
                    <span class="step6-drag-handle" title="拖动整组">⋮⋮</span>
                    <span class="step6-l1-name">{{ l1.name }}</span>
                    <span class="step6-l1-score">{{ Number(l1.score).toFixed(0) }} 分</span>
                  </div>
                  <div :ref="(el) => setStep6L2Ref(`l2-${l1Idx}`, el as Element | null)" class="step6-l2-list">
                    <div v-for="(l2, l2Idx) in l1.level2" :key="`l2-${l1Idx}-${l2Idx}-${l2.name}`" class="step6-l2-row">
                      <div class="step6-l2-head">
                        <span class="step6-drag-handle" title="拖动二级指标">⋮⋮</span>
                        <span class="step6-l2-name">{{ l2.name }}</span>
                        <span class="step6-l2-score">{{ Number(l2.score).toFixed(0) }} 分</span>
                      </div>
                      <div :ref="(el) => setStep6L3Ref(`l3-${l1Idx}-${l2Idx}`, el as Element | null)" class="step6-l3-list">
                        <div v-for="(l3, l3Idx) in l2.level3" :key="`l3-${l1Idx}-${l2Idx}-${l3.id || l3Idx}`" class="step6-l3-row">
                          <div class="step6-l3-line1">
                            <span class="step6-drag-handle" title="拖动三级指标">⋮⋮</span>
                            <span class="step6-l3-name">{{ l3.name }}</span>
                            <span class="step6-l3-score">{{ Number(l3.score).toFixed(0) }} 分</span>
                          </div>
                          <div v-if="l3.key_points" class="step6-l3-kp">解释：{{ l3.key_points }}</div>
                          <div v-if="l3.rubric && Object.keys(l3.rubric).length" class="step6-l3-rubric">
                            评分标准：{{ step6LocalCompressRubric(l3.rubric, Number(l3.score) || 0) }}
                          </div>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>

            <el-divider v-if="step6QuestionnaireItems.length" />
            <div v-if="step6QuestionnaireItems.length" style="margin-top:12px;">
              <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:8px;">
                <div style="font-weight:600;">里克特 5 级问卷看板（共 {{ step6QuestionnaireItems.length }} 题）</div>
                <el-button size="small" @click="copyToClipboard(buildStep6QuestionnaireMarkdown())">复制问卷 Markdown</el-button>
              </div>
              <div class="step6-q-board">
                <el-card v-for="(q, idx) in step6QuestionnaireItems" :key="q.id || idx" shadow="hover" class="step6-q-card">
                  <div class="step6-q-head">
                    <span class="step6-q-no">Q{{ String(idx + 1).padStart(2, '0') }}</span>
                    <span class="step6-q-title">{{ q.question }}</span>
                  </div>
                  <div v-if="q.indicator_name" class="step6-q-meta">关联指标：{{ q.indicator_name }}</div>
                  <div class="step6-q-options">
                    <el-tag
                      v-for="opt in q.options"
                      :key="opt"
                      size="large"
                      effect="plain"
                      class="step6-q-opt"
                    >{{ opt }}</el-tag>
                  </div>
                </el-card>
              </div>

              <el-divider />
              <el-collapse>
                <el-collapse-item title="试填问卷（本地保存，仅供后续 step 聚合参考）" name="fill">
                  <el-form label-width="100px" class="mb">
                    <el-form-item label="作答角色">
                      <el-radio-group v-model="step6RespondentRole">
                        <el-radio label="村民">村民</el-radio>
                        <el-radio label="村两委">村两委</el-radio>
                        <el-radio label="镇政府">镇政府</el-radio>
                        <el-radio label="其他">其他</el-radio>
                      </el-radio-group>
                    </el-form-item>
                  </el-form>
                  <el-card v-for="(q, idx) in step6QuestionnaireItems" :key="`fill-${q.id || idx}`" shadow="never" class="step6-q-fill">
                    <div class="step6-q-head">
                      <span class="step6-q-no">Q{{ String(idx + 1).padStart(2, '0') }}</span>
                      <span class="step6-q-title">{{ q.question }}</span>
                    </div>
                    <el-radio-group v-model="step6Answers[q.id]" class="step6-q-fill-group">
                      <el-radio v-for="opt in q.options" :key="opt" :label="opt">{{ opt }}</el-radio>
                    </el-radio-group>
                  </el-card>
                  <div class="upload-toolbar" style="margin-top:12px;">
                    <el-button type="primary" @click="submitStep6Response">提交本次作答</el-button>
                    <el-button @click="step6Answers = {}">清空当前作答</el-button>
                    <el-button v-if="step6ResponseHistory.length" type="danger" plain @click="clearStep6Responses">清空已保存的所有问卷答案</el-button>
                  </div>
                  <div v-if="step6ResponseHistory.length" style="margin-top:12px;">
                    <div style="font-weight:600;margin-bottom:6px;">已保存作答（{{ step6ResponseHistory.length }} 份，仅本浏览器）</div>
                    <el-table :data="step6ResponseHistory" size="small" border>
                      <el-table-column prop="respondent_role" label="角色" width="100" />
                      <el-table-column prop="submitted_at" label="提交时间" width="200">
                        <template #default="{ row }">{{ new Date(row.submitted_at).toLocaleString() }}</template>
                      </el-table-column>
                      <el-table-column label="作答摘要">
                        <template #default="{ row }">
                          <span style="color:#666;font-size:12px;">{{ Object.entries(row.answers).map(([k, v]) => `${k}=${v}`).join('；') }}</span>
                        </template>
                      </el-table-column>
                    </el-table>
                  </div>
                </el-collapse-item>
              </el-collapse>
            </div>

            <el-divider v-if="step6QuestionnaireDraft && !step6QuestionnaireItems.length" />
            <div v-if="step6QuestionnaireDraft && !step6QuestionnaireItems.length" style="margin-top:12px;">
              <div style="font-weight:600;margin-bottom:6px;">里克特 5 级问卷草稿</div>
              <el-input :model-value="step6QuestionnaireDraft" type="textarea" :rows="10" readonly />
            </div>
          </el-card>

          <!-- Step 7：指标体系分析与终审成果生成 -->
          <el-card id="sec-step7-analysis" v-if="stepId === 7" shadow="never">
            <template #header>
              <div class="flex items-center justify-between">
                <div class="font-semibold">Step 7 — 指标体系分析与终审成果生成</div>
                <div class="text-xs text-gray-500">
                  评价要点表单化录入 · AI 翻译润色 · 多模型对比 · 级联得分计算
                </div>
              </div>
            </template>

            <div v-if="!step7Form.length" class="step7-empty">
              <div class="text-gray-500 text-sm" style="margin-bottom:8px;">
                暂未识别到三级指标。可点击下方按钮立即从 Step 4 / Step 5 / Step 6 的成果回源构造录入表单；
                若仍为空，请回到对应步骤确认已保存最终版本。
              </div>
              <el-button type="primary" :loading="step7Bootstrapping" @click="step7BootstrapForm">
                立即从上游构造录入表单
              </el-button>
            </div>

            <div v-else class="step7-wrap">
              <!-- 顶部：问卷统计 -->
              <div class="step7-survey-bar">
                <div class="step7-survey-title">现场问卷与样本数据（驱动效益环节 AI 撰写）</div>
                <div class="step7-survey-row">
                  <el-input-number v-model="step7SurveySample" :min="0" :step="1" placeholder="有效样本量"
                    controls-position="right" style="width: 160px;" />
                  <el-input-number v-model="step7SurveyRate" :min="0" :max="1" :step="0.01" :precision="2"
                    placeholder="综合满意率(0~1)" controls-position="right" style="width: 200px;" />
                  <el-input v-model="step7SurveySummary" placeholder="补充说明（如：覆盖 3 村 35 户，满意率 88%）"
                    style="flex:1; min-width: 280px;" clearable />
                </div>
              </div>

              <el-divider content-position="left">逐要点表单（按指标拆分）</el-divider>

              <div class="step7-form-list">
                <div v-for="form in step7Form" :key="form.id" class="step7-form-card">
                  <div class="step7-form-head">
                    <div class="step7-form-title">
                      <el-tag size="small">{{ form.l1_name }}</el-tag>
                      <el-tag size="small" type="info">{{ form.l2_name }}</el-tag>
                      <span class="step7-form-l3">{{ form.l3_name }}</span>
                    </div>
                    <div class="step7-form-meta">
                      满分 <b>{{ Number(form.score).toFixed(2) }}</b> ｜
                      已填得分
                      <b :class="{ 'text-red-600': step7TotalUserSum(form) > Number(form.score) }">
                        {{ step7TotalUserSum(form).toFixed(2) }}
                      </b>
                    </div>
                  </div>

                  <div v-for="pt in step7Inputs[form.id] || []" :key="pt.key" class="step7-point-row">
                    <div class="step7-point-head">
                      <span class="step7-point-key">{{ pt.key }}</span>
                      <span class="step7-point-label">{{ pt.label }}</span>
                    </div>
                    <el-input v-model="pt.plain_text" type="textarea" :rows="2"
                      placeholder="大白话事实：现场看到了什么、查了什么台账、收到了什么反馈" />
                    <div class="step7-point-row2">
                      <el-input-number v-model="pt.score" :min="0" :max="Number(form.score)" :step="0.5" :precision="2"
                        controls-position="right" style="width: 140px;"
                        @change="step7ClampPoint(form, pt)" />
                      <el-input v-model="pt.deduction_reason"
                        placeholder="得分/扣分原因（如：台账缺一项 → 扣 2 分）" style="flex:1;" />
                    </div>
                  </div>
                </div>
              </div>

              <!-- 操作区 -->
              <el-divider />
              <div class="step7-actions">
                <el-button type="primary" :loading="step7Generating" @click="generateStep7Analysis">
                  AI 翻译并生成专家分析
                </el-button>
                <el-input v-model="step7ReviewFeedback" placeholder="软磨：例如『把扣分语气改得更委婉』"
                  style="flex:1; min-width: 260px;" />
                <el-button :loading="step7Reviewing" :disabled="!step7AnalysisRows.length"
                  @click="reviewStep7Analysis">软磨润色</el-button>
              </div>

              <!-- 多模型对比 -->
              <div v-if="step7Comparisons.length > 1" class="step7-compare">
                <div class="step7-compare-title">多模型同台对比（可一键采用）</div>
                <div class="step7-compare-list">
                  <div v-for="(c, idx) in step7Comparisons" :key="idx" class="step7-compare-card">
                    <div class="step7-compare-head">
                      <b>{{ c.label || c.model_name }}</b>
                      <el-button size="small" :disabled="!c.draft || !!c.error" @click="step7AdoptComparison(c)">
                        采用此模型
                      </el-button>
                    </div>
                    <pre v-if="!c.error" class="step7-compare-body">{{ c.draft }}</pre>
                    <div v-else class="step7-compare-error">⚠ {{ c.error }}</div>
                  </div>
                </div>
              </div>

              <!-- 结果总览 -->
              <div v-if="step7AnalysisRows.length" class="step7-summary">
                <el-divider content-position="left">级联得分汇总</el-divider>
                <div class="step7-stat-row">
                  <div class="step7-stat-card"><div class="step7-stat-label">项目得分</div>
                    <div class="step7-stat-value">{{ step7TotalScore.toFixed(2) }}</div></div>
                  <div class="step7-stat-card"><div class="step7-stat-label">满分</div>
                    <div class="step7-stat-value">{{ step7TotalFull.toFixed(2) }}</div></div>
                  <div class="step7-stat-card"><div class="step7-stat-label">总得分率</div>
                    <div class="step7-stat-value">{{ (step7OverallRate * 100).toFixed(2) }}%</div></div>
                </div>

                <el-divider content-position="left">AI 事实级深度分析（逐三级指标）</el-divider>
                <el-collapse>
                  <el-collapse-item v-for="row in step7AnalysisRows" :key="row.id"
                    :name="row.id">
                    <template #title>
                      <div style="display:flex;flex-wrap:wrap;gap:6px;align-items:center;">
                        <el-tag size="small">{{ row.l1_name }}</el-tag>
                        <el-tag size="small" type="info">{{ row.l2_name }}</el-tag>
                        <span style="font-weight:600;">{{ row.l3_name }}</span>
                        <el-tag size="small" :type="row.score_rate >= 0.9 ? 'success' : row.score_rate >= 0.6 ? 'warning' : 'danger'">
                          {{ Number(row.obtained_score).toFixed(2) }} / {{ Number(row.score).toFixed(2) }}（{{ (Number(row.score_rate) * 100).toFixed(1) }}%）
                        </el-tag>
                      </div>
                    </template>
                    <div v-if="row.deduction_reason" style="margin-bottom:6px;color:#b54708;">
                      扣分原因：{{ row.deduction_reason }}
                    </div>
                    <div style="white-space:pre-wrap;line-height:1.7;color:#1f2937;">{{ row.analysis }}</div>
                    <div v-if="row.model_name" style="margin-top:6px;font-size:12px;color:#6b7280;">
                      采用模型：{{ row.model_name }}
                    </div>
                  </el-collapse-item>
                </el-collapse>

                <el-divider content-position="left">分块分析（决策 / 过程 / 产出 / 效益）</el-divider>
                <div class="step7-md-preview" v-html="renderMarkdown(step7BlockMd || '')"></div>
                <el-divider content-position="left">总评分表（一级 / 二级 / 三级 / 分值 / 得分 / 扣分原因）</el-divider>
                <div class="step7-md-preview" v-html="renderMarkdown(step7OverallMd || '')"></div>

                <el-divider content-position="left">终审定稿成果（指标体系分析与得分表 · 完整版）</el-divider>
                <div class="step7-md-preview" v-html="renderMarkdown(step7FinalMd || '')"></div>
              </div>

              <!-- 导出参数 -->
              <el-divider content-position="left">导出参数（一键导出 Word / PDF）</el-divider>
              <div class="step7-export-bar">
                <el-select v-model="step7ExportFontFamily" style="width: 200px;">
                  <el-option label="仿宋_GB2312" value="FangSong_GB2312" />
                  <el-option label="宋体（SimSun）" value="SimSun" />
                  <el-option label="黑体" value="SimHei" />
                  <el-option label="楷体" value="KaiTi" />
                </el-select>
                <el-input-number v-model="step7ExportFontSize" :min="9" :max="22" :step="1"
                  controls-position="right" style="width: 140px;" />
                <el-input-number v-model="step7ExportLineHeight" :min="1.0" :max="2.5" :step="0.1" :precision="1"
                  controls-position="right" style="width: 140px;" />
                <el-button type="success" :disabled="!step7AnalysisRows.length" @click="exportStep7Document">
                  一键导出指标体系得分表
                </el-button>
              </div>
            </div>
          </el-card>

          <!-- Step8, Step10~13: 通用步骤（Step7 单独走专属表单卡片，不走这里） -->
          <el-card id="sec-stepN-prev" v-if="stepId === 8 || stepId >= 10 && stepId <= 13" shadow="never">
            <template #header>{{ titleMap[stepId] ?? `Step${stepId}` }}</template>
            <el-alert v-if="!prevStepContent && !editor" type="warning" :closable="false" show-icon :title="`未读取到 Step${stepId - 1} 结果，请确保上一步已完成并保存。`" />
            <el-alert v-else type="info" :closable="false" show-icon class="mb" :title="`基于 Step${stepId - 1} 输出内容继续生成。`" />
            <el-form v-if="prevStepContent" label-width="110px" class="mb">
              <el-form-item label="上一步内容">
                <div style="width: 100%;">
                  <div style="display: flex; justify-content: flex-end; margin-bottom: 6px;">
                    <el-radio-group v-model="prevStepViewMode" size="small">
                      <el-radio-button value="raw">原文</el-radio-button>
                      <el-radio-button value="preview">看板</el-radio-button>
                    </el-radio-group>
                  </div>
                  <el-input v-if="prevStepViewMode === 'raw'" :model-value="prevStepContent" type="textarea" :rows="6" readonly />
                  <MarkdownDashboard v-else :source="prevStepContent" />
                </div>
              </el-form-item>
            </el-form>
            <div class="upload-toolbar">
              <el-button type="primary" :loading="loading" :disabled="!canGenerate" @click="runStep('')">开始生成</el-button>
            </div>
          </el-card>

          <!-- Step9: 评价结论 + 风格 -->
          <el-card id="sec-step9-style" v-if="stepId === 9" shadow="never">
            <template #header>Step9 · 评价结论</template>
            <el-alert v-if="!prevStepContent && !editor" type="warning" :closable="false" show-icon title="未读取到 Step8 结果，请确保上一步已完成并保存。" />
            <el-alert v-else type="info" :closable="false" show-icon class="mb" title="根据前序步骤内容生成评价结论，可选择结论语气风格。" />
            <el-form label-width="110px" class="mb">
              <el-form-item label="语气风格">
                <el-radio-group v-model="step9StyleMode">
                  <el-radio label="neutral">中性客观</el-radio>
                  <el-radio label="sharp">尖锐直接</el-radio>
                  <el-radio label="gentle">温和委婉</el-radio>
                </el-radio-group>
              </el-form-item>
            </el-form>
            <el-form v-if="prevStepContent" label-width="110px" class="mb">
              <el-form-item label="上一步内容">
                <div style="width: 100%;">
                  <div style="display: flex; justify-content: flex-end; margin-bottom: 6px;">
                    <el-radio-group v-model="prevStepViewMode" size="small">
                      <el-radio-button value="raw">原文</el-radio-button>
                      <el-radio-button value="preview">看板</el-radio-button>
                    </el-radio-group>
                  </div>
                  <el-input v-if="prevStepViewMode === 'raw'" :model-value="prevStepContent" type="textarea" :rows="6" readonly />
                  <MarkdownDashboard v-else :source="prevStepContent" />
                </div>
              </el-form-item>
            </el-form>
            <div class="upload-toolbar">
              <el-button type="primary" :loading="loading" :disabled="!canGenerate" @click="runStep('')">生成评价结论</el-button>
            </div>
          </el-card>

          <!-- Step14: 评价报告 + 导出 -->
          <el-card id="sec-step14-export" v-if="stepId === 14" shadow="never">
            <template #header>Step14 · 评价报告</template>
            <el-alert v-if="!prevStepContent && !editor" type="warning" :closable="false" show-icon title="未读取到 Step13 结果，请确保上一步已完成并保存。" />
            <el-alert v-else type="info" :closable="false" show-icon class="mb" title="汇总所有步骤结果，生成最终评价报告。完成后可导出 Markdown 或 Word 文档。" />
            <el-form label-width="110px" class="mb">
              <el-form-item label="报告标题">
                <el-input v-model="step14ExportCustomTitle" placeholder="例如 某项目绩效评价报告" />
              </el-form-item>
            </el-form>
            <el-form v-if="prevStepContent" label-width="110px" class="mb">
              <el-form-item label="上一步内容">
                <div style="width: 100%;">
                  <div style="display: flex; justify-content: flex-end; margin-bottom: 6px;">
                    <el-radio-group v-model="prevStepViewMode" size="small">
                      <el-radio-button value="raw">原文</el-radio-button>
                      <el-radio-button value="preview">看板</el-radio-button>
                    </el-radio-group>
                  </div>
                  <el-input v-if="prevStepViewMode === 'raw'" :model-value="prevStepContent" type="textarea" :rows="6" readonly />
                  <MarkdownDashboard v-else :source="prevStepContent" />
                </div>
              </el-form-item>
            </el-form>
            <div class="upload-toolbar">
              <el-button type="primary" :loading="loading" :disabled="!canGenerate" @click="runStep('')">生成评价报告</el-button>
              <el-button type="warning" :loading="step14ExportSaving" :disabled="isEditorEmpty()" @click="openStep14ExportDialog">导出报告（Markdown / Word）</el-button>
              <el-button v-if="lastStep14ExportUrl" @click="downloadLastStep14Export">下载上次导出</el-button>
            </div>
          </el-card>

          <!-- Existing step1 cards -->
          <el-card id="sec-step1-export" v-if="stepId === 1" shadow="never">
            <template #header>Step1 成果区与导出</template>
            <el-alert
              type="success"
              :closable="false"
              show-icon
              class="mb"
              title="这里是最终成果区。确认内容无误后，可导出为带项目名称命名的 Word 文档，文件会直接下载到浏览器，不会写入资料草稿清单。"
            />
            <div class="upload-toolbar">
              <el-button type="warning" :loading="exportSaving" @click="openStep1ExportDialog">成果导出</el-button>
            </div>
          </el-card>
          <div id="sec-artifact-editor">
            <ArtifactEditor
            v-model="editor"
            :title="titleMap[stepId] ?? `Step ${stepId}`"
            :tag="stepId === 3 ? 'Step3 定稿区' : (currentResult?.status ? String(currentResult.status) : '最终版本')"
            :rows="18"
            :placeholder="editorPlaceholder"
            :enable-dashboard="true"
            :key-metrics="(stepId === 1 || stepId === 2) ? step1StructuredAnalysis.keyMetrics : undefined"
            :gap-items="(stepId === 1 || stepId === 2) ? step1StructuredAnalysis.gapAnalysis : undefined"
            :source-index="stepId === 2 ? step2SourceIndex : undefined"
            @request-upload="onRequestUpload"
            @step-click="goStep"
          />
          </div>
          <el-card id="sec-backend-result" shadow="never">
            <template #header>后端结果</template>
            <el-skeleton v-if="loading" :rows="4" animated />
            <template v-else>
              <el-empty v-if="!resultText" description="暂无结果" />
              <pre v-else class="result">{{ resultText }}</pre>
            </template>
          </el-card>
          <el-card shadow="never" v-if="currentOutputs.length">
            <template #header>当前步骤输出摘要</template>
            <div class="history-grid">
              <div v-for="item in currentOutputs" :key="item.title" class="history-item">
                <div class="history-title">{{ item.title }}</div>
                <div class="history-desc">{{ item.desc }}</div>
                <pre class="history-content">{{ item.content }}</pre>
              </div>
            </div>
          </el-card>
        </div>
      </div>

      <aside class="side">
        <TaskProgress
          :status="taskProgress.status"
          :percent="taskProgress.percent"
          :done-steps="taskProgress.doneSteps"
          :total-steps="taskProgress.totalSteps"
        />
      </aside>
    </div>

    <HistoryDrawer
      :visible="historyOpen"
      :items="historyItems.map((item, idx) => ({ id: item.id, title: `${idx + 1}. ${item.title}`, desc: item.desc }))"
      @close="historyOpen = false"
      @restore="restoreHistory"
      @delete="deleteHistory"
    />

    <ChatDrawer
      v-model="chatOpen"
      :project-id="projectId"
      :step-code="stepCodeOf()"
      :step-title="titleMap[stepId] ?? `Step ${stepId}`"
      :prompt-hint="promptHintMap[stepId] ?? '输入本步骤补充指令或约束'"
      :thread-id="stepId === 1 ? step1ThreadId : (stepId === 3 ? `step3:${projectId}` : undefined)"
      :workflow-state="workflowState"
      @replace-draft="replaceStep1DraftFromChat"
    />

    <el-dialog v-model="step2ExportDialogVisible" title="Step2 核心内容导出" width="720px" class="ef-confirm-dialog">
      <el-alert
        type="info"
        :closable="false"
        show-icon
        class="mb"
        title="默认以 Markdown 格式导出当前成品区核心内容；切换为 Word 后可调整经典/自定义排版与字体字号。"
      />
      <el-form label-width="140px">
        <el-form-item label="导出格式">
          <el-radio-group v-model="step2ExportFormat">
            <el-radio value="markdown">Markdown（.md）</el-radio>
            <el-radio value="docx">Word（.docx）</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="项目名称">
          <el-input :model-value="getGlobalProjectName()" disabled />
        </el-form-item>
        <el-form-item label="文档标题">
          <el-input v-model="step2ExportCustomTitle" placeholder="例如 某项目项目核心内容" />
        </el-form-item>
        <el-form-item v-if="step2ExportFormat === 'docx'" label="排版模式">
          <el-radio-group v-model="step2ExportStyle">
            <el-radio label="classic">经典排版</el-radio>
            <el-radio label="custom">自定义排版</el-radio>
          </el-radio-group>
        </el-form-item>
        <template v-if="step2ExportFormat === 'docx' && step2ExportStyle === 'custom'">
          <el-form-item label="正文字体">
            <el-select v-model="step2ExportFormatOptions.font_family" style="width: 100%">
              <el-option label="宋体（SimSun）" value="SimSun" />
              <el-option label="黑体（SimHei）" value="SimHei" />
              <el-option label="微软雅黑（Microsoft YaHei）" value="Microsoft YaHei" />
              <el-option label="仿宋（FangSong）" value="FangSong" />
              <el-option label="楷体（KaiTi）" value="KaiTi" />
              <el-option label="Times New Roman" value="Times New Roman" />
              <el-option label="Arial" value="Arial" />
            </el-select>
          </el-form-item>
          <el-form-item label="正文字号（pt）">
            <el-slider v-model="step2ExportFormatOptions.font_size_pt" :min="8" :max="22" :step="0.5" show-input />
          </el-form-item>
          <el-form-item label="标题字号（pt）">
            <el-slider v-model="step2ExportFormatOptions.heading_font_size_pt" :min="12" :max="32" :step="0.5" show-input />
          </el-form-item>
          <el-form-item label="行距倍数">
            <el-slider v-model="step2ExportFormatOptions.line_spacing" :min="1" :max="3" :step="0.05" show-input />
          </el-form-item>
          <el-form-item label="段后距（pt）">
            <el-slider v-model="step2ExportFormatOptions.paragraph_spacing_pt" :min="0" :max="24" :step="0.5" show-input />
          </el-form-item>
          <el-form-item label="首行缩进字符数">
            <el-slider v-model="step2ExportFormatOptions.first_line_indent_chars" :min="0" :max="4" :step="0.5" show-input />
          </el-form-item>
        </template>
        <el-form-item label="导出内容预览">
          <div style="width: 100%;">
            <div style="display: flex; justify-content: flex-end; margin-bottom: 6px;">
              <el-radio-group v-model="exportPreviewMode" size="small">
                <el-radio-button value="raw">原文</el-radio-button>
                <el-radio-button value="preview">看板</el-radio-button>
              </el-radio-group>
            </div>
            <el-input v-if="exportPreviewMode === 'raw'" :model-value="editor" type="textarea" :rows="8" readonly />
            <MarkdownDashboard v-else :source="editor || ''" />
          </div>
        </el-form-item>
        <el-alert v-if="lastStep2ExportUrl" type="success" :closable="false" show-icon class="mb" :title="`已生成：${lastStep2ExportFileName}`" />
      </el-form>
      <template #footer>
        <el-button @click="step2ExportDialogVisible = false">关闭</el-button>
        <el-button v-if="lastStep2ExportUrl" @click="downloadLastStep2Export">下载上次导出</el-button>
        <el-button type="primary" :loading="step2ExportSaving" @click="submitStep2Export(true)">
          {{ step2ExportFormat === 'markdown' ? '导出 Markdown 并下载' : '导出 Word 并下载' }}
        </el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="exportDialogVisible" title="Step1 成果导出" width="620px" class="ef-confirm-dialog">
      <el-alert
        type="info"
        :closable="false"
        show-icon
        class="mb"
        title="导出当前成品区内容，默认以 Markdown 格式下载；也可切换为 Word 文档。"
      />
      <el-form label-width="110px">
        <el-form-item label="导出格式">
          <el-radio-group v-model="exportFormat">
            <el-radio value="markdown">Markdown（.md）</el-radio>
            <el-radio value="docx">Word（.docx）</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="项目名称">
          <el-input :model-value="getGlobalProjectName()" disabled />
        </el-form-item>
        <el-form-item label="文档标题">
          <el-input v-model="exportCustomTitle" placeholder="例如 某项目项目资料清单" />
        </el-form-item>
        <el-form-item v-if="exportFormat === 'docx'" label="导出排版">
          <el-radio-group v-model="exportStyle">
            <el-radio label="classic">经典排版</el-radio>
            <el-radio label="custom">自定义排版</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="导出内容">
          <div style="width: 100%;">
            <div style="display: flex; justify-content: flex-end; margin-bottom: 6px;">
              <el-radio-group v-model="exportPreviewMode" size="small">
                <el-radio-button value="raw">原文</el-radio-button>
                <el-radio-button value="preview">看板</el-radio-button>
              </el-radio-group>
            </div>
            <el-input v-if="exportPreviewMode === 'raw'" :model-value="editor" type="textarea" :rows="8" readonly />
            <MarkdownDashboard v-else :source="editor || ''" />
          </div>
        </el-form-item>
        <el-alert v-if="lastExportUrl" type="success" :closable="false" show-icon class="mb" :title="`已生成：${lastExportFileName}`" />
      </el-form>
      <template #footer>
        <el-button @click="exportDialogVisible = false">关闭</el-button>
        <el-button v-if="lastExportUrl" @click="downloadLastStep1Export">下载上次导出</el-button>
        <el-button type="primary" :loading="exportSaving" @click="submitStep1Export(true)">
          {{ exportFormat === 'markdown' ? '导出 Markdown 并下载' : '导出 Word 并下载' }}
        </el-button>
      </template>
    </el-dialog>

    <el-dialog
      v-model="uploadDialogVisible"
      :title="uploadingChannel === 'media' ? '图片 / PDF 资料上传窗口' : 'Word / Excel 资料上传窗口'"
      width="560px"
      class="ef-confirm-dialog ef-upload-dialog"
    >
      <el-alert
        v-if="uploadingChannel === 'media'"
        type="warning"
        :closable="false"
        show-icon
        class="mb"
        title="这个窗口用于图片和 PDF 资料，Step2 后端会按通道把资料传给对应模型做校验与提炼。"
      />
      <el-alert
        v-else
        type="success"
        :closable="false"
        show-icon
        class="mb"
        title="这个窗口用于 Word、Excel 等文档资料，适合上传制度、预算、实施方案等文本型资料。"
      />
      <el-upload
        drag
        multiple
        :auto-upload="false"
        :limit="20"
        :show-file-list="true"
        v-model:file-list="uploadQueue"
        :accept="acceptTypes(uploadingChannel)"
        :before-upload="beforeUpload"
        :on-change="handleFileChange"
        :on-exceed="handleUploadExceed"
      >
        <div class="el-upload__text">拖拽文件到这里，或 <em>点击选择</em></div>
        <template #tip>
          <div class="el-upload__tip">Step2 会自动识别并上传所选文件，完成后同步刷新项目资料列表。</div>
          <div v-if="uploadPreviewText" class="el-upload__tip">当前已选：{{ uploadPreviewText }}</div>
        </template>
      </el-upload>
      <template #footer>
        <el-button @click="clearUploadQueue">清空</el-button>
        <el-button @click="uploadDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="uploading" @click="uploadQueuedFiles">开始上传</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="step1ExpandDialog" title="Step1 草稿放大编辑" fullscreen append-to-body class="ef-confirm-dialog">
      <el-input v-model="editor" type="textarea" :rows="30" :placeholder="editorPlaceholder" />
      <template #footer>
        <el-button @click="step1ExpandDialog = false">关闭</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="step14ExportDialogVisible" title="Step14 评价报告导出" width="620px" class="ef-confirm-dialog">
      <el-alert
        type="info"
        :closable="false"
        show-icon
        class="mb"
        title="默认以 Markdown 格式导出评价报告；也可切换为 Word 文档。"
      />
      <el-form label-width="110px">
        <el-form-item label="导出格式">
          <el-radio-group v-model="step14ExportFormat">
            <el-radio value="markdown">Markdown（.md）</el-radio>
            <el-radio value="docx">Word（.docx）</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="项目名称">
          <el-input :model-value="getGlobalProjectName()" disabled />
        </el-form-item>
        <el-form-item label="报告标题">
          <el-input v-model="step14ExportCustomTitle" placeholder="例如 某项目绩效评价报告" />
        </el-form-item>
        <el-form-item label="导出内容预览">
          <div style="width: 100%;">
            <div style="display: flex; justify-content: flex-end; margin-bottom: 6px;">
              <el-radio-group v-model="exportPreviewMode" size="small">
                <el-radio-button value="raw">原文</el-radio-button>
                <el-radio-button value="preview">看板</el-radio-button>
              </el-radio-group>
            </div>
            <el-input v-if="exportPreviewMode === 'raw'" :model-value="editor" type="textarea" :rows="8" readonly />
            <MarkdownDashboard v-else :source="editor || ''" />
          </div>
        </el-form-item>
        <el-alert v-if="lastStep14ExportUrl" type="success" :closable="false" show-icon class="mb" :title="`已生成：${lastStep14ExportFileName}`" />
      </el-form>
      <template #footer>
        <el-button @click="step14ExportDialogVisible = false">关闭</el-button>
        <el-button v-if="lastStep14ExportUrl" @click="downloadLastStep14Export">下载上次导出</el-button>
        <el-button type="primary" :loading="step14ExportSaving" @click="submitStep14Export">
          {{ step14ExportFormat === 'markdown' ? '导出 Markdown 并下载' : '导出 Word 并下载' }}
        </el-button>
      </template>
    </el-dialog>

    <el-dialog
      v-model="confirmDialogVisible"
      :title="confirmDialogTitle"
      width="420px"
      align-center
      class="ef-confirm-dialog"
      :close-on-click-modal="false"
      :close-on-press-escape="false"
      destroy-on-close
    >
      <div class="confirm-content">
        <el-alert
          :title="confirmDialogMessage"
          :type="confirmDialogType === 'danger' ? 'error' : 'warning'"
          :closable="false"
          show-icon
          class="confirm-alert"
        />
      </div>
      <template #footer>
        <div class="confirm-footer">
          <el-button @click="confirmDialogVisible = false">取消</el-button>
          <el-button :type="confirmDialogType === 'danger' ? 'danger' : 'primary'" @click="runPendingConfirmAction">
            {{ confirmDialogOkText }}
          </el-button>
        </div>
      </template>
    </el-dialog>

    <el-dialog
      v-model="gapUploadPickerVisible"
      :title="`补齐资料：${gapUploadPickerMaterial}`"
      width="720px"
      append-to-body
      class="ef-confirm-dialog"
    >
      <el-alert
        type="info"
        :closable="false"
        show-icon
        class="mb"
        title="请根据资料的格式选择对应的上传通道，并确认通道使用的模型。"
      />
      <div class="gap-channel-grid">
        <div class="gap-channel-card">
          <div class="gap-channel-head">
            <span class="gap-channel-icon">📷</span>
            <div>
              <div class="gap-channel-title">图片 / PDF 通道</div>
              <div class="gap-channel-sub">适合扫描件、批复照片、PDF 文档</div>
            </div>
          </div>
          <div class="gap-channel-body">
            <div class="gap-channel-label">当前通道模型</div>
            <el-select v-model="step2MediaModelId" clearable placeholder="不绑定时全部已启用模型参与" size="small">
              <el-option
                v-for="option in step2ChannelModelOptions"
                :key="option.id"
                :label="option.label"
                :value="option.id"
              />
            </el-select>
            <el-alert
              v-if="!step2MediaModelSupportsVision"
              type="warning"
              :closable="false"
              show-icon
              class="gap-channel-alert"
              title="当前通道未绑定支持视觉的多模态模型，扫描件可能无法被识别。"
            />
          </div>
          <el-button type="primary" class="gap-channel-action" @click="pickGapUploadChannel('media')">
            选择此通道并上传
          </el-button>
        </div>

        <div class="gap-channel-card">
          <div class="gap-channel-head">
            <span class="gap-channel-icon">📄</span>
            <div>
              <div class="gap-channel-title">Word / Excel 通道</div>
              <div class="gap-channel-sub">适合制度、预算、实施方案等文本资料</div>
            </div>
          </div>
          <div class="gap-channel-body">
            <div class="gap-channel-label">当前通道模型</div>
            <el-select v-model="step2DocsModelId" clearable placeholder="不绑定时全部已启用模型参与" size="small">
              <el-option
                v-for="option in step2ChannelModelOptions"
                :key="option.id"
                :label="option.label"
                :value="option.id"
              />
            </el-select>
          </div>
          <el-button type="primary" class="gap-channel-action" @click="pickGapUploadChannel('documents')">
            选择此通道并上传
          </el-button>
        </div>
      </div>
      <template #footer>
        <el-button @click="gapUploadPickerVisible = false">取消</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.workflow { max-width: 1400px; }
.workflow--embedded { max-width: none; padding: 0; }
.layout { display: grid; grid-template-columns: 200px minmax(0, 1fr) 260px; gap: 14px; align-items: start; }
.layout--no-sidebar { grid-template-columns: minmax(0, 1fr) 260px; }
.center { min-width: 0; }
.stack { display: grid; gap: 12px; }
.stack [id^="sec-"] { scroll-margin-top: 84px; }
.placeholder { padding: 20px; }
.side { display: grid; gap: 12px; }
.mb { margin-bottom: 12px; }
.model-config-hint { width: 100%; margin-top: 6px; font-size: 12px; color: var(--el-text-color-secondary); }
.model-config-list { display: grid; gap: 12px; margin-bottom: 12px; }
.model-config-card { border-color: var(--el-border-color-lighter); }
.model-config-card-header { display: flex; justify-content: space-between; align-items: center; gap: 12px; }
.model-config-card-actions { display: flex; align-items: center; gap: 10px; }
.pagination-row { display: flex; justify-content: flex-end; margin: 10px 0 12px; }
.upload-matrix { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; margin-bottom: 12px; }
.upload-box { border: 1px solid var(--el-border-color-light); border-radius: 12px; padding: 16px; background: var(--el-bg-color-page); display: grid; gap: 8px; }
.upload-title { font-weight: 700; font-size: 15px; }
.upload-meta { color: var(--el-text-color-secondary); font-size: 13px; }
.upload-desc { color: var(--el-text-color-regular); font-size: 13px; line-height: 1.5; }
.upload-summary { display: flex; gap: 18px; flex-wrap: wrap; color: var(--el-text-color-secondary); margin-top: 12px; }
.upload-toolbar { display: flex; flex-wrap: wrap; gap: 10px; margin: 12px 0; }
.step-card-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; margin-bottom: 12px; }
.step-card { border: 1px solid var(--el-border-color-light); border-radius: 12px; padding: 14px 16px; background: var(--el-bg-color-page); display: grid; gap: 8px; }
.step2-category-row { display: flex; flex-wrap: wrap; align-items: center; gap: 12px; margin-bottom: 12px; }
.step2-extra-row { gap: 8px; }
.step2-compare-layout { display: grid; grid-template-columns: 260px minmax(0, 1fr); gap: 14px; }
.step2-compare-list { display: grid; gap: 10px; max-height: 480px; overflow: auto; padding-right: 4px; }
.step2-compare-card { border: 1px solid var(--el-border-color-light); border-radius: 10px; padding: 10px 12px; background: var(--el-bg-color-page); cursor: pointer; display: grid; gap: 6px; }
.step2-compare-card.active { border-color: var(--el-color-primary); box-shadow: 0 0 0 2px rgba(64, 158, 255, 0.18); background: var(--el-color-primary-light-9); }
.step2-compare-title { font-size: 14px; font-weight: 700; color: var(--el-text-color-primary); }
.step2-compare-meta { font-size: 12px; color: var(--el-text-color-secondary); }
.step2-compare-detail { border: 1px solid var(--el-border-color-light); border-radius: 12px; padding: 14px 16px; background: var(--el-bg-color); min-height: 280px; }
.step2-compare-detail .result { max-height: 360px; overflow: auto; }
.step2-compare-detail-title { font-size: 15px; font-weight: 700; margin-bottom: 8px; color: var(--el-text-color-primary); }
.draft-memory-list { display: grid; gap: 8px; }
.draft-memory-item { display: grid; grid-template-columns: minmax(0, 1fr) auto; align-items: start; gap: 12px; border: 1px solid var(--el-border-color-lighter); border-radius: 10px; padding: 10px 12px; background: var(--el-bg-color-page); }
.draft-memory-main { min-width: 0; }
.draft-memory-actions { display: flex; flex-direction: column; gap: 6px; align-items: flex-start; }
.draft-memory-title { font-size: 13px; font-weight: 700; color: var(--el-text-color-primary); display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.draft-memory-toggle { margin-left: auto; }
.draft-memory-desc { font-size: 12px; color: var(--el-text-color-secondary); margin-top: 3px; }
.draft-memory-preview { margin: 8px 0 0; max-height: 160px; overflow: auto; white-space: pre-wrap; word-break: break-word; font-size: 12px; line-height: 1.5; color: var(--el-text-color-regular); background: var(--el-fill-color-blank); border-radius: 8px; padding: 8px; }
.card-head-with-toggle { display: flex; align-items: center; justify-content: space-between; gap: 12px; flex-wrap: wrap; width: 100%; }
.draft-editor-wrap { position: relative; width: 100%; }
.draft-editor-expand { position: absolute; top: 6px; right: 8px; z-index: 2; }
.step3-summary-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; margin: 12px 0; }
.step3-summary-card { border: 1px solid var(--el-border-color-light); border-radius: 12px; padding: 12px 14px; background: var(--el-bg-color-page); }
.step3-summary-title { font-size: 12px; color: var(--el-text-color-secondary); margin-bottom: 6px; }
.step3-summary-value { font-size: 14px; font-weight: 700; color: var(--el-text-color-primary); }
.result { white-space: pre-wrap; word-break: break-word; margin: 0; font-size: 12px; }
.confirm-content { padding: 4px 0 2px; }
.confirm-alert { margin-bottom: 0; }
.confirm-footer { display: flex; justify-content: flex-end; gap: 10px; }
:deep(.ef-confirm-dialog .el-dialog__body) { padding-top: 8px; }
:deep(.ef-confirm-dialog .el-dialog__footer) { padding-top: 0; }
:deep(.ef-confirm-dialog .el-dialog__header) { padding-bottom: 10px; }
:deep(.ef-upload-dialog .el-dialog__body) { padding-top: 8px; }
.gap-channel-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 14px; }
.gap-channel-card { border: 1px solid var(--el-border-color-light); border-radius: 12px; padding: 16px; background: var(--el-bg-color-page); display: grid; gap: 12px; align-content: start; }
.gap-channel-head { display: flex; align-items: center; gap: 10px; }
.gap-channel-icon { font-size: 22px; line-height: 1; }
.gap-channel-title { font-weight: 700; font-size: 15px; color: var(--el-text-color-primary); }
.gap-channel-sub { font-size: 12px; color: var(--el-text-color-secondary); margin-top: 2px; }
.gap-channel-body { display: grid; gap: 8px; }
.gap-channel-label { font-size: 12px; color: var(--el-text-color-secondary); }
.gap-channel-alert { margin-top: 4px; }
.gap-channel-action { width: 100%; }
.step6-q-board { display: flex; flex-direction: column; gap: 12px; }
.step6-q-card { border-left: 3px solid var(--el-color-primary); }
.step6-q-fill { border: 1px dashed var(--el-border-color); margin-bottom: 8px; }
.step6-q-head { display: flex; align-items: baseline; gap: 8px; }
.step6-q-no { font-weight: 600; color: var(--el-color-primary); min-width: 44px; }
.step6-q-title { font-weight: 500; line-height: 1.5; }
.step6-q-meta { color: var(--el-text-color-secondary); font-size: 12px; margin: 6px 0 8px 52px; }
.step6-q-options { display: flex; flex-wrap: wrap; gap: 8px; margin-left: 52px; }
.step6-q-opt { font-size: 13px; }
.step6-q-fill-group { display: flex; flex-wrap: wrap; gap: 12px; margin-left: 52px; margin-top: 6px; }
.step6-tree-wrap { background: var(--el-fill-color-lighter); padding: 12px; border-radius: 8px; }
.step6-tree-head { margin-bottom: 10px; }
.step6-tree-tip { color: var(--el-text-color-secondary); font-size: 12px; margin-top: 4px; }
.step6-l1-list { display: flex; flex-direction: column; gap: 10px; }
.step6-l1-row { background: var(--el-bg-color); border: 1px solid var(--el-border-color); border-radius: 6px; padding: 10px; }
.step6-l1-head { display: flex; align-items: center; gap: 10px; font-weight: 700; color: var(--el-color-primary); padding-bottom: 8px; border-bottom: 1px dashed var(--el-border-color-lighter); }
.step6-l1-name { flex: 1; }
.step6-l1-score { font-weight: 700; color: var(--el-color-warning); }
.step6-l2-list { display: flex; flex-direction: column; gap: 8px; padding: 8px 0 0 18px; }
.step6-l2-row { background: var(--el-fill-color-light); border: 1px solid var(--el-border-color-lighter); border-radius: 5px; padding: 8px; }
.step6-l2-head { display: flex; align-items: center; gap: 8px; font-weight: 600; }
.step6-l2-name { flex: 1; }
.step6-l2-score { color: var(--el-color-warning); }
.step6-l3-list { display: flex; flex-direction: column; gap: 6px; padding: 6px 0 0 18px; }
.step6-l3-row { display: flex; flex-direction: column; gap: 4px; background: var(--el-bg-color); border: 1px dashed var(--el-border-color-lighter); border-radius: 4px; padding: 8px 10px; font-size: 13px; }
.step6-l3-line1 { display: flex; align-items: center; gap: 8px; }
.step6-l3-name { flex: 1; font-weight: 500; }
.step6-l3-score { color: var(--el-color-warning); min-width: 50px; text-align: right; font-weight: 600; }
.step6-l3-kp { color: var(--el-text-color-regular); font-size: 12px; padding-left: 22px; line-height: 1.5; }
.step6-l3-rubric { color: var(--el-text-color-secondary); font-size: 12px; padding-left: 22px; line-height: 1.5; }
.step6-drag-handle { cursor: grab; color: var(--el-text-color-placeholder); user-select: none; padding: 0 4px; font-size: 14px; }
.step6-drag-handle:active { cursor: grabbing; }

/* === Step 7：指标体系分析与终审成果生成 === */
.step7-wrap { display: flex; flex-direction: column; gap: 14px; }
.step7-empty { display: flex; flex-direction: column; gap: 8px; padding: 8px 0; }
.step7-survey-bar { background: var(--el-fill-color-light); border: 1px solid var(--el-border-color-lighter); border-radius: 6px; padding: 10px 12px; display: flex; flex-direction: column; gap: 8px; }
.step7-survey-title { font-size: 13px; font-weight: 600; color: var(--el-text-color-primary); }
.step7-survey-row { display: flex; flex-wrap: wrap; gap: 10px; align-items: center; }
.step7-form-list { display: flex; flex-direction: column; gap: 12px; }
.step7-form-card { border: 1px solid var(--el-border-color); border-radius: 8px; padding: 12px 14px; background: var(--el-bg-color); }
.step7-form-head { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; justify-content: space-between; padding-bottom: 8px; border-bottom: 1px dashed var(--el-border-color-lighter); margin-bottom: 10px; }
.step7-form-title { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; }
.step7-form-l3 { font-weight: 600; font-size: 14px; color: var(--el-text-color-primary); }
.step7-form-meta { font-size: 12px; color: var(--el-text-color-regular); }
.step7-point-row { display: flex; flex-direction: column; gap: 6px; padding: 8px 10px; border-left: 3px solid var(--el-color-primary-light-5); background: var(--el-fill-color-blank); margin-bottom: 8px; border-radius: 0 4px 4px 0; }
.step7-point-head { display: flex; gap: 6px; align-items: center; }
.step7-point-key { display: inline-block; min-width: 26px; padding: 0 6px; height: 20px; line-height: 20px; text-align: center; font-size: 12px; font-weight: 600; color: var(--el-color-primary); background: var(--el-color-primary-light-9); border-radius: 3px; }
.step7-point-label { font-size: 13px; color: var(--el-text-color-primary); flex: 1; }
.step7-point-row2 { display: flex; gap: 8px; align-items: center; }
.step7-actions { display: flex; flex-wrap: wrap; gap: 10px; align-items: center; }
.step7-compare { border: 1px solid var(--el-border-color-light); border-radius: 6px; padding: 10px 12px; background: var(--el-fill-color-lighter); }
.step7-compare-title { font-weight: 600; font-size: 13px; margin-bottom: 8px; color: var(--el-text-color-primary); }
.step7-compare-list { display: grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); gap: 10px; }
.step7-compare-card { border: 1px solid var(--el-border-color-lighter); border-radius: 4px; background: var(--el-bg-color); padding: 8px 10px; display: flex; flex-direction: column; gap: 6px; }
.step7-compare-head { display: flex; justify-content: space-between; align-items: center; }
.step7-compare-body { max-height: 220px; overflow: auto; font-size: 12px; line-height: 1.5; padding: 6px 8px; background: var(--el-fill-color-light); border-radius: 4px; white-space: pre-wrap; word-break: break-word; }
.step7-compare-error { color: var(--el-color-danger); font-size: 12px; }
.step7-summary { display: flex; flex-direction: column; gap: 8px; }
.step7-stat-row { display: flex; flex-wrap: wrap; gap: 12px; }
.step7-stat-card { flex: 1; min-width: 140px; border: 1px solid var(--el-border-color-light); border-radius: 6px; padding: 10px 14px; text-align: center; background: var(--el-fill-color-lighter); }
.step7-stat-label { font-size: 12px; color: var(--el-text-color-secondary); margin-bottom: 4px; }
.step7-stat-value { font-size: 22px; font-weight: 700; color: var(--el-color-primary); }
.step7-md-preview { border: 1px solid var(--el-border-color-lighter); border-radius: 4px; padding: 10px 12px; max-height: 460px; overflow: auto; background: var(--el-bg-color); font-size: 13px; line-height: 1.65; }
.step7-md-preview :deep(table) { border-collapse: collapse; width: 100%; margin: 8px 0; }
.step7-md-preview :deep(th), .step7-md-preview :deep(td) { border: 1px solid var(--el-border-color); padding: 6px 8px; vertical-align: top; }
.step7-md-preview :deep(th) { background: var(--el-fill-color-light); font-weight: 600; }
.step7-export-bar { display: flex; flex-wrap: wrap; gap: 10px; align-items: center; }

@media (max-width: 1100px) { .layout { grid-template-columns: 1fr; } .upload-matrix { grid-template-columns: 1fr; } .step3-summary-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); } .gap-channel-grid { grid-template-columns: 1fr; } }
</style>
