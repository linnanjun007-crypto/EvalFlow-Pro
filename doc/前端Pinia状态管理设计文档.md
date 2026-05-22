# EvalFlow Pro 前端状态管理文档

> 本文档说明前端 Pinia 状态管理的设计，包括现有 stores、数据流、使用示例和扩展指南。
>
> 框架：Vue 3 + TypeScript + Pinia + Vite

---

## 目录

1. [Pinia 集成概览](#pinia-集成概览)
2. [现有 Stores](#现有-stores)
3. [推荐 Store 设计](#推荐-store-设计)
4. [使用示例](#使用示例)
5. [扩展指南](#扩展指南)

---

## Pinia 集成概览

**文件位置**：`frontend/src/stores/`

**入口文件**：`frontend/src/main.ts`

```typescript
import { createPinia } from 'pinia'

const pinia = createPinia()
app.use(pinia)
```

**全局使用**：
```typescript
import { useAuthStore } from '@/stores/auth'

const authStore = useAuthStore()
```

---

## 现有 Stores

### 1. useAuthStore - 认证状态

**文件路径**：`frontend/src/stores/auth.ts`

**职责**：
- 管理用户登录/注册
- 维护 Token 和用户信息
- 提供登出功能

**State 定义**：
```typescript
{
  user: UserResponse | null        // 当前用户信息
  token: string                    // Bearer token（格式: "user:<user_id>"）
}
```

**Getters**：
```typescript
isLoggedIn: boolean               // 是否已登录（token 非空）
```

**Actions**：
```typescript
login(payload: {
  username: string
  password: string
}): Promise<TokenResponse>        // 登录，返回 token

register(payload: {
  username: string
  password: string
}): Promise<UserResponse>         // 注册

loadMe(): Promise<UserResponse | null>  // 加载当前用户信息

logout(): void                    // 登出，清空 token 和用户信息
```

**持久化**：
- Token 保存在 `localStorage` 的 `ef_token` 键中
- 页面刷新时自动恢复 token

**示例用法**：
```typescript
<script setup lang="ts">
import { useAuthStore } from '@/stores/auth'

const authStore = useAuthStore()

// 登录
await authStore.login({ username: 'john', password: 'pass123' })

// 检查是否登录
if (authStore.isLoggedIn) {
  console.log('当前用户:', authStore.user)
}

// 登出
authStore.logout()
</script>
```

---

## 推荐 Store 设计

基于项目业务需求，建议补充以下 stores：

### 1. useProjectStore - 项目管理

**文件路径**：`frontend/src/stores/project.ts`

**State**：
```typescript
{
  projects: Array<{
    id: string
    name: string
    description: string | null
    status: 'active' | 'archived' | 'deleted'
    created_at: string
    updated_at: string
  }>
  currentProject: Project | null  // 当前打开的项目
  loading: boolean
  error: string | null
}
```

**Actions**：
```typescript
async fetchProjects(): Promise<void>
async createProject(data: {
  name: string
  description?: string
}): Promise<Project>

async getProject(projectId: string): Promise<Project>

async updateProject(projectId: string, data: {
  name?: string
  description?: string
  status?: string
}): Promise<Project>

async deleteProject(projectId: string): Promise<void>

setCurrentProject(project: Project): void
```

**Getters**：
```typescript
projectCount: number
activeProjects: Project[]
```

**示例实现**：
```typescript
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { fetchProjects, createProject, ... } from '@/services/api'

export const useProjectStore = defineStore('project', () => {
  const projects = ref<Project[]>([])
  const currentProject = ref<Project | null>(null)
  const loading = ref(false)
  const error = ref<string | null>(null)

  const projectCount = computed(() => projects.value.length)
  const activeProjects = computed(() =>
    projects.value.filter(p => p.status === 'active')
  )

  async function loadProjects() {
    loading.value = true
    try {
      const data = await fetchProjects()
      projects.value = data.items
      error.value = null
    } catch (err) {
      error.value = String(err)
    } finally {
      loading.value = false
    }
  }

  async function createNewProject(input: {
    name: string
    description?: string
  }) {
    loading.value = true
    try {
      const project = await createProject(input)
      projects.value.push(project)
      return project
    } finally {
      loading.value = false
    }
  }

  return {
    projects,
    currentProject,
    loading,
    error,
    projectCount,
    activeProjects,
    loadProjects,
    createNewProject,
  }
})
```

---

### 2. useWorkflowStore - 工作流状态

**职责**：管理 14 步工作流的进度、当前步骤、生成结果

**State**：
```typescript
{
  currentProjectId: string | null
  currentStepCode: string | null
  workflowStatus: {
    current_step: string
    completed_steps: string[]
    in_progress_steps: string[]
    failed_steps: string[]
    overall_progress: number
    last_update: string
  } | null
  stepResults: Map<string, StepOutput>  // 缓存各步骤输出
  taskQueue: Array<{
    task_id: string
    step_code: string
    status: 'queued' | 'running' | 'success' | 'failed'
    progress: number
  }>
  loading: boolean
}
```

**Actions**：
```typescript
async fetchWorkflowStatus(projectId: string): Promise<void>
async generateStep(
  projectId: string,
  stepCode: string,
  payload: any
): Promise<string>  // 返回 task_id

async getStepResult(
  projectId: string,
  stepCode: string
): Promise<StepOutput>

async saveStepResult(
  projectId: string,
  stepCode: string,
  output: StepOutput
): Promise<void>

setCurrentStep(stepCode: string): void
cacheStepResult(stepCode: string, result: StepOutput): void
```

**Getters**：
```typescript
isWorkflowComplete: boolean
currentProgress: number
completedStepsCount: number
```

---

### 3. useFileStore - 文件管理

**职责**：管理项目的上传文件

**State**：
```typescript
{
  files: Map<string, FileRecord[]>  // projectId -> files
  uploading: Map<string, {
    progress: number
    status: 'idle' | 'uploading' | 'success' | 'error'
  }>
}
```

**Actions**：
```typescript
async uploadFile(
  projectId: string,
  file: File
): Promise<FileRecord>

async listFiles(projectId: string): Promise<FileRecord[]>

async deleteFile(projectId: string, fileId: string): Promise<void>

setUploadProgress(fileId: string, progress: number): void
```

---

### 4. useAdminStore - 管理端状态

**职责**：仅 admin 用户使用，管理 Prompt、知识库、模型配置

**State**：
```typescript
{
  prompts: Map<string, PromptVersion[]>  // stepCode -> prompts
  kbs: Map<string, KbVersion[]>          // stepCode -> kbs
  models: ModelConfig[]
  selectedStep: string | null            // 当前编辑的步骤
  
  editingPrompt: {
    title: string
    content: string
    isDirty: boolean
  } | null
}
```

**Actions**：
```typescript
async loadPrompts(stepCode?: string): Promise<void>
async savePrompt(
  stepCode: string,
  title: string,
  content: string
): Promise<void>

async loadModels(): Promise<void>
async toggleModel(modelId: string, enabled: boolean): Promise<void>

selectStep(stepCode: string): void
setEditingPrompt(data: any): void
```

---

### 5. useChatStore - 对话历史

**职责**：管理与 AI 的多轮对话

**State**：
```typescript
{
  conversations: Map<string, Conversation>  // conversationId -> conversation
  currentConversation: Conversation | null
  messages: ChatMessage[]
  loading: boolean
}
```

**Actions**：
```typescript
async sendMessage(
  projectId: string,
  stepCode: string,
  message: string
): Promise<ChatMessage>

async loadConversation(conversationId: string): Promise<void>

async loadMessages(conversationId: string): Promise<void>

createNewConversation(
  projectId: string,
  stepCode: string
): Promise<Conversation>
```

---

## 使用示例

### 在组件中使用

**选项式 API**：
```vue
<template>
  <div v-if="authStore.isLoggedIn">
    <p>欢迎 {{ authStore.user?.username }}</p>
    <button @click="logout">登出</button>
  </div>
</template>

<script lang="ts">
import { defineComponent } from 'vue'
import { useAuthStore } from '@/stores/auth'

export default defineComponent({
  setup() {
    const authStore = useAuthStore()

    const logout = () => {
      authStore.logout()
      // 导航到登录页
    }

    return { authStore, logout }
  },
})
</script>
```

**组合式 API** (推荐)：
```vue
<template>
  <div v-if="authStore.isLoggedIn">
    <p>欢迎 {{ authStore.user?.username }}</p>
    <button @click="logout">登出</button>
  </div>
</template>

<script setup lang="ts">
import { useAuthStore } from '@/stores/auth'

const authStore = useAuthStore()

const logout = () => {
  authStore.logout()
}
</script>
```

### 在中间件/守卫中使用

**路由守卫** (`frontend/src/router/index.ts`)：
```typescript
import { useAuthStore } from '@/stores/auth'

router.beforeEach(async (to, from, next) => {
  const authStore = useAuthStore()

  // 如果需要认证且用户未登录
  if (to.meta.requiresAuth && !authStore.isLoggedIn) {
    next('/login')
    return
  }

  // 如果需要 admin 权限
  if (to.meta.requiresAdmin && authStore.user?.role !== 'admin') {
    next('/forbidden')
    return
  }

  next()
})
```

### 跨 Store 通信

```typescript
// 例：用户登录后自动加载项目列表
import { useAuthStore } from '@/stores/auth'
import { useProjectStore } from '@/stores/project'

async function handleLogin() {
  const authStore = useAuthStore()
  const projectStore = useProjectStore()

  await authStore.login({ username, password })

  // 登录成功后，加载项目列表
  if (authStore.isLoggedIn) {
    await projectStore.loadProjects()
  }
}
```

---

## 扩展指南

### 创建新 Store 的步骤

#### 1. 定义 TypeScript 类型

创建 `frontend/src/types/models.ts`：

```typescript
export interface Project {
  id: string
  name: string
  description: string | null
  status: 'active' | 'archived' | 'deleted'
  created_at: string
  updated_at: string
}

export interface StepOutput {
  id: string
  project_id: string
  step_code: string
  title: string
  content_text: string
  content_json: string
  version: number
  is_final: boolean
  model_name: string
}
```

#### 2. 创建 Store 文件

创建 `frontend/src/stores/yourstore.ts`：

```typescript
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

export const useYourStore = defineStore('yourstore', () => {
  // State
  const data = ref<any[]>([])
  const loading = ref(false)

  // Getters
  const count = computed(() => data.value.length)

  // Actions
  async function load() {
    loading.value = true
    try {
      const response = await fetch('/api/v1/endpoint')
      data.value = await response.json()
    } finally {
      loading.value = false
    }
  }

  return {
    data,
    loading,
    count,
    load,
  }
})
```

#### 3. 导出 Store

编辑 `frontend/src/stores/index.ts`：

```typescript
export { useAuthStore } from './auth'
export { useYourStore } from './yourstore'
```

#### 4. 在组件中使用

```typescript
import { useYourStore } from '@/stores'

const yourStore = useYourStore()
```

---

## 最佳实践

### 1. 状态设计原则

- **细粒度**：每个 store 负责一个业务域（auth、project、workflow 等）
- **单一职责**：不在一个 store 中混合多个无关的功能
- **规范化**：使用 Map 或对象存储复杂数据，便于快速查找

### 2. 异步操作处理

```typescript
// ✅ 好的做法：在 action 中管理 loading、error
async function fetchData() {
  loading.value = true
  error.value = null
  try {
    const result = await api.getData()
    data.value = result
  } catch (err) {
    error.value = String(err)
  } finally {
    loading.value = false
  }
}

// ❌ 避免：在组件中管理状态
// 这会导致大量重复代码
```

### 3. 缓存策略

```typescript
const cache = new Map<string, { data: any; timestamp: number }>()
const CACHE_DURATION = 5 * 60 * 1000  // 5 分钟

async function loadCachedData(key: string) {
  const cached = cache.get(key)
  if (cached && Date.now() - cached.timestamp < CACHE_DURATION) {
    return cached.data
  }

  const data = await api.fetchData(key)
  cache.set(key, { data, timestamp: Date.now() })
  return data
}
```

### 4. 类型安全

始终为 state、getters 和 actions 定义完整的类型：

```typescript
// ✅ 好的做法
const users = ref<User[]>([])

async function addUser(user: User): Promise<void> {
  users.value.push(user)
}

// ❌ 避免
const users = ref<any[]>([])

async function addUser(user: any): Promise<any> {
  users.value.push(user)
}
```

### 5. 避免 Store 间的循环依赖

如果 StoreA 依赖 StoreB，不要让 StoreB 反向依赖 StoreA。使用事件或中间层解耦。

---

## 性能优化建议

### 1. 使用 Computed 减少重新渲染

```typescript
// ✅ 推荐：使用 computed 缓存衍生数据
const activeUsers = computed(() =>
  users.value.filter(u => u.status === 'active')
)

// ❌ 避免：在模板中过滤
<!-- 每次渲染都会重新过滤 -->
<div v-for="u in users.filter(...)">
```

### 2. 按需加载

```typescript
async function loadUserIfNeeded(userId: string) {
  if (users.get(userId)) {
    return  // 已经加载过，不重复请求
  }
  const user = await api.fetchUser(userId)
  users.set(userId, user)
}
```

### 3. 批量操作

```typescript
// ✅ 推荐：合并多个更新为一个 action
async function loadProjectWithDetails(projectId: string) {
  const [project, files, steps] = await Promise.all([
    api.getProject(projectId),
    api.listFiles(projectId),
    api.getWorkflowStatus(projectId),
  ])
  
  // 一次性更新
  currentProject.value = project
  projectFiles.value = files
  workflowStatus.value = steps
}
```

---

## 调试 Store

### 在浏览器控制台中使用

```javascript
// 在浏览器控制台直接访问 store
const { useAuthStore } = await import('/src/stores/auth.js')
const auth = useAuthStore()
console.log(auth.$state)  // 查看完整 state
```

### Vue DevTools

安装 [Vue DevTools](https://devtools.vuejs.org/) 扩展，可以在浏览器中可视化查看所有 store 状态变化。

---

## 迁移到推荐 Stores

### Timeline

1. **第 1-2 周**：实现 `useProjectStore` 和 `useFileStore`
2. **第 2-3 周**：实现 `useWorkflowStore` 和 `useChatStore`
3. **第 3-4 周**：实现 `useAdminStore`
4. **第 4+ 周**：优化和性能调试

### 检查清单

- [ ] 类型定义完整
- [ ] 所有 action 都有错误处理
- [ ] loading 和 error 状态管理到位
- [ ] 组件已从局部 state 迁移到 store
- [ ] 路由守卫已集成 store
- [ ] 单元测试覆盖率 > 80%

---

**文档版本**：v1.0  
**最后更新**：2026-05-22
