'use client'

export const dynamic = 'force-dynamic'

import { useEffect, useState, useCallback, useMemo } from 'react'
import { createClient } from '@/lib/supabase'
import { Incident, Severity, SEVERITY_ORDER, IncidentDetail } from '@/lib/types'
import SeverityBadge from '@/components/SeverityBadge'
import IncidentTypeChip from '@/components/IncidentTypeChip'
import DateRangePicker, { DateRange } from '@/components/DateRangePicker'
import EmptyState from '@/components/EmptyState'
import { subDays, format, formatDistanceToNow } from 'date-fns'
import {
  ChevronUp, ChevronDown, ChevronsUpDown, Download, Filter,
  ChevronRight, AlertTriangle, RefreshCw, X, Search, MapPin
} from 'lucide-react'
import Link from 'next/link'

type SortField = 'created_at' | 'severity' | 'camera_name'
type SortDir = 'asc' | 'desc'

const SEVERITY_OPTIONS: Severity[] = ['low', 'medium', 'high', 'critical']
const INCIDENT_TYPES = [
  'NEAR_MISS', 'RED_LIGHT_VIOLATION', 'WRONG_WAY', 'DANGEROUS_OVERTAKE',
  'PEDESTRIAN_IN_ROAD', 'VEHICLE_STOPPED_DANGEROUSLY', 'AGGRESSIVE_DRIVING', 'CYCLIST_RISK',
]

function SortIcon({ field, sortField, sortDir }: { field: string; sortField: string; sortDir: SortDir }) {
  if (field !== sortField) return <ChevronsUpDown size={12} style={{ opacity: 0.4 }} />
  return sortDir === 'asc' ? <ChevronUp size={12} /> : <ChevronDown size={12} />
}

function exportToCSV(incidents: Incident[]) {
  const headers = ['Time', 'Camera', 'Severity', 'Types', 'Confidence', 'Scene Summary', 'Reasoning']
  const rows = incidents.map(inc => [
    format(new Date(inc.created_at), 'yyyy-MM-dd HH:mm:ss'),
    inc.camera_name,
    inc.severity,
    (inc.incidents ?? []).map(i => i.type).join('; '),
    (inc.incidents ?? []).map(i => i.confidence).join('; '),
    inc.scene_summary ?? '',
    inc.reasoning ?? '',
  ])

  const csv = [headers, ...rows]
    .map(row => row.map(cell => `"${String(cell).replace(/"/g, '""')}"`).join(','))
    .join('\n')

  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `incidents-${format(new Date(), 'yyyy-MM-dd')}.csv`
  a.click()
  URL.revokeObjectURL(url)
}

function ExpandedRow({ incident }: { incident: Incident }) {
  return (
    <tr className="row-expand-enter">
      <td
        colSpan={8}
        style={{ background: '#141720', padding: 0, borderBottom: '2px solid #2a2d3a' }}
      >
        <div style={{ padding: '16px 24px', display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 20 }}>
          {/* Scene summary */}
          <div>
            <div style={{ color: '#6b7280', fontSize: 10, fontWeight: 500, letterSpacing: '0.08em', textTransform: 'uppercase', marginBottom: 6 }}>
              Scene summary
            </div>
            <div style={{ color: '#e5e7eb', fontSize: 13, lineHeight: 1.6 }}>
              {incident.scene_summary ?? 'No summary'}
            </div>
          </div>

          {/* Reasoning */}
          <div>
            <div style={{ color: '#6b7280', fontSize: 10, fontWeight: 500, letterSpacing: '0.08em', textTransform: 'uppercase', marginBottom: 6 }}>
              AI reasoning
            </div>
            <div style={{ color: '#e5e7eb', fontSize: 13, lineHeight: 1.6, fontStyle: 'italic' }}>
              {incident.reasoning ?? 'No reasoning provided'}
            </div>
          </div>

          {/* Incidents detail */}
          <div>
            <div style={{ color: '#6b7280', fontSize: 10, fontWeight: 500, letterSpacing: '0.08em', textTransform: 'uppercase', marginBottom: 6 }}>
              Detected events
            </div>
            {(incident.incidents ?? []).length === 0 ? (
              <div style={{ color: '#6b7280', fontSize: 12 }}>No events detected</div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                {(incident.incidents ?? []).map((inc: IncidentDetail, i: number) => (
                  <div key={i} style={{ background: '#1a1d27', border: '1px solid #2a2d3a', padding: '8px 12px' }}>
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 4 }}>
                      <IncidentTypeChip type={inc.type} size="sm" />
                      <span style={{ color: '#6b7280', fontSize: 10, fontFamily: 'monospace' }}>
                        @{inc.timestamp_in_clip}  conf:{inc.confidence}
                      </span>
                    </div>
                    <div style={{ color: '#9ca3af', fontSize: 12, lineHeight: 1.5 }}>
                      {inc.description}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Camera link */}
        <div style={{ padding: '10px 24px', borderTop: '1px solid #2a2d3a', display: 'flex', justifyContent: 'flex-end' }}>
          <Link
            href={`/camera/${incident.camera_id}`}
            style={{ color: '#3b82f6', fontSize: 12, textDecoration: 'none', display: 'flex', alignItems: 'center', gap: 4 }}
          >
            <MapPin size={12} />
            View camera history →
          </Link>
        </div>
      </td>
    </tr>
  )
}

export default function IncidentsPage() {
  const supabase = createClient()
  const [incidents, setIncidents] = useState<Incident[]>([])
  const [loading, setLoading] = useState(true)
  const [expandedId, setExpandedId] = useState<string | null>(null)
  const [sortField, setSortField] = useState<SortField>('created_at')
  const [sortDir, setSortDir] = useState<SortDir>('desc')
  const [search, setSearch] = useState('')
  const [severityFilters, setSeverityFilters] = useState<Set<Severity>>(new Set())
  const [typeFilters, setTypeFilters] = useState<Set<string>>(new Set())
  const [dateRange, setDateRange] = useState<DateRange>({
    label: 'Last 7 days',
    from: subDays(new Date(), 7),
    to: new Date(),
  })
  const [showFilters, setShowFilters] = useState(false)
  const [cameras, setCameras] = useState<string[]>([])
  const [cameraFilter, setCameraFilter] = useState<string | null>(null)

  const loadIncidents = useCallback(async () => {
    setLoading(true)
    const { data, error } = await supabase
      .from('incidents')
      .select('*')
      .eq('incident_detected', true)
      .gte('created_at', dateRange.from.toISOString())
      .lte('created_at', dateRange.to.toISOString())
      .order('created_at', { ascending: false })
      .limit(5000)

    if (!error && data) {
      const rows = data as Incident[]
      setIncidents(rows)
      const cams = [...new Set(rows.map(r => r.camera_name))].sort()
      setCameras(cams)
    }
    setLoading(false)
  }, [dateRange])

  useEffect(() => { loadIncidents() }, [loadIncidents])

  function toggleSort(field: SortField) {
    if (sortField === field) {
      setSortDir(d => d === 'asc' ? 'desc' : 'asc')
    } else {
      setSortField(field)
      setSortDir('desc')
    }
  }

  function toggleSeverity(s: Severity) {
    setSeverityFilters(prev => {
      const next = new Set(prev)
      next.has(s) ? next.delete(s) : next.add(s)
      return next
    })
  }

  function toggleType(t: string) {
    setTypeFilters(prev => {
      const next = new Set(prev)
      next.has(t) ? next.delete(t) : next.add(t)
      return next
    })
  }

  const filtered = useMemo(() => {
    let rows = incidents

    if (severityFilters.size > 0) {
      rows = rows.filter(i => severityFilters.has(i.severity))
    }

    if (typeFilters.size > 0) {
      rows = rows.filter(i =>
        (i.incidents ?? []).some(inc => typeFilters.has(inc.type))
      )
    }

    if (cameraFilter) {
      rows = rows.filter(i => i.camera_name === cameraFilter)
    }

    if (search.trim()) {
      const q = search.toLowerCase()
      rows = rows.filter(i =>
        i.camera_name.toLowerCase().includes(q) ||
        (i.scene_summary ?? '').toLowerCase().includes(q) ||
        (i.incidents ?? []).some(inc => inc.type.toLowerCase().includes(q))
      )
    }

    return [...rows].sort((a, b) => {
      let cmp = 0
      if (sortField === 'created_at') {
        cmp = new Date(a.created_at).getTime() - new Date(b.created_at).getTime()
      } else if (sortField === 'severity') {
        cmp = SEVERITY_ORDER[a.severity] - SEVERITY_ORDER[b.severity]
      } else if (sortField === 'camera_name') {
        cmp = a.camera_name.localeCompare(b.camera_name)
      }
      return sortDir === 'asc' ? cmp : -cmp
    })
  }, [incidents, severityFilters, typeFilters, cameraFilter, search, sortField, sortDir])

  const activeFilterCount = severityFilters.size + typeFilters.size + (cameraFilter ? 1 : 0)

  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
      {/* Toolbar */}
      <div
        style={{
          padding: '12px 20px',
          borderBottom: '1px solid #2a2d3a',
          background: '#1a1d27',
          display: 'flex',
          alignItems: 'center',
          gap: 10,
          flexShrink: 0,
          flexWrap: 'wrap',
        }}
      >
        {/* Title */}
        <div style={{ marginRight: 8 }}>
          <span style={{ color: '#f0f2f8', fontSize: 14, fontWeight: 600, letterSpacing: '-0.01em' }}>Incidents</span>
          {!loading && (
            <span style={{ color: '#6b7280', fontSize: 12, marginLeft: 8 }}>
              {filtered.length.toLocaleString()} results
            </span>
          )}
        </div>

        <div style={{ flex: 1 }} />

        {/* Search */}
        <div style={{ position: 'relative' }}>
          <Search size={13} style={{ position: 'absolute', left: 10, top: '50%', transform: 'translateY(-50%)', color: '#6b7280' }} />
          <input
            value={search}
            onChange={e => setSearch(e.target.value)}
            placeholder="Search cameras, types..."
            style={{
              background: '#0f1117',
              border: '1px solid #2a2d3a',
              color: '#f0f2f8',
              padding: '7px 10px 7px 30px',
              fontSize: 13,
              width: 220,
              outline: 'none',
            }}
            onFocus={e => (e.target.style.borderColor = '#3b82f6')}
            onBlur={e => (e.target.style.borderColor = '#2a2d3a')}
          />
          {search && (
            <button
              onClick={() => setSearch('')}
              style={{ position: 'absolute', right: 8, top: '50%', transform: 'translateY(-50%)', background: 'none', border: 'none', cursor: 'pointer', color: '#6b7280', padding: 0 }}
            >
              <X size={13} />
            </button>
          )}
        </div>

        {/* Date range */}
        <DateRangePicker value={dateRange} onChange={setDateRange} />

        {/* Filters toggle */}
        <button
          onClick={() => setShowFilters(!showFilters)}
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 6,
            padding: '7px 12px',
            background: showFilters ? '#2a2d3a' : 'transparent',
            border: '1px solid #2a2d3a',
            color: activeFilterCount > 0 ? '#3b82f6' : '#6b7280',
            fontSize: 13,
            cursor: 'pointer',
            transition: 'all 0.1s',
          }}
        >
          <Filter size={13} />
          Filters
          {activeFilterCount > 0 && (
            <span style={{
              background: '#3b82f6',
              color: '#fff',
              borderRadius: 9999,
              fontSize: 10,
              fontWeight: 600,
              padding: '0 5px',
              minWidth: 16,
              textAlign: 'center',
            }}>
              {activeFilterCount}
            </span>
          )}
        </button>

        {/* Refresh */}
        <button
          onClick={loadIncidents}
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 6,
            padding: '7px 10px',
            background: 'transparent',
            border: '1px solid #2a2d3a',
            color: '#6b7280',
            fontSize: 13,
            cursor: 'pointer',
          }}
          title="Refresh"
        >
          <RefreshCw size={13} style={{ animation: loading ? 'spin 1s linear infinite' : 'none' }} />
        </button>

        {/* Export */}
        <button
          onClick={() => exportToCSV(filtered)}
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 6,
            padding: '7px 12px',
            background: '#3b82f6',
            border: 'none',
            color: '#fff',
            fontSize: 13,
            fontWeight: 500,
            cursor: 'pointer',
            transition: 'background 0.1s',
          }}
          onMouseEnter={e => (e.currentTarget.style.background = '#2563eb')}
          onMouseLeave={e => (e.currentTarget.style.background = '#3b82f6')}
        >
          <Download size={13} />
          Export CSV
        </button>
      </div>

      {/* Filter panel */}
      {showFilters && (
        <div
          style={{
            padding: '12px 20px',
            borderBottom: '1px solid #2a2d3a',
            background: '#141720',
            display: 'flex',
            gap: 24,
            flexWrap: 'wrap',
            alignItems: 'flex-start',
            flexShrink: 0,
          }}
        >
          {/* Severity */}
          <div>
            <div style={{ color: '#6b7280', fontSize: 10, fontWeight: 500, letterSpacing: '0.08em', textTransform: 'uppercase', marginBottom: 6 }}>
              Severity
            </div>
            <div style={{ display: 'flex', gap: 4 }}>
              {SEVERITY_OPTIONS.map(s => (
                <button
                  key={s}
                  onClick={() => toggleSeverity(s)}
                  style={{
                    padding: '4px 10px',
                    fontSize: 11,
                    background: severityFilters.has(s) ? '#2a2d3a' : 'transparent',
                    border: `1px solid ${severityFilters.has(s) ? '#3a3d4a' : '#2a2d3a'}`,
                    color: severityFilters.has(s) ? '#f0f2f8' : '#6b7280',
                    cursor: 'pointer',
                    textTransform: 'uppercase',
                    letterSpacing: '0.04em',
                    fontWeight: 500,
                    transition: 'all 0.1s',
                  }}
                >
                  {s}
                </button>
              ))}
            </div>
          </div>

          {/* Type */}
          <div>
            <div style={{ color: '#6b7280', fontSize: 10, fontWeight: 500, letterSpacing: '0.08em', textTransform: 'uppercase', marginBottom: 6 }}>
              Incident type
            </div>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
              {INCIDENT_TYPES.map(t => (
                <button
                  key={t}
                  onClick={() => toggleType(t)}
                  style={{
                    padding: '4px 10px',
                    fontSize: 10,
                    background: typeFilters.has(t) ? '#2a2d3a' : 'transparent',
                    border: `1px solid ${typeFilters.has(t) ? '#3b82f6' : '#2a2d3a'}`,
                    color: typeFilters.has(t) ? '#3b82f6' : '#6b7280',
                    cursor: 'pointer',
                    fontFamily: 'monospace',
                    textTransform: 'uppercase',
                    transition: 'all 0.1s',
                  }}
                >
                  {t.replace(/_/g, ' ')}
                </button>
              ))}
            </div>
          </div>

          {/* Camera */}
          <div>
            <div style={{ color: '#6b7280', fontSize: 10, fontWeight: 500, letterSpacing: '0.08em', textTransform: 'uppercase', marginBottom: 6 }}>
              Camera
            </div>
            <select
              value={cameraFilter ?? ''}
              onChange={e => setCameraFilter(e.target.value || null)}
              style={{
                background: '#0f1117',
                border: '1px solid #2a2d3a',
                color: cameraFilter ? '#f0f2f8' : '#6b7280',
                padding: '6px 10px',
                fontSize: 12,
                maxWidth: 200,
                outline: 'none',
                cursor: 'pointer',
              }}
            >
              <option value="">All cameras</option>
              {cameras.map(c => <option key={c} value={c}>{c}</option>)}
            </select>
          </div>

          {/* Clear */}
          {activeFilterCount > 0 && (
            <div style={{ alignSelf: 'flex-end' }}>
              <button
                onClick={() => {
                  setSeverityFilters(new Set())
                  setTypeFilters(new Set())
                  setCameraFilter(null)
                }}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 4,
                  padding: '6px 10px',
                  background: 'transparent',
                  border: '1px solid #2a2d3a',
                  color: '#6b7280',
                  fontSize: 12,
                  cursor: 'pointer',
                }}
              >
                <X size={11} />
                Clear all
              </button>
            </div>
          )}
        </div>
      )}

      {/* Table */}
      <div style={{ flex: 1, overflow: 'auto' }}>
        {loading && (
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: 200, color: '#6b7280', fontSize: 13, gap: 8 }}>
            <RefreshCw size={14} style={{ animation: 'spin 1s linear infinite' }} />
            Loading incidents...
          </div>
        )}

        {!loading && filtered.length === 0 && (
          <EmptyState
            icon={AlertTriangle}
            title="No incidents found"
            description="No incidents match the current filters. Try adjusting the date range or clearing filters."
          />
        )}

        {!loading && filtered.length > 0 && (
          <table className="ui-table" style={{ width: '100%', borderCollapse: 'collapse' }}>
            <thead style={{ position: 'sticky', top: 0, zIndex: 10 }}>
              <tr>
                <th style={{ width: 160 }}>
                  <button
                    onClick={() => toggleSort('created_at')}
                    style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'inherit', display: 'flex', alignItems: 'center', gap: 4, fontSize: 'inherit', fontWeight: 'inherit', letterSpacing: 'inherit', textTransform: 'inherit', padding: 0 }}
                  >
                    Time <SortIcon field="created_at" sortField={sortField} sortDir={sortDir} />
                  </button>
                </th>
                <th style={{ minWidth: 160 }}>
                  <button
                    onClick={() => toggleSort('camera_name')}
                    style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'inherit', display: 'flex', alignItems: 'center', gap: 4, fontSize: 'inherit', fontWeight: 'inherit', letterSpacing: 'inherit', textTransform: 'inherit', padding: 0 }}
                  >
                    Camera <SortIcon field="camera_name" sortField={sortField} sortDir={sortDir} />
                  </button>
                </th>
                <th>
                  <button
                    onClick={() => toggleSort('severity')}
                    style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'inherit', display: 'flex', alignItems: 'center', gap: 4, fontSize: 'inherit', fontWeight: 'inherit', letterSpacing: 'inherit', textTransform: 'inherit', padding: 0 }}
                  >
                    Severity <SortIcon field="severity" sortField={sortField} sortDir={sortDir} />
                  </button>
                </th>
                <th>Types</th>
                <th>Confidence</th>
                <th style={{ minWidth: 240 }}>Scene summary</th>
                <th style={{ width: 40 }} />
              </tr>
            </thead>
            <tbody>
              {filtered.map(inc => {
                const expanded = expandedId === inc.id
                return [
                  <tr
                    key={inc.id}
                    onClick={() => setExpandedId(expanded ? null : inc.id)}
                    style={{ cursor: 'pointer', background: expanded ? '#1a1d27' : undefined }}
                  >
                    <td style={{ fontFamily: 'monospace', fontSize: 12 }}>
                      <div style={{ color: '#f0f2f8' }}>{format(new Date(inc.created_at), 'HH:mm:ss')}</div>
                      <div style={{ color: '#6b7280', fontSize: 11 }}>{format(new Date(inc.created_at), 'dd MMM')}</div>
                    </td>
                    <td>
                      <div style={{ color: '#f0f2f8', fontSize: 12, fontWeight: 500 }}>{inc.camera_name}</div>
                      <div style={{ color: '#6b7280', fontSize: 11, fontFamily: 'monospace' }}>{inc.camera_id}</div>
                    </td>
                    <td>
                      <SeverityBadge severity={inc.severity} size="sm" pulse={inc.severity === 'critical'} />
                    </td>
                    <td>
                      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 3 }}>
                        {(inc.incidents ?? []).slice(0, 2).map((i, idx) => (
                          <IncidentTypeChip key={idx} type={i.type} size="sm" />
                        ))}
                        {(inc.incidents ?? []).length > 2 && (
                          <span style={{ color: '#6b7280', fontSize: 10 }}>+{(inc.incidents ?? []).length - 2}</span>
                        )}
                      </div>
                    </td>
                    <td>
                      <span style={{ color: '#9ca3af', fontSize: 12, fontFamily: 'monospace' }}>
                        {(inc.incidents ?? [])[0]?.confidence ?? '-'}
                      </span>
                    </td>
                    <td style={{ maxWidth: 300 }}>
                      <div style={{ color: '#9ca3af', fontSize: 12, lineHeight: 1.4, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                        {inc.scene_summary ?? 'No summary'}
                      </div>
                    </td>
                    <td>
                      <ChevronRight
                        size={14}
                        color="#6b7280"
                        style={{ transform: expanded ? 'rotate(90deg)' : 'none', transition: 'transform 0.15s' }}
                      />
                    </td>
                  </tr>,
                  expanded && <ExpandedRow key={`${inc.id}-expanded`} incident={inc} />,
                ]
              })}
            </tbody>
          </table>
        )}
      </div>

      {/* Status bar */}
      <div
        style={{
          padding: '6px 20px',
          borderTop: '1px solid #2a2d3a',
          background: '#1a1d27',
          display: 'flex',
          alignItems: 'center',
          gap: 16,
          flexShrink: 0,
        }}
      >
        <span style={{ color: '#6b7280', fontSize: 11 }}>
          {filtered.length.toLocaleString()} of {incidents.length.toLocaleString()} incidents
        </span>
        {activeFilterCount > 0 && (
          <span style={{ color: '#3b82f6', fontSize: 11 }}>
            {activeFilterCount} filter{activeFilterCount !== 1 ? 's' : ''} active
          </span>
        )}
      </div>
    </div>
  )
}
