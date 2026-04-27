import axios from 'axios'

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:5000/api'

const api = axios.create({
  baseURL: API_URL,
  timeout: 10000
})

export interface WeatherResponse {
  status: string
  info: string
  infocode: string
  lives?: Array<{
    province: string
    city: string
    weather: string
    temperature: string
    winddirection: string
    windpower: string
    humidity: string
    reporttime: string
  }>
}

export const weatherAPI = {
  // 实时天气
  getCurrent: (city: string) => {
    return api.get<WeatherResponse>('/weather/current', {
      params: { city }
    })
  }
}
