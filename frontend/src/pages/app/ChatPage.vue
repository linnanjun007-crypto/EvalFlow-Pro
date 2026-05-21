<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import PageHeader from '../../components/ef/PageHeader.vue'
import ChatDrawer from '../../components/ef/ChatDrawer.vue'

const route = useRoute()
const router = useRouter()
const projectId = computed(() => String(route.query.projectId ?? route.params.projectId ?? ''))
const stepCode = computed(() => String(route.query.stepCode ?? route.params.stepCode ?? 'step1'))
const drawerOpen = ref(true)

function close() {
  router.back()
}
</script>

<template>
  <div class="page-wrap">
    <PageHeader title="AI 对话" description="独立对话页，可从工作流或历史记录跳转进入。">
      <template #actions>
        <el-button @click="close">返回</el-button>
      </template>
    </PageHeader>

    <ChatDrawer v-model="drawerOpen" :project-id="projectId" :step-code="stepCode" />
  </div>
</template>
