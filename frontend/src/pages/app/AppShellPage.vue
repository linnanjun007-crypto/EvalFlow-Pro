<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'

const route = useRoute()

const active = computed(() => {
  const p = route.path
  if (p.startsWith('/app/projects')) return '/app/projects'
  if (p.startsWith('/app/kbs')) return '/app/kbs'
  return p
})
</script>

<template>
  <div class="shell">
    <aside class="aside">
      <div class="brand">
        <div class="logo-dot"></div>
        <div>
          <p class="brand-title">EvalFlow Pro</p>
          <p class="brand-sub">User Portal</p>
        </div>
      </div>

      <el-menu :default-active="active" router class="menu" background-color="transparent">
        <el-menu-item index="/app/projects"><span>项目列表</span></el-menu-item>
        <el-menu-item index="/app/kbs"><span>知识库</span></el-menu-item>
        <el-menu-item index="/app/account"><span>个人中心</span></el-menu-item>
      </el-menu>
    </aside>

    <main class="main">
      <RouterView />
    </main>
  </div>
</template>

<style scoped>
.shell {
  display: flex;
  min-height: calc(100svh - 64px);
  background: #f3f5f9;
}

.aside {
  width: 236px;
  flex-shrink: 0;
  background: linear-gradient(180deg, #031833 0%, #00152f 100%);
  color: #cbd5e1;
  padding: 14px 10px;
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
}

.brand-title {
  margin: 0;
  font-size: 15px;
  color: #f8fafc;
  font-weight: 600;
}

.brand-sub {
  margin: 2px 0 0;
  font-size: 11px;
  color: #94a3b8;
}

.menu {
  border-right: none;
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

.main {
  flex: 1;
  min-width: 0;
  padding: 16px;
}
</style>
