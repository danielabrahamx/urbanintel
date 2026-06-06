'use client'

export const dynamic = 'force-dynamic'

import { useEffect, useState, useCallback, useMemo } from 'react'
import dynamicImport from 'next/dynamic'
import Link from 'next/link'
import { createClient } from '@/lib/supabase'
import { Incident, Severity, SEVERITY_COLORS } from '@/lib/types'
import SeverityBadge from '@/components/SeverityBadge'
import { formatDistanceToNow } from 'date-fns'
import { Play, Upload, MapPin, AlertTriangle, CheckCircle, Loader2, X, ChevronRight, Trash2 } from 'lucide-react'

const MapView = dynamicImport(() => import('@/components/Map'), {
  ssr: false,
  loading: () => (
    <div style={{ width: '100%', height: '100%', background: '#0d1117', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
      <div style={{ color: '#6b7280', fontSize: 13 }}>Loading map...</div>
    </div>
  ),
})

const LocationPicker = dynamicImport(() => import('@/components/LocationPicker'), {
  ssr: false,
  loading: () => (
    <div style={{ width: '100%', height: 220, background: '#0f1117', display: 'flex', alignItems: 'center', justifyContent: 'center', border: '1px solid #2a2d3a', borderRadius: 6 }}>
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

function getAdminEmails(): string[] {
  return (process.env.NEXT_PUBLIC_ADMIN_EMAILS || process.env.NEXT_PUBLIC_ADMIN_EMAIL || '')
    .split(',')
    .map((email) => email.trim().toLowerCase())
    .filter(Boolean)
}

function getIncidentLabel(incident: unknown): string {
  if (typeof incident === 'string') return incident.replace(/_/g, ' ')
  if (incident && typeof incident === 'object' && 'type' in incident) {
    const type = (incident as { type?: unknown }).type
    return typeof type === 'string' ? type.replace(/_/g, ' ') : 'Unknown incident'
  }
  return 'Unknown incident'
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
  const [uploadCoords, setUploadCoords] = useState<{ lat: number; lon: number } | null>(null)

  // Analysis review state
  const [pendingAnalysis, setPendingAnalysis] = useState<{
    incident_detected: boolean
    severity: string
    scene_summary: string
    incidents: unknown[]
    reasoning: string
    saved_incident: any
    videoPath: string
    locationName: string
    lat: number
    lon: number
  } | null>(null)
  const [showReview, setShowReview] = useState(false)
  const [secondOpinionLoading, setSecondOpinionLoading] = useState(false)
  const [isAdmin, setIsAdmin] = useState(false)
  const [deletingId, setDeletingId] = useState<string | null>(null)

  // Load incidents
  const loadIncidents = useCallback(async () => {
    setLoading(true)
    try {
      const res = await fetch('/api/incidents?limit=200', { cache: 'no-store' })
      const json = await res.json()
      if (res.ok && Array.isArray(json.incidents)) {
        setIncidents(json.incidents as Incident[])
      }
    } catch (err) {
      console.error('Failed to load incidents:', err)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    loadIncidents()
  }, [loadIncidents])

  useEffect(() => {
    supabase.auth.getUser().then(({ data }) => {
      const email = data.user?.email?.toLowerCase()
      setIsAdmin(Boolean(email && getAdminEmails().includes(email)))
    })
  }, [supabase])

  // Realtime subscription (works for authed admins) plus a polling fallback
  // so anonymous visitors still see new incidents under RLS.
  useEffect(() => {
    const channel = supabase
      .channel('incidents-realtime')
      .on('postgres_changes', { event: 'INSERT', schema: 'public', table: 'incidents' }, (payload) => {
        const newInc = payload.new as Incident
        setIncidents((prev) => (prev.some((i) => i.id === newInc.id) ? prev : [newInc, ...prev]))
      })
      .subscribe()

    const poll = setInterval(() => { loadIncidents() }, 15000)

    return () => { supabase.removeChannel(channel); clearInterval(poll) }
  }, [supabase, loadIncidents])

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

  // Handle manual upload - now shows review first
  const handleUpload = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault()
    setUploading(true)
    setUploadError(null)
    setUploadSuccess(false)

    if (!uploadCoords) {
      setUploadError('Please select a location on the map')
      setUploading(false)
      return
    }

    const formData = new FormData(e.currentTarget)
    const locationName = (formData.get('locationName') as string) || 'Manual Upload'
    const videoFile = formData.get('video') as File | null

    if (!videoFile) {
      setUploadError('Please select a video file')
      setUploading(false)
      return
    }

    const MAX_MB = 50
    if (videoFile.size > MAX_MB * 1024 * 1024) {
      setUploadError(`File too large (max ${MAX_MB}MB)`)
      setUploading(false)
      return
    }

    try {
      // 1. Get signed upload URL from server
      const urlResponse = await fetch('/api/upload-url', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          filename: videoFile.name,
          contentType: videoFile.type,
        }),
      })

      if (!urlResponse.ok) {
        const err = await urlResponse.json().catch(() => ({}))
        throw new Error(err.error || `Failed to get upload URL (${urlResponse.status})`)
      }

      const { signedUrl, token, path } = await urlResponse.json()

      // 2. Upload directly to Supabase Storage
      const { error: uploadError } = await supabase.storage
        .from('uploads')
        .uploadToSignedUrl(path, token, videoFile, { contentType: videoFile.type })

      if (uploadError) {
        throw new Error(`Direct upload failed: ${uploadError.message}`)
      }

      // 3. Trigger analysis via backend
      const response = await fetch('/api/upload', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          path,
          lat: uploadCoords.lat,
          lon: uploadCoords.lon,
          locationName,
        }),
      })

      if (!response.ok) {
        const err = await response.json().catch(() => ({}))
        throw new Error(err.error || err.details || `Upload failed (${response.status})`)
      }

      const result = await response.json()

      if (result.success) {
        // Store analysis for review instead of auto-saving
        setPendingAnalysis({
          incident_detected: result.incident_detected,
          severity: result.severity,
          scene_summary: result.scene_summary,
          incidents: result.incidents || [],
          reasoning: result.reasoning || '',
          saved_incident: result.saved_incident,
          videoPath: result.saved_incident?.video_url || '',
          locationName,
          lat: uploadCoords.lat,
          lon: uploadCoords.lon,
        })
        setShowReview(true)
        setShowUpload(false)
      } else {
        throw new Error(result.error || 'Upload failed')
      }
    } catch (error) {
      setUploadError(error instanceof Error ? error.message : 'Upload failed')
    } finally {
      setUploading(false)
    }
  }

  const deleteManualIncident = async (incidentId: string) => {
    setDeletingId(incidentId)
    try {
      const response = await fetch(`/api/incidents/${incidentId}`, { method: 'DELETE' })
      const result = await response.json().catch(() => ({}))
      if (!response.ok) throw new Error(result.error || 'Delete failed')
      setIncidents((prev) => prev.filter((incident) => incident.id !== incidentId))
      if (pendingAnalysis?.saved_incident?.id === incidentId) {
        setShowReview(false)
        setPendingAnalysis(null)
      }
    } catch (error) {
      setUploadError(error instanceof Error ? error.message : 'Delete failed')
    } finally {
      setDeletingId(null)
    }
  }

  // Confirm and keep the already-saved incident on the map.
  const handleConfirmSave = async () => {
    if (!pendingAnalysis) return
    setUploadSuccess(true)
    await loadIncidents()
    setTimeout(() => {
      setShowReview(false)
      setPendingAnalysis(null)
      setUploadSuccess(false)
      setUploadCoords(null)
    }, 1500)
  }

  // Discard the analysis
  const handleDiscard = async () => {
    const savedId = pendingAnalysis?.saved_incident?.id
    if (savedId) {
      await deleteManualIncident(savedId)
    }
    setShowReview(false)
    setPendingAnalysis(null)
    setUploadCoords(null)
  }

  // Request second opinion with different model
  const handleSecondOpinion = async () => {
    if (!pendingAnalysis?.videoPath) return
    setSecondOpinionLoading(true)
    try {
      const response = await fetch('/api/analyze', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          videoUrl: pendingAnalysis.videoPath,
          cameraId: `manual_${Date.now()}`,
          cameraName: pendingAnalysis.locationName,
          lat: pendingAnalysis.lat,
          lon: pendingAnalysis.lon,
          secondOpinion: true,
        }),
      })
      const result = await response.json()
      if (result.success) {
        // Update with second opinion
        setPendingAnalysis({
          ...pendingAnalysis,
          incident_detected: result.incident_detected,
          severity: result.severity,
          scene_summary: result.result?.scene_summary || result.scene_summary,
          incidents: result.result?.incidents || result.incidents || [],
          reasoning: `SECOND OPINION:\n${result.result?.reasoning || result.reasoning || 'No reasoning provided'}\n\n---\n\nORIGINAL:\n${pendingAnalysis.reasoning}`,
        })
      }
    } catch (error) {
      console.error('Second opinion failed:', error)
      setUploadError('Second opinion request failed')
    } finally {
      setSecondOpinionLoading(false)
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
          <h3 style={{ color: '#f0f2f8', fontSize: 13, fontWeight: 600, margin: '0 0 12px 0', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Live Camera Analysis</h3>

          {/* Camera card */}
          <div style={{ background: '#0f1117', border: '1px solid #2a2d3a', borderRadius: 8, padding: '12px 14px', marginBottom: 12 }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 6 }}>
              <span style={{ fontSize: 12, fontWeight: 600, color: '#f0f2f8' }}>{DEMO_CAMERA.name}</span>
              <span style={{ fontSize: 10, padding: '2px 6px', background: '#10b98120', border: '1px solid #10b98140', borderRadius: 4, color: '#10b981' }}>LIVE</span>
            </div>
            <div style={{ fontSize: 10, color: '#6b7280', fontFamily: 'monospace', marginBottom: 6 }}>{DEMO_CAMERA.id}</div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 10, color: '#4b5563' }}>
              <MapPin size={10} />
              {DEMO_CAMERA.lat.toFixed(4)}, {DEMO_CAMERA.lon.toFixed(4)}
            </div>
          </div>

          {/* Analyze button */}
          <button
            onClick={handleAnalyze}
            disabled={analyzing}
            style={{
              width: '100%',
              padding: '12px 16px',
              background: analyzing ? '#1e40af' : '#3b82f6',
              border: 'none',
              borderRadius: 8,
              color: '#fff',
              fontSize: 13,
              fontWeight: 600,
              cursor: analyzing ? 'not-allowed' : 'pointer',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              gap: 8,
              opacity: analyzing ? 0.8 : 1,
              transition: 'all 0.15s',
            }}
          >
            {analyzing ? <Loader2 size={16} style={{ animation: 'spin 1s linear infinite' }} /> : <Play size={16} />}
            {analyzing ? 'Fetching live status...' : 'Get Live Status'}
          </button>

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
                  <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                    <SeverityBadge severity={incident.severity} size='sm' />
                    {isAdmin && incident.source === 'manual' && (
                      <button
                        onClick={() => deleteManualIncident(incident.id)}
                        disabled={deletingId === incident.id}
                        title="Delete manual upload"
                        style={{ background: 'transparent', border: '1px solid #7f1d1d', color: '#f87171', borderRadius: 4, padding: 3, cursor: 'pointer' }}
                      >
                        {deletingId === incident.id ? <Loader2 size={12} style={{ animation: 'spin 1s linear infinite' }} /> : <Trash2 size={12} />}
                      </button>
                    )}
                  </div>
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
      <div style={{ flex: 1, position: 'relative', zIndex: 0 }}>
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
          onClick={() => { setShowUpload(false); setUploadCoords(null) }}
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
              <button onClick={() => { setShowUpload(false); setUploadCoords(null) }} style={{ background: 'none', border: 'none', color: '#6b7280', cursor: 'pointer' }}>
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

              <div style={{ marginBottom: 16 }}>
                <label style={{ display: 'block', color: '#9ca3af', fontSize: 12, marginBottom: 6, textTransform: 'uppercase', letterSpacing: '0.05em' }}>Location</label>
                <LocationPicker onChange={setUploadCoords} value={uploadCoords} />
                <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginTop: 8, minHeight: 20 }}>
                  <MapPin size={14} color={uploadCoords ? '#3b82f6' : '#6b7280'} />
                  <span style={{ fontSize: 12, fontFamily: 'monospace', color: uploadCoords ? '#9ca3af' : '#6b7280' }}>
                    {uploadCoords ? `${uploadCoords.lat.toFixed(4)}, ${uploadCoords.lon.toFixed(4)}` : 'No location selected'}
                  </span>
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

      {/* Analysis Review Modal */}
      {showReview && pendingAnalysis && (
        <div style={{
          position: 'fixed',
          top: 0,
          left: 0,
          right: 0,
          bottom: 0,
          background: 'rgba(0, 0, 0, 0.8)',
          zIndex: 1000,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          padding: 20,
        }}>
          <div style={{
            background: '#1a1d27',
            border: '1px solid #2a2d3a',
            borderRadius: 12,
            width: '100%',
            maxWidth: 600,
            maxHeight: '90vh',
            overflow: 'auto',
          }}>
            {/* Header */}
            <div style={{
              padding: '20px 24px',
              borderBottom: '1px solid #2a2d3a',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
            }}>
              <div>
                <h3 style={{ margin: 0, fontSize: 18, fontWeight: 600, color: '#f0f2f8' }}>
                  Analysis Review
                </h3>
                <p style={{ margin: '4px 0 0', fontSize: 13, color: '#9ca3af' }}>
                  Review the model's assessment before saving
                </p>
              </div>
              <button
                onClick={handleDiscard}
                style={{
                  background: 'transparent',
                  border: 'none',
                  color: '#9ca3af',
                  cursor: 'pointer',
                  padding: 8,
                  borderRadius: 6,
                }}
              >
                <X size={20} />
              </button>
            </div>

            {/* Content */}
            <div style={{ padding: 24 }}>
              {/* Severity Badge */}
              <div style={{ marginBottom: 24 }}>
                <label style={{ display: 'block', color: '#9ca3af', fontSize: 12, marginBottom: 8, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                  Detected Severity
                </label>
                <div style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: 8,
                  padding: '8px 16px',
                  borderRadius: 6,
                  fontSize: 14,
                  fontWeight: 600,
                  background: pendingAnalysis.severity === 'critical' ? 'rgba(239, 68, 68, 0.2)' :
                             pendingAnalysis.severity === 'high' ? 'rgba(249, 115, 22, 0.2)' :
                             pendingAnalysis.severity === 'medium' ? 'rgba(234, 179, 8, 0.2)' :
                             'rgba(34, 197, 94, 0.2)',
                  color: pendingAnalysis.severity === 'critical' ? '#ef4444' :
                         pendingAnalysis.severity === 'high' ? '#f97316' :
                         pendingAnalysis.severity === 'medium' ? '#eab308' :
                         '#22c55e',
                  border: `1px solid ${pendingAnalysis.severity === 'critical' ? '#ef4444' :
                         pendingAnalysis.severity === 'high' ? '#f97316' :
                         pendingAnalysis.severity === 'medium' ? '#eab308' :
                         '#22c55e'}`,
                }}>
                  <AlertTriangle size={16} />
                  {pendingAnalysis.severity?.toUpperCase() || 'NONE'}
                  {pendingAnalysis.incident_detected && ' - INCIDENT DETECTED'}
                </div>
              </div>

              {/* Scene Summary */}
              <div style={{ marginBottom: 24 }}>
                <label style={{ display: 'block', color: '#9ca3af', fontSize: 12, marginBottom: 8, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                  Scene Summary
                </label>
                <div style={{
                  padding: 16,
                  background: '#0f1117',
                  border: '1px solid #2a2d3a',
                  borderRadius: 8,
                  color: '#f0f2f8',
                  fontSize: 14,
                  lineHeight: 1.6,
                }}>
                  {pendingAnalysis.scene_summary || 'No summary provided'}
                </div>
              </div>

              {/* Detected Incidents */}
              {pendingAnalysis.incidents && pendingAnalysis.incidents.length > 0 && (
                <div style={{ marginBottom: 24 }}>
                  <label style={{ display: 'block', color: '#9ca3af', fontSize: 12, marginBottom: 8, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                    Incident Types Detected
                  </label>
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
                    {pendingAnalysis.incidents.map((incident, idx) => (
                      <span
                        key={idx}
                        style={{
                          padding: '6px 12px',
                          background: 'rgba(59, 130, 246, 0.2)',
                          border: '1px solid rgba(59, 130, 246, 0.4)',
                          borderRadius: 4,
                          fontSize: 12,
                          color: '#60a5fa',
                          fontWeight: 500,
                        }}
                      >
                        {getIncidentLabel(incident)}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {/* Reasoning */}
              <div style={{ marginBottom: 24 }}>
                <label style={{ display: 'block', color: '#9ca3af', fontSize: 12, marginBottom: 8, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                  Model Reasoning
                </label>
                <div style={{
                  padding: 16,
                  background: '#0f1117',
                  border: '1px solid #2a2d3a',
                  borderRadius: 8,
                  color: '#9ca3af',
                  fontSize: 13,
                  lineHeight: 1.6,
                  maxHeight: 200,
                  overflow: 'auto',
                  whiteSpace: 'pre-wrap',
                }}>
                  {pendingAnalysis.reasoning || 'No detailed reasoning provided'}
                </div>
              </div>

              {/* Location Info */}
              <div style={{
                padding: 16,
                background: 'rgba(59, 130, 246, 0.1)',
                border: '1px solid rgba(59, 130, 246, 0.2)',
                borderRadius: 8,
                marginBottom: 24,
              }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
                  <MapPin size={14} color="#3b82f6" />
                  <span style={{ fontSize: 13, color: '#3b82f6', fontWeight: 500 }}>
                    {pendingAnalysis.locationName}
                  </span>
                </div>
                <span style={{ fontSize: 12, color: '#6b7280', fontFamily: 'monospace' }}>
                  {pendingAnalysis.lat.toFixed(4)}, {pendingAnalysis.lon.toFixed(4)}
                </span>
              </div>

              {/* Success Message */}
              {uploadSuccess && (
                <div style={{
                  padding: 12,
                  background: 'rgba(34, 197, 94, 0.1)',
                  border: '1px solid #22c55e',
                  borderRadius: 6,
                  marginBottom: 20,
                  display: 'flex',
                  alignItems: 'center',
                  gap: 8,
                }}>
                  <CheckCircle size={16} color="#22c55e" />
                  <span style={{ color: '#22c55e', fontSize: 14, fontWeight: 500 }}>
                    Saved to map successfully!
                  </span>
                </div>
              )}

              {/* Actions */}
              <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
                <button
                  onClick={handleConfirmSave}
                  disabled={uploadSuccess}
                  style={{
                    flex: 1,
                    minWidth: 140,
                    padding: '12px 20px',
                    background: uploadSuccess ? '#166534' : '#22c55e',
                    border: 'none',
                    borderRadius: 8,
                    color: '#fff',
                    fontSize: 14,
                    fontWeight: 600,
                    cursor: uploadSuccess ? 'default' : 'pointer',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    gap: 8,
                  }}
                >
                  <CheckCircle size={18} />
                  {uploadSuccess ? 'Saved!' : 'Save to Map'}
                </button>

                <button
                  onClick={handleSecondOpinion}
                  disabled={secondOpinionLoading || uploadSuccess}
                  style={{
                    flex: 1,
                    minWidth: 140,
                    padding: '12px 20px',
                    background: 'transparent',
                    border: '1px solid #3b82f6',
                    borderRadius: 8,
                    color: '#3b82f6',
                    fontSize: 14,
                    fontWeight: 600,
                    cursor: (secondOpinionLoading || uploadSuccess) ? 'not-allowed' : 'pointer',
                    opacity: (secondOpinionLoading || uploadSuccess) ? 0.6 : 1,
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    gap: 8,
                  }}
                >
                  {secondOpinionLoading ? (
                    <><Loader2 size={18} style={{ animation: 'spin 1s linear infinite' }} /> Analyzing...</>
                  ) : (
                    <><AlertTriangle size={18} /> Second Opinion</>
                  )}
                </button>

                <button
                  onClick={handleDiscard}
                  disabled={uploadSuccess}
                  style={{
                    flex: 1,
                    minWidth: 140,
                    padding: '12px 20px',
                    background: 'transparent',
                    border: '1px solid #6b7280',
                    borderRadius: 8,
                    color: '#9ca3af',
                    fontSize: 14,
                    fontWeight: 600,
                    cursor: uploadSuccess ? 'not-allowed' : 'pointer',
                  }}
                >
                  Discard
                </button>
              </div>

              <p style={{ marginTop: 16, fontSize: 12, color: '#6b7280', textAlign: 'center' }}>
                Second opinion re-analyzes with an alternative model for comparison
              </p>
            </div>
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
