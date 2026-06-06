const TYPE_COLORS: Record<string, { bg: string; text: string }> = {
  NEAR_MISS: { bg: 'rgba(239,68,68,0.15)', text: '#fca5a5' },
  RED_LIGHT_VIOLATION: { bg: 'rgba(234,179,8,0.15)', text: '#fde047' },
  WRONG_WAY: { bg: 'rgba(239,68,68,0.2)', text: '#ef4444' },
  DANGEROUS_OVERTAKE: { bg: 'rgba(249,115,22,0.15)', text: '#fdba74' },
  PEDESTRIAN_IN_ROAD: { bg: 'rgba(168,85,247,0.15)', text: '#d8b4fe' },
  VEHICLE_STOPPED_DANGEROUSLY: { bg: 'rgba(249,115,22,0.1)', text: '#fb923c' },
  AGGRESSIVE_DRIVING: { bg: 'rgba(239,68,68,0.15)', text: '#f87171' },
  CYCLIST_RISK: { bg: 'rgba(34,197,94,0.15)', text: '#86efac' },
}

const TYPE_SHORT: Record<string, string> = {
  NEAR_MISS: 'Near Miss',
  RED_LIGHT_VIOLATION: 'Red Light',
  WRONG_WAY: 'Wrong Way',
  DANGEROUS_OVERTAKE: 'Overtake',
  PEDESTRIAN_IN_ROAD: 'Pedestrian',
  VEHICLE_STOPPED_DANGEROUSLY: 'Stopped',
  AGGRESSIVE_DRIVING: 'Aggressive',
  CYCLIST_RISK: 'Cyclist',
}

interface Props {
  type: string
  size?: 'sm' | 'md'
}

export default function IncidentTypeChip({ type, size = 'md' }: Props) {
  const colors = TYPE_COLORS[type] ?? { bg: 'rgba(107,114,128,0.15)', text: '#9ca3af' }
  const label = TYPE_SHORT[type] ?? type.replace(/_/g, ' ').toLowerCase()

  return (
    <span
      style={{
        background: colors.bg,
        color: colors.text,
        fontSize: size === 'sm' ? 10 : 11,
        padding: size === 'sm' ? '2px 6px' : '3px 8px',
        fontWeight: 500,
        letterSpacing: '0.04em',
        whiteSpace: 'nowrap',
        textTransform: 'uppercase',
        fontFamily: 'monospace',
      }}
    >
      {label}
    </span>
  )
}
