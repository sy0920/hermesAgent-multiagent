import { useEffect, useMemo, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { fetchTeamFinal, fetchTeam, fetchTasks } from '../api/client'
import type { Team } from '../api/client'
import { useStore, expertNameById } from '../store'
import TaskDag from '../components/TaskDag'
import KanbanColumns from '../components/KanbanColumns'
import TaskDetailDrawer from '../components/TaskDetailDrawer'

export default function TeamChat() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const tasks = useStore((s) => s.tasks)
  const teamFinal = useStore((s) => s.teamFinal)
  const setTeamFinal = useStore((s) => s.setTeamFinal)
  const setTasks = useStore((s) => s.setTasks)

  const [team, setTeam] = useState<Team | null>(null)
  const [request, setRequest] = useState('')
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState<string | null>(null)
  const [selectedId, setSelectedId] = useState<string | null>(null)

  useEffect(() => {
    if (!id) return
    fetchTeam(id).then(setTeam).catch(() => setTeam(null))
  }, [id])

  // Tasks scoped to this team's members only.
  const scopedTasks = useMemo(
    () =>
      team
        ? tasks.filter((t) => team.members.includes(t.assignee ?? ''))
        : tasks,
    [tasks, team],
  )

  const doneInScope = scopedTasks.some((t) => t.status === 'done')

  // Reset the global report when switching teams so a stale report from
  // another team is never shown.
  useEffect(() => {
    setTeamFinal(null)
  }, [id, setTeamFinal])

  // Auto-fetch the final report whenever tasks change and a done task exists.
  useEffect(() => {
    if (teamFinal || !id || !doneInScope) return
    fetchTeamFinal(id)
      .then((r) => {
        if (r.report) setTeamFinal(r.report)
      })
      .catch(() => void 0)
  }, [teamFinal, id, doneInScope, setTeamFinal, tasks, scopedTasks])

  const invoke = async () => {
    if (!request.trim() || !id) return
    setBusy(true)
    setMsg(null)
    setTeamFinal(null)
    try {
      const { invokeTeam } = await import('../api/client')
      const { orchestrator_task_id } = await invokeTeam(id, request)
      setMsg(`已发起，团长已建立任务树（最终交付任务: ${orchestrator_task_id}）。任务将自动并行执行。`)
      fetchTasks().catch(() => void 0)
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
        {team && (
          <span className="tag" title="团长 · 只调度不执行">👑 {expertNameById(team.leader)}</span>
        )}
        {team?.members.map((m) => (
          <span key={m} className="tag">{expertNameById(m)}</span>
        ))}
      </div>

      <div className="card" style={{ marginBottom: 16 }}>
        <textarea
          style={{ width: '100%', minHeight: 64, padding: 10, borderRadius: 8, border: '1px solid #d0d3da', fontFamily: 'inherit' }}
          placeholder="输入团队需求，例如：全面调研 2026 年主流多智能体协作框架并输出对比报告…"
          value={request}
          onChange={(e) => setRequest(e.target.value)}
        />
        <div style={{ display: 'flex', gap: 8, marginTop: 10 }}>
          <button className="btn primary" onClick={invoke} disabled={busy}>
            {busy ? '处理中…' : '🚀 召唤专家团'}
          </button>
        </div>
        {msg && <div style={{ fontSize: 12, color: '#165dff', marginTop: 8 }}>{msg}</div>}
      </div>

      <div style={{ display: 'flex', gap: 16, alignItems: 'flex-start' }}>
        <div style={{ flex: 1 }}>
          <div className="card">
            <div className="panel-title">任务树（DAG，仅本团任务）</div>
            <TaskDag tasks={scopedTasks} onSelect={setSelectedId} />
          </div>
        </div>
        <div style={{ flex: 1 }}>
          <div className="card">
            <div className="panel-title">看板列（仅本团任务）</div>
            <KanbanColumns tasks={scopedTasks} onSelect={setSelectedId} />
          </div>
        </div>
      </div>

      {(teamFinal || doneInScope) && (
        <div className="card" style={{ marginTop: 16 }}>
          <div className="panel-title">📄 最终综合报告</div>
          <div style={{ fontSize: 13, whiteSpace: 'pre-wrap', maxHeight: 500, overflowY: 'auto' }}>
            {teamFinal ?? '（报告生成中，任务完成后自动出现）'}
          </div>
        </div>
      )}

      {selectedId && (
        <TaskDetailDrawer taskId={selectedId} onClose={() => setSelectedId(null)} />
      )}
    </div>
  )
}