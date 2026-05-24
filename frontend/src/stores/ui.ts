import { defineStore } from 'pinia'
import { ref } from 'vue'

export type WorkflowLayout = 'classic' | 'hybrid'

export const useUiStore = defineStore('ui', () => {
  const workflowLayout = ref<WorkflowLayout>(
    (localStorage.getItem('ef_workflow_layout') as WorkflowLayout) || 'classic',
  )

  function setWorkflowLayout(value: WorkflowLayout) {
    workflowLayout.value = value
    localStorage.setItem('ef_workflow_layout', value)
  }

  return { workflowLayout, setWorkflowLayout }
})
