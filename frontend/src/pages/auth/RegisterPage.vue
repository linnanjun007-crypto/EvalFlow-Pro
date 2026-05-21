<template>
  <div class="wrap">
    <div class="ef-card card">
      <div class="title ef-heading">注册</div>
      <div class="subtitle ef-muted">创建你的 EvalFlow Pro 账号</div>

      <el-alert v-if="error" :title="error" type="error" show-icon :closable="false" class="alert" />

      <el-form ref="formRef" class="form" :model="form" :rules="rules" label-position="top" @submit.prevent>
        <el-form-item label="用户名" prop="username">
          <el-input v-model="form.username" placeholder="请输入用户名" autocomplete="username" />
        </el-form-item>

        <el-form-item label="密码" prop="password">
          <el-input v-model="form.password" type="password" placeholder="请输入密码" autocomplete="new-password" show-password />
        </el-form-item>

        <el-form-item label="确认密码" prop="confirmPassword">
          <el-input v-model="form.confirmPassword" type="password" placeholder="请再次输入密码" autocomplete="new-password" show-password />
        </el-form-item>

        <el-button class="primary" type="primary" size="large" :loading="loading" @click="onRegister">注册</el-button>

        <div class="footer">
          <span class="ef-muted">已有账号？</span>
          <el-button link type="primary" @click="$router.push('/login')">去登录</el-button>
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
const form = reactive({ username: '', password: '', confirmPassword: '' })
const rules: FormRules = {
  username: [{ required: true, message: '请输入用户名', trigger: 'blur' }],
  password: [{ required: true, message: '请输入密码', trigger: 'blur' }],
  confirmPassword: [{ required: true, message: '请再次输入密码', trigger: 'blur' }],
}

async function onRegister() {
  error.value = ''
  await formRef.value?.validate(async (valid) => {
    if (!valid) return
    if (form.password !== form.confirmPassword) {
      error.value = '两次输入的密码不一致'
      return
    }
    loading.value = true
    try {
      await auth.register({ username: form.username, password: form.password })
      router.replace('/login')
    } catch (e) {
      const message = e instanceof Error ? e.message : '注册失败'
      if (message.includes('用户名已存在')) {
        error.value = '用户名已存在，请换一个再试'
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
.card { width: min(520px, 100%); padding: 28px; }
.title { font-size: 26px; font-weight: 650; letter-spacing: -0.3px; }
.subtitle { margin-top: 6px; font-size: 13px; }
.form { margin-top: 18px; }
.alert { margin-top: 14px; }
.primary { width: 100%; margin-top: 8px; }
.footer { margin-top: 14px; display: flex; justify-content: center; align-items: center; gap: 6px; }
</style>
