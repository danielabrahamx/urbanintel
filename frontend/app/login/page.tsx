'use client'

export const dynamic = 'force-dynamic'

import { useState } from 'react'
import { useRouter } from 'next/navigation'
import { createClient } from '@/lib/supabase'
import { Radio, AlertCircle, Eye, EyeOff } from 'lucide-react'

export default function LoginPage() {
  const router = useRouter()
  const supabase = createClient()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  async function handleLogin(e: React.FormEvent) {
    e.preventDefault()
    setLoading(true)
    setError(null)
    const { error } = await supabase.auth.signInWithPassword({ email, password })
    if (error) {
      setError(error.message)
      setLoading(false)
    } else {
      router.push('/')
      router.refresh()
    }
  }

  return (
    <div
      className="min-h-screen flex items-center justify-center"
      style={{ background: '#0f1117' }}
    >
      {/* Background grid */}
      <div
        className="absolute inset-0 pointer-events-none"
        style={{
          backgroundImage: 'linear-gradient(#2a2d3a 1px, transparent 1px), linear-gradient(90deg, #2a2d3a 1px, transparent 1px)',
          backgroundSize: '40px 40px',
          opacity: 0.3,
        }}
      />

      <div className="relative w-full max-w-sm px-4">
        {/* Card */}
        <div
          style={{
            background: '#1a1d27',
            border: '1px solid #2a2d3a',
            padding: '40px 36px',
          }}
        >
          {/* Logo */}
          <div className="flex items-center gap-3 mb-8">
            <div
              style={{ background: '#3b82f6', padding: '8px', width: 36, height: 36, display: 'flex', alignItems: 'center', justifyContent: 'center' }}
            >
              <Radio size={18} color="#fff" strokeWidth={2} />
            </div>
            <div>
              <div style={{ color: '#f0f2f8', fontWeight: 600, fontSize: 15, letterSpacing: '-0.01em' }}>
                Urban Intelligence
              </div>
              <div style={{ color: '#6b7280', fontSize: 11, marginTop: 1 }}>
                Road Safety Monitoring
              </div>
            </div>
          </div>

          <div style={{ color: '#f0f2f8', fontSize: 18, fontWeight: 600, marginBottom: 4, letterSpacing: '-0.02em' }}>
            Sign in
          </div>
          <div style={{ color: '#6b7280', fontSize: 13, marginBottom: 28 }}>
            Access is restricted to authorised operators.
          </div>

          {error && (
            <div
              className="flex items-center gap-2 mb-5 px-3 py-2.5"
              style={{ background: 'rgba(239,68,68,0.1)', border: '1px solid rgba(239,68,68,0.3)', color: '#fca5a5', fontSize: 13 }}
            >
              <AlertCircle size={14} />
              {error}
            </div>
          )}

          <form onSubmit={handleLogin} className="flex flex-col gap-4">
            <div>
              <label style={{ color: '#6b7280', fontSize: 11, fontWeight: 500, letterSpacing: '0.08em', textTransform: 'uppercase', display: 'block', marginBottom: 6 }}>
                Email
              </label>
              <input
                type="email"
                value={email}
                onChange={e => setEmail(e.target.value)}
                required
                placeholder="operator@council.gov.uk"
                style={{
                  width: '100%',
                  background: '#0f1117',
                  border: '1px solid #2a2d3a',
                  color: '#f0f2f8',
                  padding: '10px 12px',
                  fontSize: 14,
                  outline: 'none',
                  transition: 'border-color 0.15s',
                }}
                onFocus={e => (e.target.style.borderColor = '#3b82f6')}
                onBlur={e => (e.target.style.borderColor = '#2a2d3a')}
              />
            </div>

            <div>
              <label style={{ color: '#6b7280', fontSize: 11, fontWeight: 500, letterSpacing: '0.08em', textTransform: 'uppercase', display: 'block', marginBottom: 6 }}>
                Password
              </label>
              <div className="relative">
                <input
                  type={showPassword ? 'text' : 'password'}
                  value={password}
                  onChange={e => setPassword(e.target.value)}
                  required
                  placeholder="••••••••"
                  style={{
                    width: '100%',
                    background: '#0f1117',
                    border: '1px solid #2a2d3a',
                    color: '#f0f2f8',
                    padding: '10px 40px 10px 12px',
                    fontSize: 14,
                    outline: 'none',
                    transition: 'border-color 0.15s',
                  }}
                  onFocus={e => (e.target.style.borderColor = '#3b82f6')}
                  onBlur={e => (e.target.style.borderColor = '#2a2d3a')}
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="absolute right-3 top-1/2 -translate-y-1/2"
                  style={{ color: '#6b7280', background: 'none', border: 'none', cursor: 'pointer', padding: 0 }}
                >
                  {showPassword ? <EyeOff size={15} /> : <Eye size={15} />}
                </button>
              </div>
            </div>

            <button
              type="submit"
              disabled={loading}
              style={{
                width: '100%',
                background: loading ? '#1d4ed8' : '#3b82f6',
                color: '#fff',
                padding: '11px',
                fontSize: 14,
                fontWeight: 500,
                border: 'none',
                cursor: loading ? 'not-allowed' : 'pointer',
                marginTop: 4,
                transition: 'background 0.15s',
                letterSpacing: '-0.01em',
              }}
              onMouseEnter={e => { if (!loading) (e.currentTarget as HTMLButtonElement).style.background = '#2563eb' }}
              onMouseLeave={e => { if (!loading) (e.currentTarget as HTMLButtonElement).style.background = '#3b82f6' }}
            >
              {loading ? 'Authenticating...' : 'Sign in'}
            </button>
          </form>

          <div style={{ marginTop: 24, borderTop: '1px solid #2a2d3a', paddingTop: 20 }}>
            <p style={{ color: '#4b5563', fontSize: 12, textAlign: 'center', lineHeight: 1.5 }}>
              Accounts are provisioned by your system administrator.<br />
              Contact your council IT team for access.
            </p>
          </div>
        </div>

        {/* Footer */}
        <div style={{ textAlign: 'center', marginTop: 20 }}>
          <span style={{ color: '#374151', fontSize: 11 }}>
            Urban Intelligence &copy; {new Date().getFullYear()} — Confidential
          </span>
        </div>
      </div>
    </div>
  )
}
