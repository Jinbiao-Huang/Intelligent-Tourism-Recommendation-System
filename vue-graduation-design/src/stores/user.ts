import { reactive, ref } from 'vue'
import { defineStore } from 'pinia'
import { userAPI } from '@/api/user'

interface User {
  id: number
  username: string
  email: string
  isAdmin?: boolean
}

export const useUserStore = defineStore('user', () => {
  const user = ref<User | null>(null)
  const token = ref<string>('')
  const isLoading = ref(false)
  const isLoggedIn = ref(false)
  const isAdmin = ref(false)

  // 初始化 - 从本地存储恢复用户状态
  const initUser = () => {
    const savedToken = sessionStorage.getItem('authToken')
    const savedUser = sessionStorage.getItem('user')

    // Clear legacy localStorage auth to prevent cross-tab account contamination.
    localStorage.removeItem('authToken')
    localStorage.removeItem('user')

    if (savedToken && savedUser) {
      token.value = savedToken
      user.value = JSON.parse(savedUser)
      isLoggedIn.value = true
      isAdmin.value = Boolean(user.value?.isAdmin)
    }
  }

  // 注册
  const register = async (username: string, email: string, password: string, confirmPassword: string) => {
    if (password !== confirmPassword) {
      throw new Error('两次输入密码不一致')
    }

    isLoading.value = true
    try {
      const response = await userAPI.register({
        username,
        email,
        password,
        confirmPassword
      })

      const { data } = response
      token.value = data.token
      user.value = {
        id: data.id,
        username: data.username,
        email: data.email,
        isAdmin: data.is_admin
      }
      isLoggedIn.value = true
      isAdmin.value = Boolean(data.is_admin)

      // 保存到本地存储
      sessionStorage.setItem('authToken', data.token)
      sessionStorage.setItem('user', JSON.stringify(user.value))
      localStorage.removeItem('authToken')
      localStorage.removeItem('user')

      return data
    } finally {
      isLoading.value = false
    }
  }

  // 登录
  const login = async (email: string, password: string) => {
    isLoading.value = true
    try {
      const response = await userAPI.login({
        email,
        password
      })

      const { data } = response
      token.value = data.token
      user.value = {
        id: data.id,
        username: data.username,
        email: data.email,
        isAdmin: data.is_admin
      }
      isLoggedIn.value = true
      isAdmin.value = Boolean(data.is_admin)

      // 保存到本地存储
      sessionStorage.setItem('authToken', data.token)
      sessionStorage.setItem('user', JSON.stringify(user.value))
      localStorage.removeItem('authToken')
      localStorage.removeItem('user')

      return data
    } finally {
      isLoading.value = false
    }
  }

  // 登出
  const logout = async () => {
    await userAPI.logout()
    user.value = null
    token.value = ''
    isLoggedIn.value = false
    isAdmin.value = false
  }

  return {
    user,
    token,
    isLoading,
    isLoggedIn,
    isAdmin,
    initUser,
    register,
    login,
    logout
  }
})
