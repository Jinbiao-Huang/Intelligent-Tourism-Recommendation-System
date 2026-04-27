import { ref } from 'vue'
import { defineStore } from 'pinia'

export interface TripHistoryRecord {
  id: string
  destination: string
  days: number
  places: string[]
  createdAt: string
}

const STORAGE_PREFIX = 'trip_history_records'

const getStorageKey = (userId?: number | string | null) => {
  return `${STORAGE_PREFIX}:${userId ?? 'guest'}`
}

const parseRecords = (raw: string | null): TripHistoryRecord[] => {
  if (!raw) {
    return []
  }

  try {
    const parsed = JSON.parse(raw)
    if (!Array.isArray(parsed)) {
      return []
    }

    return parsed
      .map((item) => ({
        id: String(item?.id || ''),
        destination: String(item?.destination || ''),
        days: Number(item?.days || 0),
        places: Array.isArray(item?.places)
          ? item.places.map((place: unknown) => String(place || '').trim()).filter(Boolean)
          : [],
        createdAt: String(item?.createdAt || '')
      }))
      .filter((item) => item.id && item.destination && item.days > 0 && item.createdAt)
  } catch {
    return []
  }
}

export const useTripHistoryStore = defineStore('tripHistory', () => {
  const records = ref<TripHistoryRecord[]>([])

  const loadRecords = (userId?: number | string | null) => {
    const key = getStorageKey(userId)
    records.value = parseRecords(localStorage.getItem(key))
    return records.value
  }

  const addRecord = (
    userId: number | string | null | undefined,
    payload: {
      destination: string
      days: number
      places: string[]
    }
  ) => {
    const key = getStorageKey(userId)
    const existing = parseRecords(localStorage.getItem(key))
    const places = Array.from(
      new Set(payload.places.map((item) => String(item || '').trim()).filter(Boolean))
    )

    const record: TripHistoryRecord = {
      id: `${Date.now()}-${Math.random().toString(16).slice(2)}`,
      destination: String(payload.destination || '').trim(),
      days: Math.max(1, Math.floor(payload.days || 1)),
      places,
      createdAt: new Date().toISOString()
    }

    records.value = [record, ...existing]
    localStorage.setItem(key, JSON.stringify(records.value))
    return record
  }

  const clearRecords = (userId?: number | string | null) => {
    const key = getStorageKey(userId)
    localStorage.removeItem(key)
    records.value = []
  }

  return {
    records,
    loadRecords,
    addRecord,
    clearRecords
  }
})
