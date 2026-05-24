import { defineStore } from 'pinia'
import { ref, shallowRef } from 'vue'

export interface WorkflowCommand {
  action: 'goto_step' | 'update_field' | 'trigger_generate' | 'stop'
  step?: number
  field?: string
  value?: unknown
}

export const useWorkflowBus = defineStore('workflow-bus', () => {
  const pendingCommand = shallowRef<WorkflowCommand | null>(null)
  const currentStepId = ref(1)
  const isLoading = ref(false)
  const currentProjectId = ref('')

  function dispatch(cmd: WorkflowCommand) {
    pendingCommand.value = cmd
  }

  function consume(): WorkflowCommand | null {
    const cmd = pendingCommand.value
    pendingCommand.value = null
    return cmd
  }

  return { pendingCommand, currentStepId, isLoading, currentProjectId, dispatch, consume }
})
