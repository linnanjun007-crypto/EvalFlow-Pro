<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import ChatPanel from '../../components/ef/ChatPanel.vue'
import ProjectWorkflowPage from './ProjectWorkflowPage.vue'
import { useWorkflowBus } from '../../stores/workflowBus'

const route = useRoute()
const bus = useWorkflowBus()

const projectId = computed(() => String(route.params.projectId || ''))
const stepId = computed(() => Number(route.params.stepId || 1))
const stepCode = computed(() => `step${stepId.value || 1}`)

function onUiAction(payload: { action: 'goto_step' | 'trigger_generate' | 'stop'; step?: number }) {
  if (payload.action === 'goto_step' && payload.step) {
    bus.dispatch({ action: 'goto_step', step: payload.step })
  } else if (payload.action === 'trigger_generate') {
    bus.dispatch({ action: 'trigger_generate' })
  } else if (payload.action === 'stop') {
    bus.dispatch({ action: 'stop' })
  }
}
</script>

<template>
  <div class="hybrid-page">
    <div class="hybrid-body">
      <aside class="chat-pane">
        <ChatPanel
          :project-id="projectId"
          :step-code="stepCode"
          :step-title="`Step ${stepId}`"
          :prompt-hint="'例如：跳到第3步 / 开始生成 / 停止'"
          @ui-action="onUiAction"
        />
      </aside>
      <main class="canvas-pane">
        <ProjectWorkflowPage :embedded-mode="true" />
      </main>
    </div>
  </div>
</template>

<style scoped>
.hybrid-page { padding: 12px; min-height: calc(100vh - 64px); display: flex; flex-direction: column; gap: 10px; }
.hybrid-body { flex: 1; display: grid; grid-template-columns: minmax(320px, 0.9fr) minmax(720px, 2.4fr); gap: 12px; min-height: 0; }
.chat-pane { border: 1px solid var(--ef-border, var(--el-border-color)); border-radius: 12px; background: var(--ef-surface, var(--el-bg-color)); padding: 12px 14px; display: flex; flex-direction: column; min-height: 600px; max-height: calc(100vh - 96px); }
.canvas-pane { border: 1px solid var(--ef-border, var(--el-border-color)); border-radius: 12px; background: var(--ef-surface, var(--el-bg-color)); padding: 12px; overflow: auto; max-height: calc(100vh - 96px); }
</style>
