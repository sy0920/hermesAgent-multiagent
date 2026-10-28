import { useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { expertChat } from '../api/client'
import { useStore, expertNameById } from '../store'
import Markdown from '../components/Markdown'

interface Msg {
  role: 'user' | 'assistant'
  content: string
}

export default function ExpertChat() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const [messages, setMessages] = useState<Msg[]>([])
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)
  const sessionRef = useRef<string | null>(null)
  const bottomRef = useRef<HTMLDivElement>(null)

  const name = expertNameById(id)

  const send = async () => {
    if (!input.trim() || !id || busy) return
    const text = input.trim()
    setInput('')
    setMessages((m) => [...m, { role: 'user', content: text }])
    setBusy(true)
    try {
      const resp = await expertChat(id, text, sessionRef.current)
      sessionRef.current = resp.session_id ?? sessionRef.current
      setMessages((m) => [...m, { role: 'assistant', content: resp.reply }])
      requestAnimationFrame(() => bottomRef.current?.scrollIntoView({ behavior: 'smooth' }))
    } catch (e) {
      setMessages((m) => [...m, { role: 'assistant', content: `⚠️ ${(e as Error).message}` }])
    } finally {
      setBusy(false)
    }
  }

  return (
    <div style={{ maxWidth: 760, display: 'flex', flexDirection: 'column', height: 'calc(100vh - 120px)' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 12 }}>
        <button className="btn" onClick={() => navigate(`/experts/${id}`)}>←</button>
        <h2 className="panel-title" style={{ margin: 0 }}>与「{name}」对话</h2>
      </div>

      <div
        className="card"
        style={{
          flex: 1,
          overflowY: 'auto',
          display: 'flex',
          flexDirection: 'column',
          gap: 10,
          marginBottom: 12,
        }}
      >
        {messages.length === 0 && (
          <div style={{ color: '#86909c', fontSize: 13, textAlign: 'center', padding: 40 }}>
            开始与 {name} 对话，它将按照其人设与工作方式为你解答。
          </div>
        )}
        {messages.map((m, i) => (
          <div
            key={i}
            style={{
              alignSelf: m.role === 'user' ? 'flex-end' : 'flex-start',
              maxWidth: '78%',
              padding: '10px 14px',
              borderRadius: 10,
              fontSize: 13,
              lineHeight: 1.7,
              whiteSpace: 'pre-wrap',
              background: m.role === 'user' ? '#165dff' : '#f2f3f5',
              color: m.role === 'user' ? '#fff' : '#1f2329',
            }}
          >
            <Markdown text={m.content} />
          </div>
        ))}
        <div ref={bottomRef} />
      </div>

      <div style={{ display: 'flex', gap: 8 }}>
        <textarea
          style={{ flex: 1, padding: 10, borderRadius: 8, border: '1px solid #d0d3da', fontFamily: 'inherit', minHeight: 48 }}
          placeholder="输入消息，Enter 发送（Shift+Enter 换行）"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault()
              send()
            }
          }}
        />
        <button className="btn primary" onClick={send} disabled={busy || !input.trim()}>
          {busy ? '思考中…' : '发送'}
        </button>
      </div>
    </div>
  )
}