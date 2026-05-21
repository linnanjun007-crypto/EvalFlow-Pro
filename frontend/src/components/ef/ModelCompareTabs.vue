<script setup lang="ts">
defineProps<{
  items: Array<{ label: string; content: string }>
}>()
</script>

<template>
  <section class="ef-card panel">
    <header class="head">
      <h3>多模型对比</h3>
      <el-tag size="small" type="warning">Tab / 分栏</el-tag>
    </header>
    <el-tabs type="border-card">
      <el-tab-pane v-for="item in items" :key="item.label" :label="item.label">
        <div class="content">{{ item.content }}</div>
      </el-tab-pane>
    </el-tabs>
  </section>
</template>

<style scoped>
.panel { padding: 14px; }
.head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
.head h3 { margin: 0; font-size: 15px; }
.content { min-height: 140px; white-space: pre-wrap; color: var(--ef-text-2); line-height: 1.6; }
</style>
