<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import MarkdownIt from 'markdown-it'
import DOMPurify from 'dompurify'
import PageHeader from '../../components/ef/PageHeader.vue'
import { useAuthStore } from '../../stores/auth'
import {
  deleteReport,
  exportReport,
  listReports,
  updateReportRetention,
  type ProjectReport,
} from '../../services/reports'

const md = new MarkdownIt()

const auth = useAuthStore()
const loading = ref(false)
const activeTab = ref('account')

const reports = ref<ProjectReport[]>([])
const reportsLoading = ref(false)
const reportDrawer = ref(false)
const currentReport = ref<ProjectReport | null>(null)

async function refresh() {
  loading.value = true
  try {
    await auth.loadMe()
  } finally {
    loading.value = false
  }
}

async function loadReports() {
  reportsLoading.value = true
  try {
    reports.value = await listReports()
  } catch (e: any) {
    ElMessage.error(e.message || '加载报告失败')
  } finally {
    reportsLoading.value = false
  }
}

function viewReport(row: ProjectReport) {
  currentReport.value = row
  reportDrawer.value = true
}

async function handleExport(row: ProjectReport, format: 'md' | 'txt') {
  try {
    const blob = await exportReport(row.id, format)
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `${row.title || row.project_name}.${format}`
    a.click()
    URL.revokeObjectURL(url)
    ElMessage.success('已导出')
  } catch (e: any) {
    ElMessage.error(e.message || '导出失败')
  }
}

async function handleRetention(row: ProjectReport) {
  try {
    const { value } = await ElMessageBox.prompt('设置保留天数（1-365）', '修改保留期', {
      inputValue: String(row.retention_days),
      inputPattern: /^[1-9]\d{0,2}$/,
      inputErrorMessage: '请输入 1-365 的整数',
    })
    const days = Number(value)
    if (days < 1 || days > 365) return
    await updateReportRetention(row.id, days)
    ElMessage.success('已更新')
    loadReports()
  } catch {
    // cancelled
  }
}

async function handleDelete(row: ProjectReport) {
  try {
    await ElMessageBox.confirm(`确定删除报告「${row.title || row.project_name}」？`, '删除确认', {
      type: 'warning',
    })
    await deleteReport(row.id)
    ElMessage.success('已删除')
    loadReports()
  } catch {
    // cancelled
  }
}

function formatTime(value?: string | null): string {
  if (!value) return '—'
  const d = new Date(value)
  if (Number.isNaN(d.getTime())) return value
  return d.toLocaleString('zh-CN', { hour12: false })
}

function renderMd(src: string): string {
  return DOMPurify.sanitize(md.render(src || ''))
}

function onTabChange(tab: string | number) {
  if (tab === 'reports' && !reports.value.length) {
    loadReports()
  }
}

onMounted(refresh)
</script>

<template>
  <div class="page">
    <PageHeader title="个人中心" description="账户信息与项目报告管理。" />

    <el-tabs v-model="activeTab" class="account-tabs" @tab-change="onTabChange">
      <el-tab-pane label="账户信息" name="account">
        <section class="ef-card card">
          <el-skeleton v-if="loading" :rows="3" animated />
          <el-descriptions v-else :column="1" border>
            <el-descriptions-item label="用户 ID">{{ auth.user?.id || '未登录' }}</el-descriptions-item>
            <el-descriptions-item label="用户名">{{ auth.user?.username || '-' }}</el-descriptions-item>
            <el-descriptions-item label="角色">{{ auth.user?.role || '-' }}</el-descriptions-item>
          </el-descriptions>
          <div class="ops">
            <el-button type="danger" plain @click="auth.logout()">退出登录</el-button>
          </div>
        </section>
      </el-tab-pane>

      <el-tab-pane label="我的报告" name="reports">
        <section class="ef-card card" v-loading="reportsLoading">
          <el-table :data="reports" stripe style="width: 100%">
            <el-table-column prop="project_name" label="项目名称" min-width="160" />
            <el-table-column label="生成时间" width="170">
              <template #default="{ row }">{{ formatTime(row.generated_at) }}</template>
            </el-table-column>
            <el-table-column prop="retention_days" label="保留天数" width="90" align="center" />
            <el-table-column label="过期时间" width="170">
              <template #default="{ row }">{{ formatTime(row.expires_at) }}</template>
            </el-table-column>
            <el-table-column label="操作" width="260" fixed="right">
              <template #default="{ row }">
                <el-button link type="primary" size="small" @click="viewReport(row)">查看</el-button>
                <el-button link type="primary" size="small" @click="handleExport(row, 'md')">导出MD</el-button>
                <el-button link type="primary" size="small" @click="handleExport(row, 'txt')">导出TXT</el-button>
                <el-button link size="small" @click="handleRetention(row)">保留期</el-button>
                <el-button link type="danger" size="small" @click="handleDelete(row)">删除</el-button>
              </template>
            </el-table-column>
          </el-table>
          <el-empty v-if="!reportsLoading && !reports.length" description="暂无报告" :image-size="80" />
        </section>
      </el-tab-pane>
    </el-tabs>

    <el-drawer v-model="reportDrawer" :title="currentReport?.title || '报告详情'" size="65%" direction="rtl">
      <div v-if="currentReport" class="report-content" v-html="renderMd(currentReport.content_md || '')" />
    </el-drawer>
  </div>
</template>

<style scoped>
.page { display: grid; gap: 12px; }
.card { padding: 14px; }
.ops { margin-top: 12px; }
.account-tabs { background: transparent; }
.report-content {
  padding: 16px;
  font-size: 14px;
  line-height: 1.8;
  color: #374151;
}
.report-content :deep(h1) {
  font-size: 20px;
  font-weight: 600;
  margin: 20px 0 10px;
  color: #111827;
}
.report-content :deep(h2) {
  font-size: 17px;
  font-weight: 600;
  margin: 16px 0 8px;
  color: #1f2937;
}
.report-content :deep(h3) {
  font-size: 15px;
  font-weight: 500;
  margin: 12px 0 6px;
  color: #374151;
}
</style>
