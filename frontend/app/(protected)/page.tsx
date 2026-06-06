'use client'

export const dynamic = 'force-dynamic'

import { useEffect, useState, useCallback } from 'react'
import dynamicImport from 'next/dynamic'
import Link from 'next/link'
import { createClient } from '@/lib/supabase'
import { Incident, Severity, SEVERITY_ORDER } from '@/lib/types'
import SeverityBadge from '@/components/SeverityBadge'
import DateRangePicker, { DateRange } from '@/components/DateRangePicker'
import { subDays, formatDistanceToNow } from 'date-fns'
import { RefreshCw, ChevronRight, Zap } from 'lucide-react'

// Dynamic import to avoid SSR issues with Leaflet
const MapView = dynamicImport(() => import('@/components/Map'), {
  ssr: false,
  loading: () => (
    <div style={{ width: '100%', height: '100%', background: '#0d1117', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
      <div style={{ color: '#6b7280', fontSize: 13 }}>Loading map...</div>
    </div>
  ),
})

const SEVERITY_FILTERS: { label: string; value: Severity | 'all' }[] = [
  { label: 'All', value: 'all' },
  { label: 'Low+', value: 'low' },
  { label: 'Medium+', value: 'medium' },
  { label: 'High+', value: 'high' },
  { label: 'Critical', value: 'critical' },
]

export default function MapPage() {
  const supabase = createClient()
  const [incidents, setIncidents] = useState<Incident[]>([])
  const [loading, setLoading] = useState(true)
  const [lastRefresh, setLastRefresh] = useState(new Date())
  const [severityFilter, setSeverityFilter] = useState<Severity | 'all'>('all')
  const [dateRange, setDateRange] = useState<DateRange>({
    label: 'Last 7 days',
    from: subDays(new Date(), 7),
    to: new Date(),
  })
  const [recentAlerts, setRecentAlerts] = useState<Incident[]>([])

  const loadIncidents = useCallback(async () => {
    const { data, error } = await supabase
      .from('incidents')
      .select('*')
      .gte('created_at', dateRange.from.toISOString())
      .lte('created_at', dateRange.to.toISOString())
      .order('created_at', { ascending: false })
      .limit(2000)

    if (!error && data) {
      setIncidents(data as Incident[])
      setRecentAlerts(
        (data as Incident[])
          .filter(i => i.incident_detected && SEVERITY_ORDER[i.severity] >= SEVERITY_ORDER['medium'])
          .slice(0, 5)
      )
    }
    setLoading(false)
    setLastRefresh(new Date())
  }, [dateRange]) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    loadIncidents()
  }, [loadIncidents])

  // Realtime subscription
  useEffect(() => {
    const channel = supabase
      .channel('incidents-realtime')
      .on(
        'postgres_changes',
        { event: 'INSERT', schema: 'public', table: 'incidents' },
        (payload) => {
          const newInc = payload.new as Incident
          setIncidents(prev => [newInc, ...prev])
          if (newInc.incident_detected && SEVERITY_ORDER[newInc.severity] >= SEVERITY_ORDER['medium']) {
            setRecentAlerts(prev => [newInc, ...prev].slice(0, 5))
          }
        }
      )
      .subscribe()

    return () => { supabase.removeChannel(channel) }
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  // Filter incidents for display
  const filteredIncidents = incidents.filter(inc => {
    if (severityFilter === 'all') return true
    return SEVERITY_ORDER[inc.severity] >= SEVERITY_ORDER[severityFilter]
  })

  // Stats
  const totalIncidents = incidents.filter(i => i.incident_detected).length
  const criticalCount = incidents.filter(i => i.severity === 'critical').length
  const uniqueCameras = new Set(incidents.filter(i => i.lat != null).map(i => i.camera_id)).size

  return (
    <div style={{ display: 'flex', height: '100%', overflow: 'hidden' }}>
      {/* Left sidebar */}
      <div
        style={{
          width: 300,
          background: '#1a1d27',
          borderRight: '1px solid #2a2d3a',
          display: 'flex',
          flexDirection: 'column',
          flexShrink: 0,
          overflow: 'hidden',
        }}
      >
        {/* Header */}
        <div style={{ padding: '16px', borderBottom: '1px solid #2a2d3a' }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
            <span style={{ color: '#6b7280', fontSize: 11, fontWeight: 500, letterSpacing: '0.08em', textTransform: 'uppercase' }}>
              Live Monitor
            </span>
            <button
              onClick={loadIncidents}
              style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#6b7280', padding: 4 }}
              title="Refresh"
            >
              <RefreshCw size={13} />
            </button>
          </div>

          <DateRangePicker value={dateRange} onChange={setDateRange} />
        </div>

        {/* Stats */}
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', borderBottom: '1px solid #2a2d3a' }}>
          {[
            { label: 'Incidents', value: totalIncidents, color: '#f0f2f8' },
            { label: 'Critical', value: criticalCount, color: criticalCount > 0 ? '#ef4444' : '#f0f2f8' },
            { label: 'Cameras', value: uniqueCameras, color: '#f0f2f8' },
            { label: 'Scans', value: incidents.length, color: '#f0f2f8' },
          ].map(stat => (
            <div key={stat.label} style={{ padding: '12px 16px', borderRight: '1px solid #2a2d3a', borderBottom: '1px solid #2a2d3a' }}>
              <div style={{ color: stat.color, fontSize: 22, fontWeight: 600, letterSpacing: '-0.03em', lineHeight: 1 }}>
                {stat.value}
              </div>
              <div style={{ color: '#6b7280', fontSize: 10, fontWeight: 500, letterSpacing: '0.08em', textTransform: 'uppercase', marginTop: 4 }}>
                {stat.label}
              </div>
            </div>
          ))}
        </div>

        {/* Severity filter */}
        <div style={{ padding: '12px 16px', borderBottom: '1px solid #2a2d3a' }}>
          <div style={{ color: '#6b7280', fontSize: 10, fontWeight: 500, letterSpacing: '0.08em', textTransform: 'uppercase', marginBottom: 8 }}>
            Severity filter
          </div>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
            {SEVERITY_FILTERS.map(f => {
              const active = severityFilter === f.value
              return (
                <button
                  key={f.value}
                  onClick={() => setSeverityFilter(f.value as Severity | 'all')}
                  style={{
                    padding: '4px 10px',
                    fontSize: 11,
                    fontWeight: active ? 500 : 400,
                    color: active ? '#f0f2f8' : '#6b7280',
                    background: active ? '#2a2d3a' : 'transparent',
                    border: `1px solid ${active ? '#3a3d4a' : '#2a2d3a'}`,
                    cursor: 'pointer',
                    transition: 'all 0.1s',
                  }}
                >
                  {f.label}
                </button>
              )
            })}
          </div>
        </div>

        {/* Recent alerts */}
        <div style={{ flex: 1, overflow: 'auto' }}>
          <div style={{ padding: '12px 16px 8px', borderBottom: '1px solid #2a2d3a' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6, color: '#6b7280', fontSize: 10, fontWeight: 500, letterSpacing: '0.08em', textTransform: 'uppercase' }}>
              <Zap size={10} />
              Recent alerts
            </div>
          </div>

          {loading && (
            <div style={{ padding: '20px 16px', color: '#6b7280', fontSize: 12, textAlign: 'center' }}>
              Loading...
            </div>
          )}

          {!loading && recentAlerts.length === 0 && (
            <div style={{ padding: '20px 16px', color: '#6b7280', fontSize: 12, textAlign: 'center' }}>
              No incidents in range
            </div>
          )}

          {recentAlerts.map(alert => (
            <Link
              key={alert.id}
              href={`/camera/${alert.camera_id}`}
              style={{ textDecoration: 'none' }}
            >
              <div
                style={{
                  padding: '10px 16px',
                  borderBottom: '1px solid #2a2d3a',
                  cursor: 'pointer',
                  transition: 'background 0.1s',
                }}
                onMouseEnter={e => (e.currentTarget.style.background = '#1f2330')}
                onMouseLeave={e => (e.currentTarget.style.background = 'transparent')}
              >
                <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 8 }}>
                  <div style={{ minWidth: 0 }}>
                    <div style={{ color: '#f0f2f8', fontSize: 12, fontWeight: 500, marginBottom: 2, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {alert.camera_name}
                    </div>
                    <div style={{ color: '#9ca3af', fontSize: 11, lineHeight: 1.4, overflow: 'hidden', display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical' }}>
                      {alert.scene_summary}
                    </div>
                  </div>
                  <SeverityBadge severity={alert.severity} size="sm" />
                </div>
                <div style={{ color: '#4b5563', fontSize: 10, marginTop: 4 }}>
                  {formatDistanceToNow(new Date(alert.created_at), { addSuffix: true })}
                </div>
              </div>
            </Link>
          ))}
        </div>

        {/* Footer */}
        <div style={{ padding: '10px 16px', borderTop: '1px solid #2a2d3a' }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <span style={{ color: '#4b5563', fontSize: 10 }}>
              Updated {formatDistanceToNow(lastRefresh, { addSuffix: true })}
            </span>
            <Link href="/incidents" style={{ color: '#3b82f6', fontSize: 11, textDecoration: 'none', display: 'flex', alignItems: 'center', gap: 4 }}>
              All incidents <ChevronRight size={11} />
            </Link>
          </div>
        </div>
      </div>

      {/* Map */}
      <div style={{ flex: 1, position: 'relative' }}>
        {loading && (
          <div
            style={{
              position: 'absolute',
              top: 12,
              left: '50%',
              transform: 'translateX(-50%)',
              zIndex: 1000,
              background: '#1a1d27',
              border: '1px solid #2a2d3a',
              padding: '6px 14px',
              color: '#6b7280',
              fontSize: 12,
              display: 'flex',
              alignItems: 'center',
              gap: 6,
            }}
          >
            <RefreshCw size={12} style={{ animation: 'spin 1s linear infinite' }} />
            Loading incidents...
          </div>
        )}

        <MapView incidents={filteredIncidents} />

        {/* Map legend */}
        <div
          style={{
            position: 'absolute',
            bottom: 20,
            right: 12,
            zIndex: 1000,
            background: 'rgba(26,29,39,0.95)',
            border: '1px solid #2a2d3a',
            padding: '12px 14px',
            backdropFilter: 'blur(4px)',
          }}
        >
          <div style={{ color: '#6b7280', fontSize: 10, fontWeight: 500, letterSpacing: '0.08em', textTransform: 'uppercase', marginBottom: 8 }}>
            Severity
          </div>
          {[
            { label: 'None / clear', color: '#6b7280' },
            { label: 'Low', color: '#eab308' },
            { label: 'Medium', color: '#f97316' },
            { label: 'High', color: '#ef4444' },
            { label: 'Critical', color: '#7f1d1d' },
          ].map(item => (
            <div key={item.label} style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
              <span style={{ width: 8, height: 8, borderRadius: '50%', background: item.color, display: 'inline-block', flexShrink: 0 }} />
              <span style={{ color: '#9ca3af', fontSize: 11 }}>{item.label}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
