import type { KanbanTask } from '../api/client'
import { expertNameById } from '../store'

const COLUMNS = [
  { key: 'todo', label: '待办' },
  { key: 'doing', label: '执行中' },
  { key: 'done', label: '已完成' },
  { key: 'blocked', label: '阻塞' },
]

function columnOf(status: string): string {
  if (status === 'ready') return 'doing'
  return status
}

export default function KanbanColumns({
  tasks,
  onSelect,
}: {
  tasks: KanbanTask[]
  onSelect: (id: string) => void
}) {
  const byColumn = (key: string) =>
    tasks.filter((t) => columnOf(t.status) === key)

  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 12 }}>
      {COLUMNS.map((col) => {
        const items = byColumn(col.key)
        return (
          <div key={col.key} className="card" style={{ minHeight: 200, padding: 12 }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10 }}>
              <span style={{ fontWeight: 600, fontSize: 13 }}>
                <span className={`status-dot status-${col.key}`} />
                {col.label}
              </span>
              <span style={{ fontSize: 12, color: '#86909c' }}>{items.length}</span>
            </div>
            {items.map((t) => (
              <div
                key={t.id}
                onClick={() => onSelect(t.id)}
                style={{
                  background: '#fafbfc',
                  border: '1px solid #e5e6eb',
                  borderRadius: 8,
                  padding: 10,
                  marginBottom: 8,
                  cursor: 'pointer',
                }}
              >
                <div style={{ fontSize: 13, lineHeight: 1.4 }}>{t.title}</div>
                <div style={{ display: 'flex', alignItems: 'center', marginTop: 6 }}>
                  <span className="tag">{expertNameById(t.assignee)}</span>
                  <span style={{ fontSize: 11, color: '#86909c', marginLeft: 'auto' }}>{t.id}</span>
                </div>
              </div>
            ))}
            {items.length === 0 && (
              <div style={{ color: '#c9cdd4', fontSize: 12, textAlign: 'center', padding: 20 }}>空</div>
            )}
          </div>
        )
      })}
    </div>
  )
}