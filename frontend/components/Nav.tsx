'use client'

import Link from 'next/link'
import { usePathname, useRouter } from 'next/navigation'
import { createClient } from '@/lib/supabase'
import { Map, List, LogOut, Radio } from 'lucide-react'

const NAV_ITEMS = [
  { href: '/', label: 'Live Map', icon: Map },
  { href: '/incidents', label: 'Incidents', icon: List },
]

export default function Nav() {
  const pathname = usePathname()
  const router = useRouter()
  const supabase = createClient()

  async function signOut() {
    await supabase.auth.signOut()
    router.push('/login')
    router.refresh()
  }

  return (
    <nav
      style={{
        background: '#1a1d27',
        borderBottom: '1px solid #2a2d3a',
        height: '52px',
      }}
      className="flex items-center justify-between px-6 shrink-0"
    >
      {/* Left: brand */}
      <div className="flex items-center gap-6">
        <Link href="/" className="flex items-center gap-2.5 group">
          <div
            className="relative flex items-center justify-center"
            style={{ width: 28, height: 28, background: '#3b82f6', padding: 5 }}
          >
            <Radio size={16} color="#fff" strokeWidth={2} />
            {/* Live pulse dot */}
            <span
              className="absolute -top-1 -right-1 flex items-center justify-center"
              style={{ width: 8, height: 8 }}
            >
              <span
                className="absolute inline-flex h-full w-full rounded-full opacity-75"
                style={{ background: '#10b981', animation: 'ping 1.5s cubic-bezier(0,0,0.2,1) infinite' }}
              />
              <span
                className="relative inline-flex rounded-full"
                style={{ width: 6, height: 6, background: '#10b981' }}
              />
            </span>
          </div>
          <span
            className="font-semibold tracking-tight"
            style={{ color: '#f0f2f8', fontSize: 14, letterSpacing: '-0.01em' }}
          >
            Urban Intelligence
          </span>
        </Link>

        <div
          style={{ width: 1, height: 20, background: '#2a2d3a' }}
        />

        {/* Nav links */}
        <div className="flex items-center gap-1">
          {NAV_ITEMS.map(({ href, label, icon: Icon }) => {
            const active = pathname === href
            return (
              <Link
                key={href}
                href={href}
                className="flex items-center gap-2 px-3 py-1.5 text-sm transition-colors"
                style={{
                  color: active ? '#f0f2f8' : '#6b7280',
                  background: active ? '#2a2d3a' : 'transparent',
                  fontSize: 13,
                  fontWeight: active ? 500 : 400,
                }}
              >
                <Icon size={14} />
                {label}
              </Link>
            )
          })}
        </div>
      </div>

      {/* Right: status + sign out */}
      <div className="flex items-center gap-4">
        <div className="flex items-center gap-2">
          <span
            className="inline-flex rounded-full"
            style={{ width: 6, height: 6, background: '#10b981' }}
          />
          <span style={{ color: '#6b7280', fontSize: 12 }}>Live</span>
        </div>
        <button
          onClick={signOut}
          className="flex items-center gap-1.5 px-2.5 py-1 text-xs transition-colors"
          style={{
            color: '#6b7280',
            border: '1px solid #2a2d3a',
            background: 'transparent',
            cursor: 'pointer',
            fontSize: 12,
          }}
          onMouseEnter={e => {
            (e.currentTarget as HTMLButtonElement).style.color = '#f0f2f8'
            ;(e.currentTarget as HTMLButtonElement).style.borderColor = '#3a3d4a'
          }}
          onMouseLeave={e => {
            (e.currentTarget as HTMLButtonElement).style.color = '#6b7280'
            ;(e.currentTarget as HTMLButtonElement).style.borderColor = '#2a2d3a'
          }}
        >
          <LogOut size={12} />
          Sign out
        </button>
      </div>
    </nav>
  )
}
