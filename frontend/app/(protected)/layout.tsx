import Nav from '@/components/Nav'

export default function ProtectedLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100vh', overflow: 'hidden' }}>
      <Nav />
      <main style={{ flex: 1, overflow: 'auto', background: '#0f1117' }}>
        {children}
      </main>
    </div>
  )
}
