<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'

const props = withDefaults(
  defineProps<{
    delay?: number
    y?: number
  }>(),
  {
    delay: 0,
    y: 24,
  },
)

const rootRef = ref<HTMLElement | null>(null)
const visible = ref(false)

let observer: IntersectionObserver | null = null

onMounted(() => {
  const prefersReduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches
  if (prefersReduced) {
    visible.value = true
    return
  }

  observer = new IntersectionObserver(
    ([entry]) => {
      if (entry?.isIntersecting) {
        visible.value = true
        observer?.disconnect()
      }
    },
    { threshold: 0.15, rootMargin: '0px 0px -8% 0px' },
  )

  if (rootRef.value) observer.observe(rootRef.value)
})

onBeforeUnmount(() => {
  observer?.disconnect()
})
</script>

<template>
  <div
    ref="rootRef"
    class="reveal-on-scroll landing-ease"
    :class="visible ? 'reveal-on-scroll--visible' : ''"
    :style="{
      transitionDelay: `${delay}s`,
      '--reveal-y': `${y}px`,
    }"
  >
    <slot />
  </div>
</template>

<style scoped>
.reveal-on-scroll {
  opacity: 0;
  transform: translateY(var(--reveal-y, 24px));
  transition:
    opacity 0.75s cubic-bezier(0.23, 1, 0.32, 1),
    transform 0.75s cubic-bezier(0.23, 1, 0.32, 1);
}

.reveal-on-scroll--visible {
  opacity: 1;
  transform: translateY(0);
}

@media (prefers-reduced-motion: reduce) {
  .reveal-on-scroll {
    opacity: 1;
    transform: none;
    transition: none;
  }
}
</style>
