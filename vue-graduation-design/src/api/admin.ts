import axios from 'axios'

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:5000/api'

const api = axios.create({
  baseURL: API_URL,
  timeout: 10000
})

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

export interface AdminUser {
  id: number
  username: string
  email: string
  created_at?: string
  updated_at?: string
}

export interface AdminItineraryRecord {
  id: number
  user_id: number
  username: string
  destination: string
  days: number
  has_edited_destination: 0 | 1 | boolean
  edited_from?: string | null
  edited_to?: string | null
  created_at?: string
}

export const adminAPI = {
  getUsers: () => {
    return api.get<AdminUser[]>('/admin/users')
  },

  getItineraryRecords: () => {
    return api.get<AdminItineraryRecord[]>('/admin/itinerary-records')
  }
}
