<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { listKbs, getProjectKbs, setProjectKbs, type UserKb } from '../../services/kbs'

const props = defineProps<{ projectId: string }>()

const allKbs = ref<UserKb[]>([])
const boundIds = ref<string[]>([])
const loading = ref(false)
const saving = ref(false)

const transferData = ref<{ key: string; label: string; disabled: boolean }[]>([])

async function load() {
  loading.value = true
  try {
    const [kbs, bindings] = await Promise.all([
      listKbs(),
      getProjectKbs(props.projectId),
    ])
    allKbs.value = kbs
    transferData.value = kbs.map((kb) => ({
      key: kb.id,
      label: `${kb.name}（${kb.doc_count ?? 0} 文档）`,
      disabled: false,
    }))
    boundIds.value = bindings.map((b) => b.id)
  } catch (e: any) {
    ElMessage.error(e.message || '加载知识库绑定失败')
  } finally {
    loading.value = false
  }
}

async function save() {
  saving.value = true
  try {
    await setProjectKbs(props.projectId, boundIds.value)
    ElMessage.success('知识库绑定已保存')
  } catch (e: any) {
    ElMessage.error(e.message || '保存失败')
  } finally {
    saving.value = false
  }
}

watch(() => props.projectId, load)
onMounted(load)
</script>

<template>
  <div v-loading="loading" class="kb-binding-panel">
    <div class="panel-header">
      <span class="panel-title">关联知识库</span>
      <el-button type="primary" size="small" :loading="saving" @click="save">保存绑定</el-button>
    </div>
    <p class="panel-desc">选择要关联到本项目的知识库，工作流执行时将自动检索已关联知识库中的内容。</p>
    <el-transfer
      v-model="boundIds"
      :data="transferData"
      :titles="['可用知识库', '已关联']"
      filterable
      filter-placeholder="搜索知识库"
    />
    <el-empty v-if="!loading && !transferData.length" description="暂无可用知识库，请先在「我的知识库」中创建" :image-size="60" />
  </div>
</template>

<style scoped>
.kb-binding-panel {
  min-height: 120px;
}
.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 6px;
}
.panel-title {
  font-size: 15px;
  font-weight: 650;
}
.panel-desc {
  font-size: 13px;
  color: #64748b;
  margin: 0 0 12px;
}
</style>
