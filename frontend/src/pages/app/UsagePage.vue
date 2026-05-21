<script setup lang="ts">
import PageHeader from '../../components/ef/PageHeader.vue'

const rows = [
  {
    id: '1',
    project: '示例项目 A',
    step: 'Step3',
    time: '2026-05-01 10:20',
    tokens: '12,400',
    duration: '38s',
    model: 'gpt-4.1',
  },
]
</script>

<template>
  <div>
    <PageHeader title="用量与消费记录" description="报告 / 步骤生成记录、tokens、耗时与模型（示例一行）。" />

    <div class="ef-card card">
      <el-table :data="rows" stripe style="width: 100%">
        <el-table-column prop="time" label="时间" width="170" />
        <el-table-column prop="project" label="项目" min-width="140" />
        <el-table-column prop="step" label="步骤" width="90" />
        <el-table-column prop="tokens" label="Tokens" width="110" />
        <el-table-column prop="duration" label="耗时" width="90" />
        <el-table-column prop="model" label="模型" width="120" />
      </el-table>
    </div>
  </div>
</template>

<style scoped>
.card {
  padding: 18px;
}
</style>
