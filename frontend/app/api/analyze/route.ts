import { NextRequest, NextResponse } from 'next/server'
import { createServerSupabaseClient } from '@/lib/supabase-server'

/**
 * POST /api/analyze
 *
 * Delegates video analysis to the Python backend API.
 * The backend handles both analysis AND database persistence via IncidentRepository,
 * eliminating duplicate write logic between frontend and backend.
 */
export async function POST(request: NextRequest) {
  try {
    const supabase = await createServerSupabaseClient()
    const { videoUrl, cameraId, cameraName, lat, lon, source = 'tfl', secondOpinion = false } = await request.json()

    // Verify user is authenticated
    const { data: { user } } = await supabase.auth.getUser()
    if (!user) {
      return NextResponse.json({ error: 'Unauthorized' }, { status: 401 })
    }

    // Delegate to Python backend for analysis AND database write
    // The backend's IncidentRepository handles all database operations
    const apiUrl = process.env.BACKEND_API_URL || process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'
    const analyzeResponse = await fetch(`${apiUrl}/analyze`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        video_url: videoUrl,
        camera_id: cameraId,
        camera_name: cameraName,
        lat,
        lon,
        source,
        created_by: user.id,
        second_opinion: secondOpinion,
      }),
    })

    if (!analyzeResponse.ok) {
      const errorData = await analyzeResponse.json().catch(() => ({}))
      throw new Error(errorData.detail || 'Analysis failed')
    }

    const result = await analyzeResponse.json()

    // Return the combined result (analysis + saved incident data if any)
    return NextResponse.json({
      success: true,
      incident_detected: result.incident_detected,
      incident: result.saved_incident,
      result: {
        severity: result.severity,
        incidents: result.incidents,
        scene_summary: result.scene_summary,
        reasoning: result.reasoning,
      },
      message: result.incident_detected
        ? 'Incident detected and saved'
        : 'No incidents detected in this clip',
    })

  } catch (error) {
    console.error('Analyze error:', error)
    return NextResponse.json(
      { error: 'Analysis failed', details: error instanceof Error ? error.message : 'Unknown error' },
      { status: 500 }
    )
  }
}
