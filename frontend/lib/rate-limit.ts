/**
 * Shared rate limiter for analysis endpoints.
 *
 * Two guards, one function:
 * 1. ANALYZE_ENABLED=false  →  all analysis blocked (set in Vercel when idle)
 * 2. 30-minute cooldown     →  one analysis per 30 min window
 *
 * In-memory only — resets on cold start. Fine for a hackathon demo.
 */

const COOLDOWN_MS = 30 * 60 * 1000

let lastAnalysisAt = 0

type RateLimitResult =
  | { allowed: true }
  | { allowed: false; reason: 'disabled' }
  | { allowed: false; reason: 'cooldown'; retryAfterMs: number }

export function checkRateLimit(): RateLimitResult {
  if (process.env.ANALYZE_ENABLED === 'false') {
    return { allowed: false, reason: 'disabled' }
  }

  const now = Date.now()
  const elapsed = now - lastAnalysisAt

  if (elapsed < COOLDOWN_MS) {
    return { allowed: false, reason: 'cooldown', retryAfterMs: COOLDOWN_MS - elapsed }
  }

  lastAnalysisAt = now
  return { allowed: true }
}
