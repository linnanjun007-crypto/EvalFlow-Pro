<script setup lang="ts">
import { watch } from 'vue'
import { useRoute } from 'vue-router'
import AppLayout from './layouts/AppLayout.vue'

const route = useRoute()
watch(
  () => route.path,
  (path) => {
    document.body.classList.toggle('orbis-route', path === '/' || path === '/home')
  },
  { immediate: true },
)
</script>

<template>
  <AppLayout>
    <RouterView />
  </AppLayout>
</template>
