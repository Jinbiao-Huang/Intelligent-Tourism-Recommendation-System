<script setup lang="ts">
import { reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { useUserStore } from '@/stores/user'
import { useRouter } from 'vue-router'

const userStore = useUserStore()
const router = useRouter()

const tabsType = ref('login') // 'login' or 'register'

const studioHighlights = [
  '实时协作编辑行程版本',
  '路线与预算联动优化',
  '交通方案一键生成与保存'
]

const loginForm = reactive({
  email: '',
  password: ''
})

const registerForm = reactive({
  username: '',
  email: '',
  password: '',
  confirmPassword: ''
})

const handleLogin = async () => {
  if (!loginForm.email || !loginForm.password) {
    ElMessage.warning('请填写邮箱和密码')
    return
  }

  try {
    const loginResult = await userStore.login(loginForm.email, loginForm.password)
    ElMessage.success('登录成功！')
    if (loginResult.is_admin) {
      router.push('/admin')
    } else {
      router.push('/')
    }
  } catch (error: unknown) {
    const err = error as { response?: { data?: { message?: string } }; message?: string }
    ElMessage.error(err.response?.data?.message || err.message || '登录失败')
  }
}

const handleRegister = async () => {
  if (!registerForm.username || !registerForm.email || !registerForm.password || !registerForm.confirmPassword) {
    ElMessage.warning('请填写所有必填项')
    return
  }

  try {
    await userStore.register(
      registerForm.username,
      registerForm.email,
      registerForm.password,
      registerForm.confirmPassword
    )
    ElMessage.success('注册成功！')
    router.push('/')
  } catch (error: unknown) {
    const err = error as { response?: { data?: { message?: string } }; message?: string }
    ElMessage.error(err.response?.data?.message || err.message || '注册失败')
  }
}
</script>

<template>
  <section class="auth-page">
    <div class="auth-atmosphere" aria-hidden="true">
      <span class="orb orb-a"></span>
      <span class="orb orb-b"></span>
      <span class="orb orb-c"></span>
    </div>

    <div class="auth-shell">
      <aside class="auth-brand reveal reveal-1">
        <p class="eyebrow">Travel Collaboration Studio</p>
        <h1>智能旅游规划协作平台</h1>
        <p class="desc">从灵感到成团路线，一次登录后即可共享计划、同步编辑并实时追踪版本变化。</p>

        <ul class="highlight-list">
          <li v-for="item in studioHighlights" :key="item">{{ item }}</li>
        </ul>

        <div class="brand-meta">
          <span>地图化行程</span>
          <span>多人共创</span>
          <span>预算可控</span>
        </div>
      </aside>

      <div class="auth-card reveal reveal-2">
        <div class="auth-header">
          <p class="eyebrow">Account Access</p>
          <h2>{{ tabsType === 'login' ? '欢迎回来' : '创建你的协作空间' }}</h2>
          <div class="mode-switch">
            <button type="button" :class="{ active: tabsType === 'login' }" @click="tabsType = 'login'">登录</button>
            <button type="button" :class="{ active: tabsType === 'register' }" @click="tabsType = 'register'">注册</button>
          </div>
        </div>

        <div v-if="tabsType === 'login'" class="auth-form">
          <el-form label-position="top">
            <el-form-item label="邮箱">
              <el-input v-model="loginForm.email" type="email" placeholder="请输入邮箱地址" size="large" />
            </el-form-item>
            <el-form-item label="密码">
              <el-input v-model="loginForm.password" type="password" placeholder="请输入密码" show-password size="large" />
            </el-form-item>
            <el-button class="submit-btn" type="primary" :loading="userStore.isLoading" @click="handleLogin">
              登录并进入工作台
            </el-button>
          </el-form>
          <p class="form-footer">还没有账号？<button type="button" class="switch-link" @click="tabsType = 'register'">立即注册</button></p>
        </div>

        <div v-else class="auth-form">
          <el-form label-position="top">
            <el-form-item label="用户名">
              <el-input v-model="registerForm.username" placeholder="请输入用户名" size="large" />
            </el-form-item>
            <el-form-item label="邮箱">
              <el-input v-model="registerForm.email" type="email" placeholder="请输入邮箱地址" size="large" />
            </el-form-item>
            <el-form-item label="密码">
              <el-input v-model="registerForm.password" type="password" placeholder="请输入密码" show-password size="large" />
            </el-form-item>
            <el-form-item label="确认密码">
              <el-input v-model="registerForm.confirmPassword" type="password" placeholder="请再次输入密码" show-password size="large" />
            </el-form-item>
            <el-button class="submit-btn" type="primary" :loading="userStore.isLoading" @click="handleRegister">
              创建账号并进入
            </el-button>
          </el-form>
          <p class="form-footer">已有账号？<button type="button" class="switch-link" @click="tabsType = 'login'">去登录</button></p>
        </div>
      </div>
    </div>
  </section>
</template>

<style scoped>
@import url('https://fonts.googleapis.com/css2?family=Manrope:wght@500;600;700;800&family=Noto+Sans+SC:wght@400;500;700;900&display=swap');

.auth-page {
  position: relative;
  min-height: 100dvh;
  padding: 24px;
  overflow: hidden;
  background:
    radial-gradient(circle at 8% 20%, rgba(37, 99, 235, 0.24), transparent 40%),
    radial-gradient(circle at 85% 13%, rgba(249, 115, 22, 0.2), transparent 38%),
    linear-gradient(138deg, #f5fbff 0%, #e8f1ff 52%, #f6fcf7 100%);
}

.auth-atmosphere {
  position: absolute;
  inset: 0;
  pointer-events: none;
}

.orb {
  position: absolute;
  border-radius: 999px;
  filter: blur(4px);
  animation: float 9s ease-in-out infinite;
}

.orb-a {
  width: 260px;
  height: 260px;
  top: -86px;
  left: -60px;
  background: rgba(37, 99, 235, 0.24);
}

.orb-b {
  width: 190px;
  height: 190px;
  right: 11%;
  top: 4%;
  background: rgba(249, 115, 22, 0.22);
  animation-delay: 1.2s;
}

.orb-c {
  width: 240px;
  height: 240px;
  right: -78px;
  bottom: -68px;
  background: rgba(22, 163, 74, 0.16);
  animation-delay: 2.2s;
}

.auth-shell {
  position: relative;
  z-index: 1;
  width: min(1120px, 100%);
  min-height: calc(100dvh - 48px);
  margin: 0 auto;
  display: grid;
  grid-template-columns: 1.1fr 0.95fr;
  gap: 24px;
  align-items: stretch;
}

.auth-brand,
.auth-card {
  border-radius: 26px;
  border: 1px solid rgba(255, 255, 255, 0.85);
  backdrop-filter: blur(14px);
  box-shadow: 0 18px 40px rgba(22, 65, 148, 0.12);
}

.auth-brand {
  padding: 34px;
  background: rgba(255, 255, 255, 0.7);
  font-family: 'Manrope', 'Noto Sans SC', sans-serif;
}

.eyebrow {
  margin: 0 0 12px;
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.2em;
  text-transform: uppercase;
  color: #2563eb;
}

.auth-brand h1 {
  margin: 0;
  font-size: clamp(30px, 4vw, 42px);
  line-height: 1.15;
  font-weight: 800;
  color: #10305e;
}

.desc {
  margin-top: 16px;
  max-width: 92%;
  color: #3b587d;
}

.highlight-list {
  margin: 24px 0;
  padding: 0;
  list-style: none;
  display: grid;
  gap: 10px;
}

.highlight-list li {
  border-radius: 14px;
  padding: 12px 14px;
  background: rgba(255, 255, 255, 0.68);
  border: 1px solid rgba(37, 99, 235, 0.1);
  color: #1c416f;
  font-size: 14px;
  font-weight: 600;
}

.brand-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.brand-meta span {
  border-radius: 999px;
  padding: 7px 12px;
  font-size: 12px;
  font-weight: 700;
  color: #1d4b84;
  background: rgba(37, 99, 235, 0.11);
}

.auth-card {
  align-self: center;
  padding: 28px;
  background: rgba(255, 255, 255, 0.9);
}

.auth-header h2 {
  margin: 0;
  font-size: 29px;
  line-height: 1.2;
  font-weight: 800;
  color: #102f58;
  font-family: 'Manrope', 'Noto Sans SC', sans-serif;
}

.mode-switch {
  margin-top: 16px;
  padding: 4px;
  border-radius: 999px;
  background: #eef4ff;
  display: inline-flex;
  gap: 4px;
}

.mode-switch button {
  border: 0;
  border-radius: 999px;
  padding: 8px 18px;
  font-weight: 700;
  font-size: 13px;
  background: transparent;
  color: #506d90;
  cursor: pointer;
  transition: all 0.2s ease;
}

.mode-switch button.active {
  background: #2563eb;
  color: #ffffff;
  box-shadow: 0 6px 12px rgba(37, 99, 235, 0.25);
}

.auth-form {
  margin-top: 20px;
  animation: reveal 0.35s ease;
}

.submit-btn {
  width: 100%;
  height: 46px;
  border: 0;
  border-radius: 14px;
  font-size: 15px;
  font-weight: 700;
  letter-spacing: 0.03em;
  background: linear-gradient(120deg, #2563eb, #1d4ed8 58%, #f97316 130%);
  box-shadow: 0 10px 22px rgba(37, 99, 235, 0.22);
}

.form-footer {
  margin: 14px 0 0;
  text-align: center;
  font-size: 14px;
  color: #677f9c;
}

.switch-link {
  margin-left: 4px;
  border: 0;
  background: transparent;
  color: #2563eb;
  cursor: pointer;
  font-weight: 700;
}

:deep(.auth-form .el-form-item__label) {
  color: #2b4a71;
  font-weight: 700;
}

:deep(.auth-form .el-input__wrapper) {
  border-radius: 12px;
}

.reveal {
  opacity: 0;
  transform: translateY(14px);
  animation: pageReveal 0.65s ease forwards;
}

.reveal-2 {
  animation-delay: 0.15s;
}

@keyframes pageReveal {
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

@keyframes reveal {
  from {
    opacity: 0;
    transform: translateY(8px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

@keyframes float {
  0%,
  100% {
    transform: translateY(0);
  }
  50% {
    transform: translateY(-10px);
  }
}

@media (max-width: 980px) {
  .auth-shell {
    grid-template-columns: 1fr;
  }

  .desc {
    max-width: 100%;
  }
}

@media (max-width: 768px) {
  .auth-page {
    padding: 12px;
  }

  .auth-shell {
    min-height: auto;
    gap: 14px;
  }

  .auth-brand,
  .auth-card {
    border-radius: 20px;
    padding: 20px;
  }

  .auth-header h2 {
    font-size: 24px;
  }
}

@media (prefers-reduced-motion: reduce) {
  .orb,
  .reveal,
  .auth-form {
    animation: none;
  }
}
</style>
