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

export interface GeocodeResponse {
  status: string
  info: string
  count: string
  geocodes?: Array<{
    location: string
    formatted_address: string
    country: string
    province: string
    city: string
    district: string
    adcode: string
  }>
}

export interface PlaceCheckResponse {
  keyword: string
  city: string
  exists: boolean
  matched?: {
    name: string
    address: string
    location: string
    type?: string
    pname?: string
    cityname?: string
    adname?: string
    category?: string
    rating?: number
    cost?: number
  } | null
  suggestions?: Array<{
    name: string
    address: string
    location: string
    distance_m?: number
  }>
}

export interface RouteStep {
  instruction: string
  distance: number
  duration: number
  type?: string
  road?: string
  action?: string
  assistant_action?: string
}

export interface RoutePlan {
  distance: number
  duration: number
  cost: number
  steps: RouteStep[]
}

export interface RoutePlanResponse {
  mode: string
  route: RoutePlan
}

export interface SaveRouteRequest {
  origin_address?: string
  destination_address?: string
  origin_lnglat: string
  destination_lnglat: string
  mode: string
  distance: number
  duration: number
  cost: number
  steps: RouteStep[]
}

export interface SavedRouteItem extends SaveRouteRequest {
  id: number
  created_at: string
}

export const mapAPI = {
  // 地址 -> 经纬度
  geocode: (address: string) => {
    return api.get<GeocodeResponse>('/maps/geocode', {
      params: { address }
    })
  },

  // 校验地点是否在目标城市范围内
  checkPlaceInCity: (keyword: string, city: string, category?: string) => {
    return api.get<PlaceCheckResponse>('/maps/place-check', {
      params: { keyword, city, category }
    })
  },

  // 路线规划
  planRoute: (payload: {
    origin: string
    destination: string
    mode: string
    city?: string
    cityd?: string
    strategy?: string
  }) => {
    return api.post<RoutePlanResponse>('/maps/route', payload)
  },

  saveRoute: (payload: SaveRouteRequest) => {
    return api.post('/routes', payload)
  },

  listRoutes: () => {
    return api.get<SavedRouteItem[]>('/routes')
  }
}
