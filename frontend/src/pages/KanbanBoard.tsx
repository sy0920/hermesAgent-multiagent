import { useState } from 'react'
import { useStore } from '../store'
import KanbanColumns from '../components/KanbanColumns'
import TaskDag from '../components/TaskDag'
import TaskDetailDrawer from '../components/TaskDetailDrawer'

export default function KanbanBoard() {
  const tasks = useStore((s) => s.tasks)
  const sseEnabled = useStore((s) => s.sseEnabled)
  const [view, setView] = useState<'columns' | 'dag'>('columns')
  const [selectedId, setSelectedId] = useState<string | null>(null)

  const selected = tasks.find((t) => t.id === selectedId) ?? null

  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
        <h2 className="panel-title" style={{ margin: 0 }}>
          可视化看板
          <span style={{ fontSize: 12, color: '#86909c', marginLeft: 8 }}>
            {sseEnabled ? '● 实时连接中' : '○ 等待 SSE 连接'}
          </span>
        </h2>
        <div style={{ display: 'flex', gap: 4 }}>
          <button className={`btn${view === 'columns' ? ' primary' : ''}`} onClick={() => setView('columns')}>
            列视图
          </button>
          <button className={`btn${view === 'dag' ? ' primary' : ''}`} onClick={() => setView('dag')}>
            DAG 依赖图
          </button>
        </div>
      </div>

      {view === 'columns' ? (
        <KanbanColumns tasks={tasks} onSelect={setSelectedId} />
      ) : (
        <TaskDag tasks={tasks} onSelect={setSelectedId} />
      )}

      {selected && (
        <TaskDetailDrawer taskId={selected.id} onClose={() => setSelectedId(null)} />
      )}
    </div>
  )
}