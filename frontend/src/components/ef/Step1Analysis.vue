<script setup lang="ts">
interface KeyMetric {
  label: string
  value: string
  source: string
}

interface GapItem {
  material: string
  status: 'success' | 'error' | 'warning'
  note: string
}

interface DataFlowItem {
  file_name: string
  file_type: string
  target_steps: string[]
}

defineProps<{
  keyMetrics: KeyMetric[]
  gapAnalysis: GapItem[]
  dataFlow: DataFlowItem[]
}>()

const statusConfig: Record<string, { badge: string; bg: string; text: string }> = {
  success: { badge: '已覆盖', bg: 'bg-emerald-50', text: 'text-emerald-700' },
  error: { badge: '缺失', bg: 'bg-red-50', text: 'text-red-700' },
  warning: { badge: '待确认', bg: 'bg-amber-50', text: 'text-amber-700' },
}

const metricIcons: Record<string, string> = {
  '金额': '¥',
  '金额（亿）': '¥',
  '人数': '👤',
  '面积': '📐',
  '距离': '📏',
  '数量': '#',
  '年份': '📅',
}
</script>

<template>
  <div class="space-y-6">
    <!-- Table A: Key Metrics -->
    <section>
      <h4 class="text-sm font-semibold text-gray-700 mb-3 tracking-wide uppercase">Table A · Key Metrics（关键数字）</h4>
      <div v-if="keyMetrics.length" class="overflow-hidden rounded-xl border border-gray-200">
        <table class="w-full text-sm">
          <thead class="bg-gray-50">
            <tr>
              <th class="px-4 py-3 text-left font-medium text-gray-500 w-16">类型</th>
              <th class="px-4 py-3 text-left font-medium text-gray-500">数值</th>
              <th class="px-4 py-3 text-left font-medium text-gray-500">来源文件</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-gray-100">
            <tr v-for="(item, i) in keyMetrics" :key="i" class="hover:bg-gray-50/60 transition-colors">
              <td class="px-4 py-3">
                <span class="inline-flex items-center gap-1.5 rounded-md bg-blue-50 px-2 py-0.5 text-xs font-medium text-blue-700">
                  {{ metricIcons[item.label] || '📊' }} {{ item.label }}
                </span>
              </td>
              <td class="px-4 py-3 font-mono text-gray-900 font-medium">{{ item.value }}</td>
              <td class="px-4 py-3 text-gray-500 truncate max-w-[200px]" :title="item.source">{{ item.source }}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <div v-else class="rounded-xl border border-dashed border-gray-200 px-6 py-8 text-center text-sm text-gray-400">
        未从已上传资料中提取到可量化的关键数字
      </div>
    </section>

    <!-- Table B: Gap Analysis -->
    <section>
      <h4 class="text-sm font-semibold text-gray-700 mb-3 tracking-wide uppercase">Table B · Gap Analysis（差距分析）</h4>
      <div v-if="gapAnalysis.length" class="overflow-hidden rounded-xl border border-gray-200">
        <table class="w-full text-sm">
          <thead class="bg-gray-50">
            <tr>
              <th class="px-4 py-3 text-left font-medium text-gray-500">必备材料</th>
              <th class="px-4 py-3 text-left font-medium text-gray-500 w-24">状态</th>
              <th class="px-4 py-3 text-left font-medium text-gray-500">说明</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-gray-100">
            <tr v-for="(item, i) in gapAnalysis" :key="i" class="hover:bg-gray-50/60 transition-colors">
              <td class="px-4 py-3 text-gray-900">{{ item.material }}</td>
              <td class="px-4 py-3">
                <span
                  class="inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold"
                  :class="[statusConfig[item.status]?.bg, statusConfig[item.status]?.text]"
                >
                  {{ statusConfig[item.status]?.badge || item.status }}
                </span>
              </td>
              <td class="px-4 py-3 text-gray-500 text-xs">{{ item.note }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>

    <!-- Table C: Data Flow -->
    <section>
      <h4 class="text-sm font-semibold text-gray-700 mb-3 tracking-wide uppercase">Table C · Data Flow（Step 联动）</h4>
      <div v-if="dataFlow.length" class="overflow-hidden rounded-xl border border-gray-200">
        <table class="w-full text-sm">
          <thead class="bg-gray-50">
            <tr>
              <th class="px-4 py-3 text-left font-medium text-gray-500">文件名</th>
              <th class="px-4 py-3 text-left font-medium text-gray-500 w-20">类型</th>
              <th class="px-4 py-3 text-left font-medium text-gray-500">将用于后续步骤</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-gray-100">
            <tr v-for="(item, i) in dataFlow" :key="i" class="hover:bg-gray-50/60 transition-colors">
              <td class="px-4 py-3 text-gray-900 font-medium truncate max-w-[220px]" :title="item.file_name">{{ item.file_name }}</td>
              <td class="px-4 py-3">
                <span class="inline-flex rounded-md bg-gray-100 px-2 py-0.5 text-xs text-gray-600">{{ item.file_type }}</span>
              </td>
              <td class="px-4 py-3">
                <div class="flex flex-wrap gap-1.5">
                  <span
                    v-for="step in item.target_steps"
                    :key="step"
                    class="inline-flex items-center rounded-md bg-indigo-50 px-2 py-0.5 text-xs font-medium text-indigo-700"
                  >
                    {{ step }}
                  </span>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
      <div v-else class="rounded-xl border border-dashed border-gray-200 px-6 py-8 text-center text-sm text-gray-400">
        暂无数据流向信息
      </div>
    </section>
  </div>
</template>
