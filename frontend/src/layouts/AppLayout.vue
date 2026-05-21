<script setup lang="ts">
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'

const route = useRoute()
const router = useRouter()

const isBlankLayout = computed(() => {
  return route.meta.layout === 'blank'
})

function goBrand() {
  if (route.path.startsWith('/admin')) {
    router.push('/admin/dashboard')
    return
  }
  if (route.path.startsWith('/app')) {
    router.push('/app/projects')
    return
  }
  router.push('/')
}

function goProjects() {
  router.push('/app/projects')
}

function logout() {
  localStorage.removeItem('ef_token')
  router.push('/login')
}
</script>

<template>
  <div v-if="isBlankLayout">
    <slot />
  </div>

  <div v-else>
    <header class="topbar">
      <div
        class="brand"
        role="button"
        tabindex="0"
        @click="goBrand"
        @keydown.enter.prevent="goBrand"
        @keydown.space.prevent="goBrand"
      >
        <div class="brand-title ef-heading">EvalFlow Pro</div>
        <div class="brand-sub ef-muted">绩效评价工作台</div>
      </div>

      <div class="right">
        <el-button text class="ghost-link" @click="$router.push('/')">官网首页</el-button>
        <el-button text @click="goProjects">项目</el-button>
        <el-button text @click="$router.push('/admin/dashboard')">管理</el-button>
        <el-divider direction="vertical" />
        <el-button text @click="logout">退出</el-button>
      </div>
    </header>

    <Transition name="ef-fade" mode="out-in">
      <slot />
    </Transition>
  </div>
</template>

<style scoped>
.topbar {
  position: sticky;
  top: 0;
  z-index: 20;
  border-bottom: 1px solid var(--ef-border);
  background: color-mix(in srgb, var(--ef-surface) 88%, transparent);
  backdrop-filter: blur(14px);
  height: 64px;
  padding: 0 16px;
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.ghost-link {
  color: var(--ef-text-2);
}

.brand {
  cursor: pointer;
  user-select: none;
}

.brand:focus-visible {
  outline: 2px solid rgba(212, 175, 55, 0.75);
  outline-offset: 6px;
  border-radius: 10px;
}

.brand-title {
  font-weight: 650;
  letter-spacing: -0.2px;
}

.brand-sub {
  font-size: 12px;
  margin-top: 2px;
}

.right {
  display: flex;
  align-items: center;
  gap: 6px;
}

</style>
