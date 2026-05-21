<script setup lang="ts">
import { onMounted, ref } from 'vue'
import PageHeader from '../../components/ef/PageHeader.vue'
import { useAuthStore } from '../../stores/auth'

const auth = useAuthStore()
const loading = ref(false)

async function refresh() {
  loading.value = true
  try {
    await auth.loadMe()
  } finally {
    loading.value = false
  }
}

onMounted(refresh)
</script>

<template>
  <div class="page">
    <PageHeader title="账号中心" description="查看当前登录用户与退出登录。" />

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
  </div>
</template>

<style scoped>
.page { display: grid; gap: 12px; }
.card { padding: 14px; }
.ops { margin-top: 12px; }
</style>
