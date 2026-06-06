import { NextRequest, NextResponse } from 'next/server'
import { createServerSupabaseClient } from '@/lib/supabase-server'

/**
 * POST /api/upload
 *
 * Handles video upload to storage, then delegates analysis to Python backend.
 * The backend's IncidentRepository handles all database persistence,
 * eliminating duplicate write logic between frontend and backend.
 */
export async function POST(request: NextRequest) {
  try {
    const supabase = await createServerSupabaseClient()

    // Verify user is authenticated
    const { data: { user } } = await supabase.auth.getUser()
    if (!user) {
      return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })
    }

    const formData = await request.formData()
    const video = formData.get('video') as File
    const lat = parseFloat(formData.get('lat') as string)
    const lon = parseFloat(formData.get('lon') as string)
    const locationName = formData.get('locationName') as string

    if (!video || isNaN(lat) || isNaN(lon)) {
      return NextResponse.json({ error: 'Missing required fields' }, { status: 400 })
    }

    // Upload video to Supabase Storage
    const fileExt = video.name.split('.').pop()
    const fileName = `${user.id}/${Date.now()}.${fileExt}`

    const { data: uploadData, error: uploadError } = await supabase.storage
      .from('uploads')
      .upload(fileName, video, {
        contentType: video.type,
        upsert: false,
      })

    if (uploadError) {
      throw new Error(`Upload failed: ${uploadError.message}`)
    }

    // Get public URL
    const { data: { publicUrl } } = supabase.storage.from('uploads').getPublicUrl(fileName)

    // Delegate analysis AND database write to Python backend
    // The IncidentRepository in the backend handles all database operations
    const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'
    const analyzeResponse = await fetch(`${apiUrl}/upload`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        video_url: publicUrl,
        camera_id: `manual_${Date.now()}`,
        camera_name: locationName || 'Manual Upload',
        lat,
        lon,
        source: 'manual',
        created_by: user.id,
      }),
    })

    if (!analyzeResponse.ok) {
      const errorData = await analyzeResponse.json().catch(() => ({}))
      throw new Error(errorData.detail || 'Analysis failed')
    }

    const result = await analyzeResponse.json()

    return NextResponse.json({
      success: true,
      incident: result.saved_incident,
      result: {
        incident_detected: result.incident_detected,
        severity: result.severity,
        incidents: result.incidents,
        scene_summary: result.scene_summary,
        reasoning: result.reasoning,
      },
    })

  } catch (error) {
    console.error('Upload error:', error)
    return NextResponse.json(
      { error: 'Upload failed', details: error instanceof Error ? error.message : 'Unknown error' },
      { status: 500 }
    )
  }
}
