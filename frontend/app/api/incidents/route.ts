import { NextRequest, NextResponse } from 'next/server'
import { createServiceClient } from '@/lib/supabase'

export const dynamic = 'force-dynamic'

/**
 * GET /api/incidents
 *
 * Public read endpoint. Anonymous visitors can load the map without an account.
 * Reads run server-side with the service role, so we don't depend on anon RLS
 * policies being open on the incidents table.
 *
 * Query params:
 *   - detectedOnly=true  -> only incidents where incident_detected is true
 *   - limit=<n>          -> max rows (default 200, capped at 5000)
 *   - since=<iso>        -> created_at >= since
 */
export async function GET(request: NextRequest) {
  try {
    const supabase = createServiceClient()
    const { searchParams } = new URL(request.url)

    const detectedOnly = searchParams.get('detectedOnly') === 'true'
    const since = searchParams.get('since')
    const limit = Math.min(Number(searchParams.get('limit')) || 200, 5000)

    let query = supabase
      .from('incidents')
      .select('*')
      .order('created_at', { ascending: false })
      .limit(limit)

    if (detectedOnly) query = query.eq('incident_detected', true)
    if (since) query = query.gte('created_at', since)

    const { data, error } = await query
    if (error) throw new Error(error.message)

    return NextResponse.json({ incidents: data ?? [] })
  } catch (error) {
    console.error('[incidents]', error)
    return NextResponse.json(
      { error: error instanceof Error ? error.message : 'Failed to load incidents' },
      { status: 500 }
    )
  }
}
