import { useCallback, useEffect, useRef, useState } from 'react'
import type { SessionView } from '../api/client'
import {
  confirmPlan,
  fetchSession,
  resumeSession,
} from '../api/client'
import { expertNameById } from '../store'

const STATUS_LABEL: Record<string, string> = {
  submitting: '提交中',
  planning: '团长制定方案中',
  waiting_confirm: '等待你确认方案',
  running: '执行中',
  aggregating: '团长聚合复审中',
  finished: '已完成',
  resuming: '新一轮规划中',
  error: '出错',
}

export default function SessionRunner({
  sessionId,
  teamId,
  initialQuery,
}: {
  sessionId: string
  teamId: string
  initialQuery: string
}) {
  const [session, setSession] = useState<SessionView | null>(null)
  const [polling, setPolling] = useState(true)
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const refresh = useCallback(async () => {
    try {
      const s = await fetchSession(sessionId)
      setSession(s)
      if (['finished', 'error'].includes(s.status)) {
        setPolling(false)
        if (timerRef.current) clearInterval(timerRef.current)
      }
    } catch {
      /* keep polling */
    }
  }, [sessionId])

  useEffect(() => {
    refresh()
    timerRef.current = setInterval(() => {
      if (polling) refresh()
    }, 2500)
    return () => {
      if (timerRef.current) clearInterval(timerRef.current)
    }
  }, [polling, refresh])

  if (!session) {
    return <p style={{ color: '#86909c' }}>加载会话…</p>
  }

  const plan = parsePlan(session.plan_json)

  return (
    <div className="card" style={{ marginTop: 16 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 8 }}>
        <span className="panel-title" style={{ margin: 0 }}>📋 专家团会话</span>
        <span className={`status-dot status-${session.status === 'finished' ? 'done' : session.status === 'error' ? 'blocked' : 'doing'}`} />
        <span style={{ fontSize: 13, color: '#4e5969' }}>
          {STATUS_LABEL[session.status] ?? session.status} · 第 {session.round_no} 轮
        </span>
      </div>

      {session.status === 'waiting_confirm' && plan && (
        <PlanCard
          summary={plan.summary}
          subtasks={plan.subtasks.map((st) => st.title)}
          experts={plan.subtasks.map((st) => st.expert_id)}
          onConfirm={(decision) =>
            confirmPlan(session.session_id, decision).then(refresh)
          }
        />
      )}

      {(session.status === 'running' ||
        session.status === 'aggregating' ||
        session.status === 'resuming') && (
        <SubtaskProgress subtasks={session.subtasks} status={session.status} />
      )}

      {session.status === 'finished' && session.final_report && (
        <div style={{ marginTop: 12 }}>
          <div className="panel-title">📄 最终综合报告（第 {session.round_no} 轮）</div>
          <div
            className="chat-md"
            style={{ whiteSpace: 'pre-wrap', maxHeight: 400, overflowY: 'auto' }}
          >
            {session.final_report}
          </div>
        </div>
      )}

      {session.status === 'finished' && (
        <ResumeBar
          onResume={(fb) => resumeSession(session.session_id, fb).then(() => {
            setPolling(true)
            refresh()
          })}
        />
      )}

      {session.status === 'error' && (
        <p style={{ color: '#f53f3f' }}>团长规划失败，可重新提交需求，或稍后重试。</p>
      )}
    </div>
  )
}

function parsePlan(planJson: string) {
  if (!planJson) return null
  try {
    const obj = JSON.parse(planJson)
    if (obj && Array.isArray(obj.subtasks)) {
      return obj as { summary: string; subtasks: Array<{ title: string; expert_id: string }> }
    }
  } catch {
    /* ignore */
  }
  return null
}

function PlanCard({
  summary,
  subtasks,
  experts,
  onConfirm,
}: {
  summary: string
  subtasks: string[]
  experts: string[]
  onConfirm: (d: 'confirm' | 'regenerate' | 'edit') => void
}) {
  return (
    <div style={{ marginTop: 8 }}>
      <div className="panel-title">团长方案（待确认）</div>
      <div style={{ fontSize: 13, marginBottom: 8 }}>{summary}</div>
      <ul style={{ fontSize: 13, margin: '0 0 12px', paddingLeft: 20 }}>
        {subtasks.map((t, i) => (
          <li key={i}>
            {t} <span className="tag">👤 {expertNameById(experts[i])}</span>
          </li>
        ))}
      </ul>
      <div style={{ display: 'flex', gap: 8 }}>
        <button className="btn primary" onClick={() => onConfirm('confirm')}>
          ✅ 确认执行
        </button>
        <button className="btn" onClick={() => onConfirm('regenerate')}>
          🔄 重新生成
        </button>
        <button className="btn" onClick={() => onConfirm('edit')}>
          ✏️ 编辑需求
        </button>
      </div>
    </div>
  )
}

function SubtaskProgress({
  subtasks,
  status,
}: {
  subtasks: SessionView['subtasks']
  status: string
}) {
  const stColor: Record<string, string> = {
    pending: '#c9cdd4',
    running: '#165dff',
    success: '#00b42a',
    failed: '#f53f3f',
  }
  return (
    <div style={{ marginTop: 8 }}>
      <div className="panel-title">执行进度（{status === 'resuming' ? '新一轮' : `第 ${subtasks?.[0]?.round_no ?? 1} 轮`}）</div>
      {(!subtasks || subtasks.length === 0) && (
        <p style={{ color: '#86909c', fontSize: 13 }}>子任务准备中…</p>
      )}
      {subtasks?.map((st) => (
        <div
          key={st.subtask_id}
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 8,
            padding: '6px 4px',
            fontSize: 13,
            borderBottom: '1px solid #f2f3f5',
          }}
        >
          <span className="status-dot" style={{ background: stColor[st.status] ?? '#c9cdd4' }} />
          <span style={{ flex: 1 }}>{st.title}</span>
          <span className="tag">{expertNameById(st.expert_id)}</span>
          <span style={{ fontSize: 12, color: '#86909c' }}>{st.status}</span>
        </div>
      ))}
    </div>
  )
}

function ResumeBar({ onResume }: { onResume: (fb: string) => void }) {
  const [fb, setFb] = useState('')
  return (
    <div style={{ marginTop: 12, display: 'flex', gap: 8 }}>
      <input
        style={{ flex: 1, padding: 8, borderRadius: 6, border: '1px solid #d0d3da' }}
        placeholder="对这个结果不满意？输入补充意见，团长将在此基础上规划新一轮…"
        value={fb}
        onChange={(e) => setFb(e.target.value)}
      />
      <button
        className="btn"
        disabled={!fb.trim()}
        onClick={() => fb.trim() && onResume(fb.trim())}
      >
        继续对话（新一轮）
      </button>
    </div>
  )
}