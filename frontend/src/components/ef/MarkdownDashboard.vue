<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { createMarkdown, renderSafe } from '../../utils/markdownConfig'

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

interface SourceIndexEntry {
  ref_id: string
  source_name: string
  channel: string
  excerpt: string
  chunk_index?: number | null
}

const props = defineProps<{
  source: string
  keyMetrics?: KeyMetric[]
  gapItems?: GapItem[]
  sourceIndex?: SourceIndexEntry[]
}>()

const emit = defineEmits<{
  (e: 'request-upload', payload: { material: string }): void
  (e: 'step-click', step: number): void
}>()

const mdRoot = ref<HTMLElement | null>(null)
const md = createMarkdown()

const citePopoverVisible = ref(false)
const citePopoverTrigger = ref<HTMLElement | null>(null)
const citePopoverEntry = ref<SourceIndexEntry | null>(null)
const citePopoverRefId = ref<string>('')
let hideTimer: number | null = null

const sourceIndexMap = computed<Record<string, SourceIndexEntry>>(() => {
  const map: Record<string, SourceIndexEntry> = {}
  for (const entry of props.sourceIndex || []) {
    if (entry?.ref_id) map[entry.ref_id] = entry
  }
  return map
})

const channelLabel: Record<string, string> = {
  media: '图片 / PDF',
  documents: 'Word / Excel',
  kb: '知识库',
}

const iconMap: Record<string, string> = {
  '金额': '¥',
  '金额（亿）': '¥',
  '人数': '👥',
  '面积': '📐',
  '距离': '📏',
  '数量': '#',
  '年份': '📅',
}

function iconFor(label: string): string {
  return iconMap[label] || '📊'
}

const badgeConfig: Record<string, { cls: string; text: string }> = {
  success: { cls: 'bg-emerald-50 text-emerald-700', text: '已覆盖' },
  error: { cls: 'bg-red-50 text-red-700', text: '缺失' },
  warning: { cls: 'bg-amber-50 text-amber-700', text: '待确认' },
}

function badgeClass(status: string): string {
  return badgeConfig[status]?.cls || 'bg-gray-100 text-gray-600'
}
function badgeText(status: string): string {
  return badgeConfig[status]?.text || status
}

function stripSection(md: string, headingPattern: RegExp): string {
  const lines = md.split(/\r?\n/)
  const result: string[] = []
  let skipping = false
  for (const line of lines) {
    if (skipping) {
      const isNextHeading = /^(#{1,6}\s|##\s|\*\*[一二三四五六七八九十]+、)/.test(line.trim())
      const isAnotherTopLevel = headingPattern.test(line)
      if (isAnotherTopLevel) {
        skipping = false
        result.push(line)
        continue
      }
      if (isNextHeading && !line.match(/^(\s*-\s|\s*\d+\.\s)/)) {
        skipping = false
        result.push(line)
        continue
      }
      continue
    }
    if (headingPattern.test(line)) {
      skipping = true
      continue
    }
    result.push(line)
  }
  return result.join('\n')
}

const filteredHtml = computed(() => {
  let src = props.source || ''
  if (props.keyMetrics?.length) {
    src = stripSection(src, /^(##?\s*)?(\*\*)?[二2][、.\s]*\s*关键数字汇总/)
  }
  if (props.gapItems?.length) {
    src = stripSection(src, /^(##?\s*)?(\*\*)?[三3][、.\s]*\s*Gap\s*Analysis/i)
  }
  if (!src.trim()) return ''
  return renderSafe(md, src)
})

function handleClick(ev: Event) {
  const target = ev.target as HTMLElement | null
  if (!target) return
  const stepEl = target.closest('[data-ef-step]') as HTMLElement | null
  if (stepEl) {
    const n = Number(stepEl.dataset.efStep)
    if (n) emit('step-click', n)
  }
}

function showCitePopover(el: HTMLElement, refId: string) {
  if (hideTimer) { clearTimeout(hideTimer); hideTimer = null }
  const entry = sourceIndexMap.value[refId]
  if (!entry) return
  citePopoverTrigger.value = el
  citePopoverEntry.value = entry
  citePopoverRefId.value = refId
  citePopoverVisible.value = true
}

function scheduleCiteHide() {
  hideTimer = window.setTimeout(() => {
    citePopoverVisible.value = false
    citePopoverTrigger.value = null
  }, 150)
}

function cancelCiteHide() {
  if (hideTimer) { clearTimeout(hideTimer); hideTimer = null }
}

function handleMouseOver(ev: Event) {
  const target = ev.target as HTMLElement | null
  if (!target) return
  const citeEl = target.closest('[data-ef-cite]') as HTMLElement | null
  if (citeEl) {
    const refId = citeEl.dataset.efCite || ''
    showCitePopover(citeEl, refId)
  }
}

function handleMouseOut(ev: Event) {
  const target = ev.target as HTMLElement | null
  if (!target) return
  const citeEl = target.closest('[data-ef-cite]') as HTMLElement | null
  if (citeEl) scheduleCiteHide()
}

onMounted(() => {
  mdRoot.value?.addEventListener('click', handleClick)
  mdRoot.value?.addEventListener('mouseover', handleMouseOver)
  mdRoot.value?.addEventListener('mouseout', handleMouseOut)
})
onBeforeUnmount(() => {
  mdRoot.value?.removeEventListener('click', handleClick)
  mdRoot.value?.removeEventListener('mouseover', handleMouseOver)
  mdRoot.value?.removeEventListener('mouseout', handleMouseOut)
  if (hideTimer) clearTimeout(hideTimer)
})
</script>

<template>
  <section class="rounded-2xl bg-white shadow-sm ring-1 ring-gray-200 overflow-hidden">
    <header class="px-6 py-4 border-b border-gray-100 flex items-center justify-between">
      <h3 class="text-base font-semibold text-gray-900">资料清单 · Markdown 看板</h3>
      <span class="text-xs text-gray-400">由 LLM 生成，已过 markdown 清洗</span>
    </header>

    <div v-if="keyMetrics?.length" class="px-6 py-5">
      <h4 class="text-xs font-semibold text-gray-500 tracking-wide mb-3">关键数字汇总</h4>
      <div class="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3">
        <div
          v-for="(m, i) in keyMetrics"
          :key="m.label + m.value + i"
          class="rounded-xl bg-gradient-to-br from-blue-50 to-white ring-1 ring-blue-100 p-4"
        >
          <div class="flex items-center gap-2 text-xs text-gray-500">
            <span class="text-lg">{{ iconFor(m.label) }}</span>
            <span>{{ m.label }}</span>
          </div>
          <div class="mt-2 text-xl font-bold font-mono text-gray-900 break-all">{{ m.value }}</div>
          <div class="mt-1 text-xs text-gray-400 truncate" :title="m.source">{{ m.source }}</div>
        </div>
      </div>
    </div>

    <div v-if="gapItems?.length" class="px-6 py-5 border-t border-gray-100">
      <h4 class="text-xs font-semibold text-gray-500 tracking-wide mb-3">差距分析</h4>
      <ul class="space-y-2">
        <li
          v-for="g in gapItems"
          :key="g.material"
          class="flex items-center justify-between rounded-lg bg-gray-50 px-4 py-3 gap-3"
        >
          <div class="flex items-center gap-3 min-w-0 flex-1">
            <span
              class="rounded-full px-2 py-0.5 text-xs font-semibold shrink-0"
              :class="badgeClass(g.status)"
            >{{ badgeText(g.status) }}</span>
            <span class="text-sm text-gray-900 truncate">{{ g.material }}</span>
            <span class="text-xs text-gray-400 truncate hidden md:inline">{{ g.note }}</span>
          </div>
          <button
            v-if="g.status === 'error'"
            type="button"
            class="text-xs px-3 py-1 rounded-md bg-red-50 text-red-700 hover:bg-red-100 transition shrink-0"
            @click="emit('request-upload', { material: g.material })"
          >补齐资料</button>
        </li>
      </ul>
    </div>

    <article
      v-if="filteredHtml"
      ref="mdRoot"
      class="ef-md-prose px-6 py-5 border-t border-gray-100"
      v-html="filteredHtml"
    />
    <div
      v-else-if="!keyMetrics?.length && !gapItems?.length"
      class="px-6 py-10 text-center text-sm text-gray-400"
    >暂无可预览的 Markdown 内容</div>

    <el-popover
      :visible="citePopoverVisible"
      :virtual-ref="citePopoverTrigger || undefined"
      virtual-triggering
      placement="top"
      :width="360"
      :show-arrow="true"
      popper-class="ef-cite-popover"
    >
      <div
        v-if="citePopoverEntry"
        class="ef-cite-card"
        @mouseenter="cancelCiteHide"
        @mouseleave="scheduleCiteHide"
      >
        <div class="ef-cite-head">
          <span class="ef-cite-tag">{{ citePopoverRefId }}</span>
          <span class="ef-cite-channel" :class="`ch-${citePopoverEntry.channel}`">
            {{ channelLabel[citePopoverEntry.channel] || citePopoverEntry.channel }}
            <template v-if="citePopoverEntry.channel === 'kb' && citePopoverEntry.chunk_index != null">
              · 第 {{ Number(citePopoverEntry.chunk_index) + 1 }} 段
            </template>
          </span>
        </div>
        <div class="ef-cite-name" :title="citePopoverEntry.source_name">{{ citePopoverEntry.source_name || '未命名来源' }}</div>
        <div class="ef-cite-excerpt">{{ (citePopoverEntry.excerpt || '').slice(0, 300) }}<span v-if="(citePopoverEntry.excerpt || '').length > 300">…</span></div>
      </div>
    </el-popover>
  </section>
</template>

<style scoped>
.ef-md-prose :deep(.ef-md-table-wrap) {
  overflow-x: auto;
  border-radius: 8px;
  border: 1px solid rgb(229 231 235);
  margin: 12px 0;
}
.ef-md-prose :deep(table) {
  width: 100%;
  font-size: 13px;
  border-collapse: collapse;
}
.ef-md-prose :deep(thead) {
  background: rgb(243 244 246);
}
.ef-md-prose :deep(thead th) {
  padding: 10px 14px;
  text-align: left;
  font-weight: 600;
  color: rgb(55 65 81);
  border-bottom: 1px solid rgb(229 231 235);
  white-space: nowrap;
}
.ef-md-prose :deep(tbody tr:nth-child(even)) {
  background: rgb(249 250 251 / 0.6);
}
.ef-md-prose :deep(tbody tr:hover) {
  background: rgb(243 244 246 / 0.7);
}
.ef-md-prose :deep(tbody td) {
  padding: 10px 14px;
  color: rgb(55 65 81);
  border-bottom: 1px solid rgb(243 244 246);
  vertical-align: top;
}
.ef-md-prose :deep([data-ef-step]) {
  display: inline-flex;
  align-items: center;
  border-radius: 6px;
  background: rgb(238 242 255);
  padding: 1px 8px;
  font-size: 12px;
  font-weight: 500;
  color: rgb(67 56 202);
  cursor: pointer;
  transition: background 0.15s;
  margin: 0 2px;
  border: none;
}
.ef-md-prose :deep([data-ef-step]:hover) {
  background: rgb(224 231 255);
}
.ef-md-prose :deep([data-ef-gap-badge]) {
  display: inline-flex;
  align-items: center;
  border-radius: 9999px;
  background: rgb(254 226 226);
  padding: 1px 8px;
  font-size: 12px;
  font-weight: 700;
  color: rgb(185 28 28);
  margin: 0 2px;
}
.ef-md-prose :deep([data-ef-cite]) {
  display: inline-flex;
  align-items: center;
  border-radius: 6px;
  background: rgb(240 253 244);
  padding: 1px 6px;
  font-size: 11px;
  font-weight: 600;
  color: rgb(21 128 61);
  cursor: help;
  transition: background 0.15s, transform 0.15s;
  margin: 0 2px;
  border: 1px solid rgb(187 247 208);
  vertical-align: baseline;
}
.ef-md-prose :deep([data-ef-cite]:hover),
.ef-md-prose :deep([data-ef-cite]:focus-visible) {
  background: rgb(220 252 231);
  transform: translateY(-1px);
  outline: none;
}
.ef-md-prose :deep(h1) {
  font-size: 16px;
  font-weight: 700;
  color: rgb(17 24 39);
  margin: 16px 0 10px;
}
.ef-md-prose :deep(h2) {
  font-size: 14px;
  font-weight: 600;
  color: rgb(17 24 39);
  margin: 14px 0 8px;
}
.ef-md-prose :deep(h3) {
  font-size: 13px;
  font-weight: 600;
  color: rgb(31 41 55);
  margin: 12px 0 6px;
}
.ef-md-prose :deep(strong) {
  font-weight: 600;
  color: rgb(17 24 39);
}
.ef-md-prose :deep(p) {
  margin: 6px 0;
  font-size: 13px;
  color: rgb(55 65 81);
  line-height: 1.6;
}
.ef-md-prose :deep(ul),
.ef-md-prose :deep(ol) {
  padding-left: 20px;
  margin: 6px 0;
}
.ef-md-prose :deep(ul) { list-style: disc; }
.ef-md-prose :deep(ol) { list-style: decimal; }
.ef-md-prose :deep(li) {
  font-size: 13px;
  color: rgb(55 65 81);
  line-height: 1.6;
  margin: 2px 0;
}
.ef-md-prose :deep(code) {
  background: rgb(243 244 246);
  padding: 1px 6px;
  border-radius: 4px;
  font-size: 12px;
  font-family: ui-monospace, SFMono-Regular, monospace;
  color: rgb(55 65 81);
}
</style>

<style>
.ef-cite-popover.el-popover {
  --el-popover-padding: 0;
  padding: 0 !important;
  border-radius: 10px !important;
  border: 1px solid rgb(229 231 235) !important;
  box-shadow: 0 12px 24px -8px rgb(15 23 42 / 0.18) !important;
}
.ef-cite-card {
  padding: 12px 14px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.ef-cite-head {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.ef-cite-tag {
  display: inline-flex;
  align-items: center;
  background: rgb(220 252 231);
  color: rgb(21 128 61);
  border: 1px solid rgb(187 247 208);
  border-radius: 6px;
  padding: 1px 8px;
  font-size: 12px;
  font-weight: 700;
  font-family: ui-monospace, SFMono-Regular, monospace;
}
.ef-cite-channel {
  display: inline-flex;
  align-items: center;
  font-size: 11px;
  font-weight: 500;
  padding: 2px 8px;
  border-radius: 9999px;
  background: rgb(243 244 246);
  color: rgb(75 85 99);
}
.ef-cite-channel.ch-media { background: rgb(254 243 199); color: rgb(146 64 14); }
.ef-cite-channel.ch-documents { background: rgb(219 234 254); color: rgb(30 64 175); }
.ef-cite-channel.ch-kb { background: rgb(237 233 254); color: rgb(91 33 182); }
.ef-cite-name {
  font-size: 13px;
  font-weight: 600;
  color: rgb(17 24 39);
  word-break: break-all;
  line-height: 1.4;
}
.ef-cite-excerpt {
  font-size: 12px;
  color: rgb(75 85 99);
  line-height: 1.6;
  max-height: 180px;
  overflow-y: auto;
  white-space: pre-wrap;
  background: rgb(249 250 251);
  border-radius: 6px;
  padding: 8px 10px;
  border: 1px solid rgb(243 244 246);
}
</style>
