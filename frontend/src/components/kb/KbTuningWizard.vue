<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import {
  previewKbChunks,
  reindexAllKbDocs,
  updateKb,
  type KbChunk,
  type UserKb,
} from '../../services/kbs'

const props = defineProps<{
  modelValue: boolean
  kb: UserKb
  docId?: string
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', v: boolean): void
  (e: 'applied'): void
}>()

const visible = computed({
  get: () => props.modelValue,
  set: (v) => emit('update:modelValue', v),
})

const step = ref(0)

const form = ref({
  pdf_enhanced_parse: props.kb.pdf_enhanced_parse ?? false,
  processing_mode: props.kb.processing_mode || 'chunk',
  chunk_strategy: props.kb.chunk_strategy || 'auto',
  index_title: props.kb.index_title ?? true,
  index_image: props.kb.index_image ?? false,
  auto_supplement_index: props.kb.auto_supplement_index ?? false,
  chunk_size: props.kb.chunk_size || 500,
  chunk_overlap: props.kb.chunk_overlap || 50,
})

watch(
  () => props.kb,
  (kb) => {
    form.value = {
      pdf_enhanced_parse: kb.pdf_enhanced_parse ?? false,
      processing_mode: kb.processing_mode || 'chunk',
      chunk_strategy: kb.chunk_strategy || 'auto',
      index_title: kb.index_title ?? true,
      index_image: kb.index_image ?? false,
      auto_supplement_index: kb.auto_supplement_index ?? false,
      chunk_size: kb.chunk_size || 500,
      chunk_overlap: kb.chunk_overlap || 50,
    }
  },
)

const previewLoading = ref(false)
const previewChunks = ref<KbChunk[]>([])
const previewTotal = ref(0)

async function loadPreview() {
  if (!props.docId) {
    ElMessage.warning('无文档可预览')
    return
  }
  previewLoading.value = true
  try {
    const res = await previewKbChunks(props.kb.id, props.docId, {
      chunk_size: form.value.chunk_size,
      chunk_overlap: form.value.chunk_overlap,
      chunk_strategy: form.value.chunk_strategy,
    })
    previewChunks.value = res.items
    previewTotal.value = res.total
  } catch (e: any) {
    ElMessage.error(e.message || '预览失败')
  } finally {
    previewLoading.value = false
  }
}

const applying = ref(false)

async function applySettings() {
  applying.value = true
  try {
    await updateKb(props.kb.id, {
      pdf_enhanced_parse: form.value.pdf_enhanced_parse,
      processing_mode: form.value.processing_mode as 'chunk' | 'qa',
      chunk_strategy: form.value.chunk_strategy as any,
      index_title: form.value.index_title,
      index_image: form.value.index_image,
      auto_supplement_index: form.value.auto_supplement_index,
      chunk_size: form.value.chunk_size,
      chunk_overlap: form.value.chunk_overlap,
    })
    await reindexAllKbDocs(props.kb.id)
    emit('applied')
  } catch (e: any) {
    ElMessage.error(e.message || '保存失败')
  } finally {
    applying.value = false
  }
}

function nextStep() {
  if (step.value === 1 && !previewChunks.value.length) {
    loadPreview()
  }
  step.value++
}

function prevStep() {
  step.value--
}
</script>

<template>
  <el-dialog v-model="visible" title="调整训练参数" width="720px" destroy-on-close>
    <el-steps :active="step" finish-status="success" align-center style="margin-bottom: 24px">
      <el-step title="调整参数" />
      <el-step title="数据预览" />
      <el-step title="确认应用" />
    </el-steps>

    <!-- Step 0: 参数调整 -->
    <div v-show="step === 0" class="wizard-body">
      <el-form label-width="130px" size="default">
        <el-form-item label="PDF 增强解析">
          <el-switch v-model="form.pdf_enhanced_parse" />
        </el-form-item>
        <el-form-item label="处理方式">
          <el-radio-group v-model="form.processing_mode">
            <el-radio value="chunk">分块存储</el-radio>
            <el-radio value="qa">问答对提取</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="分块条件">
          <el-select v-model="form.chunk_strategy" style="width: 200px">
            <el-option label="自动" value="auto" />
            <el-option label="按段落" value="paragraph" />
            <el-option label="按标题" value="heading" />
            <el-option label="固定长度" value="fixed" />
          </el-select>
        </el-form-item>
        <el-form-item label="分块大小">
          <el-input-number v-model="form.chunk_size" :min="100" :max="4000" :step="50" />
          <span class="unit">字符</span>
        </el-form-item>
        <el-form-item label="分块重叠">
          <el-input-number v-model="form.chunk_overlap" :min="0" :max="500" :step="10" />
          <span class="unit">字符</span>
        </el-form-item>
        <el-divider content-position="left">索引增强</el-divider>
        <el-form-item label="标题加入索引">
          <el-switch v-model="form.index_title" />
        </el-form-item>
        <el-form-item label="图片索引">
          <el-switch v-model="form.index_image" />
        </el-form-item>
        <el-form-item label="自动补充索引">
          <el-switch v-model="form.auto_supplement_index" />
        </el-form-item>
      </el-form>
    </div>

    <!-- Step 1: 数据预览 -->
    <div v-show="step === 1" class="wizard-body" v-loading="previewLoading">
      <div v-if="previewChunks.length" class="preview-area">
        <p class="preview-summary">
          预计生成 <strong>{{ previewTotal }}</strong> 个分块（展示前 {{ previewChunks.length }} 个）
        </p>
        <div v-for="chunk in previewChunks" :key="chunk.chunk_index" class="preview-chunk">
          <div class="chunk-header">#{{ chunk.chunk_index + 1 }} · {{ chunk.char_count }} 字符</div>
          <div class="chunk-text">{{ chunk.content }}</div>
        </div>
      </div>
      <el-empty v-else-if="!previewLoading" description="点击下方按钮加载预览" :image-size="60">
        <el-button type="primary" size="small" @click="loadPreview">加载预览</el-button>
      </el-empty>
    </div>

    <!-- Step 2: 确认应用 -->
    <div v-show="step === 2" class="wizard-body">
      <el-alert type="warning" :closable="false" show-icon style="margin-bottom: 16px">
        确认后将保存参数并触发全库文档重建索引，期间搜索结果可能不完整。
      </el-alert>
      <el-descriptions :column="2" size="small" border>
        <el-descriptions-item label="PDF 增强解析">{{ form.pdf_enhanced_parse ? '是' : '否' }}</el-descriptions-item>
        <el-descriptions-item label="处理方式">{{ form.processing_mode === 'qa' ? '问答对提取' : '分块存储' }}</el-descriptions-item>
        <el-descriptions-item label="分块条件">{{ form.chunk_strategy }}</el-descriptions-item>
        <el-descriptions-item label="分块大小">{{ form.chunk_size }} 字符</el-descriptions-item>
        <el-descriptions-item label="分块重叠">{{ form.chunk_overlap }} 字符</el-descriptions-item>
        <el-descriptions-item label="标题加入索引">{{ form.index_title ? '是' : '否' }}</el-descriptions-item>
        <el-descriptions-item label="图片索引">{{ form.index_image ? '是' : '否' }}</el-descriptions-item>
        <el-descriptions-item label="自动补充索引">{{ form.auto_supplement_index ? '是' : '否' }}</el-descriptions-item>
      </el-descriptions>
    </div>

    <template #footer>
      <div class="wizard-footer">
        <el-button v-if="step > 0" @click="prevStep">上一步</el-button>
        <el-button v-if="step < 2" type="primary" @click="nextStep">下一步</el-button>
        <el-button v-if="step === 2" type="primary" :loading="applying" @click="applySettings">
          确认应用
        </el-button>
      </div>
    </template>
  </el-dialog>
</template>

<style scoped>
.wizard-body {
  min-height: 300px;
  max-height: 450px;
  overflow-y: auto;
}
.unit {
  margin-left: 8px;
  font-size: 13px;
  color: #6b7280;
}
.preview-area {
  padding: 0 4px;
}
.preview-summary {
  margin-bottom: 12px;
  font-size: 13px;
  color: #374151;
}
.preview-chunk {
  margin-bottom: 12px;
  border: 1px solid #e5e7eb;
  border-radius: 6px;
  overflow: hidden;
}
.chunk-header {
  background: #f9fafb;
  padding: 6px 12px;
  font-size: 12px;
  color: #6b7280;
  border-bottom: 1px solid #f3f4f6;
}
.chunk-text {
  padding: 10px 12px;
  font-size: 13px;
  line-height: 1.6;
  color: #374151;
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 120px;
  overflow-y: auto;
}
.wizard-footer {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}
</style>
