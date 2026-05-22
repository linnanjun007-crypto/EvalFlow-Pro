# EvalFlow Pro — Step 接口契约文档

> **用途**：定义前端 ↔ 后端 ↔ LangGraph Agent 三方之间，每个 Step 的完整数据契约。  
> 所有并行开发的 Claude 实例必须严格遵循本文档，不得自行扩展或更改字段名。  
> 如需变更，先更新本文档并同步到 `tree/front/doc/`、`tree/back/doc/`、`tree/agent/doc/`。

---

## 公共调用模式

### 前端触发生成

前端统一调用 `POST /api/v1/agent/run`：

```typescript
interface AgentRunRequest {
  workflow_role: 'client'          // 用户端固定为 'client'
  step_code: string                // 'step1' ~ 'step14'
  payload: StepPayload             // 见各步骤定义
  context: AgentRunContext
}

interface AgentRunContext {
  project_id: string
  thread_id?: string               // step1: 'step1:{project_id}', step3: 'step3:{project_id}', 其他: undefined
  workflow_role: 'client'
  run_id: string                   // 格式: '{step_code}:{project_id}:{Date.now()}:{random}'
  model_provider?: string          // 主模型 provider
  model_name?: string              // 主模型名称
  model_names?: string[]           // 所有参与对比的模型名
}
```

**响应结构**：
```typescript
interface AgentRunResponse {
  role: string
  step_code: string
  result: StepResult               // 见各步骤定义
}
```

---

### 公共 payload 字段（所有 step 均含）

```typescript
interface BasePayload {
  project_id: string
  step_code: string                // 同路径参数
  title: string                    // 如 'Step1 · 项目资料清单'
  project_name: string
  run_id: string                   // 同 context.run_id
  model_configs: ModelConfig[]     // 启用的模型列表
  temperature: number              // 主模型温度
}

interface ModelConfig {
  model_name: string
  label?: string
  provider?: string
  channel?: string
  base_url?: string
  api_key?: string
  temperature: number
  supports_vision?: boolean
  enabled: boolean
}

interface ProjectFileRef {
  id: string
  file_name: string
  file_type: string
  storage_key: string
  parse_status: 'pending' | 'parsed' | 'failed'
}
```

---

### 工作流状态 `GET /api/v1/steps/status`

```typescript
// 响应（前端 WorkflowStatusResponse）
interface WorkflowStatusResponse {
  project_id: string
  total_steps: number              // 固定 14
  done_steps: number
  status: 'queued' | 'running' | 'succeeded' | 'failed' | 'canceled'
  progress: number                 // 0-100
  steps: StepStatusItem[]
}

interface StepStatusItem {
  step_code: string                // 'step1' ~ 'step14'
  status: 'not_found' | 'draft' | 'succeeded'
  done: boolean
  version?: number | null
  title?: string | null
}
```

---

## Step 1：项目资料清单

**标题**：`Step1 · 项目资料清单`  
**thread_id**：`step1:{project_id}`

### Payload

```typescript
interface Step1Payload extends BasePayload {
  step_code: 'step1'
  file_paths: string[]             // storage_key 或 file_name
  project_files: ProjectFileRef[]
  thread_id: string                // 'step1:{project_id}'
  has_step1_draft: boolean         // 是否已有草稿（用于续写模式）
  prompt?: string                  // 用户追加指令（可选）
}
```

### Result（Agent 返回 / DB 存储）

```typescript
interface Step1Result {
  status: 'human_review' | 'approved' | 'final'
  draft_manifest: string           // 草稿清单（Markdown）
  final_manifest: string           // 定稿清单（Markdown）
  review_mode: 'auto-approval' | 'manual' | 'modify'
  approved: boolean
  content_text: string             // 存入 DB 的最终文本，等同 final_manifest
  content_json?: string
  source?: 'chat_replace' | 'agent'
  updated_at?: string
}
```

---

## Step 2：有效项目资料 / 核心内容

**标题**：`Step2 · 有效项目资料`  
**thread_id**：`step2:{project_id}`

### Payload

```typescript
interface Step2Payload extends BasePayload {
  step_code: 'step2'
  file_paths: string[]
  media_file_paths: string[]       // 图片/PDF 文件路径
  text_doc_file_paths: string[]    // 纯文本/docx 文件路径
  project_files: ProjectFileRef[]
  review_mode: 'approve' | 'modify' | 'auto-approval'
  review_feedback: string          // review_mode === 'modify' 时非空，否则空字符串
  default_categories: string[]     // 启用的默认分类
  extra_categories: string[]       // 用户自定义分类（已过滤空值）
  verification_acknowledged: boolean
  final_core_content: string       // 有内容时传当前编辑器内容，否则空字符串
  thread_id: string
  prompt?: string
}
```

### Result

```typescript
interface Step2Result {
  status: 'draft' | 'human_review' | 'approved' | 'completed'
  core_content_draft: string       // 草稿核心内容
  final_core_content: string       // 定稿核心内容（前端编辑器以此为准）
  content_text: string             // 同 final_core_content，存入 DB

  model_comparisons: ModelComparison[]
  default_categories: string[]
  extra_categories: string[]
  verification_digest: string      // 文件验证摘要
  parse_warnings: string[]
  source_index: SourceIndexItem[]
  media_metadata: Record<string, unknown>[]
  text_doc_metadata: Record<string, unknown>[]
}

interface ModelComparison {
  model_name: string
  label?: string
  provider?: string
  channel?: string
  temperature?: number
  draft: string                    // 该模型生成的草稿
  error?: string                   // 调用失败时的错误信息
}

interface SourceIndexItem {
  ref_id: string
  source_name: string
  channel: string
  excerpt: string
}
```

---

## Step 3：指标体系

**标题**：`Step3 · 指标体系`  
**thread_id**：`step3:{project_id}`  
**特殊说明**：Step3 分两个阶段，`skeleton`（骨架生成）和 `generating_l3`（逐条生成三级指标）。  
前端通过 `step3SkeletonPhase` 区分当前阶段，并据此选择 `review_mode`。

### Payload

```typescript
interface Step3Payload extends BasePayload {
  step_code: 'step3'
  project_files: ProjectFileRef[]
  project_core_content: string     // 来自 Step2 的 final_core_content
  final_core_content: string       // 同上（冗余字段，两者保持一致）

  // 指标体系配置
  system_type: string              // 如 '综合绩效评价'
  indicator_depth: 3 | 4           // 指标层级深度
  import_mode: string              // 'ai_generate' | 'import_json' 等
  imported_indicator_json: string  // import_mode === 'import_json' 时使用
  template_id: string | null

  // 骨架优化配置
  skeleton_optimize_mode: string
  per_optimize_level2_name: string

  // 审核控制（骨架阶段）
  review_mode: 'approve' | 'modify' | 'auto-approval'
  review_feedback: string          // 骨架阶段反馈

  // L3 生成阶段（generating_l3 时使用）
  // review_mode 此时来自 step3L3ReviewMode
  // review_feedback 此时来自 step3L3Feedback（仅 modify 时非空）

  flat_l2_tasks: Step3L2Task[]     // 当前骨架任务列表（生成 L3 时传入）
  active_l2_index: number          // 当前正在生成 L3 的二级指标索引
  l3_active_draft: string          // 当前 L2 下已有的 L3 草稿

  prompt?: string
}

interface Step3L2Task {
  level1_name: string
  level2_name: string
  l3_section_markdown: string      // 该二级下已完成的三级指标 markdown，初始为空
  weight?: number
  [key: string]: unknown
}
```

### Result

```typescript
interface Step3Result {
  status:
    | 'skeleton_ready'             // 骨架生成完毕，等待进入 L3 阶段
    | 'l3_draft_ready'             // 当前 L2 的 L3 草稿已就绪
    | 'l3_refined'                 // L3 修改完成
    | 'l3_level_saved'             // 当前层级已保存
    | 'completed'                  // 全部指标生成完毕

  flat_l2_tasks: Step3L2Task[]
  active_l2_index: number
  l3_active_draft: string

  // 对比模式
  l3_comparisons: ModelComparison[]

  // 定稿内容（status === 'completed' 时有效）
  final_indicator_markdown: string // 全量 markdown，存入 DB 的 content_text
  content_text: string             // 同 final_indicator_markdown

  system_type: string
  indicator_depth: 3 | 4
}
```

---

## Step 4 ~ Step 14：通用模式

**Step 4-14 目前使用 `buildGenericAgentPayload`**，后续按需细化。

### Payload（通用）

```typescript
interface GenericStepPayload extends BasePayload {
  step_code: string                // 'step4' ~ 'step14'
  file_paths: string[]
  project_files: ProjectFileRef[]
  content_text: string             // 上一步骤的定稿内容（从编辑器传入）
  prompt?: string
}
```

### Result（通用）

```typescript
interface GenericStepResult {
  status: 'draft' | 'human_review' | 'completed'
  content_text: string             // 存入 DB 的文本
  content_json?: string
  model_comparisons?: ModelComparison[]
  [key: string]: unknown           // 各步骤扩展字段
}
```

### 已知标题映射

| step_code | title |
|-----------|-------|
| step1 | Step1 · 项目资料清单 |
| step2 | Step2 · 有效项目资料 |
| step3 | Step3 · 指标体系 |
| step4 | Step4 · 生成分值 |
| step5 | Step5 · 评分标准 |
| step14 | Step14 · 评价报告 |
| step6~step13 | `Step{N} · （待定）` |

---

## `GET /api/v1/steps/{step_code}/result` 按步骤返回结构

后端 `result` 字段内容由各步骤决定，对应上方各 Result 类型：

| step_code | result 类型 |
|-----------|------------|
| step1 | `Step1Result` |
| step2 | `Step2Result` |
| step3 | `Step3Result` |
| step4~step14 | `GenericStepResult` |

---

## `POST /api/v1/agent/run` 后端处理规范

后端接收 `AgentRunRequest` 后：

1. 从 `context.project_id` 验证项目归属
2. 根据 `workflow_role` + `step_code` 路由到对应 LangGraph graph
3. 将 `payload` + `context` 合并为 graph state 传入
4. graph 执行完毕后，将 `result` 原样返回前端
5. **不**在此接口保存 DB；保存由前端主动调用 `POST /steps/{step_code}/save` 触发

---

## 取消运行

```
POST /api/v1/agent/runs/{run_id}/cancel
```

响应：
```typescript
{ run_id: string; cancelled: boolean; status: string }
```

---

**版本**：v1.1  
**最后更新**：2026-05-22  
**维护方式**：三路并行开发期间，任何字段变更须同步更新本文档并通知其他分支。
