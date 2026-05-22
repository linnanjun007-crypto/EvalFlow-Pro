<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import PageHeader from '../../components/ef/PageHeader.vue'
import { getDashboardStats, type DashboardStats } from '../../services/admin'

const stats = ref<DashboardStats | null>(null)
const loading = ref(false)

async function refresh() {
  loading.value = true
  try {
    stats.value = await getDashboardStats()
  } finally {
    loading.value = false
  }
}

const kpis = computed(() => {
  const s = stats.value
  if (!s) return []
  const fmt = (n: number) => n.toLocaleString('zh-CN')
  const successRate = s.tasks.total ? (100 - s.tasks.failure_rate).toFixed(2) + '%' : '—'
  return [
    { label: '注册用户', value: fmt(s.users.total), delta: `活跃 ${fmt(s.users.active)}` },
    { label: '项目总数', value: fmt(s.projects), delta: '所有用户' },
    { label: 'LLM 调用', value: fmt(s.llm_calls), delta: `Tokens ${fmt(s.total_tokens)}` },
    { label: '任务成功率', value: successRate, delta: `失败 ${fmt(s.tasks.failed)} / ${fmt(s.tasks.total)}` },
  ]
})

const modules = [
  { title: '用户管理', desc: '账号开通、状态管理、重置密码与使用概览。' },
  { title: '模型配置', desc: '统一维护供应商、模型 ID、连通性与启停状态。' },
  { title: 'Prompt / 知识库', desc: '按 Step1-14 管理版本，支持发布与回滚。' },
  { title: '审计与统计', desc: '查看关键操作日志与用量趋势，满足可追溯要求。' },
]

function formatTime(value?: string | null) {
  if (!value) return ''
  const d = new Date(value)
  if (Number.isNaN(d.getTime())) return value
  return d.toLocaleString('zh-CN', { hour12: false })
}

function eventLine(item: DashboardStats['recent_events'][number]) {
  const time = formatTime(item.created_at)
  const summary = item.summary || `${item.action} · ${item.target_type}`
  return time ? `${time} · ${summary}` : summary
}

onMounted(refresh)
</script>

<template>
  <div class="dashboard-page" v-loading="loading">
    <PageHeader title="管理端概览" description="账号、模型、Prompt 与审计的统一控制台。">
      <template #actions>
        <el-button @click="refresh">刷新</el-button>
      </template>
    </PageHeader>

    <section class="kpi-grid">
      <article v-for="item in kpis" :key="item.label" class="ef-card kpi-card">
        <p class="kpi-label">{{ item.label }}</p>
        <p class="kpi-value">{{ item.value }}</p>
        <p class="kpi-delta">{{ item.delta }}</p>
      </article>
    </section>

    <section class="content-grid">
      <article class="ef-card panel">
        <h3>核心模块</h3>
        <div class="module-list">
          <div v-for="module in modules" :key="module.title" class="module-item">
            <p class="module-title">{{ module.title }}</p>
            <p class="module-desc">{{ module.desc }}</p>
          </div>
        </div>
      </article>

      <article class="ef-card panel">
        <h3>最近动态</h3>
        <el-empty v-if="!stats?.recent_events?.length" description="暂无操作记录" />
        <ul v-else class="event-list">
          <li v-for="event in stats.recent_events" :key="event.id">{{ eventLine(event) }}</li>
        </ul>
      </article>
    </section>
  </div>
</template>

<style scoped>
.dashboard-page { display: flex; flex-direction: column; gap: 16px; }
.kpi-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; }
.kpi-card { padding: 18px; }
.kpi-label { margin: 0; font-size: 13px; color: var(--ef-text-2); }
.kpi-value { margin: 10px 0 4px; font-size: 30px; font-weight: 700; color: var(--ef-text-1); }
.kpi-delta { margin: 0; font-size: 12px; color: #64748b; }
.content-grid { display: grid; grid-template-columns: 1.5fr 1fr; gap: 12px; }
.panel { padding: 18px; }
.panel h3 { margin: 0 0 14px; font-size: 16px; }
.module-list { display: grid; gap: 10px; }
.module-item { border: 1px solid rgba(15, 23, 42, 0.08); border-radius: 12px; padding: 12px; background: rgba(248, 250, 252, 0.6); }
.module-title { margin: 0; font-size: 14px; font-weight: 600; }
.module-desc { margin: 6px 0 0; font-size: 13px; color: var(--ef-text-2); line-height: 1.5; }
.event-list { margin: 0; padding-left: 18px; display: grid; gap: 10px; color: var(--ef-text-2); font-size: 13px; }
@media (max-width: 1100px) {
  .kpi-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .content-grid { grid-template-columns: 1fr; }
}
@media (max-width: 640px) {
  .kpi-grid { grid-template-columns: 1fr; }
}
</style>
