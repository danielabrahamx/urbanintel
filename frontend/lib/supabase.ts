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
import type { NextRequest, NextResponse } from 'next/server'
import type { SupabaseClient } from '@supabase/supabase-js'

interface SupabaseConfig {
  url: string
  anonKey: string
}

function getConfig(): SupabaseConfig {
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL
  const anonKey = process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY

  if (!url || !anonKey) {
    throw new Error(
      'Missing Supabase environment variables. ' +
      'Check NEXT_PUBLIC_SUPABASE_URL and NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY'
    )
  }

  // Validate URL format
  try {
    new URL(url)
  } catch {
    throw new Error(`Invalid SUPABASE_URL: ${url}`)
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
