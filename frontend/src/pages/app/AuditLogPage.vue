<template>
  <div class="page">
    <PageHeader title="审计日志" description="记录登录、生成、导出、删除等关键操作。" />
    <section class="ef-card card">
      <el-empty description="当前后端先返回空列表，后续可接数据库审计表。" />
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
