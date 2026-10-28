import { useNavigate, useParams } from 'react-router-dom'
import { useStore } from '../store'

export default function ExpertDetail() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const experts = useStore((s) => s.experts)
  const expert = experts.find((e) => e.id === id)

  if (!expert) {
    return <p style={{ color: '#86909c' }}>专家不存在或尚未加载。可回到<a href="/experts">专家中心</a>。 </p>
  }

  return (
    <div style={{ maxWidth: 720 }}>
      <button className="btn" onClick={() => navigate('/experts')} style={{ marginBottom: 16 }}>
        ← 返回专家中心
      </button>
      <div className="card">
        <div style={{ display: 'flex', alignItems: 'center', gap: 14, marginBottom: 16 }}>
          <div
            style={{
              width: 56,
              height: 56,
              borderRadius: '50%',
              background: '#e8f3ff',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              fontSize: 28,
            }}
          >
            {expert.avatar || expert.display_name.charAt(0)}
          </div>
          <div style={{ flex: 1 }}>
            <div style={{ fontSize: 18, fontWeight: 600 }}>{expert.display_name}</div>
            <div style={{ fontSize: 13, color: '#86909c' }}>id: {expert.id}</div>
          </div>
          <span className={`status-dot status-${expert.status === 'running' ? 'doing' : 'todo'}`} title={expert.status} />
        </div>

        <Section title="人设身份">{expert.persona}</Section>
        <Section title="擅长领域">{expert.expertise}</Section>
        <Section title="工作方式">{expert.prompt}</Section>

        <div style={{ marginTop: 12 }}>
          <span className="tag">🧠 {expert.model}</span>
          {expert.skills.map((s) => (
            <span key={s} className="tag">📘 {s}</span>
          ))}
        </div>

        <div style={{ marginTop: 20 }}>
          <button className="btn primary" onClick={() => navigate(`/chat/expert/${expert.id}`)}>
            🤝 召唤专家
          </button>
        </div>
      </div>
    </div>
  )
}

function Section({ title, children }: { title: string; children: string }) {
  return (
    <div style={{ marginBottom: 14 }}>
      <div style={{ fontSize: 12, color: '#4e5969', fontWeight: 600, marginBottom: 4 }}>{title}</div>
      <div style={{ fontSize: 13, lineHeight: 1.7, whiteSpace: 'pre-wrap' }}>{children || '（未填写）'}</div>
    </div>
  )
}