import { useEffect, useState } from 'react'
import type { ExpertCreate, Skill } from '../api/client'
import { createExpert, fetchSkills } from '../api/client'

const MODELS = ['deepseek-chat', 'deepseek-reasoner']

export default function CreateExpertModal({
  onClose,
  onCreated,
}: {
  onClose: () => void
  onCreated: () => void
}) {
  const [skills, setSkills] = useState<Skill[]>([])
  const [form, setForm] = useState<ExpertCreate>({
    display_name: '',
    persona: '',
    expertise: '',
    prompt: '',
    model: 'deepseek-chat',
    skills: [],
  })
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    fetchSkills().then(setSkills).catch(() => setSkills([]))
  }, [])

  const set = <K extends keyof ExpertCreate>(key: K, value: ExpertCreate[K]) =>
    setForm((f) => ({ ...f, [key]: value }))

  const toggleSkill = (name: string) => {
    const list = form.skills ?? []
    set(
      'skills',
      list.includes(name) ? list.filter((s) => s !== name) : [...list, name],
    )
  }

  const submit = async () => {
    setError(null)
    if (!form.display_name.trim() || !form.persona.trim() || !form.expertise.trim() || !form.prompt.trim()) {
      setError('请填写：显示名称、人设身份、擅长领域、提示词')
      return
    }
    setBusy(true)
    try {
      await createExpert(form)
      onCreated()
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setBusy(false)
    }
  }

  const field = (
    label: string,
    key: 'display_name' | 'persona' | 'expertise' | 'prompt',
    placeholder: string,
    textarea?: boolean,
  ) => (
    <label style={{ display: 'block', marginBottom: 12 }}>
      <div style={{ fontSize: 12, color: '#4e5969', marginBottom: 4 }}>{label}</div>
      {textarea ? (
        <textarea
          style={{ width: '100%', minHeight: 64, padding: 8, borderRadius: 6, border: '1px solid #d0d3da', fontFamily: 'inherit' }}
          value={form[key]}
          placeholder={placeholder}
          onChange={(e) => set(key, e.target.value)}
        />
      ) : (
        <input
          style={{ width: '100%', padding: '8px', borderRadius: 6, border: '1px solid #d0d3da' }}
          value={form[key]}
          placeholder={placeholder}
          onChange={(e) => set(key, e.target.value)}
        />
      )}
    </label>
  )

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
        style={{ width: 480, maxHeight: '85vh', overflowY: 'auto' }}
        onClick={(e) => e.stopPropagation()}
      >
        <h3 style={{ marginTop: 0 }}>创建专家</h3>
        {field('显示名称（如：文档评审官）', 'display_name', '短角色名，便于识别和召唤')}
        {field('人设身份（是谁 + 背景）', 'persona', '有 10 年经验的后端工程师，熟悉 Go 与 Java', true)}
        {field('擅长领域（做什么 / 不做什么）', 'expertise', '写清边界，例如：评审文档不写代码', true)}
        {field('提示词（工作流程 / 输出格式 / 约束）', 'prompt', '写工作流程、输出格式与约束', true)}

        <div style={{ marginBottom: 12 }}>
          <div style={{ fontSize: 12, color: '#4e5969', marginBottom: 4 }}>模型</div>
          <select
            style={{ width: '100%', padding: 8, borderRadius: 6, border: '1px solid #d0d3da' }}
            value={form.model}
            onChange={(e) => set('model', e.target.value)}
          >
            {MODELS.map((m) => (
              <option key={m} value={m}>{m}</option>
            ))}
          </select>
        </div>

        <div style={{ marginBottom: 16 }}>
          <div style={{ fontSize: 12, color: '#4e5969', marginBottom: 4 }}>内置技能（方法论 Skill）</div>
          <div style={{ maxHeight: 120, overflowY: 'auto', border: '1px solid #d0d3da', borderRadius: 6, padding: 8 }}>
            {skills.length === 0 && <span style={{ fontSize: 12, color: '#86909c' }}>暂无可用技能列表</span>}
            {skills.map((s) => (
              <label key={s.name} style={{ display: 'block', fontSize: 13, padding: '2px 0', cursor: 'pointer' }}>
                <input type="checkbox" checked={(form.skills ?? []).includes(s.name)} onChange={() => toggleSkill(s.name)} />
                <span style={{ marginLeft: 6 }}>{s.name}</span>
                {s.description && <span style={{ color: '#86909c', fontSize: 12, marginLeft: 6 }}>— {s.description}</span>}
              </label>
            ))}
          </div>
        </div>

        {error && <div style={{ color: '#f53f3f', fontSize: 13, marginBottom: 12 }}>{error}</div>}

        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
          <button className="btn" onClick={onClose}>取消</button>
          <button className="btn primary" onClick={submit} disabled={busy}>
            {busy ? '创建中…' : '创建专家'}
          </button>
        </div>
      </div>
    </div>
  )
}