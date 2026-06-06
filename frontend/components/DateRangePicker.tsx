'use client'

import { useState } from 'react'
import { ChevronDown, Calendar } from 'lucide-react'
import { subDays, startOfDay, endOfDay, format } from 'date-fns'

export type DateRange = {
  label: string
  from: Date
  to: Date
}

const PRESETS = [
  { label: 'Today', getDates: () => ({ from: startOfDay(new Date()), to: new Date() }) },
  { label: 'Last 7 days', getDates: () => ({ from: subDays(new Date(), 7), to: new Date() }) },
  { label: 'Last 30 days', getDates: () => ({ from: subDays(new Date(), 30), to: new Date() }) },
]

interface Props {
  value: DateRange
  onChange: (range: DateRange) => void
}

export default function DateRangePicker({ value, onChange }: Props) {
  const [open, setOpen] = useState(false)

  return (
    <div className="relative">
      <button
        onClick={() => setOpen(!open)}
        className="flex items-center gap-2"
        style={{
          background: '#1a1d27',
          border: '1px solid #2a2d3a',
          color: '#f0f2f8',
          padding: '7px 12px',
          fontSize: 13,
          cursor: 'pointer',
          transition: 'border-color 0.15s',
          whiteSpace: 'nowrap',
        }}
        onMouseEnter={e => (e.currentTarget.style.borderColor = '#3a3d4a')}
        onMouseLeave={e => (e.currentTarget.style.borderColor = '#2a2d3a')}
      >
        <Calendar size={13} color="#6b7280" />
        <span>{value.label}</span>
        <ChevronDown size={13} color="#6b7280" style={{ transform: open ? 'rotate(180deg)' : 'none', transition: 'transform 0.15s' }} />
      </button>

      {open && (
        <div
          className="absolute top-full left-0 mt-1 z-50"
          style={{
            background: '#1a1d27',
            border: '1px solid #2a2d3a',
            minWidth: 160,
            boxShadow: '0 8px 32px rgba(0,0,0,0.5)',
          }}
        >
          {PRESETS.map(preset => {
            const active = value.label === preset.label
            return (
              <button
                key={preset.label}
                onClick={() => {
                  const { from, to } = preset.getDates()
                  onChange({ label: preset.label, from, to })
                  setOpen(false)
                }}
                style={{
                  display: 'block',
                  width: '100%',
                  padding: '9px 14px',
                  textAlign: 'left',
                  fontSize: 13,
                  color: active ? '#f0f2f8' : '#9ca3af',
                  background: active ? '#2a2d3a' : 'transparent',
                  border: 'none',
                  cursor: 'pointer',
                  transition: 'background 0.1s',
                }}
                onMouseEnter={e => { if (!active) (e.currentTarget as HTMLButtonElement).style.background = '#1f2330' }}
                onMouseLeave={e => { if (!active) (e.currentTarget as HTMLButtonElement).style.background = 'transparent' }}
              >
                {preset.label}
              </button>
            )
          })}
        </div>
      )}

      {/* Click outside to close */}
      {open && (
        <div
          className="fixed inset-0 z-40"
          onClick={() => setOpen(false)}
        />
      )}
    </div>
  )
}
