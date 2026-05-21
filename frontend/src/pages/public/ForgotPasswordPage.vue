<template>
  <div class="wrap">
    <div class="ef-card card">
      <div class="title ef-heading">忘记密码</div>
      <p class="ef-muted body">
        当前版本未开放自助找回密码。如需重置，请联系系统管理员处理。
      </p>
      <el-button type="primary" @click="$router.push('/login')">返回登录</el-button>
    </div>
  </div>
</template>

<style scoped>
.wrap {
  min-height: 100svh;
  display: grid;
  place-items: center;
  padding: 40px 16px;
}

.card {
  width: min(440px, 100%);
  padding: 28px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.title {
  font-size: 22px;
  font-weight: 650;
}

.body {
  margin: 0;
  line-height: 1.6;
  font-size: 14px;
}
</style>
