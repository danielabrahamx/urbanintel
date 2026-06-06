import { NextRequest, NextResponse } from 'next/server'
import { createServerSupabaseClient } from '@/lib/supabase-server'
import { createServiceClient } from '@/lib/supabase'

export const maxDuration = 60
export const dynamic = 'force-dynamic'

/**
 * POST /api/upload-url
 *
 * Generates a signed upload URL for Supabase Storage so the client can upload
 * large video files directly, bypassing the Next.js API route body-size limit.
 */
export async function POST(request: NextRequest) {
  try {
    const authClient = await createServerSupabaseClient()
    const supabase = createServiceClient()
    const { data: { user } } = await authClient.auth.getUser()

    const body = await request.json()
    const filename = body.filename || 'upload.mp4'
    const contentType = body.contentType || 'video/mp4'

    const ext = filename.split('.').pop() ?? 'mp4'
    const uploaderId = user?.id ?? 'public'
    const storagePath = `${uploaderId}/${Date.now()}.${ext}`

    const { data, error } = await supabase.storage
      .from('uploads')
      .createSignedUploadUrl(storagePath, { upsert: false })

    if (error || !data?.signedUrl || !data?.token) {
      throw new Error(`Failed to create signed upload URL: ${error?.message}`)
    }

    return NextResponse.json({
      signedUrl: data.signedUrl,
      token: data.token,
      path: storagePath,
    })
  } catch (error) {
    console.error('[upload-url]', error)
    return NextResponse.json(
      { error: error instanceof Error ? error.message : 'Failed to create upload URL' },
      { status: 500 }
    )
  }
}
