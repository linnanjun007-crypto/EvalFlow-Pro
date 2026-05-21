<template>
  <div class="page">
    <PageHeader title="全局下载" description="从项目级导出包汇总到全局下载中心。" />
    <section class="ef-card card">
      <el-empty description="当前复用导出任务列表，后续可按项目筛选。" />
    </section>
  </div>
</template>

<script setup lang="ts">
import PageHeader from '../../components/ef/PageHeader.vue'
</script>

<style scoped>
.page { display: grid; gap: 12px; }
.card { padding: 14px; }
</style>
