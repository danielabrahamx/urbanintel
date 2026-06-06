'use client'

export const dynamic = 'force-dynamic'

import { useEffect, useState, useCallback, useMemo } from 'react'
import { useParams, useRouter } from 'next/navigation'
import { createClient } from '@/lib/supabase'
import { Incident, Severity, SEVERITY_COLORS, SEVERITY_ORDER } from '@/lib/types'
import SeverityBadge from '@/components/SeverityBadge'
import IncidentTypeChip from '@/components/IncidentTypeChip'
import EmptyState from '@/components/EmptyState'
import StatCard from '@/components/StatCard'
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell, Legend
} from 'recharts'
import { format, subDays, eachDayOfInterval, startOfDay, parseISO } from 'date-fns'
import {
  ArrowLeft, MapPin, Camera, AlertTriangle, Shield, Clock,
  ChevronRight, ChevronDown, Activity
} from 'lucide-react'
import Link from 'next/link'

const SEVERITY_CHART_COLORS: Record<Severity, string> = {
  none: '#374151',
  low: '#eab308',
  medium: '#f97316',
  high: '#ef4444',
  critical: '#991b1b',
}

function buildDailyChartData(incidents: Incident[]) {
  const days = eachDayOfInterval({ start: subDays(new Date(), 29), end: new Date() })
  const buckets = new Map<string, Record<Severity, number>>()

  for (const day of days) {
    const key = format(day, 'MMM d')
    buckets.set(key, { none: 0, low: 0, medium: 0, high: 0, critical: 0 })
  }

  for (const inc of incidents) {
    if (!inc.incident_detected) continue
    const key = format(parseISO(inc.created_at), 'MMM d')
    const bucket = buckets.get(key)
    if (bucket) bucket[inc.severity] = (bucket[inc.severity] || 0) + 1
  }

  return Array.from(buckets.entries()).map(([date, counts]) => ({
    date,
    ...counts,
  }))
}

function CustomTooltip({ active, payload, label }: any) {
  if (!active || !payload?.length) return null
  const severities: Severity[] = ['critical', 'high', 'medium', 'low']
  const total = payload.reduce((sum: number, p: any) => sum + (p.value || 0), 0)

  return (
    <div style={{
      background: '#1a1d27',
      border: '1px solid #2a2d3a',
      padding: '10px 14px',
      fontSize: 12,
    }}>
      <div style={{ color: '#f0f2f8', fontWeight: 500, marginBottom: 6 }}>{label}</div>
      {severities.map(s => {
        const p = payload.find((x: any) => x.dataKey === s)
        if (!p || p.value === 0) return null
        return (
          <div key={s} style={{ display: 'flex', justifyContent: 'space-between', gap: 16, color: SEVERITY_CHART_COLORS[s], marginBottom: 2 }}>
            <span style={{ textTransform: 'capitalize' }}>{s}</span>
            <span style={{ fontFamily: 'monospace' }}>{p.value}</span>
          </div>
        )
      })}
      <div style={{ borderTop: '1px solid #2a2d3a', marginTop: 6, paddingTop: 6, color: '#9ca3af', display: 'flex', justifyContent: 'space-between', gap: 16 }}>
        <span>Total</span>
        <span style={{ fontFamily: 'monospace' }}>{total}</span>
      </div>
    </div>
  )
}

export default function CameraPage() {
  const { id } = useParams<{ id: string }>()
  const router = useRouter()
  const supabase = createClient()

  const [incidents, setIncidents] = useState<Incident[]>([])
  const [loading, setLoading] = useState(true)
  const [expandedId, setExpandedId] = useState<string | null>(null)
  const [camera, setCamera] = useState<{ name: string; lat: number | null; lon: number | null } | null>(null)

  const loadData = useCallback(async () => {
    const { data, error } = await supabase
      .from('incidents')
      .select('*')
      .eq('camera_id', id)
      .gte('created_at', subDays(new Date(), 30).toISOString())
      .order('created_at', { ascending: false })
      .limit(1000)

    if (!error && data && data.length > 0) {
      const rows = data as Incident[]
      setIncidents(rows)
      setCamera({ name: rows[0].camera_name, lat: rows[0].lat, lon: rows[0].lon })
    }
    setLoading(false)
  }, [id])

  useEffect(() => { loadData() }, [loadData])

  const stats = useMemo(() => {
    const detected = incidents.filter(i => i.incident_detected)
    const types = new Map<string, number>()
    for (const inc of detected) {
      for (const evt of inc.incidents ?? []) {
        types.set(evt.type, (types.get(evt.type) || 0) + 1)
      }
    }
    const mostCommon = [...types.entries()].sort((a, b) => b[1] - a[1])[0]
    const worstSeverity = detected.reduce<Severity>((worst, inc) => {
      return SEVERITY_ORDER[inc.severity] > SEVERITY_ORDER[worst] ? inc.severity : worst
    }, 'none')
    const lastSeen = incidents[0]?.created_at
    return { detected, types, mostCommon, worstSeverity, lastSeen }
  }, [incidents])

  const chartData = useMemo(() => buildDailyChartData(incidents), [incidents])
  const detectedIncidents = incidents.filter(i => i.incident_detected)

  if (!loading && incidents.length === 0) {
    return (
      <div style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
        <div style={{ padding: '16px 24px', borderBottom: '1px solid #2a2d3a', background: '#1a1d27' }}>
          <button
            onClick={() => router.back()}
            style={{ display: 'flex', alignItems: 'center', gap: 6, background: 'none', border: 'none', color: '#6b7280', fontSize: 13, cursor: 'pointer', padding: 0 }}
          >
            <ArrowLeft size={14} /> Back
          </button>
        </div>
        <EmptyState
          icon={Camera}
          title="Camera not found"
          description={`No data found for camera ID: ${id}`}
        />
      </div>
    )
  }

  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column', overflow: 'auto' }}>
      {/* Page header */}
      <div
        style={{
          padding: '14px 24px',
          borderBottom: '1px solid #2a2d3a',
          background: '#1a1d27',
          flexShrink: 0,
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 10 }}>
          <button
            onClick={() => router.back()}
            style={{ display: 'flex', alignItems: 'center', gap: 6, background: 'none', border: 'none', color: '#6b7280', fontSize: 13, cursor: 'pointer', padding: 0, flexShrink: 0 }}
          >
            <ArrowLeft size={14} />
          </button>
          <div>
            {loading ? (
              <div style={{ color: '#6b7280', fontSize: 14 }}>Loading...</div>
            ) : (
              <>
                <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                  <h1 style={{ color: '#f0f2f8', fontSize: 18, fontWeight: 600, letterSpacing: '-0.02em', margin: 0 }}>
                    {camera?.name ?? id}
                  </h1>
                  <SeverityBadge severity={stats.worstSeverity} />
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginTop: 4 }}>
                  <span style={{ color: '#6b7280', fontSize: 12, fontFamily: 'monospace' }}>{id}</span>
                  {camera?.lat != null && (
                    <span style={{ display: 'flex', alignItems: 'center', gap: 4, color: '#6b7280', fontSize: 12 }}>
                      <MapPin size={11} />
                      {camera.lat.toFixed(4)}, {camera.lon?.toFixed(4)}
                    </span>
                  )}
                </div>
              </>
            )}
          </div>
        </div>
      </div>

      {!loading && (
        <div style={{ padding: '20px 24px', display: 'flex', flexDirection: 'column', gap: 20 }}>
          {/* Stats bar */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 1, background: '#2a2d3a' }}>
            <StatCard
              label="Total incidents"
              value={stats.detected.length}
              sub="Last 30 days"
              icon={AlertTriangle}
              accent="#ef4444"
            />
            <StatCard
              label="Most common type"
              value={stats.mostCommon ? stats.mostCommon[0].replace(/_/g, ' ').toLowerCase() : 'None'}
              sub={stats.mostCommon ? `${stats.mostCommon[1]} occurrences` : undefined}
              icon={Activity}
              accent="#f97316"
            />
            <StatCard
              label="Worst severity"
              value={stats.worstSeverity.toUpperCase()}
              icon={Shield}
              accent={SEVERITY_COLORS[stats.worstSeverity]}
            />
            <StatCard
              label="Last detected"
              value={stats.lastSeen ? format(new Date(stats.lastSeen), 'HH:mm') : 'N/A'}
              sub={stats.lastSeen ? format(new Date(stats.lastSeen), 'dd MMM yyyy') : undefined}
              icon={Clock}
              accent="#3b82f6"
            />
          </div>

          {/* Timeline chart */}
          <div style={{ background: '#1a1d27', border: '1px solid #2a2d3a' }}>
            <div style={{ padding: '14px 20px', borderBottom: '1px solid #2a2d3a', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <span style={{ color: '#f0f2f8', fontSize: 13, fontWeight: 500 }}>Incident timeline</span>
              <span style={{ color: '#6b7280', fontSize: 11 }}>Last 30 days · stacked by severity</span>
            </div>
            <div style={{ padding: '16px 16px 8px' }}>
              <ResponsiveContainer width="100%" height={200}>
                <BarChart data={chartData} barSize={8} barGap={0} barCategoryGap="30%">
                  <XAxis
                    dataKey="date"
                    tick={{ fill: '#6b7280', fontSize: 10 }}
                    axisLine={{ stroke: '#2a2d3a' }}
                    tickLine={false}
                    interval={4}
                  />
                  <YAxis
                    tick={{ fill: '#6b7280', fontSize: 10 }}
                    axisLine={false}
                    tickLine={false}
                    allowDecimals={false}
                    width={24}
                  />
                  <Tooltip content={<CustomTooltip />} cursor={{ fill: 'rgba(255,255,255,0.03)' }} />
                  <Bar dataKey="low" stackId="a" fill={SEVERITY_CHART_COLORS.low} />
                  <Bar dataKey="medium" stackId="a" fill={SEVERITY_CHART_COLORS.medium} />
                  <Bar dataKey="high" stackId="a" fill={SEVERITY_CHART_COLORS.high} />
                  <Bar dataKey="critical" stackId="a" fill={SEVERITY_CHART_COLORS.critical} radius={[2, 2, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>

          {/* Incident history table */}
          <div style={{ background: '#1a1d27', border: '1px solid #2a2d3a' }}>
            <div style={{ padding: '14px 20px', borderBottom: '1px solid #2a2d3a', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <span style={{ color: '#f0f2f8', fontSize: 13, fontWeight: 500 }}>Incident history</span>
              <span style={{ color: '#6b7280', fontSize: 11 }}>{detectedIncidents.length} incidents</span>
            </div>

            {detectedIncidents.length === 0 ? (
              <div style={{ padding: '40px 20px', textAlign: 'center', color: '#6b7280', fontSize: 13 }}>
                No incidents detected in the last 30 days
              </div>
            ) : (
              <table className="ui-table" style={{ width: '100%', borderCollapse: 'collapse' }}>
                <thead>
                  <tr>
                    <th style={{ width: 140 }}>Time</th>
                    <th>Severity</th>
                    <th>Types</th>
                    <th>Summary</th>
                    <th style={{ width: 32 }} />
                  </tr>
                </thead>
                <tbody>
                  {detectedIncidents.map(inc => {
                    const expanded = expandedId === inc.id
                    return [
                      <tr
                        key={inc.id}
                        onClick={() => setExpandedId(expanded ? null : inc.id)}
                        style={{ cursor: 'pointer' }}
                      >
                        <td style={{ fontFamily: 'monospace', fontSize: 12 }}>
                          <div style={{ color: '#f0f2f8' }}>{format(new Date(inc.created_at), 'HH:mm:ss')}</div>
                          <div style={{ color: '#6b7280', fontSize: 11 }}>{format(new Date(inc.created_at), 'dd MMM')}</div>
                        </td>
                        <td>
                          <SeverityBadge severity={inc.severity} size="sm" />
                        </td>
                        <td>
                          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 3 }}>
                            {(inc.incidents ?? []).map((i, idx) => (
                              <IncidentTypeChip key={idx} type={i.type} size="sm" />
                            ))}
                          </div>
                        </td>
                        <td style={{ maxWidth: 360 }}>
                          <div style={{ color: '#9ca3af', fontSize: 12, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                            {inc.scene_summary ?? 'No summary'}
                          </div>
                        </td>
                        <td>
                          <ChevronDown
                            size={14}
                            color="#6b7280"
                            style={{ transform: expanded ? 'rotate(180deg)' : 'none', transition: 'transform 0.15s' }}
                          />
                        </td>
                      </tr>,
                      expanded && (
                        <tr key={`${inc.id}-exp`} className="row-expand-enter">
                          <td colSpan={5} style={{ background: '#141720', padding: '16px 20px', borderBottom: '1px solid #2a2d3a' }}>
                            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20 }}>
                              <div>
                                <div style={{ color: '#6b7280', fontSize: 10, fontWeight: 500, letterSpacing: '0.08em', textTransform: 'uppercase', marginBottom: 6 }}>Scene</div>
                                <div style={{ color: '#e5e7eb', fontSize: 13, lineHeight: 1.6 }}>{inc.scene_summary}</div>
                                <div style={{ color: '#6b7280', fontSize: 10, fontWeight: 500, letterSpacing: '0.08em', textTransform: 'uppercase', marginBottom: 6, marginTop: 14 }}>Reasoning</div>
                                <div style={{ color: '#9ca3af', fontSize: 13, lineHeight: 1.6, fontStyle: 'italic' }}>{inc.reasoning}</div>
                              </div>
                              <div>
                                <div style={{ color: '#6b7280', fontSize: 10, fontWeight: 500, letterSpacing: '0.08em', textTransform: 'uppercase', marginBottom: 6 }}>Events</div>
                                {(inc.incidents ?? []).map((evt, i) => (
                                  <div key={i} style={{ background: '#1a1d27', border: '1px solid #2a2d3a', padding: '8px 12px', marginBottom: 6 }}>
                                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 4 }}>
                                      <IncidentTypeChip type={evt.type} size="sm" />
                                      <span style={{ color: '#6b7280', fontSize: 10, fontFamily: 'monospace' }}>@{evt.timestamp_in_clip} · {evt.confidence}</span>
                                    </div>
                                    <div style={{ color: '#9ca3af', fontSize: 12 }}>{evt.description}</div>
                                  </div>
                                ))}
                              </div>
                            </div>
                          </td>
                        </tr>
                      ),
                    ]
                  })}
                </tbody>
              </table>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
