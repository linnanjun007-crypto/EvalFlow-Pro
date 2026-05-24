<script setup lang="ts">
import { ref } from 'vue'
import MarkdownDashboard from './MarkdownDashboard.vue'

interface KeyMetric {
  label: string
  value: string
  source: string
}

interface GapItem {
  material: string
  status: 'success' | 'error' | 'warning'
  note: string
}

interface SourceIndexEntry {
  ref_id: string
  source_name: string
  channel: string
  excerpt: string
  chunk_index?: number | null
}

const props = withDefaults(
  defineProps<{
    title?: string
    tag?: string
    rows?: number
    placeholder?: string
    keyMetrics?: KeyMetric[]
    gapItems?: GapItem[]
    sourceIndex?: SourceIndexEntry[]
    enableDashboard?: boolean
  }>(),
  {
    title: '成品区',
    tag: '最终版本',
    rows: 14,
    placeholder: '这里编辑最终成品内容',
    enableDashboard: true,
  },
)

const emit = defineEmits<{
  (e: 'request-upload', payload: { material: string }): void
  (e: 'step-click', step: number): void
}>()

const model = defineModel<string>({ default: '' })

const viewMode = ref<'edit' | 'preview'>('edit')
const expandDialog = ref(false)
</script>

<template>
  <section class="ef-card panel">
    <header class="head">
      <div class="head-left">
        <h3>{{ props.title }}</h3>
        <el-tag size="small" type="success">{{ props.tag }}</el-tag>
      </div>
      <div class="head-right">
        <el-radio-group v-if="props.enableDashboard" v-model="viewMode" size="small">
          <el-radio-button value="edit">编辑</el-radio-button>
          <el-radio-button value="preview">看板</el-radio-button>
        </el-radio-group>
        <el-button v-if="viewMode === 'edit'" size="small" plain @click="expandDialog = true">
          放大编辑
        </el-button>
      </div>
    </header>

    <template v-if="viewMode === 'edit' || !props.enableDashboard">
      <el-input v-model="model" type="textarea" :rows="props.rows" :placeholder="props.placeholder" />
    </template>

    <template v-else>
      <MarkdownDashboard
        :source="model"
        :key-metrics="props.keyMetrics"
        :gap-items="props.gapItems"
        :source-index="props.sourceIndex"
        @request-upload="(p) => emit('request-upload', p)"
        @step-click="(n) => emit('step-click', n)"
      />
    </template>

    <el-dialog v-model="expandDialog" :title="`${props.title} · 放大编辑`" fullscreen append-to-body>
      <el-input v-model="model" type="textarea" :rows="30" :placeholder="props.placeholder" />
      <template #footer>
        <el-button @click="expandDialog = false">关闭</el-button>
      </template>
    </el-dialog>
  </section>
</template>

<style scoped>
.panel { padding: 14px; }
.head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; gap: 12px; flex-wrap: wrap; }
.head-left { display: flex; align-items: center; gap: 8px; }
.head-right { display: flex; align-items: center; gap: 8px; }
.head h3 { margin: 0; font-size: 15px; }
</style>
