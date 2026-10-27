import { useEffect, useState } from 'react'
import {
  fetchTeamFinal,
  invokeTeam,
  runTask,
} from '../api/client'
import { useStore } from '../store'
import TaskDag from '../components/TaskDag'
import KanbanColumns from '../components/KanbanColumns'

export default function ExpertTeam() {
  const teams = useStore((s) => s.teams)
  const tasks = useStore((s) => s.tasks)
  const teamFinal = useStore((s) => s.teamFinal)
  const setTeamFinal = useStore((s) => s.setTeamFinal)

  const [request, setRequest] = useState('')
  const [busy, setBusy] = useState(false)
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [msg, setMsg] = useState<string | null>(null)
  const [executed, setExecuted] = useState<string[]>([])

  const team = teams[0]

  useEffect(() => {
    if (teamFinal) return
    fetchTeamFinal(team?.id ?? 'research').then((r) => {
      if (r.report) setTeamFinal(r.report)
    }).catch(() => void 0)
  }, [team, teamFinal, setTeamFinal])

  const invoke = async () => {
    if (!request.trim()) return
    setBusy(true)
    setMsg(null)
    setTeamFinal(null)
    setExecuted([])
    try {
      if (!team) throw new Error('无专家团配置')
      const { orchestrator_task_id } = await invokeTeam(team.id, request)
      setMsg(`已发起，团长任务: ${orchestrator_task_id}。等候团长拆解后在看板执行。`)
    } catch (e) {
      setMsg(`发起失败: ${(e as Error).message}`)
    } finally {
      setBusy(false)
    }
  }

  const runAllPending = async () => {
    const pendings = tasks.filter(
      (t) => t.status !== 'done' && !t.status.startsWith('block') && !executed.includes(t.id),
    )
    if (pendings.length === 0) {
      setMsg('没有待执行任务（或都已触发）')
      return
    }
    setBusy(true)
    try {
      for (const t of pendings) {
        await runTask(t.id)
        setExecuted((prev) => [...prev, t.id])
      }
      setMsg(`已触发 ${pendings.length} 个任务执行`)
    } catch (e) {
      setMsg(`触发失败: ${(e as Error).message}`)
    } finally {
      setBusy(false)
    }
  }

  const doneTask = tasks.find((t) => t.status === 'done' && t.title.includes('综合'))
  const finalReady = teamFinal != null

  return (
    <div>
      <h2 className="panel-title">专家团：{team?.display_name ?? '全栈研究团'}</h2>

      <div className="card" style={{ marginBottom: 16 }}>
        <div style={{ fontSize: 13, color: '#4e5969', marginBottom: 8 }}>
          团长会自主拆解任务、分配给成员（researcher-a / researcher-b / reviewer / writer）并在看板建立依赖任务树。
        </div>
        <textarea
          style={{ width: '100%', minHeight: 80, padding: 10, borderRadius: 8, border: '1px solid #d0d3da', fontFamily: 'inherit' }}
          placeholder="输入你的研究/分析需求，例如：全面调研 2026 年主流多智能体协作框架并输出对比报告…"
          value={request}
          onChange={(e) => setRequest(e.target.value)}
        />
        <div style={{ display: 'flex', gap: 8, marginTop: 10 }}>
          <button className="btn primary" onClick={invoke} disabled={busy}>
            {busy ? '处理中…' : '🚀 召唤专家团'}
          </button>
          <button className="btn" onClick={runAllPending} disabled={busy}>
            ▶ 逐个执行待办任务
          </button>
        </div>
        {msg && <div style={{ fontSize: 12, color: '#165dff', marginTop: 8 }}>{msg}</div>}
      </div>

      <div style={{ display: 'flex', gap: 16 }}>
        <div style={{ flex: 1 }}>
          <div className="card">
            <div className="panel-title">任务树（DAG）</div>
            <TaskDag tasks={tasks} onSelect={setSelectedId} />
          </div>
        </div>
        <div style={{ flex: 1 }}>
          <div className="card">
            <div className="panel-title">看板列</div>
            <KanbanColumns tasks={tasks} onSelect={setSelectedId} />
          </div>
        </div>
      </div>

      {(finalReady || doneTask) && (
        <div className="card" style={{ marginTop: 16 }}>
          <div className="panel-title">📄 最终综合报告</div>
          <div style={{ fontSize: 13, whiteSpace: 'pre-wrap', maxHeight: 500, overflowY: 'auto' }}>
            {teamFinal ?? '（报告生成中，任务全部完成后刷新）'}
          </div>
        </div>
      )}
    </div>
  )
}