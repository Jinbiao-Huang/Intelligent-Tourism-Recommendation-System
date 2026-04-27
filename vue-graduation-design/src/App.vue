<script setup lang="ts">
import { onMounted } from 'vue'
import { RouterView, useRoute } from 'vue-router'
import { useUserStore } from '@/stores/user'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useRouter } from 'vue-router'

const userStore = useUserStore()
const router = useRouter()
const route = useRoute()

// 初始化用户状态
onMounted(() => {
  userStore.initUser()
})

const handleLogout = () => {
  ElMessageBox.confirm('确定要退出登录吗？', '提示', {
    confirmButtonText: '确定',
    cancelButtonText: '取消',
    type: 'warning',
  })
    .then(async () => {
      await userStore.logout()
      ElMessage.success('已退出登录')
      router.push('/auth')
    })
    .catch(() => {
      // 取消操作
    })
}

// 检查是否在登录/注册页面
const isAuthPage = () => route.path === '/auth'
</script>

<template>
  <div class="layout">
    <header v-if="!isAuthPage() && userStore.isLoggedIn" class="topbar">
      <div class="logo-area">
        <el-icon class="logo-icon" color="#409eff" :size="28"><Location /></el-icon>
        <h1>智能旅游攻略规划系统</h1>
      </div>
      <div class="user-action">
        <div class="main-nav">
          <el-button link class="nav-link" :class="{ active: route.path === '/' }" @click="router.push('/')">
            首页
          </el-button>
          <el-button
            link
            class="nav-link"
            :class="{ active: route.path === '/trip-history' }"
            @click="router.push('/trip-history')"
          >
            我的行程记录
          </el-button>
        </div>
        <el-button v-if="userStore.isAdmin" link class="admin-link" @click="router.push('/admin')">管理员</el-button>
        <el-popover
          placement="bottom"
          :width="200"
          trigger="click"
        >
          <template #reference>
            <el-button link class="user-profile">
              {{ userStore.user?.username || '用户' }}
            </el-button>
          </template>
          <div class="user-menu">
            <p class="user-email">{{ userStore.user?.email }}</p>
            <el-button text type="danger" @click="handleLogout">登出</el-button>
          </div>
        </el-popover>
      </div>
    </header>

    <main :class="['main-container', { 'full-height': isAuthPage() }]">
      <RouterView />
    </main>

    <footer v-if="!isAuthPage() && userStore.isLoggedIn" class="footer">
      <p>© 2026 毕业设计 - 智能旅游规划系统 | 由 Vue 3 & Element Plus 提供动力</p>
    </footer>
  </div>
</template>

<style>
/* 全局样式清理 */
html,
body {
  width: 100%;
  min-height: 100%;
  margin: 0;
  padding: 0;
  background-color: #f5f7fa;
  font-family: "PingFang SC", "Helvetica Neue", Helvetica, Arial, sans-serif;
}

#app {
  width: 100%;
  min-height: 100vh;
  max-width: 100%;
  margin: 0;
  padding: 0;
}
</style>

<style scoped>
.layout {
  min-height: 100dvh;
  width: 100%;
  display: flex;
  flex-direction: column;
}

.topbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 60px;
  background: rgba(255, 255, 255, 0.95);
  backdrop-filter: blur(10px);
  border-bottom: 1px solid #e8ecf3;
  position: sticky;
  top: 0;
  z-index: 100;
  box-shadow: 0 2px 10px rgba(0, 0, 0, 0.05);
}

.logo-area {
  display: flex;
  align-items: center;
  gap: 12px;
}

.logo-area h1 {
  font-size: 20px;
  font-weight: 800;
  background: linear-gradient(120deg, #409eff, #36cfc9);
  background-clip: text;
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  margin: 0;
}

.user-action {
  display: flex;
  align-items: center;
  gap: 12px;
}

.main-nav {
  display: flex;
  align-items: center;
  gap: 6px;
}

.nav-link {
  color: #606266;
}

.nav-link.active {
  color: #409eff;
  font-weight: 600;
}

.user-profile {
  font-size: 14px;
  color: #409eff;
}

.admin-link {
  font-size: 14px;
  color: #303133;
}

.user-menu {
  padding: 8px 0;
}

.user-email {
  font-size: 12px;
  color: #909399;
  margin: 0 0 12px 0;
  word-break: break-all;
}

.main-container {
  flex: 1;
  width: 100%;
  min-height: 0;
  margin: 0;
  box-sizing: border-box;
}

.main-container.full-height {
  padding: 0;
  max-width: 100%;
  min-height: 100dvh;
}

.main-container:not(.full-height) {
  padding: 0;
  max-width: 100%;
}

.footer {
  text-align: center;
  padding: 30px;
  color: #909399;
  font-size: 14px;
}

@media (max-width: 768px) {
  .topbar {
    padding: 12px 20px;
  }

  .logo-area h1 {
    font-size: 16px;
  }

  .main-nav {
    gap: 0;
  }
}
</style>
