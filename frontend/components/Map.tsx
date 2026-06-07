'use client'

import { MapContainer, TileLayer, CircleMarker, Popup, Circle } from 'react-leaflet'
import 'leaflet/dist/leaflet.css'
import { Incident, Severity, SEVERITY_COLORS, SEVERITY_ORDER } from '@/lib/types'
import { formatDistanceToNow } from 'date-fns'
import { useMemo, useState } from 'react'

// Fetch live TfL camera URL and open it
async function openTflCamera(cameraId: string) {
  try {
    const response = await fetch(`https://api.tfl.gov.uk/Place/${cameraId}`)
    if (!response.ok) throw new Error('Failed to fetch camera')
    const camera = await response.json()
    const videoUrl = camera.additionalProperties?.find((p: any) => p.key === 'videoUrl')?.value
    if (videoUrl) {
      window.open(videoUrl, '_blank', 'noopener,noreferrer')
    } else {
      alert('No live video available for this camera')
    }
  } catch (error) {
    console.error('Failed to fetch camera URL:', error)
    alert('Failed to load camera feed')
  }
}

interface StaticCamera {
  id: string
  name: string
  lat: number
  lon: number
}

interface Props {
  incidents: Incident[]
  showHeatmap?: boolean
  staticCameras?: StaticCamera[]
}

interface HeatPoint {
  lat: number
  lon: number
  intensity: number
  incidentCount: number
}

// Camera location derived from incident rows
interface CameraPin {
  camera_id: string
  camera_name: string
  lat: number
  lon: number
  totalAnalyses: number
  detectedCount: number
  worstSeverity: Severity
  lastAnalysis: Incident
  source: string
  videoUrl: string | null
}

const SEVERITY_RADIUS: Record<Severity, number> = {
  none: 10,
  low: 12,
  medium: 14,
  high: 17,
  critical: 20,
}

function generateHeatPoints(incidents: Incident[]): HeatPoint[] {
  const gridSize = 0.002 // ~200m grid
  const grid = new Map<string, { lat: number; lon: number; count: number }>()

  for (const inc of incidents) {
    if (inc.lat == null || inc.lon == null || !inc.incident_detected) continue
    const gridX = Math.floor(inc.lon / gridSize)
    const gridY = Math.floor(inc.lat / gridSize)
    const key = `${gridX},${gridY}`
    const existing = grid.get(key)
    if (existing) {
      existing.count++
    } else {
      grid.set(key, { lat: inc.lat, lon: inc.lon, count: 1 })
    }
  }

  const gridValues = Array.from(grid.values())
  const maxCount = gridValues.length > 0 ? Math.max(...gridValues.map((g) => g.count)) : 1

  return gridValues.map((cell) => ({
    lat: cell.lat,
    lon: cell.lon,
    intensity: cell.count / maxCount,
    incidentCount: cell.count,
  }))
}

// Build one pin per unique camera_id from all incident rows (not just detected ones)
function buildCameraPins(incidents: Incident[]): CameraPin[] {
  const groups = new Map<string, Incident[]>()

  for (const inc of incidents) {
    if (inc.lat == null || inc.lon == null) continue
    const existing = groups.get(inc.camera_id)
    if (existing) {
      existing.push(inc)
    } else {
      groups.set(inc.camera_id, [inc])
    }
  }

  return Array.from(groups.entries()).map(([camera_id, rows]) => {
    let worst: Severity = 'none'
    for (const r of rows) {
      if (SEVERITY_ORDER[r.severity] > SEVERITY_ORDER[worst]) worst = r.severity
    }
    const detected = rows.filter((r) => r.incident_detected)
    // Get most recent video URL from any row
    const videoUrl = rows.find((r) => r.video_url)?.video_url ?? null
    return {
      camera_id,
      camera_name: rows[0].camera_name,
      lat: rows[0].lat!,
      lon: rows[0].lon!,
      totalAnalyses: rows.length,
      detectedCount: detected.length,
      worstSeverity: worst,
      lastAnalysis: rows[0], // rows are newest-first from DB
      source: rows[0].source ?? 'tfl',
      videoUrl,
    }
  })
}

function getWorstSeverity(incidents: Incident[]): Severity {
  let worst: Severity = 'none'
  for (const inc of incidents) {
    if (SEVERITY_ORDER[inc.severity] > SEVERITY_ORDER[worst]) worst = inc.severity
  }
  return worst
}

export default function MapView({ incidents, showHeatmap = true, staticCameras = [] }: Props) {
  const heatPoints = useMemo(() => generateHeatPoints(incidents), [incidents])
  const cameraPins = useMemo(() => buildCameraPins(incidents), [incidents])

  const center = useMemo(() => {
    const first = incidents.find((i) => i.lat != null && i.lon != null)
    if (first) return [first.lat!, first.lon!] as [number, number]
    if (staticCameras.length > 0) return [staticCameras[0].lat, staticCameras[0].lon] as [number, number]
    return [51.505, -0.09] as [number, number]
  }, [incidents, staticCameras])

  // Deduplicate: skip static cameras that already appear in incident-based pins
  const incidentCameraIds = useMemo(() => new Set(cameraPins.map((p) => p.camera_id)), [cameraPins])

  return (
    <MapContainer
      center={center as [number, number]}
      zoom={13}
      style={{ width: '100%', height: '100%' }}
      zoomControl={true}
      attributionControl={true}
    >
      <TileLayer
        url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
      />

      {/* Heatmap glow for detected incidents */}
      {showHeatmap &&
        heatPoints.map((point, idx) => (
          <Circle
            key={`heat-${idx}`}
            center={[point.lat, point.lon]}
            radius={100 + point.intensity * 200}
            pathOptions={{
              fillColor: '#ef4444',
              fillOpacity: 0.08 + point.intensity * 0.2,
              color: '#ef4444',
              weight: 0,
              opacity: 0,
            }}
          />
        ))}

      {/* Static reference cameras — subtle markers for all known London TfL cameras */}
      {staticCameras
        .filter((cam) => !incidentCameraIds.has(cam.id))
        .map((cam) => (
          <CircleMarker
            key={`static-${cam.id}`}
            center={[cam.lat, cam.lon]}
            radius={6}
            pathOptions={{
              color: '#00d4ff',
              fillColor: '#00d4ff',
              fillOpacity: 0.25,
              weight: 1,
              opacity: 0.5,
            }}
          >
            <Popup>
              <div style={{ minWidth: 200, fontFamily: 'Inter, sans-serif', background: '#1a1d27', color: '#f0f2f8', padding: 4 }}>
                <div style={{ fontSize: 13, fontWeight: 600, marginBottom: 4 }}>{cam.name}</div>
                <div style={{ fontSize: 10, color: '#6b7280', marginBottom: 6, fontFamily: 'monospace' }}>{cam.id}</div>
                <div style={{ fontSize: 10, color: '#4b5563', fontFamily: 'monospace' }}>
                  {cam.lat.toFixed(5)}, {cam.lon.toFixed(5)}
                </div>
                <div style={{ borderTop: '1px solid #2a2d3a', paddingTop: 8, marginTop: 8 }}>
                  <span style={{ fontSize: 10, color: '#6b7280', fontStyle: 'italic' }}>
                    No analysis data yet — use the Piccadilly Circus button to demo
                  </span>
                </div>
              </div>
            </Popup>
          </CircleMarker>
        ))}

      {/* One pin per monitored camera - always visible */}
      {cameraPins.map((cam) => {
        const color = SEVERITY_COLORS[cam.worstSeverity]
        const radius = SEVERITY_RADIUS[cam.worstSeverity]
        const hasIncident = cam.detectedCount > 0
        const isCritical = cam.worstSeverity === 'critical'
        const isHigh = cam.worstSeverity === 'high'

        return (
          <CircleMarker
            key={cam.camera_id}
            center={[cam.lat, cam.lon]}
            radius={hasIncident ? radius + 2 : radius}
            pathOptions={{
              color: hasIncident ? color : '#00d4ff',
              fillColor: hasIncident ? color : '#00d4ff',
              fillOpacity: hasIncident ? (isCritical ? 0.95 : isHigh ? 0.85 : 0.75) : 0.6,
              weight: hasIncident ? (isCritical ? 3 : 2) : 2,
              opacity: 1,
            }}
          >
            <Popup>
              <div style={{ minWidth: 240, fontFamily: 'Inter, sans-serif', background: '#1a1d27', color: '#f0f2f8', padding: 4 }}>
                {/* Camera name */}
                <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 4 }}>
                  {cam.camera_name}
                </div>
                <div style={{ fontSize: 10, color: '#6b7280', marginBottom: 10, fontFamily: 'monospace' }}>
                  {cam.camera_id}
                </div>

                {/* Status badges */}
                <div style={{ display: 'flex', gap: 8, marginBottom: 10 }}>
                  <span style={{
                    padding: '3px 8px',
                    background: hasIncident ? `${color}20` : '#1e3a5f',
                    border: `1px solid ${hasIncident ? color + '60' : '#3b82f6'}`,
                    borderRadius: 4, fontSize: 10, fontWeight: 600,
                    color: hasIncident ? color : '#60a5fa',
                    textTransform: 'uppercase',
                  }}>
                    {cam.worstSeverity}
                  </span>
                  <span style={{ fontSize: 11, color: '#6b7280', display: 'flex', alignItems: 'center' }}>
                    {cam.detectedCount}/{cam.totalAnalyses} detected
                  </span>
                </div>

                {/* Coordinates */}
                <div style={{ fontSize: 10, color: '#4b5563', marginBottom: 10, fontFamily: 'monospace' }}>
                  {cam.lat.toFixed(5)}, {cam.lon.toFixed(5)}
                </div>

                {/* Last analysis summary */}
                {cam.lastAnalysis.scene_summary && (
                  <div style={{ borderTop: '1px solid #2a2d3a', paddingTop: 10, marginBottom: 10 }}>
                    <div style={{ fontSize: 10, color: '#6b7280', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 4 }}>
                      Last analysis
                    </div>
                    <div style={{ fontSize: 11, color: '#9ca3af', lineHeight: 1.5 }}>
                      {cam.lastAnalysis.scene_summary}
                    </div>
                    <div style={{ fontSize: 10, color: '#4b5563', marginTop: 4 }}>
                      {formatDistanceToNow(new Date(cam.lastAnalysis.created_at), { addSuffix: true })}
                    </div>
                  </div>
                )}

                {/* Source */}
                <div style={{ borderTop: '1px solid #2a2d3a', paddingTop: 8, marginBottom: 10 }}>
                  <span style={{ fontSize: 10, color: '#6b7280', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                    {cam.source === 'manual' ? 'Manual upload' : 'TfL JamCam'}
                  </span>
                </div>

                {/* View Camera Link - for TfL cameras, fetch live URL dynamically */}
                <button
                  onClick={() => {
                    if (cam.source === 'tfl') {
                      openTflCamera(cam.camera_id)
                    } else if (cam.videoUrl) {
                      window.open(cam.videoUrl, '_blank', 'noopener,noreferrer')
                    }
                  }}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    gap: 6,
                    padding: '8px 12px',
                    background: '#00d4ff20',
                    border: '1px solid #00d4ff60',
                    borderRadius: 6,
                    color: '#00d4ff',
                    fontSize: 12,
                    fontWeight: 600,
                    textDecoration: 'none',
                    cursor: 'pointer',
                    width: '100%',
                  }}
                  onMouseEnter={(e) => {
                    e.currentTarget.style.background = '#00d4ff30'
                  }}
                  onMouseLeave={(e) => {
                    e.currentTarget.style.background = '#00d4ff20'
                  }}
                >
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <polygon points="5 3 19 12 5 21 5 3"></polygon>
                  </svg>
                  View Live Camera
                </button>
              </div>
            </Popup>
          </CircleMarker>
        )
      })}
    </MapContainer>
  )
}
