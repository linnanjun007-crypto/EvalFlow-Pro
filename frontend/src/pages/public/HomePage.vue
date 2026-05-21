<script setup lang="ts">
import { ref } from 'vue'
import { RouterLink } from 'vue-router'
import LogoMarquee from '../../components/landing/LogoMarquee.vue'
import HeroIllustration from '../../components/landing/HeroIllustration.vue'

const featureVideo =
  'https://d8j0ntlcm91z4.cloudfront.net/user_38xzZboKViGWJOttwIXH07lWA1P/hf_20260329_050842_be71947f-f16e-4a14-810c-06e83d23ddb5.mp4'

const helpFeatures = [
  {
    id: 'human-loop',
    title: '人机协同把关，掌控每一步评价',
    description:
      '在关键节点加入人工审核与批注，防止 AI 偏离评价标准。支持步骤级审批、回退与修订，让流程始终可控。',
    link: '#features',
    linkText: '了解人机协同',
    dark: true,
    video: featureVideo,
  },
  {
    id: 'workflow',
    title: '可编排的 14 步评价工作流',
    description:
      '从项目创建到报告导出，以低层级步骤编排支撑复杂业务。单项目、多角色、层级审批，一套框架全覆盖。',
    link: '/register',
    linkText: '查看工作流架构',
    dark: false,
  },
  {
    id: 'memory',
    title: '持久化记忆与历史回溯',
    description:
      '对话、生成结果与版本变更全量留存，跨会话保持上下文。随时回溯任意步骤，支撑审计与复盘。',
    link: '#features',
    linkText: '了解历史中心',
    dark: false,
  },
  {
    id: 'streaming',
    title: '流式输出，实时可见推理过程',
    description:
      'Token 级流式展示生成进度，让评价依据与推理链路对用户透明，显著提升协作体验。',
    link: '#features',
    linkText: '查看流式能力',
    dark: false,
  },
]

const testimonials = [
  {
    quote:
      'EvalFlow Pro 让我们在 14 步绩效评价闭环中实现了可追溯的 AI 协作。从模型对比到报告导出，团队迭代速度提升了一个数量级。',
    name: '张明',
    role: '评价业务负责人',
  },
  {
    quote:
      '人机协同与审计日志是我们选型的重要原因。复杂评价任务不再依赖黑盒输出，每一步都有据可查。',
    name: '李薇',
    role: '信息化主管',
  },
  {
    quote:
      '管理端的模型配置与 Prompt 知识库，让我们能快速适配不同评价场景，而不必重写整套系统。',
    name: '王浩',
    role: '技术架构师',
  },
]

const faqs = [
  {
    q: 'EvalFlow Pro 与其他 AI 评价工具有何不同？',
    a: '我们专注绩效评价的 14 步闭环，提供步骤级编排、多模型对比、人机协同与全链路审计，而非通用聊天机器人。',
  },
  {
    q: '是否会影响现有系统的性能？',
    a: '前端采用按需加载与流式响应，后端异步处理长任务。评价流程中的 AI 调用可配置超时与并发上限。',
  },
  {
    q: '是否支持私有化部署？',
    a: '支持标准 Web 部署架构，可与企业内网、自有模型 API 对接。具体部署方案请联系团队获取说明。',
  },
  {
    q: '免费试用如何开始？',
    a: '注册账号即可创建首个评价项目，体验完整 14 步流程。管理端功能需相应权限角色开通。',
  },
]

const openFaq = ref<number | null>(0)

const toggleFaq = (index: number) => {
  openFaq.value = openFaq.value === index ? null : index
}
</script>

<template>
  <div class="lg-page">
    <!-- NAV -->
    <header class="lg-nav">
      <div class="lg-container lg-nav__inner">
        <RouterLink to="/" class="lg-nav__brand">
          <span class="lg-nav__brand-icon" aria-hidden="true">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none">
              <rect x="3" y="3" width="7" height="7" rx="1.5" fill="currentColor" />
              <rect x="14" y="3" width="7" height="7" rx="1.5" fill="currentColor" opacity="0.6" />
              <rect x="3" y="14" width="7" height="7" rx="1.5" fill="currentColor" opacity="0.6" />
              <rect x="14" y="14" width="7" height="7" rx="1.5" fill="currentColor" opacity="0.35" />
            </svg>
          </span>
          EvalFlow Pro
        </RouterLink>

        <nav class="lg-nav__links" aria-label="主导航">
          <a href="#features">产品能力</a>
          <a href="#workflow">工作流</a>
          <a href="#academy">入门指南</a>
          <a href="#faq">常见问题</a>
        </nav>

        <div class="lg-nav__actions">
          <RouterLink to="/login" class="lg-btn lg-btn--ghost">登录</RouterLink>
          <RouterLink to="/register" class="lg-btn lg-btn--primary">免费试用</RouterLink>
        </div>
      </div>
    </header>

    <!-- HERO -->
    <section class="lg-hero">
      <div class="lg-container lg-hero__grid">
        <div class="lg-hero__content">
          <div class="lg-product-badge">
            <span class="lg-product-badge__icon" aria-hidden="true">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none">
                <circle cx="6" cy="6" r="2" fill="currentColor" />
                <circle cx="18" cy="6" r="2" fill="currentColor" />
                <circle cx="6" cy="18" r="2" fill="currentColor" />
                <circle cx="18" cy="18" r="2" fill="currentColor" />
              </svg>
            </span>
            <span class="lg-product-badge__label">evalflow pro</span>
          </div>

          <h1 class="lg-hero__title">平衡流程管控与智能协作</h1>

          <p class="lg-hero__subtitle">
            用 EvalFlow Pro 构建可靠、可审计的绩效评价 Agent 工作流——从项目创建到 14
            步报告生成，兼顾自动化效率与人工把关。
          </p>

          <div class="lg-hero__cta">
            <RouterLink to="/register" class="lg-btn lg-btn--solid">开始构建</RouterLink>
            <a href="#features" class="lg-btn lg-btn--outline">阅读文档</a>
          </div>
        </div>

        <div class="lg-hero__visual">
          <HeroIllustration />
        </div>
      </div>
    </section>

    <!-- LOGOS -->
    <section class="lg-logos">
      <div class="lg-container lg-logos__inner">
        <h2 class="lg-logos__title">深受领先团队信赖的 AI 评价平台</h2>
        <a href="#features" class="lg-link-arrow lg-logos__link">查看生产案例</a>
      </div>
      <LogoMarquee />
    </section>

    <!-- HOW IT HELPS -->
    <section id="workflow" class="lg-section-heading">
      <div class="lg-container">
        <h2 class="lg-section-heading__title">EvalFlow Pro 如何帮助你？</h2>
      </div>
    </section>

    <!-- FEATURE CARDS -->
    <section id="features" class="lg-features">
      <div class="lg-container lg-features__stack">
        <article
          v-for="(feature, index) in helpFeatures"
          :key="feature.id"
          class="lg-feature-card"
          :class="[
            feature.dark ? 'lg-feature-card--dark' : 'lg-feature-card--light',
            index === 0 ? 'lg-feature-card--hero' : '',
          ]"
        >
          <div class="lg-feature-card__content">
            <h3 class="lg-feature-card__title">{{ feature.title }}</h3>
            <p class="lg-feature-card__desc">{{ feature.description }}</p>
            <a :href="feature.link" class="lg-link-arrow">{{ feature.linkText }}</a>
          </div>

          <div v-if="feature.video" class="lg-feature-card__media">
            <video
              class="lg-feature-card__video"
              :src="feature.video"
              autoplay
              loop
              muted
              playsinline
            />
          </div>
          <div v-else class="lg-feature-card__placeholder" aria-hidden="true">
            <div class="lg-feature-card__placeholder-inner">
              <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
                <rect x="3" y="3" width="18" height="18" rx="3" />
                <path d="M3 9h18M9 21V9" />
              </svg>
            </div>
          </div>
        </article>
      </div>
    </section>

    <!-- ACADEMY -->
    <section id="academy" class="lg-academy">
      <div class="lg-container lg-academy__card">
        <div class="lg-academy__content">
          <p class="lg-academy__eyebrow">入门 · EvalFlow Academy</p>
          <h2 class="lg-academy__title">基础：14 步评价工作流导览</h2>
          <p class="lg-academy__desc">
            了解如何创建项目、配置模型、运行各步骤生成与导出报告。涵盖人机协同、历史回溯与用量统计。
          </p>
          <RouterLink to="/register" class="lg-btn lg-btn--solid lg-btn--on-dark">免费注册体验</RouterLink>
        </div>
        <div class="lg-academy__preview" aria-hidden="true">
          <div class="lg-academy__preview-bar">
            <span /><span /><span />
          </div>
          <div class="lg-academy__preview-body">
            <div class="lg-academy__preview-line lg-academy__preview-line--long" />
            <div class="lg-academy__preview-line" />
            <div class="lg-academy__preview-line" />
            <div class="lg-academy__preview-line lg-academy__preview-line--short" />
          </div>
        </div>
      </div>
    </section>

    <!-- TESTIMONIALS -->
    <section class="lg-testimonials">
      <div class="lg-container">
        <h2 class="lg-testimonials__title">开发者与业务团队信赖 EvalFlow Pro</h2>
        <p class="lg-testimonials__subtitle">
          快速接入任意模型供应商，在高层抽象与细粒度控制之间自由切换。
        </p>

        <div class="lg-testimonials__grid">
          <blockquote
            v-for="item in testimonials"
            :key="item.name"
            class="lg-testimonial-card"
          >
            <p class="lg-testimonial-card__quote">"{{ item.quote }}"</p>
            <footer class="lg-testimonial-card__author">
              <strong>{{ item.name }}</strong>
              <span>{{ item.role }}</span>
            </footer>
          </blockquote>
        </div>
      </div>
    </section>

    <!-- FAQ -->
    <section id="faq" class="lg-faq">
      <div class="lg-container lg-faq__grid">
        <h2 class="lg-faq__title">EvalFlow Pro 常见问题</h2>

        <div class="lg-faq__list">
          <div
            v-for="(item, index) in faqs"
            :key="item.q"
            class="lg-faq__item"
            :class="{ 'lg-faq__item--open': openFaq === index }"
          >
            <button
              type="button"
              class="lg-faq__question"
              :aria-expanded="openFaq === index"
              @click="toggleFaq(index)"
            >
              <span>{{ item.q }}</span>
              <span class="lg-faq__icon" aria-hidden="true">{{ openFaq === index ? '−' : '+' }}</span>
            </button>
            <div v-show="openFaq === index" class="lg-faq__answer">
              <p>{{ item.a }}</p>
            </div>
          </div>
        </div>
      </div>
    </section>

    <!-- CTA -->
    <section class="lg-cta">
      <div class="lg-container lg-cta__inner">
        <h2 class="lg-cta__title">看清 Agent 的每一步决策</h2>
        <p class="lg-cta__desc">
          EvalFlow Pro 帮你调试每一次生成、评估模型变更，并一键导出可追溯的评价报告。
        </p>
        <div class="lg-cta__actions">
          <RouterLink to="/register" class="lg-btn lg-btn--solid lg-btn--on-dark">开始构建</RouterLink>
          <RouterLink to="/login" class="lg-btn lg-btn--outline lg-btn--on-dark">登录控制台</RouterLink>
        </div>
      </div>
    </section>

    <!-- FOOTER -->
    <footer class="lg-footer">
      <div class="lg-container lg-footer__grid">
        <div class="lg-footer__brand-col">
          <div class="lg-footer__brand">EvalFlow Pro</div>
          <p class="lg-footer__tagline">绩效评价 AI 协作工作台</p>
        </div>
        <div>
          <h4 class="lg-footer__heading">产品</h4>
          <a href="#features">工作流</a>
          <a href="#academy">入门指南</a>
          <RouterLink to="/register">注册</RouterLink>
        </div>
        <div>
          <h4 class="lg-footer__heading">资源</h4>
          <a href="#faq">文档</a>
          <a href="#features">案例</a>
          <RouterLink to="/login">登录</RouterLink>
        </div>
        <div>
          <h4 class="lg-footer__heading">公司</h4>
          <a href="#academy">关于</a>
          <a href="#faq">支持</a>
        </div>
      </div>
      <div class="lg-container lg-footer__bottom">
        <p>© {{ new Date().getFullYear() }} EvalFlow Pro. All rights reserved.</p>
      </div>
    </footer>
  </div>
</template>

<style scoped>
.lg-page {
  --lg-bg: #f5f2ed;
  --lg-text: #1a1a1a;
  --lg-blue: #2563eb;
  --lg-blue-heading: #1d4ed8;
  --lg-muted: #64748b;
  --lg-border: rgba(26, 26, 26, 0.1);
  --lg-dark: #0f1419;
  --lg-dark-2: #0d1322;
  --lg-light-band: #eef4f8;
  --lg-card: #ffffff;

  min-height: 100vh;
  background: var(--lg-bg);
  color: var(--lg-text);
  font-family: 'Inter', ui-sans-serif, system-ui, sans-serif;
  font-size: 17px;
  line-height: 1.5;
}

.lg-container {
  width: 100%;
  max-width: 1200px;
  margin: 0 auto;
  padding-left: 1.5rem;
  padding-right: 1.5rem;
}

/* NAV */
.lg-nav {
  position: sticky;
  top: 0;
  z-index: 50;
  background: color-mix(in srgb, var(--lg-bg) 92%, transparent);
  backdrop-filter: blur(12px);
  border-bottom: 1px solid var(--lg-border);
}

.lg-nav__inner {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1.5rem;
  height: 64px;
}

.lg-nav__brand {
  display: inline-flex;
  align-items: center;
  gap: 0.5rem;
  font-weight: 600;
  font-size: 1rem;
  color: var(--lg-text);
  text-decoration: none;
}

.lg-nav__brand-icon {
  display: flex;
  color: var(--lg-blue);
}

.lg-nav__links {
  display: none;
  align-items: center;
  gap: 1.75rem;
  font-size: 0.9375rem;
  font-weight: 500;
}

.lg-nav__links a {
  color: var(--lg-muted);
  text-decoration: none;
  transition: color 0.2s;
}

.lg-nav__links a:hover {
  color: var(--lg-text);
}

.lg-nav__actions {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

/* BUTTONS */
.lg-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 0.65rem 1.15rem;
  border-radius: 6px;
  font-size: 0.9375rem;
  font-weight: 500;
  text-decoration: none;
  cursor: pointer;
  transition:
    background 0.2s,
    border-color 0.2s,
    opacity 0.2s;
  border: 1px solid transparent;
  white-space: nowrap;
}

.lg-btn--ghost {
  color: var(--lg-text);
  background: transparent;
}

.lg-btn--ghost:hover {
  background: rgba(26, 26, 26, 0.05);
}

.lg-btn--primary {
  background: var(--lg-text);
  color: #fff;
}

.lg-btn--primary:hover {
  opacity: 0.88;
}

.lg-btn--solid {
  background: #dbeafe;
  color: var(--lg-dark);
  border-color: transparent;
}

.lg-btn--solid:hover {
  background: #bfdbfe;
}

.lg-btn--outline {
  background: transparent;
  color: var(--lg-text);
  border-color: rgba(26, 26, 26, 0.22);
}

.lg-btn--outline:hover {
  border-color: rgba(26, 26, 26, 0.4);
  background: rgba(255, 255, 255, 0.5);
}

.lg-btn--on-dark.lg-btn--solid {
  background: #e5f4ff;
  color: var(--lg-dark);
}

.lg-btn--on-dark.lg-btn--outline {
  color: #cce9ff;
  border-color: rgba(204, 233, 255, 0.35);
}

.lg-btn--on-dark.lg-btn--outline:hover {
  background: rgba(255, 255, 255, 0.06);
}

.lg-link-arrow {
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  font-size: 0.9375rem;
  font-weight: 500;
  color: var(--lg-blue);
  text-decoration: none;
}

.lg-link-arrow::after {
  content: '→';
  transition: transform 0.2s;
}

.lg-link-arrow:hover::after {
  transform: translateX(3px);
}

/* HERO */
.lg-hero {
  padding: 3.5rem 0 4rem;
}

.lg-hero__grid {
  display: grid;
  gap: 3rem;
  align-items: center;
}

.lg-product-badge {
  display: inline-flex;
  align-items: center;
  gap: 0.5rem;
  margin-bottom: 1rem;
}

.lg-product-badge__icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 2rem;
  height: 2rem;
  border-radius: 6px;
  background: rgba(37, 99, 235, 0.12);
  color: var(--lg-blue);
}

.lg-product-badge__label {
  font-size: 0.875rem;
  font-weight: 500;
  color: var(--lg-blue-heading);
  letter-spacing: 0.02em;
}

.lg-hero__title {
  margin: 0 0 1.5rem;
  font-size: clamp(2.5rem, 5.5vw, 4.25rem);
  font-weight: 300;
  line-height: 1.05;
  letter-spacing: -0.03em;
  color: var(--lg-blue-heading);
}

.lg-hero__subtitle {
  max-width: 34rem;
  margin: 0 0 2rem;
  font-size: 1.0625rem;
  line-height: 1.6;
  color: var(--lg-muted);
}

.lg-hero__cta {
  display: flex;
  flex-wrap: wrap;
  gap: 0.75rem;
}

.lg-hero__visual {
  display: flex;
  justify-content: center;
  align-items: center;
}

/* LOGOS */
.lg-logos {
  padding: 2.5rem 0 3.5rem;
  border-top: 1px solid var(--lg-border);
}

.lg-logos__inner {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  justify-content: space-between;
  gap: 1rem;
  margin-bottom: 2rem;
}

.lg-logos__title {
  margin: 0;
  font-size: 1.125rem;
  font-weight: 500;
  color: var(--lg-blue-heading);
}

.lg-logos__link {
  font-size: 0.875rem;
}

/* SECTION HEADING */
.lg-section-heading {
  padding: 2rem 0 1.5rem;
}

.lg-section-heading__title {
  margin: 0;
  font-size: clamp(1.75rem, 3vw, 2.25rem);
  font-weight: 400;
  text-align: center;
  color: var(--lg-blue-heading);
}

/* FEATURES */
.lg-features {
  padding-bottom: 4rem;
}

.lg-features__stack {
  display: flex;
  flex-direction: column;
  gap: 1.25rem;
}

.lg-feature-card {
  display: grid;
  gap: 0;
  border-radius: 20px;
  overflow: hidden;
}

.lg-feature-card--hero {
  grid-template-columns: 1fr;
}

.lg-feature-card--dark {
  background: var(--lg-dark-2);
  color: #e5f4ff;
}

.lg-feature-card--light {
  background: var(--lg-card);
  border: 1px solid var(--lg-border);
  box-shadow: 0 1px 3px rgba(15, 23, 42, 0.04);
}

.lg-feature-card__content {
  padding: 2.5rem 2rem;
}

.lg-feature-card--hero .lg-feature-card__content {
  padding: 2.5rem 2rem 1.5rem;
}

.lg-feature-card__title {
  margin: 0 0 1.5rem;
  font-size: clamp(1.375rem, 2.5vw, 1.75rem);
  font-weight: 400;
  line-height: 1.25;
  letter-spacing: -0.02em;
}

.lg-feature-card--dark .lg-feature-card__title {
  color: #fff;
}

.lg-feature-card__desc {
  margin: 0 0 1.5rem;
  font-size: 1rem;
  line-height: 1.65;
  max-width: 36rem;
}

.lg-feature-card--dark .lg-feature-card__desc {
  color: rgba(229, 244, 255, 0.65);
}

.lg-feature-card--light .lg-feature-card__desc {
  color: var(--lg-muted);
}

.lg-feature-card--dark .lg-link-arrow {
  color: #93c5fd;
}

.lg-feature-card__media {
  aspect-ratio: 16 / 9;
  background: #000;
}

.lg-feature-card__video {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.lg-feature-card__placeholder {
  min-height: 200px;
  background: linear-gradient(135deg, #eef4f8 0%, #e2e8f0 100%);
  display: flex;
  align-items: center;
  justify-content: center;
}

.lg-feature-card__placeholder-inner {
  color: rgba(37, 99, 235, 0.35);
}

/* ACADEMY */
.lg-academy {
  padding: 0 0 4rem;
}

.lg-academy__card {
  display: grid;
  gap: 2rem;
  padding: 2.5rem;
  border-radius: 20px;
  background: var(--lg-dark-2);
  color: #e5f4ff;
}

.lg-academy__eyebrow {
  margin: 0 0 0.75rem;
  font-size: 0.8125rem;
  font-weight: 500;
  color: #93c5fd;
  text-transform: uppercase;
  letter-spacing: 0.06em;
}

.lg-academy__title {
  margin: 0 0 1rem;
  font-size: clamp(1.5rem, 3vw, 2rem);
  font-weight: 400;
  line-height: 1.2;
  color: #fff;
}

.lg-academy__desc {
  margin: 0 0 1.5rem;
  max-width: 32rem;
  color: rgba(229, 244, 255, 0.7);
  line-height: 1.65;
}

.lg-academy__preview {
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.06);
  border: 1px solid rgba(255, 255, 255, 0.08);
  overflow: hidden;
}

.lg-academy__preview-bar {
  display: flex;
  gap: 6px;
  padding: 12px 14px;
  background: rgba(0, 0, 0, 0.25);
}

.lg-academy__preview-bar span {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.2);
}

.lg-academy__preview-body {
  padding: 1.5rem;
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.lg-academy__preview-line {
  height: 10px;
  border-radius: 4px;
  background: rgba(147, 197, 253, 0.25);
  width: 80%;
}

.lg-academy__preview-line--long {
  width: 95%;
  height: 14px;
}

.lg-academy__preview-line--short {
  width: 45%;
}

/* TESTIMONIALS */
.lg-testimonials {
  padding: 4rem 0;
  background: var(--lg-light-band);
}

.lg-testimonials__title {
  margin: 0 0 0.75rem;
  font-size: clamp(1.75rem, 3vw, 2.25rem);
  font-weight: 400;
  text-align: center;
  color: var(--lg-blue-heading);
}

.lg-testimonials__subtitle {
  margin: 0 auto 2.5rem;
  max-width: 36rem;
  text-align: center;
  color: var(--lg-muted);
}

.lg-testimonials__grid {
  display: grid;
  gap: 1.25rem;
}

.lg-testimonial-card {
  margin: 0;
  padding: 1.75rem;
  border-radius: 16px;
  background: var(--lg-card);
  border: 1px solid var(--lg-border);
}

.lg-testimonial-card__quote {
  margin: 0 0 1.25rem;
  font-size: 1rem;
  line-height: 1.65;
  color: var(--lg-text);
}

.lg-testimonial-card__author {
  display: flex;
  flex-direction: column;
  gap: 0.15rem;
  font-size: 0.875rem;
}

.lg-testimonial-card__author strong {
  color: var(--lg-text);
}

.lg-testimonial-card__author span {
  color: var(--lg-muted);
}

/* FAQ */
.lg-faq {
  padding: 4rem 0;
}

.lg-faq__grid {
  display: grid;
  gap: 2rem;
}

.lg-faq__title {
  margin: 0;
  font-size: clamp(1.5rem, 3vw, 2rem);
  font-weight: 400;
  color: var(--lg-blue-heading);
}

.lg-faq__list {
  border-top: 1px solid var(--lg-border);
}

.lg-faq__item {
  border-bottom: 1px solid var(--lg-border);
}

.lg-faq__question {
  width: 100%;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
  padding: 1.25rem 0;
  background: none;
  border: none;
  font: inherit;
  font-size: 1rem;
  font-weight: 500;
  text-align: left;
  color: var(--lg-text);
  cursor: pointer;
}

.lg-faq__icon {
  flex-shrink: 0;
  font-size: 1.25rem;
  color: var(--lg-muted);
  line-height: 1;
}

.lg-faq__answer {
  padding: 0 0 1.25rem;
}

.lg-faq__answer p {
  margin: 0;
  color: var(--lg-muted);
  line-height: 1.65;
}

/* CTA */
.lg-cta {
  padding: 4.5rem 0;
  background: var(--lg-dark);
  color: #cce9ff;
}

.lg-cta__inner {
  text-align: center;
}

.lg-cta__title {
  margin: 0 0 1rem;
  font-size: clamp(1.75rem, 4vw, 2.5rem);
  font-weight: 400;
  color: #7fc8ff;
}

.lg-cta__desc {
  margin: 0 auto 2rem;
  max-width: 32rem;
  color: rgba(204, 233, 255, 0.75);
  line-height: 1.65;
}

.lg-cta__actions {
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  gap: 0.75rem;
}

/* FOOTER */
.lg-footer {
  padding: 3rem 0 2rem;
  border-top: 1px solid var(--lg-border);
}

.lg-footer__grid {
  display: grid;
  gap: 2rem;
  grid-template-columns: 1fr;
  margin-bottom: 2.5rem;
}

.lg-footer__brand {
  font-weight: 600;
  font-size: 1rem;
  margin-bottom: 0.35rem;
}

.lg-footer__tagline {
  margin: 0;
  font-size: 0.875rem;
  color: var(--lg-muted);
}

.lg-footer__heading {
  margin: 0 0 0.75rem;
  font-size: 0.8125rem;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--lg-muted);
}

.lg-footer__grid a {
  display: block;
  margin-bottom: 0.5rem;
  font-size: 0.9375rem;
  color: var(--lg-text);
  text-decoration: none;
  opacity: 0.8;
}

.lg-footer__grid a:hover {
  opacity: 1;
  color: var(--lg-blue);
}

.lg-footer__bottom {
  padding-top: 1.5rem;
  border-top: 1px solid var(--lg-border);
  font-size: 0.8125rem;
  color: var(--lg-muted);
}

.lg-footer__bottom p {
  margin: 0;
}

/* RESPONSIVE */
@media (min-width: 768px) {
  .lg-nav__links {
    display: flex;
  }

  .lg-hero__grid {
    grid-template-columns: 1fr 1fr;
    gap: 2rem;
  }

  .lg-feature-card--hero {
    grid-template-columns: 1fr 1fr;
  }

  .lg-feature-card--hero .lg-feature-card__content {
    padding: 2.5rem;
  }

  .lg-feature-card:not(.lg-feature-card--hero) {
    grid-template-columns: 1fr 1fr;
  }

  .lg-feature-card:not(.lg-feature-card--hero):nth-child(even) .lg-feature-card__placeholder,
  .lg-feature-card:not(.lg-feature-card--hero):nth-child(even) .lg-feature-card__media {
    order: -1;
  }

  .lg-academy__card {
    grid-template-columns: 1.1fr 0.9fr;
    align-items: center;
  }

  .lg-testimonials__grid {
    grid-template-columns: repeat(3, 1fr);
  }

  .lg-faq__grid {
    grid-template-columns: 0.9fr 1.1fr;
    gap: 4rem;
    align-items: start;
  }

  .lg-footer__grid {
    grid-template-columns: 1.5fr repeat(3, 1fr);
  }
}

@media (min-width: 1024px) {
  .lg-hero {
    padding: 4.5rem 0 5rem;
  }
}
</style>
