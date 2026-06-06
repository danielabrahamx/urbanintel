'use client'

export const dynamic = 'force-dynamic'

import { useEffect, useState, useCallback, useMemo } from 'react'
import dynamicImport from 'next/dynamic'
import Link from 'next/link'
import { createClient } from '@/lib/supabase'
import { Incident, Severity, SEVERITY_COLORS } from '@/lib/types'
import SeverityBadge from '@/components/SeverityBadge'
import { formatDistanceToNow } from 'date-fns'
import { Play, Upload, MapPin, AlertTriangle, CheckCircle, Loader2, X, ChevronRight } from 'lucide-react'

const MapView = dynamicImport(() => import('@/components/Map'), {
  ssr: false,
  loading: () => (
    <div style={{ width: '100%', height: '100%', background: '#0d1117', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
      <div style={{ color: '#6b7280', fontSize: 13 }}>Loading map...</div>
    </div>
  ),
})

// Default TfL camera for demo
const DEMO_CAMERA = {
  id: 'JamCams_00001.07450',
  name: 'Piccadilly Circus',
  lat: 51.5096,
  lon: -0.1348,
}

export default function DashboardPage() {
  const supabase = createClient()
  const [incidents, setIncidents] = useState<Incident[]>([])
  const [loading, setLoading] = useState(true)
  const [analyzing, setAnalyzing] = useState(false)
  const [lastAnalysis, setLastAnalysis] = useState<{ detected: boolean; summary?: string } | null>(null)

  // Upload form state
  const [showUpload, setShowUpload] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [uploadError, setUploadError] = useState<string | null>(null)
  const [uploadSuccess, setUploadSuccess] = useState(false)

  // Load incidents
  const loadIncidents = useCallback(async () => {
    setLoading(true)
    const { data } = await supabase
      .from('incidents')
      .select('*')
      .order('created_at', { ascending: false })
      .limit(200)
    if (data) setIncidents(data as Incident[])
    setLoading(false)
  }, [supabase])

  useEffect(() => {
    loadIncidents()
  }, [loadIncidents])

  // Realtime subscription
  useEffect(() => {
    const channel = supabase
      .channel('incidents-realtime')
      .on('postgres_changes', { event: 'INSERT', schema: 'public', table: 'incidents' }, (payload) => {
        const newInc = payload.new as Incident
        setIncidents((prev) => [newInc, ...prev])
      })
      .subscribe()
    return () => { supabase.removeChannel(channel) }
  }, [supabase])

  // Analyze TfL clip
  const handleAnalyze = async () => {
    setAnalyzing(true)
    setLastAnalysis(null)

    try {
      // First fetch the video URL from TfL
      const tflResponse = await fetch(`https://api.tfl.gov.uk/Place/Type/JamCam?app_key=${process.env.NEXT_PUBLIC_TFL_APP_KEY || ''}`)
      const cameras = await tflResponse.json()
      const camera = cameras.find((c: any) => c.id === DEMO_CAMERA.id)

      if (!camera) {
        throw new Error('Demo camera not found')
      }

      const videoUrl = camera.additionalProperties.find((p: any) => p.key === 'videoUrl')?.value

      if (!videoUrl) {
        throw new Error('No video URL available')
      }

      // Call analysis API
      const response = await fetch('/api/analyze', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          videoUrl,
          cameraId: DEMO_CAMERA.id,
          cameraName: DEMO_CAMERA.name,
          lat: DEMO_CAMERA.lat,
          lon: DEMO_CAMERA.lon,
        }),
      })

      const result = await response.json()

      if (result.success) {
        setLastAnalysis({
          detected: result.incident_detected,
          summary: result.result?.scene_summary,
        })
        // Reload incidents after every analysis so the feed always updates
        await loadIncidents()
      } else {
        throw new Error(result.error || 'Analysis failed')
      }
    } catch (error) {
      console.error('Analyze error:', error)
      setLastAnalysis({ detected: false, summary: 'Analysis failed: ' + (error instanceof Error ? error.message : 'Unknown error') })
    } finally {
      setAnalyzing(false)
    }
  }

  // Handle manual upload
  const handleUpload = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault()
    setUploading(true)
    setUploadError(null)
    setUploadSuccess(false)

    const formData = new FormData(e.currentTarget)

    try {
      const response = await fetch('/api/upload', {
        method: 'POST',
        body: formData,
      })

      if (!response.ok) {
        const err = await response.json().catch(() => ({}))
        throw new Error(err.error || err.details || `Upload failed (${response.status})`)
      }

      const result = await response.json()

      if (result.success) {
        setUploadSuccess(true)
        await loadIncidents()
        setTimeout(() => {
          setShowUpload(false)
          setUploadSuccess(false)
        }, 2000)
      } else {
        throw new Error(result.error || 'Upload failed')
      }
    } catch (error) {
      setUploadError(error instanceof Error ? error.message : 'Upload failed')
    } finally {
      setUploading(false)
    }
  }

  // Stats
  const detectedCount = incidents.filter((i) => i.incident_detected).length
  const criticalCount = incidents.filter((i) => i.severity === 'critical').length
  const recentIncidents = incidents.slice(0, 5)

  // Map data - only show incidents with locations
  const mapIncidents = useMemo(() => {
    return incidents.filter((i) => i.lat != null && i.lon != null)
  }, [incidents])

  return (
    <div style={{ display: 'flex', height: '100%', overflow: 'hidden', background: '#0d1117' }}>
      {/* Left Panel - Controls */}
      <div style={{ width: 360, background: '#1a1d27', borderRight: '1px solid #2a2d3a', display: 'flex', flexDirection: 'column', flexShrink: 0, overflow: 'hidden' }}>
        {/* Header */}
        <div style={{ padding: '20px', borderBottom: '1px solid #2a2d3a' }}>
          <h1 style={{ color: '#f0f2f8', fontSize: 20, fontWeight: 700, margin: 0 }}>Urban Intelligence</h1>
          <p style={{ color: '#6b7280', fontSize: 13, marginTop: 4 }}>AI-powered traffic incident detection</p>
        </div>

        {/* Stats */}
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, padding: '16px 20px', borderBottom: '1px solid #2a2d3a' }}>
          <div style={{ padding: '12px', background: '#0f1117', borderRadius: 8, border: '1px solid #2a2d3a' }}>
            <div style={{ fontSize: 24, fontWeight: 700, color: detectedCount > 0 ? '#f97316' : '#6b7280' }}>{detectedCount}</div>
            <div style={{ fontSize: 11, color: '#6b7280', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Incidents</div>
          </div>
          <div style={{ padding: '12px', background: '#0f1117', borderRadius: 8, border: '1px solid #2a2d3a' }}>
            <div style={{ fontSize: 24, fontWeight: 700, color: criticalCount > 0 ? '#ef4444' : '#6b7280' }}>{criticalCount}</div>
            <div style={{ fontSize: 11, color: '#6b7280', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Critical</div>
          </div>
        </div>

        {/* Main Actions */}
        <div style={{ padding: '20px', borderBottom: '1px solid #2a2d3a' }}>
          <h3 style={{ color: '#f0f2f8', fontSize: 13, fontWeight: 600, margin: '0 0 12px 0', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Analyze Traffic</h3>

          {/* Analyze TfL Button */}
          <button
            onClick={handleAnalyze}
            disabled={analyzing}
            style={{
              width: '100%',
              padding: '14px 16px',
              background: analyzing ? '#1e40af' : '#3b82f6',
              border: 'none',
              borderRadius: 8,
              color: '#fff',
              fontSize: 14,
              fontWeight: 600,
              cursor: analyzing ? 'not-allowed' : 'pointer',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              gap: 10,
              opacity: analyzing ? 0.8 : 1,
              transition: 'all 0.15s',
            }}
          >
            {analyzing ? <Loader2 size={18} style={{ animation: 'spin 1s linear infinite' }} /> : <Play size={18} />}
            {analyzing ? 'Analyzing...' : 'Analyze TfL Clip'}
          </button>

          <p style={{ color: '#6b7280', fontSize: 11, marginTop: 8, lineHeight: 1.5 }}>
            Fetches and analyzes a 10-second clip from {DEMO_CAMERA.name}
          </p>

          {/* Analysis Result */}
          {lastAnalysis && (
            <div
              style={{
                marginTop: 12,
                padding: '12px',
                background: lastAnalysis.detected ? 'rgba(239, 68, 68, 0.1)' : 'rgba(34, 197, 94, 0.1)',
                border: `1px solid ${lastAnalysis.detected ? '#ef4444' : '#22c55e'}`,
                borderRadius: 8,
                display: 'flex',
                alignItems: 'flex-start',
                gap: 10,
              }}
            >
              {lastAnalysis.detected ? <AlertTriangle size={18} color='#ef4444' /> : <CheckCircle size={18} color='#22c55e' />}
              <div>
                <div style={{ fontSize: 13, fontWeight: 600, color: lastAnalysis.detected ? '#ef4444' : '#22c55e' }}>
                  {lastAnalysis.detected ? 'Incident Detected' : 'No Issues Found'}
                </div>
                {lastAnalysis.summary && (
                  <div style={{ fontSize: 11, color: '#9ca3af', marginTop: 4, lineHeight: 1.4 }}>{lastAnalysis.summary}</div>
                )}
              </div>
            </div>
          )}
        </div>

        {/* Upload Section */}
        <div style={{ padding: '20px', borderBottom: '1px solid #2a2d3a' }}>
          <h3 style={{ color: '#f0f2f8', fontSize: 13, fontWeight: 600, margin: '0 0 12px 0', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Manual Upload</h3>

          <button
            onClick={() => setShowUpload(true)}
            style={{
              width: '100%',
              padding: '12px 16px',
              background: '#0f1117',
              border: '1px solid #2a2d3a',
              borderRadius: 8,
              color: '#f0f2f8',
              fontSize: 13,
              fontWeight: 500,
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              gap: 10,
              transition: 'all 0.15s',
            }}
          >
            <Upload size={16} />
            Upload Video + Location
          </button>

          <p style={{ color: '#6b7280', fontSize: 11, marginTop: 8, lineHeight: 1.5 }}>
            Upload your own traffic footage and specify the location
          </p>
        </div>

        {/* Recent Activity */}
        <div style={{ flex: 1, overflow: 'auto' }}>
          <div style={{ padding: '16px 20px', borderBottom: '1px solid #2a2d3a' }}>
            <h3 style={{ color: '#f0f2f8', fontSize: 13, fontWeight: 600, margin: 0, textTransform: 'uppercase', letterSpacing: '0.05em' }}>Recent Activity</h3>
          </div>

          {loading ? (
            <div style={{ padding: 40, textAlign: 'center' }}>
              <Loader2 size={24} color='#6b7280' style={{ animation: 'spin 1s linear infinite' }} />
            </div>
          ) : recentIncidents.length === 0 ? (
            <div style={{ padding: 40, textAlign: 'center', color: '#6b7280', fontSize: 13 }}>No incidents yet</div>
          ) : (
            recentIncidents.map((incident) => (
              <div key={incident.id} style={{ padding: '12px 20px', borderBottom: '1px solid #2a2d3a' }}>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 6 }}>
                  <span style={{ fontSize: 12, fontWeight: 500, color: '#f0f2f8' }}>{incident.camera_name}</span>
                  <SeverityBadge severity={incident.severity} size='sm' />
                </div>
                <p style={{ fontSize: 11, color: '#9ca3af', margin: '0 0 6px 0', lineHeight: 1.4 }}>
                  {incident.scene_summary || 'No description'}
                </p>
                <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 10, color: '#6b7280' }}>
                  <MapPin size={10} />
                  {incident.lat?.toFixed(4)}, {incident.lon?.toFixed(4)}
                  <span style={{ marginLeft: 'auto' }}>{formatDistanceToNow(new Date(incident.created_at), { addSuffix: true })}</span>
                </div>
              </div>
            ))
          )}
        </div>

        {/* Footer */}
        <div style={{ padding: '12px 20px', borderTop: '1px solid #2a2d3a' }}>
          <Link href='/incidents' style={{ color: '#3b82f6', fontSize: 12, textDecoration: 'none', display: 'flex', alignItems: 'center', gap: 4 }}>
            View all incidents <ChevronRight size={12} />
          </Link>
        </div>
      </div>

      {/* Map */}
      <div style={{ flex: 1, position: 'relative' }}>
        <MapView incidents={mapIncidents} showHeatmap={true} />

        {/* Map Legend */}
        <div
          style={{
            position: 'absolute',
            bottom: 20,
            right: 20,
            background: 'rgba(26,29,39,0.95)',
            border: '1px solid #2a2d3a',
            padding: '12px 16px',
            borderRadius: 8,
            backdropFilter: 'blur(4px)',
          }}
        >
          <div style={{ fontSize: 11, fontWeight: 600, color: '#f0f2f8', marginBottom: 8, textTransform: 'uppercase', letterSpacing: '0.05em' }}>Incident Severity</div>
          {[
            { label: 'None', color: '#6b7280' },
            { label: 'Low', color: '#eab308' },
            { label: 'Medium', color: '#f97316' },
            { label: 'High', color: '#ef4444' },
            { label: 'Critical', color: '#7f1d1d' },
          ].map((item) => (
            <div key={item.label} style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
              <span style={{ width: 8, height: 8, borderRadius: '50%', background: item.color }} />
              <span style={{ fontSize: 11, color: '#9ca3af' }}>{item.label}</span>
            </div>
          ))}
        </div>
      </div>

      {/* Upload Modal */}
      {showUpload && (
        <div
          style={{
            position: 'fixed',
            inset: 0,
            background: 'rgba(0,0,0,0.8)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 1000,
          }}
          onClick={() => setShowUpload(false)}
        >
          <div
            style={{
              width: 480,
              background: '#1a1d27',
              border: '1px solid #2a2d3a',
              borderRadius: 12,
              padding: 24,
            }}
            onClick={(e) => e.stopPropagation()}
          >
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 20 }}>
              <h2 style={{ color: '#f0f2f8', fontSize: 18, fontWeight: 600, margin: 0 }}>Upload Video</h2>
              <button onClick={() => setShowUpload(false)} style={{ background: 'none', border: 'none', color: '#6b7280', cursor: 'pointer' }}>
                <X size={20} />
              </button>
            </div>

            <form onSubmit={handleUpload}>
              <div style={{ marginBottom: 16 }}>
                <label style={{ display: 'block', color: '#9ca3af', fontSize: 12, marginBottom: 6, textTransform: 'uppercase', letterSpacing: '0.05em' }}>Video File</label>
                <input
                  type='file'
                  name='video'
                  accept='video/*'
                  required
                  style={{
                    width: '100%',
                    padding: 12,
                    background: '#0f1117',
                    border: '1px solid #2a2d3a',
                    borderRadius: 6,
                    color: '#f0f2f8',
                    fontSize: 13,
                  }}
                />
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginBottom: 16 }}>
                <div>
                  <label style={{ display: 'block', color: '#9ca3af', fontSize: 12, marginBottom: 6, textTransform: 'uppercase', letterSpacing: '0.05em' }}>Latitude</label>
                  <input
                    type='number'
                    name='lat'
                    step='any'
                    required
                    placeholder='51.5130'
                    style={{
                      width: '100%',
                      padding: 12,
                      background: '#0f1117',
                      border: '1px solid #2a2d3a',
                      borderRadius: 6,
                      color: '#f0f2f8',
                      fontSize: 13,
                    }}
                  />
                </div>
                <div>
                  <label style={{ display: 'block', color: '#9ca3af', fontSize: 12, marginBottom: 6, textTransform: 'uppercase', letterSpacing: '0.05em' }}>Longitude</label>
                  <input
                    type='number'
                    name='lon'
                    step='any'
                    required
                    placeholder='-0.1300'
                    style={{
                      width: '100%',
                      padding: 12,
                      background: '#0f1117',
                      border: '1px solid #2a2d3a',
                      borderRadius: 6,
                      color: '#f0f2f8',
                      fontSize: 13,
                    }}
                  />
                </div>
              </div>

              <div style={{ marginBottom: 20 }}>
                <label style={{ display: 'block', color: '#9ca3af', fontSize: 12, marginBottom: 6, textTransform: 'uppercase', letterSpacing: '0.05em' }}>Location Name (optional)</label>
                <input
                  type='text'
                  name='locationName'
                  placeholder='e.g., Oxford Circus'
                  style={{
                    width: '100%',
                    padding: 12,
                    background: '#0f1117',
                    border: '1px solid #2a2d3a',
                    borderRadius: 6,
                    color: '#f0f2f8',
                    fontSize: 13,
                  }}
                />
              </div>

              {uploadError && (
                <div style={{ padding: 12, background: 'rgba(239, 68, 68, 0.1)', border: '1px solid #ef4444', borderRadius: 6, marginBottom: 16 }}>
                  <p style={{ color: '#ef4444', fontSize: 13, margin: 0 }}>{uploadError}</p>
                </div>
              )}

              {uploadSuccess && (
                <div style={{ padding: 12, background: 'rgba(34, 197, 94, 0.1)', border: '1px solid #22c55e', borderRadius: 6, marginBottom: 16 }}>
                  <p style={{ color: '#22c55e', fontSize: 13, margin: 0 }}>Upload successful!</p>
                </div>
              )}

              <button
                type='submit'
                disabled={uploading}
                style={{
                  width: '100%',
                  padding: '14px',
                  background: uploading ? '#1e40af' : '#3b82f6',
                  border: 'none',
                  borderRadius: 8,
                  color: '#fff',
                  fontSize: 14,
                  fontWeight: 600,
                  cursor: uploading ? 'not-allowed' : 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  gap: 10,
                  opacity: uploading ? 0.8 : 1,
                }}
              >
                {uploading ? <Loader2 size={18} style={{ animation: 'spin 1s linear infinite' }} /> : <Upload size={18} />}
                {uploading ? 'Uploading...' : 'Upload & Analyze'}
              </button>
            </form>
          </div>
        </div>
      )}

      <style jsx global>{`
        @keyframes spin {
          from { transform: rotate(0deg); }
          to { transform: rotate(360deg); }
        }
      `}</style>
    </div>
  )
}
