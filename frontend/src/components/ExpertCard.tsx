import type { Expert } from '../api/client'

const STATUS_COLOR: Record<string, string> = {
  running: 'green',
  parked: 'gray',
  stopped: 'gray',
}

export default function ExpertCard({
  expert,
  onDelete,
}: {
  expert: Expert
  onDelete: (id: string) => void
}) {
  const dotColor = STATUS_COLOR[expert.status] ?? 'gray'
  return (
    <div className="card" style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
        <div
          style={{
            width: 40,
            height: 40,
            borderRadius: '50%',
            background: '#e8f3ff',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            fontSize: 20,
          }}
        >
          {expert.avatar || expert.display_name.charAt(0)}
        </div>
        <div style={{ flex: 1 }}>
          <div style={{ fontWeight: 600, fontSize: 14 }}>{expert.display_name}</div>
          <div style={{ fontSize: 12, color: '#86909c' }}>{expert.id}</div>
        </div>
        <span className="status-dot" style={{ background: dotColor }} title={expert.status} />
      </div>
      <div style={{ fontSize: 12, color: '#4e5969', minHeight: 36, lineHeight: 1.5 }}>
        {expert.expertise || expert.persona}
      </div>
      <div>
        {expert.skills.map((s) => (
          <span key={s} className="tag">📘 {s}</span>
        ))}
        <span className="tag">🧠 {expert.model}</span>
      </div>
      <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8, marginTop: 4 }}>
        <button className="btn" onClick={() => onDelete(expert.id)} style={{ fontSize: 12 }}>
          删除
        </button>
      </div>
    </div>
  )
}