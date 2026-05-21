<template>
  <div class="wrap">
    <div class="ef-card card">
      <div class="title ef-heading">登录</div>
      <div class="subtitle ef-muted">使用你的账号进入 EvalFlow Pro</div>

      <el-alert v-if="error" :title="error" type="error" show-icon :closable="false" class="alert" />

      <el-form ref="formRef" class="form" :model="form" :rules="rules" label-position="top" @submit.prevent>
        <el-form-item label="账号" prop="username">
          <el-input v-model="form.username" placeholder="请输入账号" autocomplete="username" />
        </el-form-item>

        <el-form-item label="密码" prop="password">
          <el-input v-model="form.password" type="password" placeholder="请输入密码" autocomplete="current-password" show-password />
        </el-form-item>

        <div class="forgot">
          <el-button link type="primary" @click="$router.push('/forgot-password')">忘记密码？</el-button>
        </div>

        <el-button class="primary" type="primary" size="large" :loading="loading" @click="onLogin">登录</el-button>

        <div class="footer">
          <span class="ef-muted">还没有账号？</span>
          <el-button link type="primary" @click="$router.push('/register')">注册</el-button>
        </div>
      </el-form>
    </div>
  </div>
</template>

<script setup lang="ts">
import { reactive, ref } from 'vue'
import type { FormInstance, FormRules } from 'element-plus'
import { useRouter } from 'vue-router'
import { useAuthStore } from '../../stores/auth'

const router = useRouter()
const auth = useAuthStore()
const formRef = ref<FormInstance>()
const loading = ref(false)
const error = ref('')
const form = reactive({ username: '', password: '' })
const rules: FormRules = {
  username: [{ required: true, message: '请输入账号', trigger: 'blur' }],
  password: [{ required: true, message: '请输入密码', trigger: 'blur' }],
}

async function onLogin() {
  error.value = ''
  await formRef.value?.validate(async (valid) => {
    if (!valid) return
    loading.value = true
    try {
      await auth.login(form)
      const url = new URLSearchParams(window.location.search).get('redirect')
      router.replace(url || '/app/projects')
    } catch (e) {
      const message = e instanceof Error ? e.message : '登录失败'
      if (message.includes('用户名或密码错误')) {
        error.value = '账号不存在或密码错误，请检查后重试'
      } else if (message.includes('用户不存在')) {
        error.value = '用户不存在，请先注册账号'
      } else if (message.includes('已被禁用')) {
        error.value = '该账号已被禁用，请联系管理员'
      } else {
        error.value = message
      }
    } finally {
      loading.value = false
    }
  })
}
</script>

<style scoped>
.wrap { min-height: 100svh; display: grid; place-items: center; padding: 40px 16px; }
.card { width: min(420px, 100%); padding: 28px; }
.title { font-size: 26px; font-weight: 650; letter-spacing: -0.3px; }
.subtitle { margin-top: 6px; font-size: 13px; }
.form { margin-top: 18px; }
.alert { margin-top: 14px; }
.forgot { display: flex; justify-content: flex-end; margin: -4px 0 8px; }
.primary { width: 100%; margin-top: 8px; }
.footer { margin-top: 14px; display: flex; justify-content: center; align-items: center; gap: 6px; }
</style>
