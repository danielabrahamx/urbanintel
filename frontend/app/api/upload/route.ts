import { NextRequest, NextResponse } from 'next/server'
import { createServerSupabaseClient } from '@/lib/supabase-server'
import { createServiceClient } from '@/lib/supabase'

// Raise body size limit for this route to handle 50MB video uploads
export const maxDuration = 60 // seconds
export const dynamic = 'force-dynamic'

/**
 * POST /api/upload
 *
 * 1. Receives multipart form (video file + lat/lon/locationName)
 * 2. Uploads file to Supabase Storage (private bucket)
 * 3. Creates a signed URL valid for 1 hour
 * 4. Sends signed URL to Python backend for download + analysis
 * 5. Returns analysis result
 */
export async function POST(request: NextRequest) {
  try {
    const authClient = await createServerSupabaseClient()
    const supabase = createServiceClient()
    const { data: { user } } = await authClient.auth.getUser()

    const formData = await request.formData()
    const video = formData.get('video') as File | null
    const lat = parseFloat(formData.get('lat') as string)
    const lon = parseFloat(formData.get('lon') as string)
    const locationName = (formData.get('locationName') as string) || 'Manual Upload'

    if (!video) {
      return NextResponse.json({ error: 'No video file provided' }, { status: 400 })
    }
    if (isNaN(lat) || isNaN(lon)) {
      return NextResponse.json({ error: 'lat and lon are required' }, { status: 400 })
    }

    const MAX_MB = 50
    if (video.size > MAX_MB * 1024 * 1024) {
      return NextResponse.json({ error: `File too large (max ${MAX_MB}MB)` }, { status: 413 })
    }

    // Upload to private Supabase Storage bucket
    const ext = video.name.split('.').pop() ?? 'mp4'
    const uploaderId = user?.id ?? 'public'
    const storagePath = `${uploaderId}/${Date.now()}.${ext}`

    const { error: uploadError } = await supabase.storage
      .from('uploads')
      .upload(storagePath, video, { contentType: video.type, upsert: false })

    if (uploadError) {
      throw new Error(`Storage upload failed: ${uploadError.message}`)
    }

    // Signed URL - 1 hour, enough for the Python backend to download
    const { data: signedData, error: signedError } = await supabase.storage
      .from('uploads')
      .createSignedUrl(storagePath, 3600)

    if (signedError || !signedData?.signedUrl) {
      throw new Error(`Failed to create signed URL: ${signedError?.message}`)
    }

    // Send to Python backend for analysis + DB write
    const apiUrl = process.env.BACKEND_API_URL || process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'
    const analyzeResponse = await fetch(`${apiUrl}/upload`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        video_url: signedData.signedUrl,
        camera_id: `manual_${Date.now()}`,
        camera_name: locationName,
        lat,
        lon,
        source: 'manual',
        created_by: user?.id,
      }),
    })

    if (!analyzeResponse.ok) {
      const err = await analyzeResponse.json().catch(() => ({}))
      throw new Error(err.detail || `Analysis failed (${analyzeResponse.status})`)
    }

    const result = await analyzeResponse.json()

    return NextResponse.json({
      success: true,
      incident_detected: result.incident_detected,
      severity: result.severity,
      scene_summary: result.scene_summary,
      incidents: result.incidents,
      reasoning: result.reasoning,
      saved_incident: result.saved_incident,
    })

  } catch (error) {
    console.error('[upload]', error)
    return NextResponse.json(
      { success: false, error: error instanceof Error ? error.message : 'Upload failed' },
      { status: 500 }
    )
  }
}
