import type { RouteRecordRaw } from 'vue-router'
import { createRouter, createWebHistory } from 'vue-router'

import AppShellPage from '../pages/app/AppShellPage.vue'
import ProjectListPage from '../pages/app/ProjectListPage.vue'
import ProjectCreatePage from '../pages/app/ProjectCreatePage.vue'
import ProjectOverviewPage from '../pages/app/ProjectOverviewPage.vue'
import WorkflowRouter from '../pages/app/WorkflowRouter.vue'
import HistoryCenterPage from '../pages/app/HistoryCenterPage.vue'
import UsagePage from '../pages/app/UsagePage.vue'
import AccountPage from '../pages/app/AccountPage.vue'
import DownloadsPage from '../pages/app/DownloadsPage.vue'
import ConversationPage from '../pages/app/ConversationPage.vue'
import PersonalKbPage from '../pages/app/PersonalKbPage.vue'

import AdminShellPage from '../pages/admin/AdminShellPage.vue'
import AdminDashboardPage from '../pages/admin/AdminDashboardPage.vue'
import UserManagementPage from '../pages/admin/UserManagementPage.vue'
import ModelRegistryPage from '../pages/admin/ModelRegistryPage.vue'
import PromptKbManagementPage from '../pages/admin/PromptKbManagementPage.vue'
import ChangeLogPage from '../pages/admin/ChangeLogPage.vue'
import AuditLogPage from '../pages/admin/AuditLogPage.vue'
import UsageAnalyticsPage from '../pages/admin/UsageAnalyticsPage.vue'
import GlobalDownloadPage from '../pages/admin/GlobalDownloadPage.vue'

import HomePage from '../pages/public/HomePage.vue'
import LoginPage from '../pages/auth/LoginPage.vue'
import RegisterPage from '../pages/auth/RegisterPage.vue'
import ForgotPasswordPage from '../pages/public/ForgotPasswordPage.vue'
import NotFoundPage from '../pages/public/NotFoundPage.vue'

const routes: RouteRecordRaw[] = [
  {
    path: '/',
    name: 'home',
    component: HomePage,
    meta: { public: true, layout: 'blank' },
  },
  {
    path: '/home',
    redirect: '/',
  },

  {
    path: '/login',
    name: 'login',
    component: LoginPage,
    meta: { public: true, layout: 'blank' },
  },
  {
    path: '/register',
    name: 'register',
    component: RegisterPage,
    meta: { public: true, layout: 'blank' },
  },
  {
    path: '/forgot-password',
    name: 'forgot-password',
    component: ForgotPasswordPage,
    meta: { public: true, layout: 'blank' },
  },

  {
    path: '/app',
    component: AppShellPage,
    children: [
      { path: '', redirect: '/app/projects' },
      {
        path: 'projects',
        name: 'projects',
        component: ProjectListPage,
      },
      {
        path: 'projects/new',
        name: 'project-new',
        component: ProjectCreatePage,
      },
      {
        path: 'projects/:projectId/overview',
        name: 'project-overview',
        component: ProjectOverviewPage,
      },
      {
        path: 'projects/:projectId/workflow/:stepId',
        name: 'project-workflow',
        component: WorkflowRouter,
        meta: { workflow: true },
      },
      {
        path: 'history',
        name: 'history',
        component: HistoryCenterPage,
      },
      {
        path: 'usage',
        name: 'usage',
        component: UsagePage,
      },
      {
        path: 'account',
        name: 'account',
        component: AccountPage,
      },
      {
        path: 'downloads',
        name: 'downloads',
        component: DownloadsPage,
      },
      {
        path: 'chat',
        name: 'chat',
        component: ConversationPage,
      },
      {
        path: 'kbs',
        name: 'personal-kbs',
        component: PersonalKbPage,
      },
    ],
  },

  {
    path: '/admin',
    component: AdminShellPage,
    children: [
      { path: '', redirect: '/admin/dashboard' },
      {
        path: 'dashboard',
        name: 'admin-dashboard',
        component: AdminDashboardPage,
      },
      {
        path: 'users',
        name: 'admin-users',
        component: UserManagementPage,
      },
      {
        path: 'models',
        name: 'admin-models',
        component: ModelRegistryPage,
      },
      {
        path: 'prompts',
        name: 'admin-prompts',
        component: PromptKbManagementPage,
      },
      {
        path: 'change-logs',
        name: 'admin-change-logs',
        component: ChangeLogPage,
      },
      {
        path: 'audit-logs',
        name: 'admin-audit-logs',
        component: AuditLogPage,
      },
      {
        path: 'usage-analytics',
        name: 'admin-usage-analytics',
        component: UsageAnalyticsPage,
      },
      {
        path: 'downloads',
        name: 'admin-downloads',
        component: GlobalDownloadPage,
      },
    ],
  },

  {
    path: '/:pathMatch(.*)*',
    name: 'not-found',
    component: NotFoundPage,
    meta: { public: true, layout: 'blank' },
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
  scrollBehavior: () => ({ top: 0 }),
})

router.beforeEach((to) => {
  if (to.meta.public) return true

  const token = localStorage.getItem('ef_token')
  if (!token) return { name: 'login', query: { redirect: to.fullPath } }

  return true
})

export default router
