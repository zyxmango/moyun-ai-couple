import { createRouter, createWebHashHistory } from 'vue-router'
import { useUserStore } from '../stores/user'

const routes = [
  { path: '/reset-password', name: 'reset-password', component: () => import('../views/auth/ResetPassword.vue') },
  { path: '/login', name: 'login', component: () => import('../views/auth/Login.vue'), meta: { guest: true } },
  { path: '/register', name: 'register', component: () => import('../views/auth/Register.vue'), meta: { guest: true } },
  {
    path: '/',
    component: () => import('../views/Layout.vue'),
    meta: { requiresAuth: true },
    children: [
      { path: '', name: 'home', component: () => import('../views/Home.vue') },
      { path: 'home', redirect: '/' },
      { path: 'ai', name: 'ai-explore', component: () => import('../views/Explore.vue'), meta: { requiresCouple: true } },
      { path: 'life', name: 'life-explore', component: () => import('../views/Explore.vue'), meta: { requiresCouple: true } },
      { path: 'bind', name: 'bind', component: () => import('../views/auth/BindCouple.vue') },
      { path: 'chat', name: 'chat', component: () => import('../views/chat/Chat.vue'), meta: { requiresCouple: true } },
      { path: 'anniversary', name: 'anniversary', component: () => import('../views/anniversary/Anniversary.vue'), meta: { requiresCouple: true } },
      { path: 'album', name: 'album', component: () => import('../views/album/Album.vue'), meta: { requiresCouple: true } },
      { path: 'diary', name: 'diary', component: () => import('../views/diary/Diary.vue'), meta: { requiresCouple: true } },
      { path: 'recipe', name: 'recipe', component: () => import('../views/recipe/RecipeList.vue'), meta: { requiresCouple: true } },
      { path: 'recipe/:id', name: 'recipe-detail', component: () => import('../views/recipe/RecipeDetail.vue'), meta: { requiresCouple: true } },
      { path: 'ai/companion', name: 'ai-companion', component: () => import('../views/ai/Companion.vue'), meta: { requiresCouple: true } },
      { path: 'ai/generate', name: 'ai-generate', component: () => import('../views/ai/Generate.vue'), meta: { requiresCouple: true } },
      { path: 'ai/summary', name: 'ai-summary', component: () => import('../views/ai/Summary.vue'), meta: { requiresCouple: true } },
      { path: 'ai/rag', name: 'ai-rag', component: () => import('../views/ai/RagAgent.vue'), meta: { requiresCouple: true } },
      { path: 'ai/memory', name: 'ai-memory', component: () => import('../views/ai/MemoryHub.vue'), meta: { requiresCouple: true } },
      { path: 'ai/date-plan', name: 'ai-date-plan', component: () => import('../views/ai/DatePlanner.vue'), meta: { requiresCouple: true } },
      { path: 'ai/reminders', name: 'ai-reminders', component: () => import('../views/ai/Reminders.vue'), meta: { requiresCouple: true } },
      { path: 'settings', name: 'settings', component: () => import('../views/settings/Settings.vue') },
    ],
  },
  {
    path: '/admin',
    component: () => import('../views/Layout.vue'),
    meta: { requiresAuth: true, requiresAdmin: true },
    children: [
      { path: '', redirect: '/admin/stats' },
      { path: 'stats', name: 'admin-stats', component: () => import('../views/admin/Stats.vue') },
      { path: 'users', name: 'admin-users', component: () => import('../views/admin/Users.vue') },
      { path: 'couples', name: 'admin-couples', component: () => import('../views/admin/Couples.vue') },
      { path: 'logs', name: 'admin-logs', component: () => import('../views/admin/Logs.vue') },
    ],
  },
]

const router = createRouter({
  history: createWebHashHistory(),
  routes,
})

router.beforeEach(async (to) => {
  const store = useUserStore()
  if (store.token && !store.user) {
    await store.fetchUser()
  }

  if (to.meta.requiresAuth && !store.isLoggedIn) {
    return '/login'
  }
  if (to.meta.guest && store.isLoggedIn) {
    return '/'
  }
  if (to.meta.requiresCouple && store.user && !store.user.couple_id) {
    return '/bind'
  }
  if (to.meta.requiresAdmin && !store.isAdmin) {
    return '/'
  }
})

export default router
