import { createRouter, createWebHistory } from 'vue-router'
import { useUserStore } from '@/stores/user'
import TourPlan from '../views/TourPlan.vue'
import AuthView from '../views/AuthView.vue'
import AdminView from '../views/AdminView.vue'
import TripHistoryView from '../views/TripHistoryView.vue'

const router = createRouter({
  history: createWebHistory('/'),
  routes: [
    {
      path: '/auth',
      name: 'auth',
      component: AuthView,
      meta: { requiresAuth: false }
    },
    {
      path: '/',
      name: 'home',
      component: TourPlan,
      meta: { requiresAuth: true }
    },
    {
      path: '/admin',
      name: 'admin',
      component: AdminView,
      meta: { requiresAuth: true }
    },
    {
      path: '/trip-history',
      name: 'trip-history',
      component: TripHistoryView,
      meta: { requiresAuth: true }
    },
  ],
})

// 路由守卫 - 检查认证状态
router.beforeEach((to, from, next) => {
  const userStore = useUserStore()
  const isLoggedIn = userStore.isLoggedIn

  if (to.meta.requiresAuth && !isLoggedIn) {
    // 需要认证但未登录，跳转到登录页
    next('/auth')
  } else if (to.path === '/admin' && !userStore.isAdmin) {
    // 需要管理员权限但不是管理员
    next('/')
  } else if (to.path === '/auth' && isLoggedIn) {
    // 已登录但访问登录页，按角色跳转
    next(userStore.isAdmin ? '/admin' : '/')
  } else {
    next()
  }
})

export default router
