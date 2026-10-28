import { useEffect, useState } from 'react'
import { useStore, expertNameById } from '../store'
import { fetchHealth } from '../api/client'

export default function Settings() {
  const teams = useStore((s) => s.teams)
  const sseEnabled = useStore((s) => s.sseEnabled)
  const [health, setHealth] = useState<{ status: string } | null>(null)

  useEffect(() => {
    fetchHealth().then(setHealth).catch(() => setHealth(null))
  }, [])

  return (
    <div>
      <h2 className="panel-title">配置</h2>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: 16 }}>
        <div className="card">
          <div className="panel-title">后端服务</div>
          <table style={{ fontSize: 13, width: '100%' }}>
            <tbody>
              <tr><td style={{ color: '#86909c', padding: '4px 0' }}>后端 API</td><td>/api (localhost:8000)</td></tr>
              <tr><td style={{ color: '#86909c', padding: '4px 0' }}>健康检查</td><td>{health ? `✓ ${health.status}` : '—'}</td></tr>
              <tr><td style={{ color: '#86909c', padding: '4px 0' }}>SSE 实时连接</td><td>{sseEnabled ? '● 已连接' : '○ 未连接'}</td></tr>
              <tr><td style={{ color: '#86909c', padding: '4px 0' }}>默认模型</td><td>deepseek-chat</td></tr>
            </tbody>
          </table>
        </div>
        <div className="card">
          <div className="panel-title">专家团</div>
          {teams.map((t) => (
            <div key={t.id} style={{ marginBottom: 8, fontSize: 13 }}>
              <div style={{ fontWeight: 600 }}>{t.display_name} ({t.id})</div>
              <div style={{ color: '#86909c' }}>
                👑 主理人: {expertNameById(t.leader)} · 成员: {t.members.map((m) => expertNameById(m)).join('、')}
              </div>
            </div>
          ))}
          {teams.length === 0 && <div style={{ color: '#86909c', fontSize: 13 }}>暂无专家团，请在"专家团中心"创建。</div>}
        </div>
      </div>
      <div className="card" style={{ marginTop: 16 }}>
        <div className="panel-title">架构说明</div>
        <div style={{ fontSize: 13, lineHeight: 1.8, color: '#4e5969' }}>
          <p>本平台基于 Hermes Agent 构建：</p>
          <ul>
            <li><b>专家 = Hermes Profile</b>（SOUL.md 人设 + 独立模型 + skills 方法论）</li>
            <li><b>可视化看板 = Hermes Kanban</b>（任务树含依赖，状态 todo/doing/done/blocked）</li>
            <li><b>专家团 = orchestrator 人物 + 任务分解</b>：团长拆解 → 成员并行执行 → 综合交付</li>
          </ul>
          <p style={{ color: '#86909c' }}>
            可通过 scripts/bootstrap_experts.sh 加载预置的 4 个专家 + 1 个团长。
          </p>
        </div>
      </div>
    </div>
  )
}