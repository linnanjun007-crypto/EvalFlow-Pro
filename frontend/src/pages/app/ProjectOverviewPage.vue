<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import PageHeader from '../../components/ef/PageHeader.vue'
import { getProject, type ProjectResponse } from '../../services/projects'
import { getWorkflowStatus, type WorkflowStatusResponse } from '../../services/steps'

const route = useRoute()
const router = useRouter()
const projectId = computed(() => String(route.params.projectId ?? ''))
const project = ref<ProjectResponse | null>(null)
const workflowStatus = ref<WorkflowStatusResponse | null>(null)
const loading = ref(false)

const progress = computed(() => workflowStatus.value?.progress ?? 0)
const doneSteps = computed(() => workflowStatus.value?.done_steps ?? 0)
const totalSteps = computed(() => workflowStatus.value?.total_steps ?? 14)
const progressStatus = computed(() => {
  if (!workflowStatus.value) return 'warning'
  if (workflowStatus.value.status === 'succeeded') return 'success'
  if (workflowStatus.value.status === 'failed') return 'exception'
  return doneSteps.value > 0 ? 'warning' : 'exception'
})
const progressText = computed(() => {
  if (!workflowStatus.value) return '暂无真实流程数据，先从 Step1 开始'
  const current = workflowStatus.value.steps.find((item) => !item.done)
  const currentStep = current ? current.step_code.replace('step', '') : totalSteps.value
  return `已完成 ${doneSteps.value}/${totalSteps.value} 步，当前建议继续 Step ${currentStep}`
})

async function refresh() {
  loading.value = true
  try {
    project.value = await getProject(projectId.value)
    workflowStatus.value = await getWorkflowStatus(projectId.value)
  } catch {
    project.value = null
    workflowStatus.value = null
  } finally {
    loading.value = false
  }
}

function goWorkflow(step: number) {
  router.push(`/app/projects/${projectId.value}/workflow/${step}`)
}

watch(projectId, refresh, { immediate: true })
onMounted(refresh)
</script>

<template>
  <div class="page">
    <PageHeader :title="`项目总览 · ${projectId}`" description="项目基本信息、流程进度、近期产物与任务入口。">
      <template #actions>
        <el-button type="primary" @click="goWorkflow(1)">进入工作台</el-button>
        <el-button @click="router.push('/app/history')">查看历史</el-button>
        <el-button @click="router.push('/app/downloads')">导出</el-button>
      </template>
    </PageHeader>

    <section class="grid">
      <article class="ef-card block">
        <h2 class="h">基本信息</h2>
        <el-skeleton v-if="loading" :rows="4" animated />
        <el-descriptions v-else :column="1" border>
          <el-descriptions-item label="项目 ID">{{ project?.id || projectId }}</el-descriptions-item>
          <el-descriptions-item label="项目名称">{{ project?.name || '-' }}</el-descriptions-item>
          <el-descriptions-item label="状态">{{ project?.status || 'unknown' }}</el-descriptions-item>
          <el-descriptions-item label="描述">{{ project?.description || '-' }}</el-descriptions-item>
        </el-descriptions>
      </article>

      <article class="ef-card block">
        <h2 class="h">14 步进度</h2>
        <el-skeleton v-if="loading" :rows="2" animated />
        <template v-else>
          <el-progress :percentage="progress" :stroke-width="10" :status="progressStatus" />
          <p class="tip">{{ progressText }}</p>
          <el-button type="primary" @click="goWorkflow(Number((workflowStatus?.steps.find((item) => !item.done)?.step_code || 'step1').replace('step', ''))) ">继续下一步</el-button>
        </template>
      </article>

      <article class="ef-card block wide">
        <h2 class="h">近期产物 / 任务</h2>
        <el-table v-if="workflowStatus?.steps?.length" :data="workflowStatus.steps" size="small">
          <el-table-column prop="step_code" label="步骤" width="90" />
          <el-table-column prop="title" label="标题" min-width="180">
            <template #default="{ row }">
              {{ row.title || `Step ${row.step_code.replace('step', '')}` }}
            </template>
          </el-table-column>
          <el-table-column prop="status" label="状态" width="110" />
          <el-table-column prop="version" label="版本" width="90" />
          <el-table-column label="操作" width="120">
            <template #default="{ row }">
              <el-button size="small" type="primary" plain @click="goWorkflow(Number(row.step_code.replace('step', ''))) ">进入</el-button>
            </template>
          </el-table-column>
        </el-table>
        <el-empty v-else description="暂无真实步骤数据" />
      </article>
    </section>
  </div>
</template>

<style scoped>
.page { display: grid; gap: 12px; }
.grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 12px; }
.block { padding: 16px; }
.h { margin: 0 0 12px; font-size: 15px; font-weight: 650; }
.tip { margin: 10px 0 14px; font-size: 13px; color: var(--ef-text-2); }
.wide { grid-column: 1 / -1; }
@media (max-width: 900px) { .grid { grid-template-columns: 1fr; } }
</style>
