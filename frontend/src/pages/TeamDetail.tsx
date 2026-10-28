import { useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { fetchTeam } from '../api/client'
import type { Team } from '../api/client'
import { useStore, expertNameById } from '../store'

export default function TeamDetail() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const cached = useStore((s) => s.teams.find((t) => t.id === id))
  const [team, setTeam] = useState<Team | null>(cached ?? null)
  const [notFound, setNotFound] = useState(false)

  useEffect(() => {
    if (cached) {
      setTeam(cached)
      return
    }
    if (!id) return
    fetchTeam(id)
      .then(setTeam)
      .catch(() => setNotFound(true))
  }, [id, cached])

  if (notFound) {
    return <p style={{ color: '#86909c' }}>专家团不存在。返回<a href="/teams">专家团中心</a>。 </p>
  }
  if (!team) {
    return <p style={{ color: '#86909c' }}>加载中…</p>
  }

  return (
    <div style={{ maxWidth: 720 }}>
      <button className="btn" onClick={() => navigate('/teams')} style={{ marginBottom: 16 }}>
        ← 返回专家团中心
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
            {team.avatar}
          </div>
          <div style={{ flex: 1 }}>
            <div style={{ fontSize: 18, fontWeight: 600 }}>{team.display_name}</div>
            <div style={{ fontSize: 13, color: '#86909c' }}>id: {team.id}</div>
          </div>
        </div>

        {team.description && (
          <div style={{ marginBottom: 14 }}>
            <div style={{ fontSize: 12, color: '#4e5969', fontWeight: 600, marginBottom: 4 }}>能力介绍</div>
            <div style={{ fontSize: 13, lineHeight: 1.7 }}>{team.description}</div>
          </div>
        )}

        <div style={{ marginBottom: 14 }}>
          <div style={{ fontSize: 12, color: '#4e5969', fontWeight: 600, marginBottom: 6 }}>👑 主理人（团长，只调度）</div>
          <div style={{ fontSize: 14, fontWeight: 500 }}>{expertNameById(team.leader)}</div>
        </div>

        <div>
          <div style={{ fontSize: 12, color: '#4e5969', fontWeight: 600, marginBottom: 6 }}>团队成员</div>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
            {team.members.map((m) => (
              <span key={m} className="tag" style={{ fontSize: 13, padding: '4px 10px' }}>
                {expertNameById(m)}
              </span>
            ))}
          </div>
        </div>

        <div style={{ marginTop: 24 }}>
          <button className="btn primary" onClick={() => navigate(`/chat/team/${team.id}`)}>
            🚀 召唤专家团
          </button>
        </div>
      </div>
    </div>
  )
}