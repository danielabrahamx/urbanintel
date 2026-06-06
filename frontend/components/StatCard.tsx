import { LucideIcon } from 'lucide-react'

interface Props {
  label: string
  value: string | number
  sub?: string
  icon?: LucideIcon
  accent?: string
  trend?: 'up' | 'down' | 'neutral'
}

export default function StatCard({ label, value, sub, icon: Icon, accent = '#3b82f6', trend }: Props) {
  return (
    <div
      style={{
        background: '#1a1d27',
        border: '1px solid #2a2d3a',
        padding: '20px 24px',
      }}
    >
      <div className="flex items-start justify-between">
        <div>
          <div
            style={{ color: '#6b7280', fontSize: 11, fontWeight: 500, letterSpacing: '0.08em', textTransform: 'uppercase', marginBottom: 8 }}
          >
            {label}
          </div>
          <div
            style={{ color: '#f0f2f8', fontSize: 28, fontWeight: 600, lineHeight: 1, letterSpacing: '-0.03em' }}
          >
            {value}
          </div>
          {sub && (
            <div style={{ color: '#6b7280', fontSize: 12, marginTop: 6 }}>
              {sub}
            </div>
          )}
        </div>
        {Icon && (
          <div
            style={{ background: `${accent}15`, border: `1px solid ${accent}30`, padding: 10 }}
          >
            <Icon size={18} color={accent} strokeWidth={1.5} />
          </div>
        )}
      </div>
    </div>
  )
}
