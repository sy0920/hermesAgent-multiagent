import { useMemo } from 'react'
import {
  ReactFlow,
  Background,
  Controls,
  type Edge,
  type Node,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import type { KanbanTask } from '../api/client'
import { expertNameById } from '../store'

const STATUS_COLOR: Record<string, string> = {
  todo: '#c9cdd4',
  ready: '#f7ba1e',
  doing: '#165dff',
  done: '#00b42a',
  blocked: '#f53f3f',
}

interface LayoutNode {
  task: KanbanTask
  depth: number
}

function computeDepth(tasks: KanbanTask[], id: string, memo: Map<string, number>): number {
  if (memo.has(id)) return memo.get(id)!
  const task = tasks.find((t) => t.id === id)
  if (!task || task.parents.length === 0) {
    memo.set(id, 0)
    return 0
  }
  const depth = 1 + Math.max(...task.parents.map((p) => computeDepth(tasks, p, memo)))
  memo.set(id, depth)
  return depth
}

export default function TaskDag({
  tasks,
  onSelect,
}: {
  tasks: KanbanTask[]
  onSelect: (id: string) => void
}) {
  const { nodes, edges } = useMemo(() => {
    const memo = new Map<string, number>()
    const depthOf = (id: string) => computeDepth(tasks, id, memo)
    const byDepth = new Map<number, LayoutNode[]>()
    for (const task of tasks) {
      const depth = depthOf(task.id)
      if (!byDepth.has(depth)) byDepth.set(depth, [])
      byDepth.get(depth)!.push({ task, depth })
    }
    const nodes: Node[] = []
    for (const [depth, group] of byDepth) {
      const per = (group.length - 1) * 90
      group.forEach((item, idx) => {
        nodes.push({
          id: item.task.id,
          position: { x: depth * 260, y: idx * 110 - per / 2 },
          data: {
            label: `${expertNameById(item.task.assignee)}:\n${item.task.title}`,
          },
          style: {
            border: `2px solid ${STATUS_COLOR[item.task.status] ?? '#c9cdd4'}`,
            borderRadius: 8,
            padding: 8,
            background: '#fff',
            fontSize: 12,
            maxWidth: 220,
          },
        })
      })
    }
    const edges: Edge[] = []
    for (const task of tasks) {
      for (const parent of task.parents) {
        edges.push({
          id: `${parent}-${task.id}`,
          source: parent,
          target: task.id,
          animated: task.status === 'doing',
        })
      }
    }
    return { nodes, edges }
  }, [tasks])

  return (
    <div style={{ height: 480, border: '1px solid #e5e6eb', borderRadius: 10, background: '#fff' }}>
      <ReactFlow nodes={nodes} edges={edges} fitView onNodeClick={(_, n) => onSelect(n.id)}>
        <Background />
        <Controls />
      </ReactFlow>
    </div>
  )
}