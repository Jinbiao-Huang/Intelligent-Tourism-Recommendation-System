<script setup lang="ts">
import { computed, onBeforeUnmount, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Location, Timer, Bicycle, Guide, Loading } from '@element-plus/icons-vue'
import { tourAPI, type CollabChangeLog, type CollabConflictResponse, type CollabMember, type CollabSessionResponse } from '@/api/tour'
import { weatherAPI } from '@/api/weather'
import { mapAPI, type PlaceCheckResponse, type RoutePlan, type SavedRouteItem } from '@/api/map'
import { useUserStore } from '@/stores/user'
import { useTripHistoryStore } from '@/stores/tripHistory'
import {
  connectCollab,
  disconnectCollab,
  isCollabSocketConnected,
  joinCollab,
  leaveCollab,
  onCollabAck,
  onCollabConnectError,
  onCollabConflict,
  onCollabError,
  onCollabJoined,
  onCollabPresence,
  onCollabUpdated,
  sendCollabPatch
} from '@/services/collabSocket'

interface PlanItem {
  time: string
  content: string
  tips?: string
  recommend_reason?: string
  opening_hours?: string
  opening_hint?: string
  opening_status?: string
  category?: string
  cost?: number
  rating?: number
  next_distance?: number | null
  location?: string
  poi_type?: string
}

interface DayPlan {
  day: number
  activities: PlanItem[]
}

interface WeatherLive {
  province: string
  city: string
  weather: string
  temperature: string
  winddirection: string
  windpower: string
  humidity: string
  reporttime: string
}

interface CollabConflictNotice {
  message: string
  serverVersion: number
  lastEditorName: string
  createdAt: string
}

type MatchedPlaceInfo = NonNullable<PlaceCheckResponse['matched']>

const userStore = useUserStore()
const tripHistoryStore = useTripHistoryStore()
const loading = ref(false)
const generatedPlan = ref<DayPlan[] | null>(null)
const currentWeather = ref<WeatherLive | null>(null)
const routeLoading = ref(false)
const saveRouteLoading = ref(false)
const listRouteLoading = ref(false)
const routePlan = ref<RoutePlan | null>(null)
const routeMode = ref('')
const originLngLat = ref('')
const destinationLngLat = ref('')
const savedRoutes = ref<SavedRouteItem[]>([])
const editableCategories = ['景点', '餐饮', '住宿']
const activityValidationErrors = reactive<Record<string, string>>({})
const activityValidationLoading = reactive<Record<string, boolean>>({})
const activityValidationSuggestions = reactive<Record<string, Array<{ name: string; address: string; location: string; distance_m?: number }>>>({})
const activitySavedDetails = reactive<Record<string, MatchedPlaceInfo>>({})
const activityDrafts = reactive<Record<string, string>>({})
const collabLoading = ref(false)
const collabSaving = ref(false)
const collabPolling = ref(false)
const collabSessionId = ref<number | null>(null)
const collabShareToken = ref('')
const collabVersion = ref(0)
const collabChanges = ref<CollabChangeLog[]>([])
const collabMembers = ref<CollabMember[]>([])
const collabRole = ref('')
const collabLastEditorName = ref('')
const collabTitle = ref('')
const collabJoinToken = ref('')
const collabTimer = ref<number | null>(null)
const collabAckTimer = ref<number | null>(null)
const collabRealtimeConnected = ref(false)
const collabPollingIntervalMs = ref(5000)
const collabRealtimeErrorNotified = ref(false)
const collabConflictNotice = ref<CollabConflictNotice | null>(null)
const collabTraceLoading = ref(false)
const collabTraceAnchor = ref<CollabChangeLog | null>(null)
const collabTraceChain = ref<CollabChangeLog[]>([])
let collabSocketUnsubscribers: Array<() => void> = []

const queryForm = reactive({
  destination: '',
  days: 3,
  visitDate: '',
  budget: 3000,
  recommendFocus: 'rating' as 'rating' | 'distance',
  pace: 'intense' as 'leisure' | 'normal' | 'intense',
  preferences: [] as string[]
})

const routeForm = reactive({
  originAddress: '',
  destinationAddress: '',
  mode: 'driving',
  city: '',
  cityd: '',
  useCurrentLocation: true
})

const preferenceOptions = ['自然风光', '历史古迹', '美食品尝', '现代都游', '户外徒步', '艺术文化']

const recommendFocusOptions = [
  { label: '侧重打分', value: 'rating' },
  { label: '侧重距离', value: 'distance' }
]

const paceOptions = [
  { label: '闲游', value: 'leisure' },
  { label: '正常旅游', value: 'normal' },
  { label: '特种兵式旅游', value: 'intense' }
]

const routeModes = [
  { label: '驾车', value: 'driving' },
  { label: '步行', value: 'walking' },
  { label: '骑行', value: 'bicycling' },
  { label: '公交/地铁/高铁', value: 'transit' }
]

const collectPlanDestinations = (destination: string, plans: DayPlan[]) => {
  const places = plans
    .flatMap((dayPlan) => dayPlan.activities.map((activity) => String(activity.content || '').trim()))
    .filter(Boolean)
  const uniquePlaces = Array.from(new Set(places))
  if (uniquePlaces.length) {
    return uniquePlaces
  }
  const fallback = String(destination || '').trim()
  return fallback ? [fallback] : []
}

const persistItineraryRecord = async (payload: {
  destination: string
  days: number
  hasEditedDestination: boolean
  editedFrom?: string
  editedTo?: string
}) => {
  try {
    await tourAPI.saveItineraryRecord({
      destination: payload.destination,
      days: payload.days,
      has_edited_destination: payload.hasEditedDestination,
      edited_from: payload.editedFrom,
      edited_to: payload.editedTo
    })
  } catch {
    // 后台记录失败不阻塞主流程
  }
}

const persistTourPlan = async (payload: {
  destination: string
  days: number
  budget: number
  preferences: string[]
  plans: DayPlan[]
  visitDate: string
}) => {
  try {
    const range = buildTourDateRange(payload.visitDate, payload.days)
    await tourAPI.createTourPlan({
      destination: payload.destination,
      start_date: range.startDate,
      end_date: range.endDate,
      budget: payload.budget,
      preferences: payload.preferences,
      plan_data: payload.plans
    })
  } catch {
    // 行程落库失败不阻塞主流程
  }
}

const mergeCollabChanges = (incoming: CollabChangeLog[] = []) => {
  if (!incoming.length) {
    return
  }
  const current = new Map<number, CollabChangeLog>()
  collabChanges.value.forEach((item) => {
    current.set(item.id, item)
  })
  incoming.forEach((item) => {
    current.set(item.id, item)
  })
  collabChanges.value = Array.from(current.values())
    .sort((a, b) => a.version - b.version)
    .slice(-60)
}

const asObject = (value: unknown): Record<string, unknown> | null => {
  if (typeof value === 'object' && value !== null) {
    return value as Record<string, unknown>
  }
  return null
}

const asNumber = (value: unknown, fallback = 0) => {
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : fallback
}

const getAuthToken = () => {
  return String(userStore.token || sessionStorage.getItem('authToken') || '').trim()
}

const clearCollabAckTimer = () => {
  if (collabAckTimer.value !== null) {
    window.clearTimeout(collabAckTimer.value)
    collabAckTimer.value = null
  }
}

const formatCollabTime = (value?: string) => {
  if (!value) {
    return '未知时间'
  }
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) {
    return value
  }
  return date.toLocaleString('zh-CN', {
    hour12: false,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit'
  })
}

const clearCollabConflictNotice = () => {
  collabConflictNotice.value = null
}

const clearCollabTrace = () => {
  collabTraceAnchor.value = null
  collabTraceChain.value = []
  collabTraceLoading.value = false
}

const refreshCollabChangesSince = async (sinceVersion: number, silent = true) => {
  if (!collabSessionId.value) {
    return
  }
  try {
    const response = await tourAPI.getCollabChanges(collabSessionId.value, Math.max(0, sinceVersion), 80)
    const latestVersion = asNumber(response.data.version, collabVersion.value)
    mergeCollabChanges(response.data.changes || [])
    if (latestVersion > collabVersion.value) {
      collabVersion.value = latestVersion
    }
  } catch (error: unknown) {
    if (!silent) {
      const err = error as { response?: { data?: { message?: string } }; message?: string }
      ElMessage.warning(err.response?.data?.message || err.message || '刷新协作日志失败')
    }
  }
}

const traceCollabChange = async (change: CollabChangeLog) => {
  if (!collabSessionId.value) {
    return
  }
  collabTraceAnchor.value = change
  collabTraceLoading.value = true
  try {
    const sinceVersion = Math.max((change.version || 1) - 1, 0)
    const response = await tourAPI.getCollabChanges(collabSessionId.value, sinceVersion, 120)
    const chain = (response.data.changes || [])
      .filter((item) => item.version >= change.version)
      .sort((a, b) => a.version - b.version)

    mergeCollabChanges(response.data.changes || [])
    collabTraceChain.value = chain
  } catch {
    collabTraceChain.value = collabChanges.value
      .filter((item) => item.version >= change.version)
      .sort((a, b) => a.version - b.version)
    ElMessage.warning('追溯链路加载失败，已展示本地日志')
  } finally {
    collabTraceLoading.value = false
  }
}

const clearCollabSocketListeners = () => {
  collabSocketUnsubscribers.forEach((dispose) => dispose())
  collabSocketUnsubscribers = []
}

const teardownCollabRealtime = (leaveRoom = true) => {
  const sessionId = collabSessionId.value
  clearCollabAckTimer()
  clearCollabSocketListeners()
  if (leaveRoom && sessionId) {
    leaveCollab(sessionId)
  }
  disconnectCollab()
  collabRealtimeConnected.value = false
  collabRealtimeErrorNotified.value = false
}

const handleRealtimeUpdated = (payload: unknown) => {
  const data = asObject(payload)
  if (!data || !collabSessionId.value) {
    return
  }

  const itineraryId = asNumber(data.itinerary_id ?? data.planId, 0)
  if (itineraryId !== collabSessionId.value) {
    return
  }

  const previousVersion = collabVersion.value
  const nextVersion = asNumber(data.version, previousVersion)
  if (nextVersion > 0) {
    collabVersion.value = nextVersion
  }

  const destination = String(data.destination || '').trim()
  if (destination) {
    queryForm.destination = destination
  }

  const days = asNumber(data.days, queryForm.days)
  if (days > 0) {
    queryForm.days = days
  }

  if (Array.isArray(data.plans) && data.plans.length) {
    generatedPlan.value = data.plans as DayPlan[]
    initActivityDrafts(generatedPlan.value)
  }

  const lastEditor = asObject(data.last_editor)
  const editorName = String(lastEditor?.username || '').trim()
  const editorId = asNumber(lastEditor?.id, 0)
  const currentUserId = asNumber(userStore.user?.id, 0)
  if (editorName) {
    collabLastEditorName.value = editorName
  }

  if (nextVersion > previousVersion) {
    clearCollabConflictNotice()
    void refreshCollabChangesSince(previousVersion)
  }

  if (nextVersion > previousVersion && editorId && editorId !== currentUserId) {
    ElMessage.info(`检测到 ${editorName || '协作者'} 的更新，已同步至 v${nextVersion}`)
  }
}

const handleRealtimeConflict = (payload: unknown) => {
  clearCollabAckTimer()
  collabSaving.value = false

  const conflict = payload as CollabConflictResponse
  if (!conflict || conflict.code !== 'VERSION_CONFLICT') {
    ElMessage.warning('检测到协作冲突，请手动同步最新版本')
    void pollCollabSession(false)
    return
  }

  generatedPlan.value = conflict.server_plan_data as DayPlan[]
  queryForm.destination = conflict.server_destination || queryForm.destination
  queryForm.days = Math.max(1, Number(conflict.server_days || queryForm.days))
  collabVersion.value = conflict.server_version
  mergeCollabChanges(conflict.changes_since_base || [])
  initActivityDrafts(generatedPlan.value)
  collabConflictNotice.value = {
    message: conflict.message || '版本冲突：当前内容已被其他协作者更新',
    serverVersion: asNumber(conflict.server_version, collabVersion.value),
    lastEditorName: String(conflict.last_editor?.username || '未知用户'),
    createdAt: formatCollabTime(new Date().toISOString())
  }
  ElMessage.warning('检测到版本冲突，已同步服务器最新版本，请在最新版本上重新编辑')
}

const handleRealtimeError = (payload: unknown) => {
  clearCollabAckTimer()
  collabSaving.value = false
  const data = asObject(payload)
  ElMessage.error(String(data?.message || '协作通道异常，请稍后重试'))
}

const setupCollabRealtime = (itineraryId: number) => {
  const token = getAuthToken()
  if (!token) {
    collabRealtimeConnected.value = false
    return false
  }

  clearCollabSocketListeners()
  clearCollabAckTimer()

  const socket = connectCollab(token)
  const onConnect = () => {
    collabRealtimeConnected.value = true
    collabRealtimeErrorNotified.value = false
    joinCollab(itineraryId)
    if (collabPollingIntervalMs.value !== 8000) {
      startCollabPolling(8000)
    }
  }
  const onDisconnect = () => {
    collabRealtimeConnected.value = false
    if (collabPollingIntervalMs.value !== 5000) {
      startCollabPolling(5000)
    }
  }
  const onConnectError = () => {
    collabRealtimeConnected.value = false
    if (!collabRealtimeErrorNotified.value) {
      ElMessage.warning('实时通道连接失败，已自动切换为轮询同步')
      collabRealtimeErrorNotified.value = true
    }
    if (collabPollingIntervalMs.value !== 5000) {
      startCollabPolling(5000)
    }
  }

  socket.on('connect', onConnect)
  socket.on('disconnect', onDisconnect)

  collabSocketUnsubscribers.push(() => socket.off('connect', onConnect))
  collabSocketUnsubscribers.push(() => socket.off('disconnect', onDisconnect))
  collabSocketUnsubscribers.push(onCollabUpdated(handleRealtimeUpdated))
  collabSocketUnsubscribers.push(onCollabConflict(handleRealtimeConflict))
  collabSocketUnsubscribers.push(onCollabError(handleRealtimeError))
  collabSocketUnsubscribers.push(onCollabConnectError(onConnectError))
  collabSocketUnsubscribers.push(onCollabJoined((payload: unknown) => {
    const data = asObject(payload)
    const version = asNumber(data?.version, 0)
    if (version > 0) {
      collabVersion.value = version
    }
  }))
  collabSocketUnsubscribers.push(onCollabAck((payload: unknown) => {
    clearCollabAckTimer()
    collabSaving.value = false
    const previousVersion = collabVersion.value
    const data = asObject(payload)
    const version = asNumber(data?.version, 0)
    if (version > collabVersion.value) {
      collabVersion.value = version
    }
    clearCollabConflictNotice()
    void refreshCollabChangesSince(previousVersion)
  }))
  collabSocketUnsubscribers.push(onCollabPresence((payload: unknown) => {
    const data = asObject(payload)
    const incomingItineraryId = asNumber(data?.itinerary_id, 0)
    if (incomingItineraryId !== collabSessionId.value) {
      return
    }
    const eventType = String(data?.event || '')
    if (eventType === 'join' || eventType === 'leave') {
      void pollCollabSession(true)
    }
  }))

  if (socket.connected) {
    collabRealtimeConnected.value = true
    collabRealtimeErrorNotified.value = false
    joinCollab(itineraryId)
  }

  collabRealtimeConnected.value = isCollabSocketConnected()
  return collabRealtimeConnected.value
}

const stopCollabPolling = () => {
  if (collabTimer.value !== null) {
    window.clearInterval(collabTimer.value)
    collabTimer.value = null
  }
}

const clearCollabState = (stopPolling = true) => {
  teardownCollabRealtime(true)
  if (stopPolling) {
    stopCollabPolling()
  }
  collabSessionId.value = null
  collabShareToken.value = ''
  collabVersion.value = 0
  collabChanges.value = []
  collabMembers.value = []
  collabRole.value = ''
  collabLastEditorName.value = ''
  collabTitle.value = ''
  clearCollabConflictNotice()
  clearCollabTrace()
}

const applyCollabSession = (session: CollabSessionResponse, allowPlanOverride = true) => {
  collabSessionId.value = session.id
  collabShareToken.value = session.share_token || ''
  collabVersion.value = session.version || 1
  collabRole.value = session.role || ''
  collabTitle.value = session.title || ''
  collabMembers.value = session.members || []
  collabLastEditorName.value = session.last_editor?.username || ''
  mergeCollabChanges(session.changes || [])
  clearCollabConflictNotice()

  if (allowPlanOverride && session.plan_data?.length) {
    generatedPlan.value = session.plan_data as DayPlan[]
    queryForm.destination = session.destination || queryForm.destination
    queryForm.days = Math.max(1, Number(session.days || queryForm.days))
    initActivityDrafts(generatedPlan.value)
  }
}

const pollCollabSession = async (silent = true) => {
  if (!collabSessionId.value || collabPolling.value) {
    return
  }

  collabPolling.value = true
  try {
    const response = await tourAPI.getCollabSession(collabSessionId.value, collabVersion.value || undefined)
    const session = response.data
    const previousVersion = collabVersion.value
    const currentUserId = asNumber(userStore.user?.id, 0)
    applyCollabSession(session, !!session.has_updates)

    if (!silent && session.has_updates && session.version > previousVersion) {
      const author = session.last_editor?.username || '协作者'
      if (asNumber(session.last_editor?.id, 0) !== currentUserId) {
        ElMessage.info(`检测到 ${author} 的更新，已同步至 v${session.version}`)
      }
    }
  } catch (error: unknown) {
    if (!silent) {
      const err = error as { response?: { data?: { message?: string } }; message?: string }
      ElMessage.error(err.response?.data?.message || err.message || '协作同步失败')
    }
  } finally {
    collabPolling.value = false
  }
}

const startCollabPolling = (intervalMs = 5000) => {
  stopCollabPolling()
  if (!collabSessionId.value) {
    return
  }
  collabPollingIntervalMs.value = Math.max(3000, Math.floor(intervalMs))
  void pollCollabSession(true)
  collabTimer.value = window.setInterval(() => {
    void pollCollabSession(true)
  }, collabPollingIntervalMs.value)
}

const pushCollabUpdateByHttp = async (summary: string, notifyFallback = false) => {
  if (!collabSessionId.value || !generatedPlan.value) {
    return
  }

  if (notifyFallback) {
    ElMessage.warning('实时通道响应超时，已自动切换 HTTP 同步本次修改')
  }

  try {
    const previousVersion = collabVersion.value
    const response = await tourAPI.updateCollabSession(collabSessionId.value, {
      base_version: collabVersion.value,
      destination: queryForm.destination,
      days: generatedPlan.value.length,
      plans: generatedPlan.value,
      summary
    })
    applyCollabSession(response.data)
    void refreshCollabChangesSince(previousVersion)
  } catch (error: unknown) {
    const err = error as {
      response?: { status?: number; data?: CollabConflictResponse & { message?: string } }
      message?: string
    }

    if (err.response?.status === 409 && err.response.data?.code === 'VERSION_CONFLICT') {
      const conflict = err.response.data
      generatedPlan.value = conflict.server_plan_data as DayPlan[]
      queryForm.destination = conflict.server_destination || queryForm.destination
      queryForm.days = Math.max(1, Number(conflict.server_days || queryForm.days))
      collabVersion.value = conflict.server_version
      mergeCollabChanges(conflict.changes_since_base || [])
      initActivityDrafts(generatedPlan.value)
      collabConflictNotice.value = {
        message: conflict.message || '版本冲突：当前内容已被其他协作者更新',
        serverVersion: asNumber(conflict.server_version, collabVersion.value),
        lastEditorName: String(conflict.last_editor?.username || '未知用户'),
        createdAt: formatCollabTime(new Date().toISOString())
      }
      ElMessage.warning('检测到版本冲突，已同步服务器最新版本，请在最新版本上重新编辑')
    } else {
      ElMessage.error(err.response?.data?.message || err.message || '协作保存失败')
    }
  } finally {
    collabSaving.value = false
  }
}

const pushCollabUpdate = async (summary: string) => {
  if (!collabSessionId.value || !generatedPlan.value || collabSaving.value) {
    return
  }

  collabSaving.value = true

  if (collabRealtimeConnected.value) {
    clearCollabAckTimer()
    sendCollabPatch({
      itinerary_id: collabSessionId.value,
      base_version: collabVersion.value,
      destination: queryForm.destination,
      days: generatedPlan.value.length,
      plans: generatedPlan.value as unknown as Array<Record<string, unknown>>,
      summary
    })

    collabAckTimer.value = window.setTimeout(() => {
      if (!collabSaving.value) {
        return
      }
      collabRealtimeConnected.value = isCollabSocketConnected()
      void pushCollabUpdateByHttp(summary, true)
    }, 4500)
    return
  }

  await pushCollabUpdateByHttp(summary)
}

const createCollabSession = async () => {
  if (!generatedPlan.value?.length) {
    ElMessage.warning('请先生成行程后再开启协作')
    return
  }
  collabLoading.value = true
  try {
    const response = await tourAPI.createCollabSession({
      destination: queryForm.destination,
      days: generatedPlan.value.length,
      plans: generatedPlan.value,
      title: `${queryForm.destination} 协作行程`
    })
    applyCollabSession(response.data)
    const realtimeEnabled = setupCollabRealtime(response.data.id)
    startCollabPolling(realtimeEnabled ? 8000 : 5000)
    ElMessage.success(
      realtimeEnabled
        ? `协作会话已创建并启用 WebSocket，邀请码：${response.data.share_token}`
        : `协作会话已创建（当前使用轮询），邀请码：${response.data.share_token}`
    )
  } catch (error: unknown) {
    const err = error as { response?: { data?: { message?: string } }; message?: string }
    ElMessage.error(err.response?.data?.message || err.message || '创建协作会话失败')
  } finally {
    collabLoading.value = false
  }
}

const joinCollabSession = async () => {
  const shareToken = String(collabJoinToken.value || '').trim()
  if (!shareToken) {
    ElMessage.warning('请输入协作邀请码')
    return
  }
  collabLoading.value = true
  try {
    const response = await tourAPI.joinCollabSession(shareToken)
    applyCollabSession(response.data)
    const realtimeEnabled = setupCollabRealtime(response.data.id)
    startCollabPolling(realtimeEnabled ? 8000 : 5000)
    ElMessage.success(realtimeEnabled ? '已加入协作会话并启用 WebSocket 实时同步' : '已加入协作会话（当前使用轮询同步）')
  } catch (error: unknown) {
    const err = error as { response?: { data?: { message?: string } }; message?: string }
    ElMessage.error(err.response?.data?.message || err.message || '加入协作会话失败')
  } finally {
    collabLoading.value = false
  }
}

const copyCollabToken = async () => {
  if (!collabShareToken.value) {
    ElMessage.warning('暂无可复制的邀请码')
    return
  }
  try {
    await navigator.clipboard.writeText(collabShareToken.value)
    ElMessage.success('邀请码已复制')
  } catch {
    ElMessage.error('复制失败，请手动复制')
  }
}

const resolveVisitWeekday = (visitDate: string) => {
  const text = String(visitDate || '').trim()
  if (!text) {
    return undefined
  }
  const parsed = new Date(`${text}T00:00:00`)
  if (Number.isNaN(parsed.getTime())) {
    return undefined
  }
  const day = parsed.getDay()
  return day === 0 ? 6 : day - 1
}

const formatDate = (date: Date) => {
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

const resolveStartDate = (visitDate: string) => {
  const text = String(visitDate || '').trim()
  if (!text) {
    return new Date()
  }
  const parsed = new Date(`${text}T00:00:00`)
  if (Number.isNaN(parsed.getTime())) {
    return new Date()
  }
  return parsed
}

const buildTourDateRange = (visitDate: string, days: number) => {
  const start = resolveStartDate(visitDate)
  const safeDays = Math.max(1, Math.floor(days || 1))
  const end = new Date(start.getFullYear(), start.getMonth(), start.getDate() + safeDays - 1)
  return {
    startDate: formatDate(start),
    endDate: formatDate(end)
  }
}

const getOpeningSuggestion = (activity: PlanItem) => {
  const hint = String(activity.opening_hint || '').trim()
  if (hint) {
    return hint
  }
  const openingHours = String(activity.opening_hours || '').trim()
  if (!openingHours) {
    return ''
  }
  return openingHours
}

const handleGenerate = async () => {
  if (!queryForm.destination) {
    ElMessage.warning('请输入目的地')
    return
  }
  if (!Number.isFinite(queryForm.budget) || queryForm.budget <= 0) {
    ElMessage.warning('请输入有效预算金额')
    return
  }

  loading.value = true
  try {
    clearCollabState(true)
    const totalDays = Math.max(1, Math.floor(queryForm.days))
    const requestPayload = {
      destination: queryForm.destination,
      days: totalDays,
      visit_date: queryForm.visitDate || undefined,
      visit_weekday: resolveVisitWeekday(queryForm.visitDate),
      budget: queryForm.budget,
      recommend_focus: queryForm.recommendFocus,
      preferences: queryForm.preferences,
      pace: queryForm.pace
    } as Parameters<typeof tourAPI.generateItinerary>[0]
    const response = await tourAPI.generateItinerary(requestPayload)
    generatedPlan.value = response.data.plans
    initActivityDrafts(generatedPlan.value)
    tripHistoryStore.addRecord(userStore.user?.id, {
      destination: queryForm.destination,
      days: totalDays,
      places: collectPlanDestinations(queryForm.destination, response.data.plans || [])
    })
    await persistItineraryRecord({
      destination: queryForm.destination,
      days: totalDays,
      hasEditedDestination: false
    })
    await persistTourPlan({
      destination: queryForm.destination,
      days: totalDays,
      budget: queryForm.budget,
      preferences: queryForm.preferences,
      plans: response.data.plans || [],
      visitDate: queryForm.visitDate
    })

    try {
      const weatherRes = await weatherAPI.getCurrent(queryForm.destination)
      const live = weatherRes.data.lives?.[0]
      currentWeather.value = live || null
    } catch (weatherError: unknown) {
      currentWeather.value = null
      const err = weatherError as { response?: { data?: { message?: string } }; message?: string }
      ElMessage.warning(err.response?.data?.message || err.message || '天气获取失败')
    }

    ElMessage.success('行程规划生成成功！')
  } catch (error: unknown) {
    const err = error as { response?: { data?: { message?: string } }; message?: string }
    ElMessage.error(err.response?.data?.message || err.message || '行程生成失败')
  } finally {
    loading.value = false
  }
}

const resetForm = () => {
  clearCollabState(true)
  queryForm.destination = ''
  queryForm.days = 3
  queryForm.visitDate = ''
  queryForm.budget = 3000
  queryForm.recommendFocus = 'rating'
  queryForm.pace = 'intense'
  queryForm.preferences = []
  generatedPlan.value = null
  currentWeather.value = null
  routePlan.value = null
  originLngLat.value = ''
  destinationLngLat.value = ''
  savedRoutes.value = []
  routeForm.originAddress = ''
  routeForm.destinationAddress = ''
  routeForm.mode = 'driving'
  routeForm.city = ''
  routeForm.cityd = ''
  routeForm.useCurrentLocation = true
  Object.keys(activityValidationErrors).forEach((key) => {
    delete activityValidationErrors[key]
  })
  Object.keys(activityValidationLoading).forEach((key) => {
    delete activityValidationLoading[key]
  })
  Object.keys(activityValidationSuggestions).forEach((key) => {
    delete activityValidationSuggestions[key]
  })
  Object.keys(activitySavedDetails).forEach((key) => {
    delete activitySavedDetails[key]
  })
  Object.keys(activityDrafts).forEach((key) => {
    delete activityDrafts[key]
  })
}

const formatCost = (cost?: number) => {
  if (cost === undefined || cost === null) {
    return ''
  }
  return `￥${cost.toLocaleString('zh-CN')}`
}

const calcDayTotal = (activities: PlanItem[]) => {
  return activities.reduce((sum, item) => sum + (item.cost || 0), 0)
}

const estimated_cost = computed(() => {
  if (!generatedPlan.value?.length) {
    return 0
  }
  return generatedPlan.value.reduce((sum, dayPlan) => sum + calcDayTotal(dayPlan.activities), 0)
})

const budgetOverflowAmount = computed(() => {
  const budget = Number(queryForm.budget || 0)
  if (!budget || estimated_cost.value <= budget) {
    return 0
  }
  return estimated_cost.value - budget
})

const isBudgetExceeded = computed(() => {
  return budgetOverflowAmount.value > 0
})

const notifyBudgetExceeded = () => {
  if (!isBudgetExceeded.value) {
    return
  }
  ElMessage.warning(
    `预计消费总金额 ${formatCost(estimated_cost.value)}，已超出预算 ${formatCost(queryForm.budget)}（超出 ${formatCost(budgetOverflowAmount.value)}）`
  )
}

const formatDistance = (meters: number) => {
  if (!meters) {
    return ''
  }
  if (meters >= 1000) {
    return `${(meters / 1000).toFixed(1)} km`
  }
  return `${meters} m`
}

const formatRating = (rating?: number) => {
  if (rating === undefined || rating === null || Number.isNaN(rating)) {
    return ''
  }
  return rating.toFixed(1)
}

const formatDuration = (seconds: number) => {
  if (!seconds) {
    return ''
  }
  const minutes = Math.max(1, Math.round(seconds / 60))
  if (minutes < 60) {
    return `${minutes} 分钟`
  }
  const hours = Math.floor(minutes / 60)
  const rest = minutes % 60
  return rest ? `${hours} 小时${rest} 分钟` : `${hours} 小时`
}

const parseLngLat = (location?: string) => {
  const text = String(location || '').trim()
  if (!text.includes(',')) {
    return null
  }
  const [lngText, latText] = text.split(',').map((item) => item.trim())
  const lng = Number(lngText)
  const lat = Number(latText)
  if (!Number.isFinite(lng) || !Number.isFinite(lat)) {
    return null
  }
  return { lng, lat }
}

const calcHaversineMeters = (
  pointA: { lng: number; lat: number },
  pointB: { lng: number; lat: number }
) => {
  const rad = (deg: number) => (deg * Math.PI) / 180
  const dLat = rad(pointB.lat - pointA.lat)
  const dLng = rad(pointB.lng - pointA.lng)
  const lat1 = rad(pointA.lat)
  const lat2 = rad(pointB.lat)
  const a =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(lat1) * Math.cos(lat2) * Math.sin(dLng / 2) ** 2
  const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a))
  return Math.round(6371000 * c)
}

const recalcDayNextDistances = (dayPlan: DayPlan) => {
  dayPlan.activities.forEach((activity) => {
    activity.next_distance = undefined
  })

  const pointIndexes = dayPlan.activities
    .map((activity, idx) => ({ idx, point: parseLngLat(activity.location) }))
    .filter((item) => !!item.point) as Array<{ idx: number; point: { lng: number; lat: number } }>

  pointIndexes.forEach((current, pointerIdx) => {
    const next = pointIndexes[pointerIdx + 1]
    const currentActivity = dayPlan.activities[current.idx]
    if (!currentActivity) {
      return
    }
    currentActivity.next_distance = next ? calcHaversineMeters(current.point, next.point) : null
  })
}

const pickCity = (geo?: { city?: string; province?: string; district?: string }) => {
  return geo?.city || geo?.province || geo?.district || ''
}

const syncDestination = () => {
  if (queryForm.destination) {
    routeForm.destinationAddress = queryForm.destination
  }
}

const getActivityKey = (day: number, idx: number) => {
  return `${day}-${idx}`
}

const initActivityDrafts = (plans: DayPlan[] | null) => {
  Object.keys(activityDrafts).forEach((key) => {
    delete activityDrafts[key]
  })
  Object.keys(activitySavedDetails).forEach((key) => {
    delete activitySavedDetails[key]
  })
  if (!plans) {
    return
  }
  plans.forEach((dayPlan) => {
    dayPlan.activities.forEach((activity, idx) => {
      activityDrafts[getActivityKey(dayPlan.day, idx)] = String(activity.content || '')
    })
  })
}

const canEditActivity = (activity: PlanItem) => {
  return editableCategories.includes(activity.category || '')
}

const getActivityValidationError = (day: number, idx: number) => {
  return activityValidationErrors[getActivityKey(day, idx)] || ''
}

const isActivityValidationLoading = (day: number, idx: number) => {
  return !!activityValidationLoading[getActivityKey(day, idx)]
}

const clearActivityValidation = (day: number, idx: number) => {
  const key = getActivityKey(day, idx)
  delete activityValidationErrors[key]
  delete activityValidationSuggestions[key]
}

const getActivityDraft = (day: number, idx: number, activity: PlanItem) => {
  const key = getActivityKey(day, idx)
  if (Object.prototype.hasOwnProperty.call(activityDrafts, key)) {
    return activityDrafts[key]
  }
  const fallback = String(activity.content || '')
  activityDrafts[key] = fallback
  return fallback
}

const getActivitySuggestions = (day: number, idx: number) => {
  return activityValidationSuggestions[getActivityKey(day, idx)] || []
}

const getActivitySavedDetail = (day: number, idx: number) => {
  return activitySavedDetails[getActivityKey(day, idx)] || null
}

const formatSavedPlaceArea = (detail: MatchedPlaceInfo) => {
  const parts = [detail.pname, detail.cityname, detail.adname].filter((item) => String(item || '').trim())
  return parts.join(' ')
}

const getActivitySuggestionNote = (day: number, idx: number) => {
  const key = getActivityKey(day, idx)
  if (!activityValidationErrors[key]) {
    return ''
  }
  const suggestions = activityValidationSuggestions[key] || []
  return suggestions.length ? '' : '附近 5 公里暂无同类型推荐'
}

const validateActivityPlace = async (day: number, idx: number, activity: PlanItem) => {
  if (!canEditActivity(activity)) {
    return { ok: false as const }
  }

  const key = getActivityKey(day, idx)
  const placeName = String(getActivityDraft(day, idx, activity) || '').trim()
  const city = String(queryForm.destination || '').trim()

  if (!placeName) {
    activityValidationErrors[key] = '地点不存在'
    delete activityValidationSuggestions[key]
    return { ok: false as const }
  }

  if (!city) {
    activityValidationErrors[key] = '缺少目的地城市，无法校验该地点'
    delete activityValidationSuggestions[key]
    ElMessage.warning(activityValidationErrors[key])
    return { ok: false as const }
  }

  activityValidationLoading[key] = true
  try {
    const response = await mapAPI.checkPlaceInCity(placeName, city, activity.category)
    if (!response.data.exists) {
      activityValidationErrors[key] = `该地点在${city}范围内不存在`
      activityValidationSuggestions[key] = response.data.suggestions || []
      ElMessage.warning(activityValidationErrors[key])
      return { ok: false as const }
    }
    delete activityValidationErrors[key]
    delete activityValidationSuggestions[key]
    return {
      ok: true as const,
      matched: response.data.matched || null
    }
  } catch {
    activityValidationErrors[key] = '地点校验失败，请稍后重试'
    delete activityValidationSuggestions[key]
    return { ok: false as const }
  } finally {
    activityValidationLoading[key] = false
  }
}

const saveActivityEdit = async (day: number, idx: number, activity: PlanItem) => {
  const key = getActivityKey(day, idx)
  const previousContent = String(activity.content || '').trim()
  const result = await validateActivityPlace(day, idx, activity)
  if (result.ok) {
    const matched = result.matched
    activity.content = String(matched?.name || activityDrafts[key] || '').trim()
    activityDrafts[key] = activity.content
    if (matched) {
      activitySavedDetails[key] = matched
      if (matched.category) {
        activity.category = matched.category
      }
      if (matched.cost !== undefined && matched.cost !== null) {
        activity.cost = matched.cost
      }
      if (matched.rating !== undefined && matched.rating !== null) {
        activity.rating = matched.rating
      }
      if (matched.location) {
        activity.location = matched.location
      }
      if (matched.type) {
        activity.poi_type = matched.type
      }

      const area = formatSavedPlaceArea(matched)
      const address = matched.address || '地址待确认'
      const costText = activity.cost !== undefined ? `人均￥${activity.cost}` : '消费待确认'
      activity.tips = area
        ? `地址：${address}｜区域：${area}｜${costText}`
        : `地址：${address}｜${costText}`
    } else {
      delete activitySavedDetails[key]
    }

    const dayPlan = generatedPlan.value?.find((item) => item.day === day)
    if (dayPlan) {
      recalcDayNextDistances(dayPlan)
    }

    if (activity.content !== previousContent && generatedPlan.value?.length) {
      tripHistoryStore.addRecord(userStore.user?.id, {
        destination: queryForm.destination,
        days: generatedPlan.value.length,
        places: collectPlanDestinations(queryForm.destination, generatedPlan.value)
      })
      await persistItineraryRecord({
        destination: queryForm.destination,
        days: generatedPlan.value.length,
        hasEditedDestination: true,
        editedFrom: previousContent,
        editedTo: activity.content
      })
      await pushCollabUpdate(`第 ${day} 天地点更新：${previousContent} -> ${activity.content}`)
    }

    notifyBudgetExceeded()
    ElMessage.success('地点已保存')
    return
  }
  activityDrafts[key] = String(activity.content || '')
  ElMessage.error('地点不存在，未保存')
}

const clearActivityStateByDay = (day: number) => {
  const dayPrefix = `${day}-`
  Object.keys(activityValidationErrors).forEach((key) => {
    if (key.startsWith(dayPrefix)) {
      delete activityValidationErrors[key]
    }
  })
  Object.keys(activityValidationLoading).forEach((key) => {
    if (key.startsWith(dayPrefix)) {
      delete activityValidationLoading[key]
    }
  })
  Object.keys(activityValidationSuggestions).forEach((key) => {
    if (key.startsWith(dayPrefix)) {
      delete activityValidationSuggestions[key]
    }
  })
  Object.keys(activitySavedDetails).forEach((key) => {
    if (key.startsWith(dayPrefix)) {
      delete activitySavedDetails[key]
    }
  })
  Object.keys(activityDrafts).forEach((key) => {
    if (key.startsWith(dayPrefix)) {
      delete activityDrafts[key]
    }
  })
}

const deleteActivity = async (day: number, idx: number) => {
  const dayPlan = generatedPlan.value?.find((item) => item.day === day)
  const activity = dayPlan?.activities[idx]
  if (!dayPlan || !activity) {
    return
  }

  const removedContent = String(activity.content || '').trim() || '未命名地点'
  try {
    await ElMessageBox.confirm(`确认删除“${removedContent}”吗？`, '删除可编辑目的地', {
      confirmButtonText: '删除',
      cancelButtonText: '取消',
      type: 'warning'
    })
  } catch {
    return
  }

  dayPlan.activities.splice(idx, 1)
  recalcDayNextDistances(dayPlan)
  clearActivityStateByDay(day)
  dayPlan.activities.forEach((item, nextIdx) => {
    activityDrafts[getActivityKey(day, nextIdx)] = String(item.content || '')
  })

  if (generatedPlan.value?.length) {
    tripHistoryStore.addRecord(userStore.user?.id, {
      destination: queryForm.destination,
      days: generatedPlan.value.length,
      places: collectPlanDestinations(queryForm.destination, generatedPlan.value)
    })
    await persistItineraryRecord({
      destination: queryForm.destination,
      days: generatedPlan.value.length,
      hasEditedDestination: true,
      editedFrom: removedContent,
      editedTo: '（已删除）'
    })
    await pushCollabUpdate(`第 ${day} 天删除地点：${removedContent}`)
  }

  notifyBudgetExceeded()
  ElMessage.success('目的地已删除')
}

const resolveOrigin = async () => {
  if (routeForm.useCurrentLocation) {
    return new Promise<string>((resolve, reject) => {
      if (!navigator.geolocation) {
        reject(new Error('浏览器不支持定位'))
        return
      }
      navigator.geolocation.getCurrentPosition(
        (pos) => {
          const lng = pos.coords.longitude.toFixed(6)
          const lat = pos.coords.latitude.toFixed(6)
          resolve(`${lng},${lat}`)
        },
        (err) => reject(err),
        { enableHighAccuracy: true, timeout: 10000 }
      )
    })
  }

  if (!routeForm.originAddress) {
    throw new Error('请输入出发地地址')
  }

  const geocodeRes = await mapAPI.geocode(routeForm.originAddress)
  const geo = geocodeRes.data.geocodes?.[0]
  if (!geo?.location) {
    throw new Error('出发地解析失败')
  }
  if (!routeForm.city) {
    routeForm.city = pickCity(geo)
  }
  return geo.location
}

const resolveDestination = async () => {
  const destinationText = routeForm.destinationAddress || queryForm.destination
  if (!destinationText) {
    throw new Error('请输入目的地')
  }
  const geocodeRes = await mapAPI.geocode(destinationText)
  const geo = geocodeRes.data.geocodes?.[0]
  if (!geo?.location) {
    throw new Error('目的地解析失败')
  }
  if (!routeForm.cityd) {
    routeForm.cityd = pickCity(geo)
  }
  if (!routeForm.city) {
    routeForm.city = pickCity(geo)
  }
  return geo.location
}

const handlePlanRoute = async () => {
  routeLoading.value = true
  try {
    const origin = await resolveOrigin()
    const destination = await resolveDestination()

    originLngLat.value = origin
    destinationLngLat.value = destination

    const response = await mapAPI.planRoute({
      origin,
      destination,
      mode: routeForm.mode,
      city: routeForm.mode === 'transit' ? routeForm.city : undefined,
      cityd: routeForm.mode === 'transit' ? routeForm.cityd : undefined
    })

    routePlan.value = response.data.route
    routeMode.value = response.data.mode
    ElMessage.success('路线规划成功')
  } catch (error: unknown) {
    routePlan.value = null
    const err = error as { response?: { data?: { message?: string } }; message?: string }
    ElMessage.error(err.response?.data?.message || err.message || '路线规划失败')
  } finally {
    routeLoading.value = false
  }
}

const saveCurrentRoute = async () => {
  if (!routePlan.value) {
    ElMessage.warning('请先生成路线')
    return
  }
  saveRouteLoading.value = true
  try {
    await mapAPI.saveRoute({
      origin_address: routeForm.useCurrentLocation ? '在线定位' : routeForm.originAddress,
      destination_address: routeForm.destinationAddress || queryForm.destination,
      origin_lnglat: originLngLat.value,
      destination_lnglat: destinationLngLat.value,
      mode: routeMode.value,
      distance: routePlan.value.distance,
      duration: routePlan.value.duration,
      cost: routePlan.value.cost,
      steps: routePlan.value.steps
    })
    ElMessage.success('路线已保存')
  } catch (error: unknown) {
    const err = error as { response?: { data?: { message?: string } }; message?: string }
    ElMessage.error(err.response?.data?.message || err.message || '路线保存失败')
  } finally {
    saveRouteLoading.value = false
  }
}

const loadSavedRoutes = async () => {
  listRouteLoading.value = true
  try {
    const response = await mapAPI.listRoutes()
    savedRoutes.value = response.data
    if (!savedRoutes.value.length) {
      ElMessage.info('暂无已保存路线')
    }
  } catch (error: unknown) {
    const err = error as { response?: { data?: { message?: string } }; message?: string }
    ElMessage.error(err.response?.data?.message || err.message || '获取路线失败')
  } finally {
    listRouteLoading.value = false
  }
}

onBeforeUnmount(() => {
  clearCollabAckTimer()
  stopCollabPolling()
  teardownCollabRealtime(true)
})
</script>

<template>
  <div class="tour-planner">
    <div class="planner-atmosphere" aria-hidden="true">
      <span class="orb orb-sea"></span>
      <span class="orb orb-sun"></span>
      <span class="orb orb-leaf"></span>
    </div>

    <section class="planner-hero reveal-up">
      <div>
        <p class="hero-eyebrow">Smart Itinerary Workspace</p>
        <h2>{{ queryForm.destination || '登录后主页面' }} · 旅游协作工作台</h2>
        <p>在同一块画布里规划路线、同步协作、管理预算与交通方案。</p>
      </div>
      <div class="planner-chip-grid">
        <div class="planner-chip">
          <span>计划天数</span>
          <strong>{{ queryForm.days }} 天</strong>
        </div>
        <div class="planner-chip">
          <span>协作版本</span>
          <strong>v{{ collabVersion }}</strong>
        </div>
        <div class="planner-chip">
          <span>交通方案</span>
          <strong>{{ routePlan ? '已生成' : '待生成' }}</strong>
        </div>
      </div>
    </section>

    <el-row :gutter="24" class="planner-grid">
      <el-col :md="8" :sm="24">
        <el-card class="config-card" header="规划您的奇妙旅程">
          <el-form :model="queryForm" label-position="top">
            <el-form-item label="你想去哪里？">
              <el-input v-model="queryForm.destination" placeholder="如：西安、成都、大理..." :prefix-icon="Location" />
            </el-form-item>

            <el-form-item label="计划游玩几天？">
              <el-input-number v-model="queryForm.days" :min="1" :max="15" style="width: 100%" />
            </el-form-item>

            <el-form-item label="计划出行日期（用于判断开放日）">
              <el-date-picker
                v-model="queryForm.visitDate"
                type="date"
                value-format="YYYY-MM-DD"
                placeholder="选择计划出行日期"
                style="width: 100%"
                clearable
              />
            </el-form-item>

            <el-form-item label="预算金额（元）">
              <el-input-number
                v-model="queryForm.budget"
                :min="100"
                :max="200000"
                :step="100"
                :precision="0"
                controls-position="right"
                style="width: 100%"
              />
            </el-form-item>

            <el-form-item label="推荐侧重">
              <el-radio-group v-model="queryForm.recommendFocus">
                <el-radio-button
                  v-for="item in recommendFocusOptions"
                  :key="item.value"
                  :label="item.value"
                  :value="item.value"
                >
                  {{ item.label }}
                </el-radio-button>
              </el-radio-group>
            </el-form-item>

            <el-form-item label="旅游紧凑度">
              <el-radio-group v-model="queryForm.pace">
                <el-radio-button
                  v-for="item in paceOptions"
                  :key="item.value"
                  :label="item.value"
                  :value="item.value"
                >
                  {{ item.label }}
                </el-radio-button>
              </el-radio-group>
            </el-form-item>

            <el-form-item label="兴趣偏好">
              <el-checkbox-group v-model="queryForm.preferences">
                <el-checkbox v-for="opt in preferenceOptions" :key="opt" :label="opt" :value="opt">
                  {{ opt }}
                </el-checkbox>
              </el-checkbox-group>
            </el-form-item>

            <div class="form-actions">
              <el-button type="primary" :loading="loading" @click="handleGenerate" class="generate-btn">
                <el-icon><Guide /></el-icon> 立即生成行程
              </el-button>
              <el-button @click="resetForm">重置</el-button>
            </div>
          </el-form>
        </el-card>

        <el-card class="config-card route-card" header="交通行程规划">
          <el-form :model="routeForm" label-position="top">
            <el-form-item label="出发地">
              <el-input
                v-model="routeForm.originAddress"
                :disabled="routeForm.useCurrentLocation"
                placeholder="定位当前城市或手动输入地址"
              />
            </el-form-item>
            <el-form-item>
              <el-switch v-model="routeForm.useCurrentLocation" active-text="使用在线定位" />
            </el-form-item>

            <el-form-item label="目的地">
              <el-input v-model="routeForm.destinationAddress" placeholder="输入目的地地址" />
              <el-button link type="primary" @click="syncDestination">同步上方目的地</el-button>
            </el-form-item>

            <el-form-item label="交通方式">
              <el-select v-model="routeForm.mode" style="width: 100%">
                <el-option v-for="item in routeModes" :key="item.value" :label="item.label" :value="item.value" />
              </el-select>
            </el-form-item>

            <el-form-item v-if="routeForm.mode === 'transit'" label="出发城市">
              <el-input v-model="routeForm.city" placeholder="如：西安" />
            </el-form-item>
            <el-form-item v-if="routeForm.mode === 'transit'" label="目的地城市">
              <el-input v-model="routeForm.cityd" placeholder="如：成都" />
            </el-form-item>

            <div class="form-actions">
              <el-button type="primary" :loading="routeLoading" @click="handlePlanRoute">
                生成交通方案
              </el-button>
              <el-button :loading="listRouteLoading" @click="loadSavedRoutes">
                查看已保存路线
              </el-button>
            </div>
          </el-form>
        </el-card>

        <el-card class="config-card route-card" header="轻量实时协作">
          <div class="collab-panel">
            <div class="collab-join-row">
              <el-input
                v-model="collabJoinToken"
                placeholder="输入协作邀请码加入会话"
                clearable
              />
              <el-button type="primary" :loading="collabLoading" @click="joinCollabSession">
                加入
              </el-button>
            </div>

            <div class="collab-actions-row">
              <el-button
                type="success"
                plain
                :loading="collabLoading"
                :disabled="!generatedPlan?.length"
                @click="createCollabSession"
              >
                开启协作会话
              </el-button>
              <el-button
                :disabled="!collabSessionId"
                :loading="collabPolling"
                @click="pollCollabSession(false)"
              >
                立即同步
              </el-button>
            </div>

            <div v-if="collabSessionId" class="collab-status">
              <div><strong>会话ID：</strong>{{ collabSessionId }}</div>
              <div>
                <strong>邀请码：</strong>{{ collabShareToken }}
                <el-button link type="primary" @click="copyCollabToken">复制</el-button>
              </div>
              <div><strong>当前版本：</strong>v{{ collabVersion }}</div>
              <div><strong>我的角色：</strong>{{ collabRole || 'editor' }}</div>
              <div><strong>实时通道：</strong>{{ collabRealtimeConnected ? 'WebSocket 已连接' : '未连接（轮询兜底）' }}</div>
              <div><strong>最近编辑：</strong>{{ collabLastEditorName || '暂无' }}</div>
              <div><strong>协作者：</strong>{{ collabMembers.map((item) => item.username).join('、') || '暂无' }}</div>
              <el-alert
                v-if="collabConflictNotice"
                class="collab-conflict-alert"
                type="warning"
                show-icon
                :closable="true"
                :title="`检测到冲突：服务器版本 v${collabConflictNotice.serverVersion}`"
                :description="`${collabConflictNotice.message}（最近编辑：${collabConflictNotice.lastEditorName}，时间：${collabConflictNotice.createdAt}）`"
                @close="clearCollabConflictNotice"
              />
            </div>
          </div>
        </el-card>
      </el-col>

      <el-col :md="16" :sm="24">
        <div v-if="loading" class="loading-state">
           <el-skeleton :rows="10" animated />
           <p>正在为您推荐最佳路线...</p>
        </div>

        <div v-else-if="generatedPlan" class="plan-display">
          <div class="plan-header">
            <h3>为您生成的专属路线：{{ queryForm.destination }}之旅</h3>
            <div v-if="collabSessionId" class="plan-collab-meta">
              <el-tag type="success" effect="plain">协作中</el-tag>
              <el-tag type="info" effect="plain">版本 v{{ collabVersion }}</el-tag>
              <el-tag v-if="collabSaving" type="warning" effect="plain">正在同步</el-tag>
            </div>
          </div>

          <el-card v-if="currentWeather" class="weather-card">
            <div class="weather-header">当天天气</div>
            <div class="weather-body">
              <div class="weather-main">
                <span class="weather-city">{{ currentWeather.city }}</span>
                <span class="weather-state">{{ currentWeather.weather }}</span>
              </div>
              <div class="weather-detail">
                <span>温度：{{ currentWeather.temperature }}°C</span>
                <span>风向：{{ currentWeather.winddirection }} {{ currentWeather.windpower }}</span>
                <span>湿度：{{ currentWeather.humidity }}%</span>
                <span>更新时间：{{ currentWeather.reporttime }}</span>
              </div>
            </div>
          </el-card>

          <el-card class="estimated-cost-card">
            <div class="estimated-cost-main">
              <span>消费总金额（estimated_cost）</span>
              <strong>{{ formatCost(estimated_cost) }}</strong>
            </div>
            <div class="estimated-cost-sub">
              预算金额：{{ formatCost(queryForm.budget) }}
            </div>
            <el-alert
              v-if="isBudgetExceeded"
              type="warning"
              show-icon
              :closable="false"
              :title="`预算超支：${formatCost(budgetOverflowAmount)}`"
              :description="`当前预计总消费 ${formatCost(estimated_cost)}，已超过预算 ${formatCost(queryForm.budget)}`"
              class="budget-alert"
            />
          </el-card>

          <el-timeline>
            <el-timeline-item
              v-for="dayPlan in generatedPlan"
              :key="dayPlan.day"
              :timestamp="'第 ' + dayPlan.day + ' 天'"
              placement="top"
              type="primary"
              size="large"
            >
              <el-card class="day-card">
                <div class="day-summary">
                  <span>当日预计花费</span>
                  <strong>{{ formatCost(calcDayTotal(dayPlan.activities)) }}</strong>
                </div>
                <div v-for="(activity, idx) in dayPlan.activities" :key="idx" class="activity-item">
                  <div class="activity-time">
                    <el-tag size="small" effect="dark" type="info">{{ activity.time }}</el-tag>
                    <el-tag v-if="activity.category" size="small" class="activity-category">{{ activity.category }}</el-tag>
                    <el-tag v-if="activity.cost !== undefined" size="small" effect="plain" type="success">
                      {{ formatCost(activity.cost) }}
                    </el-tag>
                    <el-tag v-if="activity.rating !== undefined" size="small" effect="plain" type="warning">
                      评分 {{ formatRating(activity.rating) }}
                    </el-tag>
                  </div>
                  <div class="activity-desc">
                    <div v-if="canEditActivity(activity)" class="activity-edit-row">
                      <el-input
                        v-model="activityDrafts[getActivityKey(dayPlan.day, idx)]"
                        size="small"
                        class="activity-edit-input"
                        placeholder="可编辑地点"
                        @input="clearActivityValidation(dayPlan.day, idx)"
                      >
                        <template #suffix>
                          <el-icon v-if="isActivityValidationLoading(dayPlan.day, idx)" class="is-loading">
                            <Loading />
                          </el-icon>
                        </template>
                      </el-input>
                      <el-button
                        size="small"
                        type="primary"
                        :loading="isActivityValidationLoading(dayPlan.day, idx)"
                        @click="saveActivityEdit(dayPlan.day, idx, activity)"
                      >
                        保存
                      </el-button>
                      <el-button
                        size="small"
                        type="danger"
                        plain
                        @click="deleteActivity(dayPlan.day, idx)"
                      >
                        删除
                      </el-button>
                    </div>
                    <strong v-else>{{ activity.content }}</strong>
                    <p v-if="getActivityValidationError(dayPlan.day, idx)" class="activity-error">
                      {{ getActivityValidationError(dayPlan.day, idx) }}
                    </p>
                    <div v-if="getActivitySuggestions(dayPlan.day, idx).length" class="activity-suggestions">
                      <div class="suggestions-title">附近 5 公里同类型：</div>
                      <div class="suggestion-items">
                        <div
                          v-for="item in getActivitySuggestions(dayPlan.day, idx)"
                          :key="item.name + item.address"
                          class="suggestion-item"
                        >
                          <span class="suggestion-name">{{ item.name }}</span>
                          <span v-if="item.address" class="suggestion-address">· {{ item.address }}</span>
                          <span v-if="item.distance_m" class="suggestion-distance">
                            ({{ formatDistance(item.distance_m) }})
                          </span>
                        </div>
                      </div>
                    </div>
                    <p v-else-if="getActivitySuggestionNote(dayPlan.day, idx)" class="activity-suggestions">
                      {{ getActivitySuggestionNote(dayPlan.day, idx) }}
                    </p>
                    <div v-if="getActivitySavedDetail(dayPlan.day, idx)" class="activity-saved-detail">
                      <div class="saved-detail-title">已保存地点信息</div>
                      <div class="saved-detail-item">
                        名称：{{ getActivitySavedDetail(dayPlan.day, idx)?.name }}
                      </div>
                      <div v-if="getActivitySavedDetail(dayPlan.day, idx)?.address" class="saved-detail-item">
                        地址：{{ getActivitySavedDetail(dayPlan.day, idx)?.address }}
                      </div>
                      <div v-if="formatSavedPlaceArea(getActivitySavedDetail(dayPlan.day, idx)!)" class="saved-detail-item">
                        区域：{{ formatSavedPlaceArea(getActivitySavedDetail(dayPlan.day, idx)!) }}
                      </div>
                      <div v-if="getActivitySavedDetail(dayPlan.day, idx)?.location" class="saved-detail-item">
                        坐标：{{ getActivitySavedDetail(dayPlan.day, idx)?.location }}
                      </div>
                      <div v-if="getActivitySavedDetail(dayPlan.day, idx)?.type" class="saved-detail-item">
                        类型：{{ getActivitySavedDetail(dayPlan.day, idx)?.type }}
                      </div>
                    </div>
                    <p v-if="activity.recommend_reason" class="activity-reason">
                      <el-icon><Guide /></el-icon> 推荐理由：{{ activity.recommend_reason }}
                    </p>
                    <p v-if="getOpeningSuggestion(activity)" class="activity-opening">
                      <el-icon><Timer /></el-icon> 开放时间：{{ getOpeningSuggestion(activity) }}
                    </p>
                    <p v-if="activity.tips" class="activity-tips">
                      <el-icon><Timer /></el-icon> 建议：{{ activity.tips }}
                    </p>
                    <p v-if="activity.next_distance !== undefined && activity.next_distance !== null" class="activity-distance-next">
                      到下一地点：{{ formatDistance(activity.next_distance) }}
                    </p>
                  </div>
                </div>
              </el-card>
            </el-timeline-item>
          </el-timeline>
        </div>

        <el-card v-if="collabSessionId" class="route-plan-card collab-log-card">
          <div class="route-plan-header">
            <h3>协作变更日志{{ collabTitle ? ` · ${collabTitle}` : '' }}</h3>
          </div>
          <el-timeline v-if="collabChanges.length">
            <el-timeline-item
              v-for="change in collabChanges"
              :key="change.id"
              :timestamp="formatCollabTime(change.created_at)"
              placement="top"
            >
              <el-card
                class="route-step-card collab-change-card"
                :class="{ 'is-active-trace': collabTraceAnchor?.id === change.id }"
                @click="traceCollabChange(change)"
              >
                <div class="route-step-title">
                  v{{ change.version }} · {{ change.summary || '更新行程内容' }}
                </div>
                <div class="route-step-meta">
                  <span>操作者：{{ change.editor_username || '未知用户' }}</span>
                  <span>时间：{{ formatCollabTime(change.created_at) }}</span>
                  <el-tag size="small" type="info" effect="plain">点击追溯</el-tag>
                </div>
              </el-card>
            </el-timeline-item>
          </el-timeline>
          <el-empty v-else description="暂无变更日志" />

          <el-card v-if="collabTraceAnchor" class="collab-trace-card" shadow="never">
            <div class="collab-trace-header">
              <strong>变更追溯 · 起点 v{{ collabTraceAnchor.version }}</strong>
              <el-button link type="primary" @click="clearCollabTrace">关闭</el-button>
            </div>
            <div class="collab-trace-subtitle">
              起点：{{ collabTraceAnchor.summary || '更新行程内容' }}
            </div>

            <el-skeleton v-if="collabTraceLoading" :rows="3" animated />

            <el-timeline v-else-if="collabTraceChain.length" class="collab-trace-timeline">
              <el-timeline-item
                v-for="item in collabTraceChain"
                :key="item.id"
                :timestamp="formatCollabTime(item.created_at)"
                placement="top"
              >
                <div class="collab-trace-item">
                  <div class="collab-trace-item-title">v{{ item.version }} · {{ item.summary || '更新行程内容' }}</div>
                  <div class="collab-trace-item-meta">操作者：{{ item.editor_username || '未知用户' }}</div>
                  <pre
                    v-if="item.change_payload && Object.keys(item.change_payload).length"
                    class="collab-trace-payload"
                  >{{ JSON.stringify(item.change_payload, null, 2) }}</pre>
                </div>
              </el-timeline-item>
            </el-timeline>

            <el-empty v-else description="暂无可追溯变更" />
          </el-card>
        </el-card>

        <el-card v-if="routePlan" class="route-plan-card">
          <div class="route-plan-header">
            <h3>交通方案：{{ routeModes.find((item) => item.value === routeMode)?.label }}</h3>
            <div class="route-summary">
              <span>距离：{{ formatDistance(routePlan.distance) }}</span>
              <span>耗时：{{ formatDuration(routePlan.duration) }}</span>
              <span>费用：￥{{ routePlan.cost.toFixed(1) }}</span>
            </div>
            <p class="route-coords" v-if="originLngLat && destinationLngLat">
              起点：{{ originLngLat }} ｜ 终点：{{ destinationLngLat }}
            </p>
            <div class="route-actions">
              <el-button type="primary" :loading="saveRouteLoading" @click="saveCurrentRoute">
                保存这条路线
              </el-button>
            </div>
          </div>
          <el-timeline>
            <el-timeline-item
              v-for="(step, idx) in routePlan.steps"
              :key="idx"
              :timestamp="formatDuration(step.duration)"
              placement="top"
            >
              <el-card class="route-step-card">
                <div class="route-step-title">{{ step.instruction }}</div>
                <div class="route-step-meta">
                  <span>距离：{{ formatDistance(step.distance) }}</span>
                  <span v-if="step.road">道路：{{ step.road }}</span>
                  <span v-if="step.type">方式：{{ step.type }}</span>
                </div>
              </el-card>
            </el-timeline-item>
          </el-timeline>
        </el-card>

        <el-card v-if="savedRoutes.length" class="route-plan-card">
          <div class="route-plan-header">
            <h3>已保存路线</h3>
          </div>
          <el-timeline>
            <el-timeline-item
              v-for="item in savedRoutes"
              :key="item.id"
              :timestamp="item.created_at"
              placement="top"
            >
              <el-card class="route-step-card">
                <div class="route-step-title">
                  {{ item.origin_address || item.origin_lnglat }} → {{ item.destination_address || item.destination_lnglat }}
                </div>
                <div class="route-step-meta">
                  <span>方式：{{ routeModes.find((m) => m.value === item.mode)?.label || item.mode }}</span>
                  <span>距离：{{ formatDistance(item.distance) }}</span>
                  <span>耗时：{{ formatDuration(item.duration) }}</span>
                  <span>费用：￥{{ item.cost.toFixed(1) }}</span>
                </div>
              </el-card>
            </el-timeline-item>
          </el-timeline>
        </el-card>

        <div v-if="!loading && !generatedPlan && !routePlan" class="empty-state">
          <el-empty description="输入您的目的地，开启个性化行程定制">
            <template #image>
              <el-icon :size="100" color="#e4e7ed"><Bicycle /></el-icon>
            </template>
          </el-empty>
        </div>
      </el-col>
    </el-row>
  </div>
</template>

<style scoped>
@import url('https://fonts.googleapis.com/css2?family=Manrope:wght@500;600;700;800&family=Noto+Sans+SC:wght@400;500;700;900&display=swap');

.tour-planner {
  --primary: #2563eb;
  --primary-soft: #eaf2ff;
  --cta: #f97316;
  --text-main: #17365f;
  --text-sub: #516e8f;
  position: relative;
  min-height: calc(100dvh - 140px);
  padding: 18px;
  overflow: hidden;
  background:
    radial-gradient(circle at 10% 16%, rgba(37, 99, 235, 0.2), transparent 38%),
    radial-gradient(circle at 86% 9%, rgba(249, 115, 22, 0.18), transparent 35%),
    linear-gradient(145deg, #f5fbff 0%, #ecf3ff 52%, #f8fdf7 100%);
}

.planner-atmosphere {
  position: absolute;
  inset: 0;
  pointer-events: none;
}

.orb {
  position: absolute;
  border-radius: 999px;
  filter: blur(4px);
  animation: float 10s ease-in-out infinite;
}

.orb-sea {
  width: 210px;
  height: 210px;
  top: -74px;
  left: -56px;
  background: rgba(37, 99, 235, 0.22);
}

.orb-sun {
  width: 160px;
  height: 160px;
  top: 10px;
  right: 9%;
  background: rgba(249, 115, 22, 0.2);
  animation-delay: 1.4s;
}

.orb-leaf {
  width: 230px;
  height: 230px;
  right: -72px;
  bottom: -84px;
  background: rgba(22, 163, 74, 0.15);
  animation-delay: 2.4s;
}

.planner-hero {
  position: relative;
  z-index: 1;
  display: grid;
  grid-template-columns: 1.2fr 1fr;
  gap: 16px;
  align-items: center;
  margin-bottom: 16px;
  border-radius: 24px;
  padding: 22px 24px;
  border: 1px solid rgba(255, 255, 255, 0.85);
  backdrop-filter: blur(12px);
  background: rgba(255, 255, 255, 0.75);
  box-shadow: 0 14px 32px rgba(22, 65, 148, 0.1);
}

.hero-eyebrow {
  margin: 0 0 8px;
  font-size: 12px;
  letter-spacing: 0.2em;
  text-transform: uppercase;
  color: var(--primary);
  font-weight: 700;
}

.planner-hero h2 {
  margin: 0;
  font-size: clamp(24px, 3vw, 36px);
  color: #0f2f59;
  font-weight: 800;
  font-family: 'Manrope', 'Noto Sans SC', sans-serif;
}

.planner-hero p {
  margin: 10px 0 0;
  color: var(--text-sub);
}

.planner-chip-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 8px;
}

.planner-chip {
  border-radius: 14px;
  padding: 12px;
  background: rgba(255, 255, 255, 0.72);
  border: 1px solid rgba(37, 99, 235, 0.1);
  display: grid;
  gap: 4px;
}

.planner-chip span {
  font-size: 12px;
  color: var(--text-sub);
}

.planner-chip strong {
  color: #143760;
  font-size: 16px;
}

.planner-grid {
  position: relative;
  z-index: 1;
}

.config-card,
.route-plan-card,
.day-card,
.route-step-card,
.weather-card,
.estimated-cost-card {
  border-radius: 16px;
  border: 1px solid rgba(255, 255, 255, 0.85);
  box-shadow: 0 14px 32px rgba(22, 65, 148, 0.08);
  background: rgba(255, 255, 255, 0.88);
}

.config-card {
  backdrop-filter: blur(10px);
}

.config-card :deep(.el-card__header) {
  font-weight: 800;
  font-size: 1rem;
  color: var(--text-main);
  border-bottom: 1px solid rgba(37, 99, 235, 0.08);
  font-family: 'Manrope', 'Noto Sans SC', sans-serif;
}

:deep(.config-card .el-card__body) {
  padding-top: 18px;
}

:deep(.el-form-item__label) {
  color: #2b4a71;
  font-weight: 700;
}

:deep(.el-input__wrapper),
:deep(.el-input-number),
:deep(.el-date-editor.el-input__wrapper),
:deep(.el-select__wrapper) {
  border-radius: 12px;
}

.form-actions {
  margin-top: 22px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.generate-btn {
  height: 44px;
  font-size: 1rem;
  border: 0;
  border-radius: 12px;
  font-weight: 700;
  background: linear-gradient(120deg, var(--primary), #1d4ed8 56%, var(--cta) 130%);
}

.plan-header {
  margin-bottom: 18px;
  padding: 14px;
  border-radius: 12px;
  background: var(--primary-soft);
  border: 1px solid rgba(37, 99, 235, 0.12);
}

.plan-header h3 {
  margin: 0;
  color: #11355f;
  font-family: 'Manrope', 'Noto Sans SC', sans-serif;
}

.plan-collab-meta {
  margin-top: 8px;
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.route-card {
  margin-top: 18px;
}

.weather-card,
.estimated-cost-card {
  margin-bottom: 18px;
}

.estimated-cost-main {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 6px;
  font-size: 14px;
  color: var(--text-sub);
}

.estimated-cost-main strong {
  font-size: 20px;
  color: #0d335f;
}

.estimated-cost-sub {
  margin-bottom: 10px;
  font-size: 13px;
  color: #6a82a0;
}

.budget-alert {
  margin-top: 4px;
}

.weather-header {
  font-weight: 700;
  color: var(--primary);
  margin-bottom: 8px;
}

.weather-body {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.weather-main {
  display: flex;
  align-items: center;
  gap: 12px;
  font-size: 16px;
}

.weather-city {
  font-weight: 700;
  color: #173b66;
}

.weather-state {
  color: #35597f;
}

.weather-detail {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 6px 16px;
  font-size: 13px;
  color: #516e8f;
}

.day-card {
  margin-bottom: 14px;
}

.day-summary {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 14px;
  padding: 10px 12px;
  background: #f2f8ff;
  border: 1px solid rgba(37, 99, 235, 0.08);
  border-radius: 10px;
  font-size: 13px;
  color: #446182;
}

.day-summary strong {
  color: #123b6d;
}

.activity-item {
  display: flex;
  margin-bottom: 15px;
  padding-bottom: 12px;
  border-bottom: 1px dashed rgba(37, 99, 235, 0.14);
}

.activity-item:last-child {
  margin-bottom: 0;
  padding-bottom: 0;
  border-bottom: none;
}

.activity-time {
  min-width: 76px;
  margin-right: 15px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.activity-category {
  background-color: #edf4ff;
  color: var(--primary);
}

.activity-desc strong {
  display: block;
  margin-bottom: 5px;
  color: #11365f;
}

.activity-edit-input {
  flex: 1;
}

.activity-edit-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
}

.activity-error {
  margin: 0 0 6px;
  font-size: 12px;
  color: #e24f4f;
}

.activity-suggestions {
  margin: 0 0 6px;
  font-size: 12px;
  color: #4e6786;
}

.suggestions-title {
  margin-bottom: 2px;
  color: #7a90ab;
}

.suggestion-items {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.suggestion-name {
  font-weight: 700;
  color: #24496f;
}

.suggestion-address,
.suggestion-distance {
  margin-left: 4px;
  color: #8095ac;
}

.activity-saved-detail {
  margin: 0 0 8px;
  padding: 8px 10px;
  border-radius: 8px;
  background: #f4fdf7;
  border: 1px solid #d6f2df;
}

.saved-detail-title {
  margin-bottom: 4px;
  font-size: 12px;
  font-weight: 700;
  color: #2f8a56;
}

.saved-detail-item {
  font-size: 12px;
  color: #4e6786;
  line-height: 1.5;
}

.activity-tips,
.activity-reason,
.activity-opening {
  font-size: 0.85rem;
  display: flex;
  align-items: center;
  gap: 4px;
  margin-bottom: 4px;
}

.activity-tips {
  color: #607890;
}

.activity-reason {
  color: #355ac9;
}

.activity-opening {
  color: #2f8a56;
}

.activity-distance-next {
  margin-top: 4px;
  font-size: 0.82rem;
  color: #617a97;
}

.loading-state {
  text-align: center;
  padding: 36px;
  color: #6c85a1;
  border-radius: 14px;
  background: rgba(255, 255, 255, 0.74);
  border: 1px solid rgba(37, 99, 235, 0.08);
}

.empty-state {
  height: 100%;
  min-height: 380px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(255, 255, 255, 0.72);
  border-radius: 16px;
  border: 1px dashed rgba(37, 99, 235, 0.25);
}

.route-plan-card {
  margin-top: 22px;
}

.route-plan-header h3 {
  margin: 0 0 8px;
  color: #153d69;
  font-family: 'Manrope', 'Noto Sans SC', sans-serif;
}

.route-summary {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  font-size: 13px;
  color: #516e8f;
}

.route-coords {
  margin-top: 8px;
  font-size: 12px;
  color: #738ba5;
}

.route-actions {
  margin-top: 12px;
}

.route-step-title {
  font-weight: 700;
  color: #143b66;
  margin-bottom: 6px;
}

.route-step-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  font-size: 12px;
  color: #516e8f;
}

.collab-panel {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.collab-join-row {
  display: flex;
  gap: 8px;
}

.collab-actions-row {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.collab-status {
  padding: 12px;
  border-radius: 10px;
  border: 1px solid #e0ecff;
  background: #f4f9ff;
  font-size: 12px;
  color: #4e6786;
  line-height: 1.8;
}

.collab-conflict-alert {
  margin-top: 8px;
}

.collab-log-card {
  margin-top: 16px;
}

.collab-change-card {
  cursor: pointer;
  transition: border-color 0.2s ease, box-shadow 0.2s ease, transform 0.2s ease;
}

.collab-change-card:hover {
  border-color: #bfd8ff;
  box-shadow: 0 6px 16px rgba(64, 158, 255, 0.12);
  transform: translateY(-2px);
}

.collab-change-card.is-active-trace {
  border-color: #409eff;
  box-shadow: 0 0 0 1px rgba(64, 158, 255, 0.25);
}

.collab-trace-card {
  margin-top: 12px;
  border-radius: 12px;
  background: #fbfdff;
}

.collab-trace-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 6px;
}

.collab-trace-subtitle {
  margin-bottom: 10px;
  font-size: 12px;
  color: #5f7897;
}

.collab-trace-timeline {
  margin-top: 8px;
}

.collab-trace-item-title {
  font-weight: 700;
  color: #173c69;
  margin-bottom: 4px;
}

.collab-trace-item-meta {
  font-size: 12px;
  color: #5f7897;
  margin-bottom: 6px;
}

.collab-trace-payload {
  margin: 0;
  padding: 8px 10px;
  border-radius: 8px;
  background: #f2f6fc;
  border: 1px solid #e1e9f6;
  font-size: 12px;
  color: #364a63;
  white-space: pre-wrap;
  word-break: break-all;
}

.reveal-up {
  opacity: 0;
  transform: translateY(12px);
  animation: revealUp 0.65s ease forwards;
}

@keyframes revealUp {
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

@media (max-width: 1024px) {
  .planner-hero {
    grid-template-columns: 1fr;
  }

  .planner-chip-grid {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
}

@media (max-width: 768px) {
  .tour-planner {
    min-height: calc(100dvh - 120px);
    padding: 12px;
  }

  .planner-hero {
    padding: 18px;
    border-radius: 18px;
    margin-bottom: 12px;
  }

  .planner-chip-grid {
    grid-template-columns: 1fr;
  }

  .weather-detail {
    grid-template-columns: 1fr;
  }

  .activity-item {
    flex-direction: column;
    gap: 10px;
  }

  .activity-time {
    margin-right: 0;
    flex-direction: row;
    min-width: 0;
    flex-wrap: wrap;
  }

  .collab-join-row,
  .activity-edit-row {
    flex-direction: column;
    align-items: stretch;
  }
}

@media (prefers-reduced-motion: reduce) {
  .orb,
  .reveal-up,
  .collab-change-card {
    animation: none;
    transition: none;
    transform: none;
  }
}
</style>
