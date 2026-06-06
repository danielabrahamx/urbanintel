import { NextRequest, NextResponse } from 'next/server'
import { createServerSupabaseClient } from '@/lib/supabase-server'
import { createServiceClient } from '@/lib/supabase'

function getAdminEmails(): string[] {
  return (process.env.ADMIN_EMAILS || process.env.ADMIN_EMAIL || '')
    .split(',')
    .map((email) => email.trim().toLowerCase())
    .filter(Boolean)
}

export async function DELETE(
  _request: NextRequest,
  { params }: { params: { id: string } }
) {
  try {
    const authClient = await createServerSupabaseClient()
    const { data: { user } } = await authClient.auth.getUser()
    const adminEmails = getAdminEmails()

    if (!user?.email || !adminEmails.includes(user.email.toLowerCase())) {
      return NextResponse.json({ error: 'Admin access required' }, { status: 403 })
    }

    const supabase = createServiceClient()
    const { data: incident, error: fetchError } = await supabase
      .from('incidents')
      .select('id, source, video_url')
      .eq('id', params.id)
      .maybeSingle()

    if (fetchError || !incident) {
      return NextResponse.json({ error: 'Incident not found' }, { status: 404 })
    }

    if (incident.source !== 'manual') {
      return NextResponse.json({ error: 'Only manual uploads can be deleted' }, { status: 400 })
    }

    const { error: deleteError } = await supabase
      .from('incidents')
      .delete()
      .eq('id', params.id)
      .eq('source', 'manual')

    if (deleteError) {
      throw new Error(deleteError.message)
    }

    return NextResponse.json({ success: true })
  } catch (error) {
    console.error('[delete incident]', error)
    return NextResponse.json(
      { error: error instanceof Error ? error.message : 'Delete failed' },
      { status: 500 }
    )
  }
}
