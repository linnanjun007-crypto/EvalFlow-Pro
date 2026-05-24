<script setup lang="ts">
import { computed, defineAsyncComponent } from 'vue'
import { useUiStore } from '../../stores/ui'

const uiStore = useUiStore()

const ClassicPage = defineAsyncComponent(() => import('./ProjectWorkflowPage.vue'))
const HybridPage = defineAsyncComponent(() => import('./HybridWorkflowPage.vue'))

const activeComponent = computed(() =>
  uiStore.workflowLayout === 'hybrid' ? HybridPage : ClassicPage,
)
</script>

<template>
  <component :is="activeComponent" />
</template>
