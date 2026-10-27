import { useEffect, useState } from 'react'
import type { KanbanTaskDetail } from '../api/client'
import { fetchTask, runTask, unblockTask } from '../api/client'

export default function TaskDetailDrawer({
  taskId,
  onClose,
}: {
  taskId: string
  onClose: () => void
}) {
  const [detail, setDetail] = useState<KanbanTaskDetail | null>(null)
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState<string | null>(null)

  useEffect(() => {
    setDetail(null)
    fetchTask(taskId).then(setDetail).catch((e) => setMsg((e as Error).message))
  }, [taskId])

  const handleRun = async () => {
    setBusy(true)
    setMsg(null)
    try {
      await runTask(taskId)
      setMsg('已触发执行（可在看板观察状态变化）')
    } catch (e) {
      setMsg(`执行失败: ${(e as Error).message}`)
    } finally {
      setBusy(false)
    }
  }

  const handleUnblock = async () => {
    setBusy(true)
    setMsg(null)
    try {
      await unblockTask(taskId)
      setMsg('已解封')
    } catch (e) {
      setMsg(`解封失败: ${(e as Error).message}`)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div
      style={{
        position: 'fixed',
        inset: 0,
        background: 'rgba(0,0,0,0.3)',
        zIndex: 90,
      }}
      onClick={onClose}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          position: 'absolute',
          right: 0,
          top: 0,
          bottom: 0,
          width: 420,
          background: '#fff',
          boxShadow: '-4px 0 16px rgba(0,0,0,0.1)',
          padding: 20,
          overflowY: 'auto',
        }}
      >
        <h3 style={{ marginTop: 0 }}>{detail?.title ?? taskId}</h3>
        <div style={{ fontSize: 12, color: '#86909c', marginBottom: 12 }}>
          {detail?.id} · assignee: {detail?.assignee ?? '-'} · status: {detail?.status ?? '-'}
        </div>

        <div className="card" style={{ marginBottom: 12 }}>
          <div className="panel-title">任务描述</div>
          <div style={{ fontSize: 13, whiteSpace: 'pre-wrap' }}>{detail?.body || '（无）'}</div>
        </div>

        {detail?.summary && (
          <div className="card" style={{ marginBottom: 12 }}>
            <div className="panel-title">交接摘要（summary）</div>
            <div style={{ fontSize: 13, whiteSpace: 'pre-wrap' }}>{detail.summary}</div>
          </div>
        )}

        {detail?.metadata && Object.keys(detail.metadata).length > 0 && (
          <div className="card" style={{ marginBottom: 12 }}>
            <div className="panel-title">元数据（metadata）</div>
            <pre style={{ fontSize: 12, whiteSpace: 'pre-wrap', margin: 0 }}>
              {JSON.stringify(detail.metadata, null, 2)}
            </pre>
          </div>
        )}

        <div style={{ display: 'flex', gap: 8, marginTop: 16 }}>
          <button className="btn primary" onClick={handleRun} disabled={busy}>
            运行任务
          </button>
          {detail?.status === 'blocked' && (
            <button className="btn" onClick={handleUnblock} disabled={busy}>
              解封
            </button>
          )}
        </div>
        {msg && <div style={{ fontSize: 12, color: '#165dff', marginTop: 8 }}>{msg}</div>}
      </div>
    </div>
  )
}