<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import PageHeader from '../../components/ef/PageHeader.vue'
import { listUsers, setUserStatus, type UserResponse } from '../../services/auth'

const keyword = ref('')
const status = ref<'全部' | 'active' | 'disabled'>('全部')
const loading = ref(false)
const rows = ref<UserResponse[]>([])
const filteredRows = computed(() => rows.value.filter((row) => (!keyword.value || row.username.includes(keyword.value)) && (status.value === '全部' || row.status === status.value)))

async function refresh() {
  loading.value = true
  try {
    rows.value = await listUsers()
  } finally {
    loading.value = false
  }
}

async function toggleUser(row: UserResponse) {
  await setUserStatus(row.id, row.status === 'active' ? 'disabled' : 'active')
  await refresh()
}

onMounted(refresh)
</script>

<template>
  <div class="page">
    <PageHeader title="用户管理" description="新增账号、重置密码、启用/禁用与使用情况。">
      <template #actions>
        <el-button type="primary">新增账号</el-button>
      </template>
    </PageHeader>

    <section class="ef-card toolbar">
      <el-input v-model="keyword" placeholder="搜索账号或用户名" style="width: 260px" />
      <el-select v-model="status" style="width: 140px">
        <el-option label="全部" value="全部" />
        <el-option label="启用" value="active" />
        <el-option label="禁用" value="disabled" />
      </el-select>
    </section>

    <section class="ef-card card">
      <el-table v-loading="loading" :data="filteredRows" stripe style="width: 100%">
        <el-table-column prop="username" label="账号" width="160" />
        <el-table-column prop="role" label="角色" width="140" />
        <el-table-column prop="status" label="状态" width="100" />
        <el-table-column label="操作" width="220" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" size="small" @click="toggleUser(row)">{{ row.status === 'active' ? '禁用' : '启用' }}</el-button>
          </template>
        </el-table-column>
      </el-table>
    </section>
  </div>
</template>

<style scoped>
.page { display: grid; gap: 12px; }
.toolbar { padding: 14px; display: flex; gap: 10px; flex-wrap: wrap; }
.card { padding: 14px; }
</style>
