'use client'

import { MapContainer, TileLayer, CircleMarker, Popup } from 'react-leaflet'
import 'leaflet/dist/leaflet.css'
import { Incident, Severity, SEVERITY_COLORS, SEVERITY_ORDER } from '@/lib/types'
import { formatDistanceToNow } from 'date-fns'

interface CameraMarker {
  camera_id: string
  camera_name: string
  lat: number
  lon: number
  worst_severity: Severity
  last_incident: Incident
  incident_count: number
}

interface Props {
  incidents: Incident[]
  onMarkerClick?: (cameraId: string) => void
}

function groupByCameraMarkers(incidents: Incident[]): CameraMarker[] {
  const map = new Map<string, CameraMarker>()

  for (const inc of incidents) {
    if (inc.lat == null || inc.lon == null) continue

    const existing = map.get(inc.camera_id)
    if (!existing) {
      map.set(inc.camera_id, {
        camera_id: inc.camera_id,
        camera_name: inc.camera_name,
        lat: inc.lat,
        lon: inc.lon,
        worst_severity: inc.severity,
        last_incident: inc,
        incident_count: inc.incident_detected ? 1 : 0,
      })
    } else {
      if (SEVERITY_ORDER[inc.severity] > SEVERITY_ORDER[existing.worst_severity]) {
        existing.worst_severity = inc.severity
      }
      if (new Date(inc.created_at) > new Date(existing.last_incident.created_at)) {
        existing.last_incident = inc
      }
      if (inc.incident_detected) existing.incident_count++
    }
  }

  return Array.from(map.values())
}

const SEVERITY_RADIUS: Record<Severity, number> = {
  none: 6,
  low: 8,
  medium: 9,
  high: 11,
  critical: 13,
}

export default function MapView({ incidents, onMarkerClick }: Props) {
  const markers = groupByCameraMarkers(incidents)

  return (
    <MapContainer
      center={[51.505, -0.09]}
      zoom={12}
      style={{ width: '100%', height: '100%' }}
      zoomControl={true}
      attributionControl={true}
    >
      <TileLayer
        url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
      />

      {markers.map(marker => {
        const color = SEVERITY_COLORS[marker.worst_severity]
        const radius = SEVERITY_RADIUS[marker.worst_severity]
        const isCritical = marker.worst_severity === 'critical'
        const isHigh = marker.worst_severity === 'high'

        return (
          <CircleMarker
            key={marker.camera_id}
            center={[marker.lat, marker.lon]}
            radius={radius}
            pathOptions={{
              color: color,
              fillColor: color,
              fillOpacity: isCritical ? 0.9 : isHigh ? 0.8 : 0.7,
              weight: isCritical ? 2 : 1.5,
              opacity: 1,
            }}
            eventHandlers={{
              click: () => onMarkerClick?.(marker.camera_id),
            }}
          >
            <Popup>
              <div style={{ minWidth: 200, fontFamily: 'Inter, sans-serif' }}>
                {/* Camera name */}
                <div style={{ fontSize: 13, fontWeight: 600, color: '#f0f2f8', marginBottom: 8, lineHeight: 1.3 }}>
                  {marker.camera_name}
                </div>

                {/* Severity row */}
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
                  <span style={{ fontSize: 10, color: '#6b7280', textTransform: 'uppercase', letterSpacing: '0.06em' }}>
                    Worst severity (24h)
                  </span>
                  <span style={{
                    background: `${color}20`,
                    color: color,
                    border: `1px solid ${color}40`,
                    padding: '2px 8px',
                    fontSize: 10,
                    fontWeight: 600,
                    textTransform: 'uppercase',
                    letterSpacing: '0.06em',
                    fontFamily: 'monospace',
                  }}>
                    {marker.worst_severity}
                  </span>
                </div>

                {/* Last incident */}
                {marker.last_incident.incident_detected && (
                  <div style={{ borderTop: '1px solid #2a2d3a', paddingTop: 8, marginBottom: 8 }}>
                    <div style={{ fontSize: 10, color: '#6b7280', textTransform: 'uppercase', letterSpacing: '0.06em', marginBottom: 4 }}>
                      Last incident
                    </div>
                    {marker.last_incident.incidents?.[0] && (
                      <div style={{ fontSize: 11, color: '#f0f2f8', marginBottom: 4 }}>
                        {marker.last_incident.incidents[0].type.replace(/_/g, ' ')}
                      </div>
                    )}
                    <div style={{ fontSize: 11, color: '#9ca3af', lineHeight: 1.5 }}>
                      {marker.last_incident.scene_summary}
                    </div>
                    <div style={{ fontSize: 10, color: '#6b7280', marginTop: 6 }}>
                      {formatDistanceToNow(new Date(marker.last_incident.created_at), { addSuffix: true })}
                    </div>
                  </div>
                )}

                {/* Count + link */}
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', borderTop: '1px solid #2a2d3a', paddingTop: 8 }}>
                  <span style={{ fontSize: 11, color: '#6b7280' }}>
                    {marker.incident_count} incident{marker.incident_count !== 1 ? 's' : ''} detected
                  </span>
                  <a
                    href={`/camera/${marker.camera_id}`}
                    style={{ fontSize: 11, color: '#3b82f6', textDecoration: 'none', fontWeight: 500 }}
                  >
                    View camera &rarr;
                  </a>
                </div>
              </div>
            </Popup>
          </CircleMarker>
        )
      })}
    </MapContainer>
  )
}
