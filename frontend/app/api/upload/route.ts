import { NextRequest, NextResponse } from 'next/server'
import { createServerSupabaseClient } from '@/lib/supabase-server'
import { createServiceClient } from '@/lib/supabase'

export const maxDuration = 60
export const dynamic = 'force-dynamic'

/**
 * POST /api/upload
 *
 * 1. Receives storage path + metadata (video already uploaded directly to Supabase)
 * 2. Creates a signed URL valid for 1 hour
 * 3. Sends signed URL to Python backend for download + analysis
 * 4. Returns analysis result
 */
export async function POST(request: NextRequest) {
  try {
    const authClient = await createServerSupabaseClient()
    const supabase = createServiceClient()
    const { data: { user } } = await authClient.auth.getUser()

    const body = await request.json()
    const path = body.path as string | undefined
    const lat = parseFloat(body.lat as string)
    const lon = parseFloat(body.lon as string)
    const locationName = (body.locationName as string) || 'Manual Upload'

    if (!path) {
      return NextResponse.json({ error: 'No storage path provided' }, { status: 400 })
    }
    if (isNaN(lat) || isNaN(lon)) {
      return NextResponse.json({ error: 'lat and lon are required' }, { status: 400 })
    }

    // Signed URL - 1 hour, enough for the Python backend to download
    const { data: signedData, error: signedError } = await supabase.storage
      .from('uploads')
      .createSignedUrl(path, 3600)

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
