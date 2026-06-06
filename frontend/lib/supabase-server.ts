/**
 * Re-export for backward compatibility.
 *
 * Prefer importing from '@/lib/supabase' directly:
 *   import { createServerClient } from '@/lib/supabase'
 *
 * This file exists to avoid breaking existing imports.
 */
export { createServerClient as createServerSupabaseClient } from './supabase'
