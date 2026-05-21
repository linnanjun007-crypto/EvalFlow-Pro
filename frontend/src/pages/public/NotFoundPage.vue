<template>
  <div class="wrap">
    <div class="ef-card card">
      <div class="code">404</div>
      <div class="title ef-heading">页面不存在</div>
      <p class="ef-muted desc">请检查地址，或返回首页 / 登录后继续。</p>
      <div class="row">
        <el-button type="primary" @click="$router.push('/')">回首页</el-button>
        <el-button @click="$router.push('/login')">去登录</el-button>
      </div>
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
  text-align: center;
}

.code {
  font-size: 48px;
  font-weight: 800;
  color: var(--ef-accent);
  letter-spacing: -2px;
}

.title {
  margin-top: 8px;
  font-size: 20px;
  font-weight: 650;
}

.desc {
  margin: 10px 0 18px;
  font-size: 14px;
  line-height: 1.5;
}

.row {
  display: flex;
  justify-content: center;
  gap: 10px;
  flex-wrap: wrap;
}
</style>
