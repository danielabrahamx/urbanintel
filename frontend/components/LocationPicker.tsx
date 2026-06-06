'use client'

import { useState } from 'react'
import { MapContainer, TileLayer, Marker, useMapEvents } from 'react-leaflet'
import 'leaflet/dist/leaflet.css'
import L from 'leaflet'

// Fix for default marker icon in Leaflet with Next.js
const markerIcon = L.divIcon({
  className: 'custom-marker',
  html: `<svg xmlns="http://www.w3.org/2000/svg" width="32" height="32" viewBox="0 0 24 24" fill="#3b82f6" stroke="#fff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"></path><circle cx="12" cy="10" r="3"></circle></svg>`,
  iconSize: [32, 32],
  iconAnchor: [16, 32],
  popupAnchor: [0, -32],
})

interface LocationPickerProps {
  onChange: (coords: { lat: number; lon: number }) => void
  value?: { lat: number; lon: number } | null
}

// Inner component to handle map click events
function MapClickHandler({ onPositionChange }: { onPositionChange: (pos: { lat: number; lon: number }) => void }) {
  useMapEvents({
    click(e) {
      onPositionChange({ lat: e.latlng.lat, lon: e.latlng.lng })
    },
  })
  return null
}

export default function LocationPicker({ onChange, value }: LocationPickerProps) {
  const [position, setPosition] = useState<{ lat: number; lon: number } | null>(value || null)

  const handlePositionChange = (newPos: { lat: number; lon: number }) => {
    setPosition(newPos)
    onChange(newPos)
  }

  const handleDragEnd = (e: L.DragEndEvent) => {
    const marker = e.target as L.Marker
    const latLng = marker.getLatLng()
    const newPos = { lat: latLng.lat, lon: latLng.lng }
    setPosition(newPos)
    onChange(newPos)
  }

  return (
    <div style={{ position: 'relative', width: '100%', height: 220 }}>
      <MapContainer
        center={[51.505, -0.09]}
        zoom={11}
        style={{ width: '100%', height: '100%', borderRadius: 6 }}
        zoomControl={false}
        attributionControl={false}
      >
        <TileLayer
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
        />
        <MapClickHandler onPositionChange={handlePositionChange} />
        {position && (
          <Marker
            position={[position.lat, position.lon]}
            icon={markerIcon}
            draggable
            eventHandlers={{
              dragend: handleDragEnd,
            }}
          />
        )}
      </MapContainer>

      {/* Placeholder overlay when no pin is set */}
      {!position && (
        <div
          style={{
            position: 'absolute',
            top: '50%',
            left: '50%',
            transform: 'translate(-50%, -50%)',
            pointerEvents: 'none',
            textAlign: 'center',
          }}
        >
          <span
            style={{
              fontSize: 14,
              color: '#6b7280',
              background: 'rgba(15, 17, 23, 0.8)',
              padding: '8px 16px',
              borderRadius: 6,
              border: '1px solid #2a2d3a',
            }}
          >
            Click to set location
          </span>
        </div>
      )}

      {/* Border overlay for consistent styling */}
      <div
        style={{
          position: 'absolute',
          inset: 0,
          border: '1px solid #2a2d3a',
          borderRadius: 6,
          pointerEvents: 'none',
        }}
      />
    </div>
  )
}
