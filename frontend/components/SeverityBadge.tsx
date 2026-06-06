import { Severity, SEVERITY_BG, SEVERITY_COLORS } from '@/lib/types'

interface Props {
  severity: Severity
  size?: 'sm' | 'md'
  pulse?: boolean
}

const SEVERITY_LABELS: Record<Severity, string> = {
  none: 'Clear',
  low: 'Low',
  medium: 'Medium',
  high: 'High',
  critical: 'Critical',
}

export default function SeverityBadge({ severity, size = 'md', pulse = false }: Props) {
  const isCritical = severity === 'critical'
  const dotColor = SEVERITY_COLORS[severity]

  return (
    <span
      className={`inline-flex items-center gap-1.5 border font-mono ${SEVERITY_BG[severity]} ${isCritical && pulse ? 'severity-critical' : ''}`}
      style={{
        fontSize: size === 'sm' ? 10 : 11,
        padding: size === 'sm' ? '2px 6px' : '3px 8px',
        letterSpacing: '0.06em',
        textTransform: 'uppercase',
        fontWeight: 500,
      }}
    >
      <span
        className="inline-block rounded-full"
        style={{ width: size === 'sm' ? 5 : 6, height: size === 'sm' ? 5 : 6, background: dotColor, flexShrink: 0 }}
      />
      {SEVERITY_LABELS[severity]}
    </span>
  )
}
