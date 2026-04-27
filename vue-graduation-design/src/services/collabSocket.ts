import { io, Socket } from 'socket.io-client'

let socket: Socket | null = null
let currentAuthToken = ''

const API_URL = (import.meta.env.VITE_API_URL as string) || 'http://localhost:5000/api'
const WS_URL = API_URL.replace(/\/api\/?$/, '')

type CollabPlanItem = Record<string, unknown>

type CollabPatchPayload = {
  itinerary_id: number
  base_version: number
  destination: string
  days: number
  plans: CollabPlanItem[]
  summary?: string
}

export function connectCollab(token: string) {
  const normalizedToken = String(token || '').trim()

  // Token changed means user context changed; recreate socket to avoid auth leakage.
  if (socket && currentAuthToken && normalizedToken !== currentAuthToken) {
    socket.disconnect()
    socket = null
  }

  if (!socket) {
    socket = io(WS_URL, {
      transports: ['websocket', 'polling'],
      auth: { token: normalizedToken },
      reconnection: true,
      reconnectionAttempts: 10,
      timeout: 10000,
      autoConnect: false
    })
  } else {
    socket.auth = { token: normalizedToken }
  }

  currentAuthToken = normalizedToken

  if (!socket.connected) {
    socket.connect()
  }

  return socket
}

export function disconnectCollab() {
  socket?.disconnect()
  socket = null
  currentAuthToken = ''
}

export function isCollabSocketConnected() {
  return !!socket?.connected
}

export function joinCollab(itineraryId: number) {
  socket?.emit('collab:join', { itinerary_id: itineraryId })
}

export function leaveCollab(itineraryId: number) {
  socket?.emit('collab:leave', { itinerary_id: itineraryId })
}

export function sendCollabPatch(payload: CollabPatchPayload) {
  socket?.emit('collab:patch', payload)
}

export function onCollabUpdated(handler: (payload: unknown) => void) {
  socket?.on('collab:updated', handler)
  return () => socket?.off('collab:updated', handler)
}

export function onCollabConflict(handler: (payload: unknown) => void) {
  socket?.on('collab:conflict', handler)
  return () => socket?.off('collab:conflict', handler)
}

export function onCollabError(handler: (payload: unknown) => void) {
  socket?.on('collab:error', handler)
  return () => socket?.off('collab:error', handler)
}

export function onCollabJoined(handler: (payload: unknown) => void) {
  socket?.on('collab:joined', handler)
  return () => socket?.off('collab:joined', handler)
}

export function onCollabAck(handler: (payload: unknown) => void) {
  socket?.on('collab:ack', handler)
  return () => socket?.off('collab:ack', handler)
}

export function onCollabPresence(handler: (payload: unknown) => void) {
  socket?.on('collab:presence', handler)
  return () => socket?.off('collab:presence', handler)
}

export function onCollabConnectError(handler: (error: unknown) => void) {
  socket?.on('connect_error', handler)
  return () => socket?.off('connect_error', handler)
}
