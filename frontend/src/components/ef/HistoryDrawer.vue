<script setup lang="ts">
defineProps<{
  visible: boolean
  items: Array<{ id: string; title: string; desc: string }>
}>()

const emit = defineEmits<{ (e: 'close'): void; (e: 'restore', idx: number): void; (e: 'delete', idx: number): void }>()
</script>

<template>
  <el-drawer :model-value="visible" title="历史记录" size="360px" @close="emit('close')">
    <el-empty v-if="!items.length" description="暂无历史输出" />
    <div v-else class="list">
      <div v-for="(item, idx) in items" :key="item.id" class="item">
        <div>
          <div class="title">{{ item.title }}</div>
          <div class="desc">{{ item.desc }}</div>
        </div>
        <div class="actions">
          <el-button size="small" @click="emit('restore', idx)">恢复</el-button>
          <el-button size="small" type="danger" plain @click="emit('delete', idx)">删除</el-button>
        </div>
      </div>
    </div>
  </el-drawer>
</template>

<style scoped>
.list { display: grid; gap: 10px; }
.item { border: 1px solid var(--ef-border); border-radius: 10px; padding: 12px; display: flex; justify-content: space-between; gap: 10px; }
.actions { display: flex; gap: 8px; align-items: center; }
.title { font-size: 14px; font-weight: 600; }
.desc { font-size: 12px; color: var(--ef-text-2); margin-top: 4px; }
</style>
