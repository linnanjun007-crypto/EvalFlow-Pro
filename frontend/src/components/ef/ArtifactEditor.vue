<script setup lang="ts">
const props = withDefaults(defineProps<{
  title?: string
  tag?: string
  rows?: number
  placeholder?: string
}>(), {
  title: '成品区',
  tag: '最终版本',
  rows: 14,
  placeholder: '这里编辑最终成品内容',
})

const model = defineModel<string>({ default: '' })
</script>

<template>
  <section class="ef-card panel">
    <header class="head">
      <h3>{{ props.title }}</h3>
      <el-tag size="small" type="success">{{ props.tag }}</el-tag>
    </header>
    <el-input v-model="model" type="textarea" :rows="props.rows" :placeholder="props.placeholder" />
  </section>
</template>

<style scoped>
.panel { padding: 14px; }
.head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
.head h3 { margin: 0; font-size: 15px; }
</style>
