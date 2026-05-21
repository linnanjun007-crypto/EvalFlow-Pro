<script setup lang="ts">
import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import PageHeader from '../../components/ef/PageHeader.vue'
import { createProject } from '../../services/projects'

const router = useRouter()
const loading = ref(false)
const error = ref('')
const form = reactive({ name: '', description: '', type: '', remark: '' })

async function submit() {
  if (!form.name.trim()) {
    error.value = '请输入项目名称'
    return
  }
  loading.value = true
  error.value = ''
  try {
    const project = await createProject({ name: form.name.trim(), description: form.description.trim() || form.remark.trim() || null })
    router.push(`/app/projects/${project.id}/overview`)
  } catch (e) {
    error.value = e instanceof Error ? e.message : '创建项目失败'
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="page">
    <PageHeader title="新建项目" description="创建项目后进入总览页，开始 14 步工作流。" />

    <section class="ef-card card">
      <el-alert v-if="error" :title="error" type="error" :closable="false" show-icon class="mb" />
      <el-form label-position="top" @submit.prevent="submit">
        <el-form-item label="项目名称" required>
          <el-input v-model="form.name" placeholder="例如：2025 年度某部门整体支出评价" />
        </el-form-item>
        <el-form-item label="简介">
          <el-input v-model="form.description" type="textarea" :rows="4" placeholder="项目简介，可选" />
        </el-form-item>
        <el-form-item label="项目类型">
          <el-select v-model="form.type" placeholder="可选" clearable style="width: 100%">
            <el-option label="部门整体" value="dept" />
            <el-option label="财政重点" value="fiscal" />
            <el-option label="自定义" value="custom" />
          </el-select>
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="form.remark" type="textarea" :rows="4" placeholder="可选" />
        </el-form-item>
        <div class="ops">
          <el-button type="primary" :loading="loading" :disabled="!form.name.trim()" native-type="submit">创建并进入总览</el-button>
          <el-button @click="router.back()">取消</el-button>
        </div>
      </el-form>
    </section>
  </div>
</template>

<style scoped>
.page { display: grid; gap: 12px; }
.card { max-width: 720px; padding: 20px; }
.ops { display: flex; gap: 10px; }
.mb { margin-bottom: 12px; }
</style>
