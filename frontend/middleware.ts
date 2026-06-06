import { NextResponse } from 'next/server'
import type { NextRequest } from 'next/server'
import { createMiddlewareClientFactory } from './lib/supabase'

export async function middleware(request: NextRequest) {
  const response = NextResponse.next()

  const clientFactory = createMiddlewareClientFactory()
  const supabase = clientFactory.createForRequest(request, response)

  const { data: { user } } = await supabase.auth.getUser()
  const { pathname } = request.nextUrl

  // The map and upload flow are public so people can submit footage remotely.
  // Login remains available only for optional admin sessions.
  if (user && pathname === '/login') {
    const url = request.nextUrl.clone()
    url.pathname = '/'
    return NextResponse.redirect(url)
  }

  return response
}

export const config = {
  matcher: ['/((?!_next/static|_next/image|favicon.ico|api).*)'],
}
