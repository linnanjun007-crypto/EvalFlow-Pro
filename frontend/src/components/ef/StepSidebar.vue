<script setup lang="ts">
defineProps<{
  steps: Array<{ id: number; title: string; done?: boolean }>
  activeStep: number
}>()

const emit = defineEmits<{ (e: 'select', stepId: number): void }>()
</script>

<template>
  <aside class="ef-card sidebar">
    <div class="hd">14 步流程</div>
    <button
      v-for="step in steps"
      :key="step.id"
      type="button"
      class="item"
      :class="{ active: step.id === activeStep }"
      @click="emit('select', step.id)"
    >
      <span>Step {{ step.id }}</span>
      <el-tag v-if="step.done" size="small" type="success">完成</el-tag>
    </button>
  </aside>
</template>

<style scoped>
.sidebar { padding: 12px; }
.hd { font-size: 12px; color: var(--ef-text-2); margin-bottom: 8px; }
.item {
  width: 100%; display: flex; justify-content: space-between; align-items: center;
  border: 0; background: transparent; padding: 8px 10px; border-radius: 8px; cursor: pointer; margin-bottom: 4px;
}
.item:hover { background: #f1f5f9; }
.item.active { background: #e0ecff; color: #1d4ed8; font-weight: 600; }
</style>
