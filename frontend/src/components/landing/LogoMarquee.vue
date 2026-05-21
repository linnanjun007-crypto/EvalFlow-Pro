<script setup lang="ts">
const logos = [
  'Klarna',
  'LinkedIn',
  'Coinbase',
  'Uber',
  'Lyft',
  'Gong',
  'Harvey',
  'Cloudflare',
  'Workday',
  'Cisco',
  'NVIDIA',
  'Monday.com',
  'Rippling',
  'Vanta',
  'Clay',
  'Mercor',
]
</script>

<template>
  <div class="marquee" aria-hidden="true">
    <div class="marquee__track">
      <span v-for="(name, i) in [...logos, ...logos]" :key="`${name}-${i}`" class="marquee__item">
        {{ name }}
      </span>
    </div>
  </div>
</template>

<style scoped>
.marquee {
  overflow: hidden;
  width: 100%;
  mask-image: linear-gradient(90deg, transparent, #000 8%, #000 92%, transparent);
}

.marquee__track {
  display: flex;
  width: max-content;
  gap: 3rem;
  animation: marquee-scroll 40s linear infinite;
}

.marquee__item {
  flex-shrink: 0;
  font-size: 1.125rem;
  font-weight: 600;
  letter-spacing: -0.02em;
  color: rgba(26, 26, 26, 0.35);
  white-space: nowrap;
}

@keyframes marquee-scroll {
  from {
    transform: translateX(0);
  }
  to {
    transform: translateX(-50%);
  }
}

@media (prefers-reduced-motion: reduce) {
  .marquee__track {
    animation: none;
    flex-wrap: wrap;
    justify-content: center;
    width: 100%;
  }
}
</style>
