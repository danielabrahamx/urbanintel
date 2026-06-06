import { LucideIcon } from 'lucide-react'

interface Props {
  icon: LucideIcon
  title: string
  description: string
}

export default function EmptyState({ icon: Icon, title, description }: Props) {
  return (
    <div
      className="flex flex-col items-center justify-center py-20"
      style={{ color: '#6b7280' }}
    >
      <div
        style={{ background: '#1a1d27', border: '1px solid #2a2d3a', padding: 20, marginBottom: 16 }}
      >
        <Icon size={32} strokeWidth={1.2} color="#4b5563" />
      </div>
      <div style={{ color: '#f0f2f8', fontSize: 14, fontWeight: 500, marginBottom: 6 }}>
        {title}
      </div>
      <div style={{ fontSize: 13, maxWidth: 320, textAlign: 'center', lineHeight: 1.6 }}>
        {description}
      </div>
    </div>
  )
}
