<script setup lang="ts">
import PageHeader from '../../components/ef/PageHeader.vue'

const stats = [
  { label: '平均 tokens', value: '3.4M' },
  { label: '平均耗时', value: '42s' },
  { label: '成功率', value: '99.2%' },
]
</script>

<template>
  <div class="page">
    <PageHeader title="用量统计" description="按用户 / 项目 / 步骤 / 模型查看 tokens、耗时与成功率。" />

    <section class="grid">
      <article v-for="stat in stats" :key="stat.label" class="ef-card stat">
        <p class="label">{{ stat.label }}</p>
        <p class="value">{{ stat.value }}</p>
      </article>
    </section>

    <section class="ef-card card">
      <div class="placeholder">统计图表区域（后续可接 ECharts）。</div>
    </section>
  </div>
</template>

<style scoped>
.page { display: grid; gap: 12px; }
.grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; }
.stat { padding: 16px; }
.label { margin: 0; color: var(--ef-text-2); font-size: 13px; }
.value { margin: 10px 0 0; font-size: 28px; font-weight: 700; }
.card { padding: 14px; }
.placeholder { min-height: 280px; border: 1px dashed var(--ef-border); border-radius: 10px; display: grid; place-items: center; color: var(--ef-text-2); }
@media (max-width: 900px) { .grid { grid-template-columns: 1fr; } }
</style>
