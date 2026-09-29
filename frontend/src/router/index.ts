/** 路由：登录守卫 + 页面懒加载。新页面在 routes 数组登记即可（ROADMAP 扩展性约定 4）。 */
import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/login',
      name: 'login',
      component: () => import('@/pages/LoginPage.vue'),
      meta: { public: true },
    },
    {
      path: '/',
      component: () => import('@/layouts/AppLayout.vue'),
      children: [
        { path: '', redirect: '/home' },
        { path: 'home', name: 'home', component: () => import('@/pages/HomePage.vue') },
        { path: 'contacts', name: 'contacts', component: () => import('@/pages/ContactsPage.vue') },
        {
          path: 'contacts/:id',
          name: 'contact-detail',
          component: () => import('@/pages/ContactDetailPage.vue'),
        },
        { path: 'activities', name: 'activities', component: () => import('@/pages/ActivitiesPage.vue') },
        { path: 'tasks', name: 'tasks', component: () => import('@/pages/TasksPage.vue') },
        { path: 'gifts', name: 'gifts', component: () => import('@/pages/GiftsPage.vue') },
        { path: 'wishlist', name: 'wishlist', component: () => import('@/pages/WishlistPage.vue') },
        { path: 'funds', name: 'funds', component: () => import('@/pages/FundsPage.vue') },
        { path: 'graph', name: 'graph', component: () => import('@/pages/GraphPage.vue') },
        { path: 'map', name: 'map', component: () => import('@/pages/MapPage.vue') },
        { path: 'assistant', name: 'assistant', component: () => import('@/pages/ChatPage.vue') },
        { path: 'search', name: 'search', component: () => import('@/pages/SearchPage.vue') },
        { path: 'settings', name: 'settings', component: () => import('@/pages/SettingsPage.vue') },
      ],
    },
    { path: '/:pathMatch(.*)*', redirect: '/home' },
  ],
})

router.beforeEach((to) => {
  const auth = useAuthStore()
  if (!to.meta.public && !auth.isLoggedIn) {
    return { name: 'login' }
  }
  if (to.name === 'login' && auth.isLoggedIn) {
    return { path: '/contacts' }
  }
  return true
})

export default router
