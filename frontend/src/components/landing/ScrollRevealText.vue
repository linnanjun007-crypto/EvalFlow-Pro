<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'

const props = defineProps<{
  text: string
}>()

const rootRef = ref<HTMLElement | null>(null)
const charOpacities = ref<number[]>([])

let rafId = 0

const updateOpacities = () => {
  const el = rootRef.value
  if (!el) return

  const rect = el.getBoundingClientRect()
  const viewport = window.innerHeight
  const start = viewport * 0.88
  const end = viewport * 0.32
  const range = Math.max(start - end, 1)
  const progress = Math.min(1, Math.max(0, (start - rect.top) / range))
  const chars = [...props.text]

  charOpacities.value = chars.map((_, index) => {
    const threshold = index / Math.max(chars.length - 1, 1)
    const local = Math.min(1, Math.max(0, (progress - threshold * 0.55) / 0.45))
    return 0.2 + local * 0.8
  })
}

const onScroll = () => {
  if (rafId) cancelAnimationFrame(rafId)
  rafId = requestAnimationFrame(() => {
    updateOpacities()
    rafId = 0
  })
}

onMounted(() => {
  charOpacities.value = [...props.text].map(() => 0.2)
  updateOpacities()
  window.addEventListener('scroll', onScroll, { passive: true })
  window.addEventListener('resize', onScroll, { passive: true })
})

onBeforeUnmount(() => {
  window.removeEventListener('scroll', onScroll)
  window.removeEventListener('resize', onScroll)
  if (rafId) cancelAnimationFrame(rafId)
})
</script>

<template>
  <p ref="rootRef" class="scroll-reveal-text">
    <span
      v-for="(char, index) in text"
      :key="`${char}-${index}`"
      class="scroll-reveal-text__char"
      :style="{ opacity: charOpacities[index] ?? 0.2 }"
    >{{ char }}</span>
  </p>
</template>

<style scoped>
.scroll-reveal-text {
  margin: 0;
  font-size: 1.125rem;
  line-height: 1.75;
  color: #1a1a1a;
}

.scroll-reveal-text__char {
  transition: opacity 0.12s ease-out;
}

@media (prefers-reduced-motion: reduce) {
  .scroll-reveal-text__char {
    opacity: 1 !important;
    transition: none;
  }
}
</style>
