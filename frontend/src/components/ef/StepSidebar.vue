<script setup lang="ts">
import { ref, watch, nextTick } from 'vue'

export interface StepSection {
  id: string
  label: string
}

const props = defineProps<{
  steps: Array<{ id: number; title: string; done?: boolean }>
  activeStep: number
  sections?: StepSection[]
}>()

const emit = defineEmits<{
  (e: 'select', stepId: number): void
  (e: 'scroll-to', sectionId: string): void
}>()

const activeSection = ref('')

watch(() => props.activeStep, () => {
  activeSection.value = ''
})

function onSectionClick(sectionId: string) {
  activeSection.value = sectionId
  emit('scroll-to', sectionId)
}
</script>

<template>
  <aside class="step-sidebar">
    <div class="sidebar-title">流程导航</div>
    <nav class="step-list">
      <button
        v-for="step in steps"
        :key="step.id"
        type="button"
        class="step-item"
        :class="{ active: step.id === activeStep }"
        @click="emit('select', step.id)"
      >
        <span class="step-num">{{ step.id }}</span>
        <span class="step-label">{{ step.title }}</span>
        <span v-if="step.done" class="step-badge">&#10003;</span>
      </button>
    </nav>

    <template v-if="sections && sections.length">
      <div class="section-divider"></div>
      <div class="section-title">本页板块</div>
      <nav class="section-list">
        <button
          v-for="sec in sections"
          :key="sec.id"
          type="button"
          class="section-item"
          :class="{ active: activeSection === sec.id }"
          @click="onSectionClick(sec.id)"
        >
          {{ sec.label }}
        </button>
      </nav>
    </template>
  </aside>
</template>

<style scoped>
.step-sidebar {
  padding: 14px 10px;
  background: var(--el-bg-color);
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 12px;
  position: sticky;
  top: 76px;
  max-height: calc(100vh - 96px);
  overflow-y: auto;
}
.sidebar-title {
  font-size: 11px;
  font-weight: 600;
  color: var(--el-text-color-secondary);
  text-transform: uppercase;
  letter-spacing: 0.5px;
  margin-bottom: 8px;
  padding: 0 6px;
}
.step-list {
  display: grid;
  gap: 2px;
}
.step-item {
  width: 100%;
  display: flex;
  align-items: center;
  gap: 8px;
  border: 0;
  background: transparent;
  padding: 7px 8px;
  border-radius: 8px;
  cursor: pointer;
  font-size: 13px;
  color: var(--el-text-color-regular);
  text-align: left;
  transition: background 0.15s, color 0.15s;
}
.step-item:hover {
  background: var(--el-fill-color-light);
}
.step-item.active {
  background: var(--el-color-primary-light-9);
  color: var(--el-color-primary);
  font-weight: 600;
}
.step-num {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 20px;
  border-radius: 50%;
  background: var(--el-fill-color);
  font-size: 11px;
  font-weight: 700;
  flex-shrink: 0;
}
.step-item.active .step-num {
  background: var(--el-color-primary);
  color: #fff;
}
.step-label {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.step-badge {
  font-size: 12px;
  color: var(--el-color-success);
  flex-shrink: 0;
}
.section-divider {
  height: 1px;
  background: var(--el-border-color-lighter);
  margin: 10px 4px;
}
.section-title {
  font-size: 11px;
  font-weight: 600;
  color: var(--el-text-color-secondary);
  margin-bottom: 6px;
  padding: 0 6px;
}
.section-list {
  display: grid;
  gap: 1px;
}
.section-item {
  width: 100%;
  border: 0;
  background: transparent;
  padding: 6px 8px 6px 14px;
  border-radius: 6px;
  cursor: pointer;
  font-size: 12px;
  color: var(--el-text-color-regular);
  text-align: left;
  transition: background 0.15s, color 0.15s;
  border-left: 2px solid transparent;
}
.section-item:hover {
  background: var(--el-fill-color-light);
}
.section-item.active {
  color: var(--el-color-primary);
  border-left-color: var(--el-color-primary);
  background: var(--el-color-primary-light-9);
  font-weight: 500;
}
</style>
