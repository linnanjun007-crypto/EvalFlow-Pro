<script setup lang="ts">
defineProps<{
  status: 'queued' | 'running' | 'succeeded' | 'failed' | 'canceled'
  percent: number
  doneSteps: number
  totalSteps: number
}>()
</script>

<template>
  <section class="ef-card panel">
    <header class="head">
      <h3>任务进度</h3>
      <el-tag size="small" :type="status === 'succeeded' ? 'success' : status === 'failed' ? 'danger' : 'info'">{{ status }}</el-tag>
    </header>
    <el-progress :percentage="percent" />
    <p class="desc">已完成 {{ doneSteps }} / {{ totalSteps }} 个步骤，进度来自后端实际保存的最终版本。</p>
  </section>
</template>

<style scoped>
.panel { padding: 14px; }
.head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
.head h3 { margin: 0; font-size: 15px; }
.desc { font-size: 12px; color: var(--ef-text-2); line-height: 1.5; margin: 10px 0 0; }
</style>
