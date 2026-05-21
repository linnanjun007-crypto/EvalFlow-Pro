<script setup lang="ts">
const props = defineProps<{
  title?: string
  loading?: boolean
}>()

const emit = defineEmits<{
  (e: 'generate'): void
  (e: 'stop'): void
}>()
</script>

<template>
  <section class="ef-card panel">
    <header class="head">
      <h3>{{ props.title ?? '生成区' }}</h3>
    </header>

    <div class="ops">
      <el-button type="primary" :loading="props.loading" @click="emit('generate')">生成</el-button>
      <el-button type="danger" plain :disabled="!props.loading" @click="emit('stop')">停止</el-button>
    </div>
  </section>
</template>

<style scoped>
.panel { padding: 14px; }
.head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px; }
.head h3 { margin: 0; font-size: 15px; }
.ops { display: flex; gap: 8px; }
</style>
