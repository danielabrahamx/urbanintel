import { NextResponse } from 'next/server'
import type { NextRequest } from 'next/server'
import { createMiddlewareClientFactory } from './lib/supabase'

export async function middleware(request: NextRequest) {
  const response = NextResponse.next()

  const clientFactory = createMiddlewareClientFactory()
  const supabase = clientFactory.createForRequest(request, response)

  const { data: { user } } = await supabase.auth.getUser()
  const { pathname } = request.nextUrl

  // Redirect unauthenticated users to login
  if (!user && pathname !== '/login') {
    const url = request.nextUrl.clone()
    url.pathname = '/login'
    return NextResponse.redirect(url)
  }

  // Redirect authenticated users away from login page
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
