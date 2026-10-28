import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { fetchTeams } from '../api/client'
import { useStore, expertNameById } from '../store'
import CreateTeamModal from '../components/CreateTeamModal'

export default function TeamCenter() {
  const teams = useStore((s) => s.teams)
  const setTeams = useStore((s) => s.setTeams)
  const [showCreate, setShowCreate] = useState(false)
  const navigate = useNavigate()

  const refresh = () => fetchTeams().then(setTeams).catch(console.error)

  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
        <h2 className="panel-title" style={{ margin: 0 }}>专家团中心</h2>
        <button className="btn primary" onClick={() => setShowCreate(true)}>
          + 创建专家团
        </button>
      </div>

      {teams.length === 0 ? (
        <div className="card" style={{ textAlign: 'center', padding: '60px 20px' }}>
          <div style={{ fontSize: 40, marginBottom: 12 }}>🧩</div>
          <p style={{ color: '#4e5969' }}>
            还没有专家团。创建一个团队：选择主理人（团长）与成员，团长会负责拆解任务、安排协作。
          </p>
          <button className="btn primary" onClick={() => setShowCreate(true)}>
            创建第一个专家团
          </button>
        </div>
      ) : (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: 16 }}>
          {teams.map((t) => (
            <div
              key={t.id}
              className="card"
              onClick={() => navigate(`/teams/${t.id}`)}
              style={{ cursor: 'pointer' }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 10 }}>
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
                  {t.avatar}
                </div>
                <div style={{ fontWeight: 600, fontSize: 14 }}>{t.display_name}</div>
              </div>
              {t.description && (
                <div style={{ fontSize: 12, color: '#4e5969', minHeight: 32, marginBottom: 8 }}>
                  {t.description}
                </div>
              )}
              <div style={{ fontSize: 12, color: '#86909c' }}>
                👑 主理人：{expertNameById(t.leader)}
              </div>
              <div style={{ fontSize: 12, color: '#86909c', marginTop: 4 }}>
                成员: {t.members.map((m) => expertNameById(m)).join('、')}
              </div>
            </div>
          ))}
        </div>
      )}

      {showCreate && (
        <CreateTeamModal
          onClose={() => setShowCreate(false)}
          onCreated={() => {
            setShowCreate(false)
            refresh()
          }}
        />
      )}
    </div>
  )
}