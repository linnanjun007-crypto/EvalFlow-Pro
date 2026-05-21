<script setup lang="ts">
import { onMounted, ref } from 'vue'

export type TextSegment = {
  text: string
  italic?: boolean
}

const props = withDefaults(
  defineProps<{
    segments: TextSegment[]
    stagger?: number
  }>(),
  {
    stagger: 0.08,
  },
)

const visible = ref(false)

onMounted(() => {
  requestAnimationFrame(() => {
    visible.value = true
  })
})
</script>

<template>
  <h2 class="multi-style-heading">
    <template v-for="(segment, segIndex) in segments" :key="segIndex">
      <span
        v-for="(word, wordIndex) in segment.text.split(/(\s+)/).filter((w) => w.length > 0)"
        :key="`${segIndex}-${wordIndex}`"
        class="multi-style-heading__unit"
      >
        <span
          class="multi-style-heading__inner landing-ease"
          :class="[
            visible ? 'multi-style-heading__inner--visible' : '',
            segment.italic ? 'font-serif italic' : '',
          ]"
          :style="{
            transitionDelay: `${(segIndex * 6 + wordIndex) * stagger}s`,
          }"
        >{{ word.trim() === '' ? '\u00a0' : word }}</span>
      </span>
    </template>
  </h2>
</template>

<style scoped>
.multi-style-heading {
  margin: 0;
  font-family: var(--font-sans, 'Almarai', sans-serif);
  font-weight: 400;
  line-height: 1.15;
}

.multi-style-heading__unit {
  display: inline-block;
  overflow: hidden;
  vertical-align: bottom;
}

.multi-style-heading__inner {
  display: inline-block;
  transform: translateY(110%);
  opacity: 0;
  transition:
    transform 0.85s cubic-bezier(0.23, 1, 0.32, 1),
    opacity 0.65s cubic-bezier(0.23, 1, 0.32, 1);
}

.multi-style-heading__inner--visible {
  transform: translateY(0);
  opacity: 1;
}

@media (prefers-reduced-motion: reduce) {
  .multi-style-heading__inner {
    transform: none;
    opacity: 1;
    transition: none;
  }
}
</style>
