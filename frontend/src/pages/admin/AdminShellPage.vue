<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import {
  Odometer, User, Cpu, Operation, Clock,
  DocumentChecked, DataAnalysis, Download,
  Expand, Fold, SwitchButton, Close, UserFilled,
} from '@element-plus/icons-vue'
import { useAuthStore } from '../../stores/auth'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()

const collapsed = ref(false)
const mobileOpen = ref(false)

const active = computed(() => {
  const p = route.path
  if (p === '/admin' || p === '/admin/') return '/admin/dashboard'
  return p
})

const menuItems = [
  { index: '/admin/dashboard', label: '控制台', icon: Odometer },
  { index: '/admin/users', label: '账户管理', icon: User },
  { index: '/admin/models', label: '模型配置', icon: Cpu },
  { index: '/admin/prompts', label: '14步配置中心', icon: Operation },
  { index: '/admin/change-logs', label: '修改日志', icon: Clock },
  { index: '/admin/audit-logs', label: '审计日志', icon: DocumentChecked },
  { index: '/admin/usage-analytics', label: '用量分析', icon: DataAnalysis },
  { index: '/admin/downloads', label: '全量下载', icon: Download },
]

const breadcrumbs = computed(() => {
  const items: Array<{ label: string; to?: string }> = [
    { label: '管理端', to: '/admin/dashboard' },
  ]
  const current = menuItems.find((m) => m.index === active.value)
  if (current && current.index !== '/admin/dashboard') {
    items.push({ label: current.label })
  }
  return items
})

function handleMenuSelect(index: string) {
  mobileOpen.value = false
  router.push(index)
}

function toggleCollapse() {
  collapsed.value = !collapsed.value
}

function handleLogout() {
  auth.logout()
  router.push('/login')
}

function closeMobile() {
  mobileOpen.value = false
}

onMounted(() => {
  if (!auth.user && auth.token) {
    auth.loadMe()
  }
})

watch(() => route.path, () => {
  mobileOpen.value = false
})
</script>

<template>
  <div class="shell" :class="{ collapsed, mobile: mobileOpen }">
    <!-- Mobile overlay -->
    <div v-if="mobileOpen" class="mobile-overlay" @click="closeMobile" />

    <!-- Sidebar -->
    <aside class="aside" :class="{ collapsed, open: mobileOpen }">
      <div class="brand">
        <div class="logo-dot" />
        <div v-show="!collapsed" class="brand-text">
          <p class="brand-title">云海睿评</p>
          <p class="brand-sub">Admin Console</p>
        </div>
      </div>

      <el-menu
        :default-active="active"
        :collapse="collapsed"
        router
        class="menu"
        background-color="transparent"
        @select="handleMenuSelect"
      >
        <el-menu-item v-for="item in menuItems" :key="item.index" :index="item.index">
          <el-icon><component :is="item.icon" /></el-icon>
          <template #title>
            <span>{{ item.label }}</span>
          </template>
        </el-menu-item>
      </el-menu>

      <!-- Sidebar footer: user info -->
      <div class="aside-footer" :class="{ collapsed }">
        <div class="user-row">
          <el-avatar :size="32"><el-icon><UserFilled /></el-icon></el-avatar>
          <div v-show="!collapsed" class="user-text">
            <p class="user-name">{{ auth.user?.username || '管理员' }}</p>
            <p class="user-role">{{ auth.user?.role || 'admin' }}</p>
          </div>
        </div>
        <el-button
          v-show="!collapsed"
          text
          class="logout-btn"
          @click="handleLogout"
        >
          <el-icon><SwitchButton /></el-icon>
          <span>退出</span>
        </el-button>
      </div>
    </aside>

    <!-- Main -->
    <main class="main">
      <!-- Top bar inside main -->
      <header class="admin-topbar">
        <div class="topbar-left">
          <el-button
            text
            class="collapse-btn"
            @click="toggleCollapse"
          >
            <el-icon :size="18">
              <Fold v-if="!collapsed" />
              <Expand v-else />
            </el-icon>
          </el-button>

          <el-breadcrumb separator="/">
            <el-breadcrumb-item
              v-for="(item, idx) in breadcrumbs"
              :key="idx"
              :to="item.to"
            >
              {{ item.label }}
            </el-breadcrumb-item>
          </el-breadcrumb>
        </div>

        <div class="topbar-right">
          <el-button
            class="mobile-menu-btn"
            text
            @click="mobileOpen = !mobileOpen"
          >
            <el-icon :size="20"><Close v-if="mobileOpen" /><Expand v-else /></el-icon>
          </el-button>
        </div>
      </header>

      <div class="content">
        <RouterView />
      </div>
    </main>
  </div>
</template>

<style scoped>
.shell {
  display: flex;
  min-height: calc(100svh - 64px);
  background: #f3f5f9;
}

/* ── Sidebar ── */
.aside {
  width: 236px;
  flex-shrink: 0;
  background: linear-gradient(180deg, #031833 0%, #00152f 100%);
  color: #cbd5e1;
  padding: 14px 10px;
  display: flex;
  flex-direction: column;
  transition: width 0.22s ease;
  overflow: hidden;
}

.aside.collapsed {
  width: 64px;
  padding: 14px 6px;
}

.brand {
  display: flex;
  gap: 10px;
  align-items: center;
  padding: 8px 10px 14px;
}

.logo-dot {
  width: 30px;
  height: 30px;
  border-radius: 50%;
  background: radial-gradient(circle at 30% 30%, #93c5fd, #3b82f6);
  flex-shrink: 0;
}

.brand-text {
  min-width: 0;
  overflow: hidden;
}

.brand-title {
  margin: 0;
  font-size: 15px;
  color: #f8fafc;
  font-weight: 600;
  white-space: nowrap;
}

.brand-sub {
  margin: 2px 0 0;
  font-size: 11px;
  color: #94a3b8;
  white-space: nowrap;
}

.menu {
  border-right: none;
  flex: 1;
}

.menu :deep(.el-menu-item) {
  height: 38px;
  line-height: 38px;
  border-radius: 8px;
  color: #cbd5e1;
  margin-bottom: 4px;
}

.menu :deep(.el-menu-item:hover) {
  background: rgba(59, 130, 246, 0.18);
}

.menu :deep(.el-menu-item.is-active) {
  background: #1976ff;
  color: #fff;
  font-weight: 600;
}

/* Collapsed menu tweaks */
.aside.collapsed .menu :deep(.el-menu-item) {
  justify-content: center;
  padding: 0 !important;
}

.aside.collapsed .menu :deep(.el-menu-item .el-icon) {
  margin-right: 0 !important;
}

/* ── Sidebar footer ── */
.aside-footer {
  margin-top: auto;
  padding: 10px 6px;
  border-top: 1px solid rgba(148, 163, 184, 0.14);
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.aside-footer.collapsed {
  align-items: center;
  padding: 10px 0;
}

.user-row {
  display: flex;
  gap: 8px;
  align-items: center;
}

.user-text {
  min-width: 0;
  overflow: hidden;
}

.user-name {
  margin: 0;
  font-size: 13px;
  color: #f8fafc;
  font-weight: 500;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.user-role {
  margin: 2px 0 0;
  font-size: 11px;
  color: #94a3b8;
}

.logout-btn {
  color: #94a3b8;
  font-size: 12px;
  justify-content: flex-start;
  padding: 4px 6px;
}

.logout-btn:hover {
  color: #f87171;
}

/* ── Main ── */
.main {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
}

.admin-topbar {
  height: 48px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 14px;
  border-bottom: 1px solid rgba(15, 23, 42, 0.08);
  background: #fff;
  flex-shrink: 0;
}

.topbar-left {
  display: flex;
  align-items: center;
  gap: 10px;
}

.collapse-btn {
  color: #64748b;
  padding: 4px;
}

.collapse-btn:hover {
  color: #1e293b;
  background: #f1f5f9;
}

.content {
  flex: 1;
  padding: 16px;
  overflow: auto;
}

.mobile-menu-btn {
  display: none;
}

/* ── Responsive ── */
@media (max-width: 860px) {
  .aside {
    position: fixed;
    top: 64px;
    left: 0;
    bottom: 0;
    z-index: 30;
    transform: translateX(-100%);
    transition: transform 0.22s ease;
  }

  .aside.open {
    transform: translateX(0);
  }

  .aside.collapsed {
    width: 236px;
    padding: 14px 10px;
  }

  .mobile-overlay {
    position: fixed;
    inset: 0;
    top: 64px;
    z-index: 25;
    background: rgba(0, 0, 0, 0.4);
  }

  .mobile-menu-btn {
    display: inline-flex;
  }

  .content {
    padding: 12px;
  }
}
</style>
