<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

const props = withDefaults(
  defineProps<{
    text: string
    as?: 'h1' | 'h2' | 'p' | 'span'
    stagger?: number
    by?: 'word' | 'char'
  }>(),
  {
    as: 'h1',
    stagger: 0.08,
    by: 'char',
  },
)

const visible = ref(false)
const units = computed(() => {
  if (props.by === 'word') return props.text.split(/(\s+)/).filter((u) => u.length > 0)
  return [...props.text]
})

onMounted(() => {
  requestAnimationFrame(() => {
    visible.value = true
  })
})
</script>

<template>
  <component :is="as" class="words-pull-up">
    <span
      v-for="(unit, index) in units"
      :key="`${unit}-${index}`"
      class="words-pull-up__unit"
      :class="{ 'words-pull-up__space': unit.trim() === '' }"
    >
      <span
        class="words-pull-up__inner landing-ease"
        :class="visible ? 'words-pull-up__inner--visible' : ''"
        :style="{ transitionDelay: `${index * stagger}s` }"
      >{{ unit === ' ' ? '\u00a0' : unit }}</span>
    </span>
  </component>
</template>

<style scoped>
.words-pull-up {
  margin: 0;
}

.words-pull-up__unit {
  display: inline-block;
  overflow: hidden;
  vertical-align: bottom;
}

.words-pull-up__inner {
  display: inline-block;
  transform: translateY(110%);
  opacity: 0;
  transition:
    transform 0.85s cubic-bezier(0.23, 1, 0.32, 1),
    opacity 0.65s cubic-bezier(0.23, 1, 0.32, 1);
}

.words-pull-up__inner--visible {
  transform: translateY(0);
  opacity: 1;
}

@media (prefers-reduced-motion: reduce) {
  .words-pull-up__inner {
    transform: none;
    opacity: 1;
    transition: none;
  }
}
</style>
