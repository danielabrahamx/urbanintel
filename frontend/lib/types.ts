export type Severity = 'none' | 'low' | 'medium' | 'high' | 'critical'

export interface IncidentDetail {
  type: string
  severity: Severity
  description: string
  confidence: 'low' | 'medium' | 'high'
  timestamp_in_clip: string
}

export interface Incident {
  id: string
  created_at: string
  camera_id: string
  camera_name: string
  lat: number | null
  lon: number | null
  incident_detected: boolean
  severity: Severity
  incidents: IncidentDetail[] | null
  scene_summary: string | null
  reasoning: string | null
  raw_response: Record<string, unknown> | null
  source?: 'tfl' | 'manual'
  video_url?: string | null
}

export const SEVERITY_ORDER: Record<Severity, number> = {
  none: 0,
  low: 1,
  medium: 2,
  high: 3,
  critical: 4,
}

export const SEVERITY_COLORS: Record<Severity, string> = {
  none: '#6b7280',
  low: '#eab308',
  medium: '#f97316',
  high: '#ef4444',
  critical: '#7f1d1d',
}

export const SEVERITY_BG: Record<Severity, string> = {
  none: 'bg-gray-500/20 text-gray-400 border-gray-500/30',
  low: 'bg-yellow-500/20 text-yellow-400 border-yellow-500/30',
  medium: 'bg-orange-500/20 text-orange-400 border-orange-500/30',
  high: 'bg-red-500/20 text-red-400 border-red-500/30',
  critical: 'bg-red-900/40 text-red-300 border-red-800/50',
}

// Camera status types for real-time command center
export type CameraStatus = 'idle' | 'measuring' | 'error' | 'offline'

export interface CameraStatusRecord {
  id: string
  created_at: string
  updated_at: string
  camera_id: string
  camera_name: string
  lat: number | null
  lon: number | null
  status: CameraStatus
  last_polled_at: string | null
  last_incident_at: string | null
  incident_count_24h: number
  error_message: string | null
  video_url: string | null
  poll_interval_seconds: number
}

export const CAMERA_STATUS_COLORS: Record<CameraStatus, string> = {
  idle: '#22c55e',
  measuring: '#3b82f6',
  error: '#ef4444',
  offline: '#6b7280',
}

export const CAMERA_STATUS_LABELS: Record<CameraStatus, string> = {
  idle: 'Idle',
  measuring: 'Measuring',
  error: 'Error',
  offline: 'Offline',
}
