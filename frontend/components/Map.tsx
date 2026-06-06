'use client'

import { MapContainer, TileLayer, CircleMarker, Popup, Circle } from 'react-leaflet'
import 'leaflet/dist/leaflet.css'
import { Incident, Severity, SEVERITY_COLORS, SEVERITY_ORDER } from '@/lib/types'
import { formatDistanceToNow } from 'date-fns'
import { useMemo } from 'react'

interface Props {
  incidents: Incident[]
  showHeatmap?: boolean
}

interface HeatPoint {
  lat: number
  lon: number
  intensity: number
  incidentCount: number
}

const SEVERITY_RADIUS: Record<Severity, number> = {
  none: 5,
  low: 7,
  medium: 9,
  high: 12,
  critical: 15,
}

function generateHeatPoints(incidents: Incident[]): HeatPoint[] {
  // Group incidents by approximate location (grid-based)
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
      grid.set(key, {
        lat: inc.lat,
        lon: inc.lon,
        count: 1,
      })
    }
  }

  const gridValues = Array.from(grid.values())
  const maxCount = gridValues.length > 0 ? Math.max(...gridValues.map((g) => g.count)) : 1

  return Array.from(grid.values()).map((cell) => ({
    lat: cell.lat,
    lon: cell.lon,
    intensity: cell.count / maxCount,
    incidentCount: cell.count,
  }))
}

function groupByLocation(incidents: Incident[]): Map<string, Incident[]> {
  const groups = new Map<string, Incident[]>()

  for (const inc of incidents) {
    if (inc.lat == null || inc.lon == null) continue

    // Group by camera_id or approximate location
    const key = inc.camera_id
    const existing = groups.get(key)
    if (existing) {
      existing.push(inc)
    } else {
      groups.set(key, [inc])
    }
  }

  return groups
}

function getWorstSeverity(incidents: Incident[]): Severity {
  let worst: Severity = 'none'
  for (const inc of incidents) {
    if (SEVERITY_ORDER[inc.severity] > SEVERITY_ORDER[worst]) {
      worst = inc.severity
    }
  }
  return worst
}

export default function MapView({ incidents, showHeatmap = true }: Props) {
  const heatPoints = useMemo(() => generateHeatPoints(incidents), [incidents])
  const locationGroups = useMemo(() => groupByLocation(incidents), [incidents])

  // Get center from first incident or default to London
  const center = useMemo(() => {
    const first = incidents.find((i) => i.lat != null && i.lon != null)
    return first ? [first.lat, first.lon] : [51.505, -0.09]
  }, [incidents])

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

      {/* Heatmap circles */}
      {showHeatmap &&
        heatPoints.map((point, idx) => (
          <Circle
            key={`heat-${idx}`}
            center={[point.lat, point.lon]}
            radius={100 + point.intensity * 200}
            pathOptions={{
              fillColor: '#ef4444',
              fillOpacity: 0.1 + point.intensity * 0.25,
              color: '#ef4444',
              weight: 1,
              opacity: 0.4,
            }}
          />
        ))}

      {/* Incident markers */}
      {Array.from(locationGroups.entries()).map(([key, locationIncidents]) => {
        const first = locationIncidents[0]
        const worstSeverity = getWorstSeverity(locationIncidents)
        const detectedCount = locationIncidents.filter((i) => i.incident_detected).length
        const lastIncident = locationIncidents[0] // Already sorted by time
        const color = SEVERITY_COLORS[worstSeverity]
        const radius = SEVERITY_RADIUS[worstSeverity]
        const isCritical = worstSeverity === 'critical'
        const isHigh = worstSeverity === 'high'

        return (
          <CircleMarker
            key={key}
            center={[first.lat!, first.lon!]}
            radius={detectedCount > 1 ? radius + 3 : radius}
            pathOptions={{
              color: color,
              fillColor: color,
              fillOpacity: isCritical ? 0.9 : isHigh ? 0.8 : 0.7,
              weight: isCritical ? 3 : 2,
              opacity: 1,
            }}
          >
            <Popup>
              <div style={{ minWidth: 240, fontFamily: 'Inter, sans-serif' }}>
                {/* Location name */}
                <div style={{ fontSize: 14, fontWeight: 600, color: '#f0f2f8', marginBottom: 8 }}>
                  {first.camera_name}
                </div>

                {/* Stats */}
                <div style={{ display: 'flex', gap: 12, marginBottom: 12 }}>
                  <div
                    style={{
                      padding: '4px 10px',
                      background: `${color}20`,
                      border: `1px solid ${color}40`,
                      borderRadius: 4,
                      fontSize: 11,
                      fontWeight: 600,
                      color: color,
                      textTransform: 'uppercase',
                    }}
                  >
                    {worstSeverity}
                  </div>
                  <div style={{ fontSize: 11, color: '#6b7280', display: 'flex', alignItems: 'center' }}>
                    {detectedCount} incident{detectedCount !== 1 ? 's' : ''} detected
                  </div>
                </div>

                {/* Coordinates */}
                <div style={{ fontSize: 10, color: '#4b5563', marginBottom: 12 }}>
                  {first.lat?.toFixed(5)}, {first.lon?.toFixed(5)}
                </div>

                {/* Last incident */}
                {lastIncident?.incident_detected && (
                  <div style={{ borderTop: '1px solid #2a2d3a', paddingTop: 12, marginBottom: 12 }}>
                    <div
                      style={{
                        fontSize: 10,
                        color: '#6b7280',
                        textTransform: 'uppercase',
                        letterSpacing: '0.05em',
                        marginBottom: 6,
                      }}
                    >
                      Latest incident
                    </div>
                    <div style={{ fontSize: 12, color: '#f0f2f8', marginBottom: 4, lineHeight: 1.4 }}>
                      {lastIncident.incidents?.[0]?.type?.replace(/_/g, ' ') || 'Unknown type'}
                    </div>
                    <div style={{ fontSize: 11, color: '#9ca3af', lineHeight: 1.5, marginBottom: 6 }}>
                      {lastIncident.scene_summary || 'No description available'}
                    </div>
                    <div style={{ fontSize: 10, color: '#4b5563' }}>
                      {formatDistanceToNow(new Date(lastIncident.created_at), { addSuffix: true })}
                    </div>
                  </div>
                )}

                {/* Source badge */}
                <div style={{ borderTop: '1px solid #2a2d3a', paddingTop: 12 }}>
                  <span
                    style={{
                      fontSize: 10,
                      color: '#6b7280',
                      textTransform: 'uppercase',
                      letterSpacing: '0.05em',
                    }}
                  >
                    Source: {first.source === 'manual' ? 'Manual Upload' : 'TfL Camera'}
                  </span>
                </div>
              </div>
            </Popup>
          </CircleMarker>
        )
      })}
    </MapContainer>
  )
}
