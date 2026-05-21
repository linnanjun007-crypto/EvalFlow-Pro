<script setup lang="ts">
import PageHeader from '../../components/ef/PageHeader.vue'

const kpis = [
  { label: '今日活跃用户', value: '128', delta: '+12.4%' },
  { label: '今日生成次数', value: '2,436', delta: '+8.1%' },
  { label: '今日 Tokens', value: '9.8M', delta: '+6.7%' },
  { label: '失败率', value: '0.82%', delta: '-0.3%' },
]

const modules = [
  { title: '用户管理', desc: '账号开通、状态管理、重置密码与使用概览。' },
  { title: '模型配置', desc: '统一维护供应商、模型 ID、连通性与启停状态。' },
  { title: 'Prompt / 知识库', desc: '按 Step1-14 管理版本，支持发布与回滚。' },
  { title: '审计与统计', desc: '查看关键操作日志与用量趋势，满足可追溯要求。' },
]

const recentEvents = [
  '09:21 · 发布 Step7 Prompt v1.4',
  '10:05 · 新增财政局账号 3 个',
  '10:36 · 全量下载任务完成（用户组 A）',
  '11:12 · 模型连通性测试通过（GPT-4o）',
]
</script>

<template>
  <div class="dashboard-page">
    <PageHeader title="管理端概览" description="账号、模型、Prompt 与审计的统一控制台。" />

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
        <ul class="event-list">
          <li v-for="event in recentEvents" :key="event">{{ event }}</li>
        </ul>
      </article>
    </section>
  </div>
</template>

<style scoped>
.dashboard-page {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.kpi-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
}

.kpi-card {
  padding: 18px;
}

.kpi-label {
  margin: 0;
  font-size: 13px;
  color: var(--ef-text-2);
}

.kpi-value {
  margin: 10px 0 4px;
  font-size: 30px;
  font-weight: 700;
  color: var(--ef-text-1);
}

.kpi-delta {
  margin: 0;
  font-size: 12px;
  color: #16a34a;
}

.content-grid {
  display: grid;
  grid-template-columns: 1.5fr 1fr;
  gap: 12px;
}

.panel {
  padding: 18px;
}

.panel h3 {
  margin: 0 0 14px;
  font-size: 16px;
}

.module-list {
  display: grid;
  gap: 10px;
}

.module-item {
  border: 1px solid rgba(15, 23, 42, 0.08);
  border-radius: 12px;
  padding: 12px;
  background: rgba(248, 250, 252, 0.6);
}

.module-title {
  margin: 0;
  font-size: 14px;
  font-weight: 600;
}

.module-desc {
  margin: 6px 0 0;
  font-size: 13px;
  color: var(--ef-text-2);
  line-height: 1.5;
}

.event-list {
  margin: 0;
  padding-left: 18px;
  display: grid;
  gap: 10px;
  color: var(--ef-text-2);
  font-size: 13px;
}

@media (max-width: 1100px) {
  .kpi-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .content-grid {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 640px) {
  .kpi-grid {
    grid-template-columns: 1fr;
  }
}
</style>
