import { useEffect, useMemo, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { createSession, fetchTeam, fetchTasks } from '../api/client'
import type { Team } from '../api/client'
import { useStore, expertNameById } from '../store'
import TaskDag from '../components/TaskDag'
import KanbanColumns from '../components/KanbanColumns'
import TaskDetailDrawer from '../components/TaskDetailDrawer'
import SessionRunner from '../components/SessionRunner'

export default function TeamChat() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const tasks = useStore((s) => s.tasks)
  const setTasks = useStore((s) => s.setTasks)

  const [team, setTeam] = useState<Team | null>(null)
  const [request, setRequest] = useState('')
  const [busy, setBusy] = useState(false)
  const [sessionId, setSessionId] = useState<string | null>(null)
  const [msg, setMsg] = useState<string | null>(null)
  const [selectedId, setSelectedId] = useState<string | null>(null)

  useEffect(() => {
    if (!id) return
    fetchTeam(id).then(setTeam).catch(() => setTeam(null))
    fetchTasks().then(setTasks).catch(() => void 0)
  }, [id, setTasks])

  const scopedTasks = useMemo(
    () =>
      team
        ? tasks.filter((t) => team.members.includes(t.assignee ?? ''))
        : tasks,
    [tasks, team],
  )

  const invoke = async () => {
    if (!request.trim() || !id || busy) return
    setBusy(true)
    setMsg(null)
    try {
      const { session_id } = await createSession(id, request)
      setSessionId(session_id)
      setMsg('会话已创建：等待团长制定方案…')
    } catch (e) {
      setMsg(`发起失败: ${(e as Error).message}`)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 12 }}>
        <button className="btn" onClick={() => navigate(`/teams/${id}`)}>←</button>
        <h2 className="panel-title" style={{ margin: 0 }}>专家团：{team?.display_name ?? id}</h2>
        {team && <span className="tag" title="团长 · 只调度不执行">👑 {expertNameById(team.leader)}</span>}
        {team?.members.map((m) => (
          <span key={m} className="tag">{expertNameById(m)}</span>
        ))}
      </div>

      <div className="card" style={{ marginBottom: 16 }}>
        <textarea
          style={{ width: '100%', minHeight: 64, padding: 10, borderRadius: 8, border: '1px solid #d0d3da', fontFamily: 'inherit' }}
          placeholder="输入团队需求：团长会先出方案让你确认（Plan 确认），确认后安排专家并行执行…"
          value={request}
          onChange={(e) => setRequest(e.target.value)}
        />
        <div style={{ display: 'flex', gap: 8, marginTop: 10 }}>
          <button className="btn primary" onClick={invoke} disabled={busy}>
            {busy ? '处理中…' : '🚀 提交需求'}
          </button>
        </div>
        {msg && <div style={{ fontSize: 12, color: '#165dff', marginTop: 8 }}>{msg}</div>}
      </div>

      {sessionId && <SessionRunner sessionId={sessionId} teamId={id ?? ''} initialQuery={request} />}

      <div style={{ display: 'flex', gap: 16, alignItems: 'flex-start', marginTop: 16 }}>
        <div style={{ flex: 1 }}>
          <div className="card">
            <div className="panel-title">任务树（DAG，调度器回写 · 本团任务）</div>
            <TaskDag tasks={scopedTasks} onSelect={setSelectedId} />
          </div>
        </div>
        <div style={{ flex: 1 }}>
          <div className="card">
            <div className="panel-title">看板列（调度器回写 · 本团任务）</div>
            <KanbanColumns tasks={scopedTasks} onSelect={setSelectedId} />
          </div>
        </div>
      </div>

      {selectedId && <TaskDetailDrawer taskId={selectedId} onClose={() => setSelectedId(null)} />}
    </div>
  )
}