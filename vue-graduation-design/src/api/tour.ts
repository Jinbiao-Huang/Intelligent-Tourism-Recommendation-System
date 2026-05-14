import axios from 'axios'

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:5000/api'

const api = axios.create({
	baseURL: API_URL,
	timeout: 15000
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

export interface PlanItem {
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

export interface DayPlan {
	day: number
	activities: PlanItem[]
}

export interface ItineraryResponse {
	destination: string
	days: number
	plans: DayPlan[]
	recommend_focus?: 'rating' | 'distance'
	budget?: number
	estimated_cost?: number
	visit_weekday?: number | null
	visit_time?: string | null
}

export interface ItineraryRecordPayload {
	destination: string
	days: number
	has_edited_destination: boolean
	edited_from?: string
	edited_to?: string
}

export interface TourPlanPayload {
	destination: string
	start_date: string
	end_date: string
	budget?: number
	preferences?: string[]
	plan_data?: DayPlan[]
}

export interface CollabMember {
	user_id: number
	username: string
	role: 'owner' | 'editor' | 'viewer' | string
	joined_at: string
}

export interface CollabChangeLog {
	id: number
	version: number
	editor_user_id?: number | null
	editor_username?: string | null
	summary?: string
	change_payload?: Record<string, unknown>
	created_at: string
}

export interface CollabSessionResponse {
	id: number
	role: string
	title: string
	destination: string
	days: number
	share_token: string
	version: number
	updated_at: string
	has_updates: boolean
	plan_data?: DayPlan[]
	last_editor?: {
		id: number
		username: string
	} | null
	members: CollabMember[]
	changes: CollabChangeLog[]
}

export interface CollabConflictResponse {
	message: string
	code: 'VERSION_CONFLICT'
	server_version: number
	server_plan_data: DayPlan[]
	server_destination: string
	server_days: number
	last_editor?: {
		id: number
		username: string
	} | null
	changes_since_base?: CollabChangeLog[]
}

export const tourAPI = {
	generateItinerary: (payload: {
		destination: string
		days: number
		budget: number
		preferences: string[]
		recommend_focus: 'rating' | 'distance'
		pace?: 'leisure' | 'normal' | 'intense'
		visit_date?: string
		visit_weekday?: number | string
		visit_time?: string
	}) => {
		return api.post<ItineraryResponse>('/itinerary/generate', payload)
	},

	saveItineraryRecord: (payload: ItineraryRecordPayload) => {
		return api.post('/itinerary/records', payload)
	},

	createTourPlan: (payload: TourPlanPayload) => {
		return api.post('/tours', payload)
	},

	createCollabSession: (payload: {
		destination: string
		days: number
		plans: DayPlan[]
		title?: string
	}) => {
		return api.post<CollabSessionResponse>('/collab/itineraries', payload)
	},

	joinCollabSession: (shareToken: string) => {
		return api.post<CollabSessionResponse>('/collab/itineraries/join', {
			share_token: shareToken
		})
	},

	getCollabSession: (itineraryId: number, sinceVersion?: number) => {
		return api.get<CollabSessionResponse>(`/collab/itineraries/${itineraryId}`, {
			params: sinceVersion !== undefined ? { since_version: sinceVersion } : undefined
		})
	},

	updateCollabSession: (itineraryId: number, payload: {
		base_version: number
		destination: string
		days: number
		plans: DayPlan[]
		summary?: string
	}) => {
		return api.put<CollabSessionResponse>(`/collab/itineraries/${itineraryId}`, payload)
	},

	getCollabChanges: (itineraryId: number, sinceVersion = 0, limit = 50) => {
		return api.get<{ itinerary_id: number; version: number; changes: CollabChangeLog[] }>(
			`/collab/itineraries/${itineraryId}/changes`,
			{
				params: {
					since_version: sinceVersion,
					limit
				}
			}
		)
	}
}
