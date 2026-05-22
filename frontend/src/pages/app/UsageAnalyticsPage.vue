<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import PageHeader from '../../components/ef/PageHeader.vue'
import { getUsageSummary, type UsageSummary } from '../../services/usage'

const data = ref<UsageSummary | null>(null)
const loading = ref(false)

async function refresh() {
  loading.value = true
  try {
    data.value = await getUsageSummary()
  } finally {
    loading.value = false
  }
}

const stepMax = computed(() => {
  const calls = data.value?.by_step.map((it) => it.calls) || []
  return Math.max(1, ...calls)
})

function formatNumber(n: number | undefined) {
  if (n == null) return '—'
  return n.toLocaleString('zh-CN')
}

onMounted(refresh)
</script>

<template>
  <div class="page" v-loading="loading">
    <PageHeader title="使用分析" description="个人项目数、步骤生成数、LLM 调用与 token 消耗的统计。">
      <template #actions>
        <el-button @click="refresh">刷新</el-button>
      </template>
    </PageHeader>

    <section class="kpi-grid" v-if="data">
      <div class="ef-card kpi">
        <div class="kpi-label">项目总数</div>
        <div class="kpi-value">{{ formatNumber(data.projects.total) }}</div>
        <div class="kpi-foot">活跃 {{ formatNumber(data.projects.active) }}</div>
      </div>
      <div class="ef-card kpi">
        <div class="kpi-label">已生成步骤</div>
        <div class="kpi-value">{{ formatNumber(data.steps_generated) }}</div>
        <div class="kpi-foot">材料 {{ formatNumber(data.files) }}</div>
      </div>
      <div class="ef-card kpi">
        <div class="kpi-label">LLM 调用</div>
        <div class="kpi-value">{{ formatNumber(data.llm.calls) }}</div>
        <div class="kpi-foot">平均延时 {{ formatNumber(data.llm.avg_latency_ms) }} ms</div>
      </div>
      <div class="ef-card kpi">
        <div class="kpi-label">Token 总消耗</div>
        <div class="kpi-value">{{ formatNumber(data.llm.total_tokens) }}</div>
        <div class="kpi-foot">
          输入 {{ formatNumber(data.llm.prompt_tokens) }} / 输出 {{ formatNumber(data.llm.completion_tokens) }}
        </div>
      </div>
      <div class="ef-card kpi">
        <div class="kpi-label">任务成功率</div>
        <div class="kpi-value">
          {{ data.tasks.total ? (100 - data.tasks.failure_rate).toFixed(1) + '%' : '—' }}
        </div>
        <div class="kpi-foot">
          总 {{ formatNumber(data.tasks.total) }} · 失败 {{ formatNumber(data.tasks.failed) }}
        </div>
      </div>
    </section>

    <section class="ef-card card" v-if="data">
      <div class="card-title">按步骤分布</div>
      <el-empty v-if="!data.by_step.length" description="暂无调用记录" />
      <div v-else class="bar-list">
        <div class="bar-row" v-for="row in data.by_step" :key="row.step_code">
          <div class="bar-name">{{ row.step_code }}</div>
          <div class="bar-track">
            <div class="bar-fill" :style="{ width: `${(row.calls / stepMax) * 100}%` }" />
          </div>
          <div class="bar-meta">
            <span>{{ formatNumber(row.calls) }} 次</span>
            <span class="bar-tokens">{{ formatNumber(row.total_tokens) }} tok</span>
          </div>
        </div>
      </div>
    </section>

    <section class="ef-card card" v-if="data">
      <div class="card-title">按模型分布</div>
      <el-empty v-if="!data.by_model.length" description="暂无调用记录" />
      <el-table v-else :data="data.by_model" stripe>
        <el-table-column prop="model_name" label="模型" />
        <el-table-column prop="calls" label="调用次数" align="right" width="120">
          <template #default="{ row }">{{ formatNumber(row.calls) }}</template>
        </el-table-column>
        <el-table-column prop="total_tokens" label="Token 总数" align="right" width="160">
          <template #default="{ row }">{{ formatNumber(row.total_tokens) }}</template>
        </el-table-column>
      </el-table>
    </section>
  </div>
</template>

<style scoped>
.page { display: grid; gap: 12px; }
.kpi-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 12px; }
.kpi { padding: 16px; }
.kpi-label { color: #64748b; font-size: 13px; }
.kpi-value { font-size: 26px; font-weight: 700; color: #0f172a; margin: 6px 0 4px; }
.kpi-foot { color: #94a3b8; font-size: 12px; }
.card { padding: 16px; }
.card-title { font-weight: 600; color: #0f172a; margin-bottom: 12px; }
.bar-list { display: flex; flex-direction: column; gap: 10px; }
.bar-row { display: grid; grid-template-columns: 70px 1fr 160px; align-items: center; gap: 12px; }
.bar-name { color: #475569; font-size: 13px; }
.bar-track { background: #f1f5f9; border-radius: 999px; height: 10px; overflow: hidden; }
.bar-fill { background: linear-gradient(90deg, #6366f1, #8b5cf6); height: 100%; border-radius: 999px; }
.bar-meta { display: flex; justify-content: flex-end; gap: 12px; font-size: 12px; color: #475569; }
.bar-tokens { color: #94a3b8; }
</style>
