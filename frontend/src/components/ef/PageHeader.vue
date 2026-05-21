<script setup lang="ts">
defineProps<{
  title: string
  description?: string
}>()
</script>

<template>
  <header class="page-header">
    <div class="text">
      <h1 class="title ef-heading">{{ title }}</h1>
      <p v-if="description" class="desc ef-muted">{{ description }}</p>
    </div>
    <div v-if="$slots.actions" class="actions">
      <slot name="actions" />
    </div>
  </header>
</template>

<style scoped>
.page-header {
  display: flex;
  flex-wrap: wrap;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px 20px;
  margin-bottom: 18px;
}

.title {
  margin: 0;
  font-size: 20px;
  font-weight: 650;
  letter-spacing: -0.2px;
}

.desc {
  margin: 6px 0 0;
  font-size: 13px;
  line-height: 1.5;
  max-width: 72ch;
}

.actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
}
</style>
