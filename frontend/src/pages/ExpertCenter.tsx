import { useEffect, useState } from 'react'
import type { Expert } from '../api/client'
import { deleteExpert, fetchExperts, fetchSkills } from '../api/client'
import { useStore } from '../store'
import ExpertCard from '../components/ExpertCard'
import CreateExpertModal from '../components/CreateExpertModal'

export default function ExpertCenter() {
  const experts = useStore((s) => s.experts)
  const setExperts = useStore((s) => s.setExperts)
  const [showCreate, setShowCreate] = useState(false)

  const refresh = () => fetchExperts().then(setExperts).catch(console.error)

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
          <ExpertCard key={e.id} expert={e} onDelete={handleDelete} />
        ))}
        {experts.length === 0 && (
          <p style={{ color: '#86909c' }}>暂无专家。点击右上角「+ 创建专家」开始。可先运行 scripts/bootstrap_experts.sh 加载预置 5 个专家。</p>
        )}
      </div>
      {showCreate && (
        <CreateExpertModal
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