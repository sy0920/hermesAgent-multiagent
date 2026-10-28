import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import type { Expert } from '../api/client'
import { deleteExpert, fetchExperts, fetchSkills, fetchTeams } from '../api/client'
import { useStore } from '../store'
import ExpertCard from '../components/ExpertCard'
import CreateExpertModal from '../components/CreateExpertModal'

export default function ExpertCenter() {
  const experts = useStore((s) => s.experts)
  const setExperts = useStore((s) => s.setExperts)
  const setTeams = useStore((s) => s.setTeams)
  const [showCreate, setShowCreate] = useState(false)
  const navigate = useNavigate()

  const refresh = () => fetchExperts().then(setExperts).catch(console.error)
  const refreshTeams = () => fetchTeams().then(setTeams).catch(console.error)

  useEffect(() => {
    fetchSkills().catch(() => void 0)
  }, [])

  const handleDelete = async (id: string) => {
    if (!window.confirm(`确定删除专家 ${id} 吗？`)) return
    try {
      await deleteExpert(id)
      setExperts(experts.filter((e) => e.id !== id))
    } catch (err) {
      alert(`删除失败: ${(err as Error).message}`)
    }
  }

  const handleOpen = (e: Expert) => {
    navigate(`/experts/${e.id}`)
  }

  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
        <h2 className="panel-title" style={{ margin: 0 }}>专家中心</h2>
        <button className="btn primary" onClick={() => setShowCreate(true)}>
          + 创建专家
        </button>
      </div>
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fill, minmax(260px, 1fr))',
          gap: 16,
        }}
      >
        {experts.map((e) => (
          <div key={e.id} style={{ cursor: 'pointer' }} onClick={() => handleOpen(e)}>
            <ExpertCard expert={e} onDelete={handleDelete} />
          </div>
        ))}
        {experts.length === 0 && (
          <p style={{ color: '#86909c' }}>暂无专家。点击右上角「+ 创建专家」开始。</p>
        )}
      </div>
      {showCreate && (
        <CreateExpertModal
          onClose={() => setShowCreate(false)}
          onCreated={() => {
            setShowCreate(false)
            refresh()
            refreshTeams()
          }}
        />
      )}
    </div>
  )
}