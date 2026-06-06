/**
 * Single factory for all Supabase client instances.
 *
 * This module provides a unified way to create Supabase clients for different
 * contexts: browser (React components), server (Server Components/API routes),
 * and middleware (Next.js middleware).
 *
 * Usage:
 *   - Browser: const supabase = createClient()
 *   - Server:  const supabase = await createServerClient()
 *   - Middleware: const factory = createMiddlewareClientFactory()
 *                 const supabase = factory.createForRequest(request, response)
 */
import { createBrowserClient as createBrowserClientSSR, createServerClient as createServerClientSSR } from '@supabase/ssr'
import { createClient as createRawSupabaseClient } from '@supabase/supabase-js'
import type { NextRequest, NextResponse } from 'next/server'
import type { SupabaseClient } from '@supabase/supabase-js'

interface SupabaseConfig {
  url: string
  anonKey: string
}

// Harmless placeholders so client construction never throws during the Next.js
// build/prerender pass when env vars are absent. Real values are inlined at build
// when present (NEXT_PUBLIC_*) or read at runtime on the server. If these
// placeholders ever reach a real request, the call fails loudly at that point
// instead of crashing the entire build.
const PLACEHOLDER_URL = 'https://placeholder.supabase.co'
const PLACEHOLDER_ANON = 'placeholder-anon-key'

function getConfig(): SupabaseConfig {
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL
  const anonKey = process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY

  if (!url || !anonKey) {
    // Do NOT throw here: this runs during prerender of client pages at build
    // time. Throwing fails the whole Vercel build. Warn and fall back instead.
    if (typeof window !== 'undefined') {
      console.warn(
        'Missing Supabase env vars (NEXT_PUBLIC_SUPABASE_URL / NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY). ' +
        'Set them in your Vercel project settings.'
      )
    }
    return { url: url || PLACEHOLDER_URL, anonKey: anonKey || PLACEHOLDER_ANON }
  }

  // Validate URL format; fall back rather than crash the build on a bad value.
  try {
    new URL(url)
  } catch {
    return { url: PLACEHOLDER_URL, anonKey }
  }

  return { url, anonKey }
}

// Lazily loaded config (validates on first use)
let cachedConfig: SupabaseConfig | null = null
function getCachedConfig(): SupabaseConfig {
  if (!cachedConfig) {
    cachedConfig = getConfig()
  }
  return cachedConfig
}

export type ClientMode = 'browser' | 'server' | 'middleware'

// Browser client - synchronous for client-side React components
export type TypedSupabaseClient = SupabaseClient

/**
 * Create a browser-side Supabase client.
 * For use in Client Components (marked with 'use client').
 *
 * @example
 * const supabase = createClient()
 * const { data: { user } } = await supabase.auth.getUser()
 */
export function createClient(): TypedSupabaseClient {
  const config = getCachedConfig()
  return createBrowserClientSSR(config.url, config.anonKey)
}

export function createServiceClient(): TypedSupabaseClient {
  const config = getCachedConfig()
  const serviceRoleKey = process.env.SUPABASE_SERVICE_ROLE_KEY

  if (!serviceRoleKey) {
    throw new Error('Missing SUPABASE_SERVICE_ROLE_KEY')
  }

  return createRawSupabaseClient(config.url, serviceRoleKey, {
    auth: {
      persistSession: false,
      autoRefreshToken: false,
    },
  })
}

/**
 * Create a server-side Supabase client.
 * For use in Server Components and API routes.
 *
 * Note: This is async because it needs to access cookies.
 *
 * @example
 * const supabase = await createServerClient()
 * const { data: { user } } = await supabase.auth.getUser()
 */
export async function createServerClient(): Promise<TypedSupabaseClient> {
  const config = getCachedConfig()
  // Dynamic import to avoid loading next/headers in client components
  const { cookies } = await import('next/headers')
  const cookieStore = await cookies()

  return createServerClientSSR(config.url, config.anonKey, {
    cookies: {
      getAll() {
        return cookieStore.getAll()
      },
      setAll(cookiesToSet) {
        try {
          cookiesToSet.forEach(({ name, value, options }) =>
            cookieStore.set(name, value, options)
          )
        } catch {
          // Server component - cookies are set by middleware
        }
      },
    },
  })
}

/**
 * Factory for creating middleware clients.
 * Returns an object with a method to create a client bound to a specific request.
 *
 * @example
 * const factory = createMiddlewareClientFactory()
 * const supabase = factory.createForRequest(request, response)
 * const { data: { user } } = await supabase.auth.getUser()
 */
export function createMiddlewareClientFactory(): {
  createForRequest(request: NextRequest, response: NextResponse): TypedSupabaseClient
} {
  const config = getCachedConfig()

  return {
    createForRequest(request: NextRequest, response: NextResponse): TypedSupabaseClient {
      return createServerClientSSR(config.url, config.anonKey, {
        cookies: {
          getAll() {
            return request.cookies.getAll()
          },
          setAll(cookiesToSet) {
            cookiesToSet.forEach(({ name, value, options }) => {
              response.cookies.set(name, value, options)
            })
          },
        },
      })
    }
  }
}

/**
 * Unified factory for creating Supabase clients based on mode.
 *
 * @param mode - 'browser' | 'server' | 'middleware'
 * @returns Client instance (or factory for middleware)
 *
 * @example
 * const browserClient = await createSupabaseClient('browser')
 * const serverClient = await createSupabaseClient('server')
 * const middlewareFactory = await createSupabaseClient('middleware')
 */
export async function createSupabaseClient(mode: ClientMode): Promise<TypedSupabaseClient | ReturnType<typeof createMiddlewareClientFactory>> {
  switch (mode) {
    case 'browser':
      return createClient()
    case 'server':
      return createServerClient()
    case 'middleware':
      return createMiddlewareClientFactory()
    default:
      throw new Error(`Unknown client mode: ${mode}`)
  }
}
