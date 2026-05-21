<template>
  <div class="page">
    <PageHeader title="使用分析" description="项目数、步骤生成数、下载量与活跃情况。" />
    <section class="ef-card card">
      <el-empty description="后端已预留统计接口，下一步可接真实图表。" />
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
