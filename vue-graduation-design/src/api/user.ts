import axios from 'axios'

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:5000/api'

interface LoginRequest {
  email: string
  password: string
}

interface RegisterRequest {
  username: string
  email: string
  password: string
  confirmPassword: string
}

interface UserResponse {
  id: number
  username: string
  email: string
  token: string
  is_admin: boolean
}

const api = axios.create({
  baseURL: API_URL,
  timeout: 10000
})

// 添加请求拦截器 - 在请求头中添加 token
api.interceptors.request.use(
  (config) => {
    const token = sessionStorage.getItem('authToken')
    if (token) {
      config.headers.Authorization = `Bearer ${token}`
    }
    return config
  },
  (error) => Promise.reject(error)
)

export const userAPI = {
  // 用户注册
  register: (data: RegisterRequest) => {
    return api.post<UserResponse>('/auth/register', {
      username: data.username,
      email: data.email,
      password: data.password
    })
  },

  // 用户登录
  login: (data: LoginRequest) => {
    return api.post<UserResponse>('/auth/login', {
      email: data.email,
      password: data.password
    })
  },

  // 获取当前用户信息
  getCurrentUser: () => {
    return api.get('/auth/me')
  },

  // 用户登出
  logout: () => {
    sessionStorage.removeItem('authToken')
    sessionStorage.removeItem('user')
    localStorage.removeItem('authToken')
    localStorage.removeItem('user')
    return Promise.resolve()
  }
}
