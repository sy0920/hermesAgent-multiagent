import { useState } from 'react'
import { createTeam } from '../api/client'
import type { TeamCreate } from '../api/client'
import { useStore, expertNameById } from '../store'

export default function CreateTeamModal({
  onClose,
  onCreated,
}: {
  onClose: () => void
  onCreated: () => void
}) {
  const experts = useStore((s) => s.experts)
  const [form, setForm] = useState<TeamCreate>({
    display_name: '',
    description: '',
    leader: '',
    members: [],
  })
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const set = <K extends keyof TeamCreate>(key: K, value: TeamCreate[K]) =>
    setForm((f) => ({ ...f, [key]: value }))

  // Toggling a member: keep leader valid (leader must be a member).
  const toggleMember = (name: string) => {
    const has = form.members.includes(name)
    const members = has ? form.members.filter((m) => m !== name) : [...form.members, name]
    const leader = has && form.leader === name ? '' : form.leader
    setForm((f) => ({ ...f, members, leader }))
  }

  const submit = async () => {
    setError(null)
    if (!form.display_name.trim()) {
      setError('请填写团队名称')
      return
    }
    if (!form.leader) {
      setError('请选择主理人（团长）')
      return
    }
    if (form.members.length === 0) {
      setError('请至少选择一名成员')
      return
    }
    setBusy(true)
    try {
      await createTeam(form)
      onCreated()
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div
      style={{
        position: 'fixed',
        inset: 0,
        background: 'rgba(0,0,0,0.4)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        zIndex: 100,
      }}
      onClick={onClose}
    >
      <div
        className="card"
        style={{ width: 460, maxHeight: '85vh', overflowY: 'auto' }}
        onClick={(e) => e.stopPropagation()}
      >
        <h3 style={{ marginTop: 0 }}>创建专家团</h3>

        <label style={{ display: 'block', marginBottom: 12 }}>
          <div style={{ fontSize: 12, color: '#4e5969', marginBottom: 4 }}>团队名称</div>
          <input
            style={{ width: '100%', padding: 8, borderRadius: 6, border: '1px solid #d0d3da' }}
            value={form.display_name}
            placeholder="如：SQL 优化团"
            onChange={(e) => set('display_name', e.target.value)}
          />
        </label>

        <label style={{ display: 'block', marginBottom: 12 }}>
          <div style={{ fontSize: 12, color: '#4e5969', marginBottom: 4 }}>能力介绍（可选）</div>
          <textarea
            style={{ width: '100%', minHeight: 48, padding: 8, borderRadius: 6, border: '1px solid #d0d3da', fontFamily: 'inherit' }}
            value={form.description ?? ''}
            placeholder="擅长方向、协作方式等"
            onChange={(e) => set('description', e.target.value)}
          />
        </label>

        <label style={{ display: 'block', marginBottom: 12 }}>
          <div style={{ fontSize: 12, color: '#4e5969', marginBottom: 4 }}>主理人（团长，只调度不执行）</div>
          <select
            style={{ width: '100%', padding: 8, borderRadius: 6, border: '1px solid #d0d3da' }}
            value={form.leader}
            onChange={(e) => set('leader', e.target.value)}
          >
            <option value="">请选择主理人…</option>
            {experts.map((e) => (
              <option key={e.id} value={e.id} disabled={!form.members.includes(e.id)}>
                {e.display_name} {form.members.includes(e.id) ? '' : '（需先加入成员）'}
              </option>
            ))}
          </select>
        </label>

        <div style={{ marginBottom: 16 }}>
          <div style={{ fontSize: 12, color: '#4e5969', marginBottom: 4 }}>团队成员（多选）</div>
          <div style={{ maxHeight: 140, overflowY: 'auto', border: '1px solid #d0d3da', borderRadius: 6, padding: 8 }}>
            {experts.length === 0 && (
              <span style={{ fontSize: 12, color: '#86909c' }}>暂无专家，请先在专家中心创建。</span>
            )}
            {experts.map((e) => (
              <label key={e.id} style={{ display: 'block', fontSize: 13, padding: '2px 0', cursor: 'pointer' }}>
                <input type="checkbox" checked={form.members.includes(e.id)} onChange={() => toggleMember(e.id)} />
                <span style={{ marginLeft: 6 }}>{expertNameById(e.id)}</span>
              </label>
            ))}
          </div>
        </div>

        {error && <div style={{ color: '#f53f3f', fontSize: 13, marginBottom: 12 }}>{error}</div>}

        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
          <button className="btn" onClick={onClose}>取消</button>
          <button className="btn primary" onClick={submit} disabled={busy}>
            {busy ? '创建中…' : '创建专家团'}
          </button>
        </div>
      </div>
    </div>
  )
}