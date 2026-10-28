// Lightweight Markdown rendering for chat replies.
// Supports: headings, bold, italic, inline code, fenced code blocks,
// bullet/numbered lists, and paragraphs. No external dependency.

import React from 'react'

function escapeHtml(s: string): string {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
}

function inline(text: string): string {
  let t = escapeHtml(text)
  t = t.replace(/`([^`]+)`/g, '<code>$1</code>')
  t = t.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
  t = t.replace(/__([^_]+)__/g, '<strong>$1</strong>')
  t = t.replace(/(^|[^*])\*([^*\n]+)\*/g, '$1<em>$2</em>')
  return t
}

function renderBlock(raw: string): string {
  const lines = raw.split('\n')
  const out: string[] = []
  let codeBuf: string[] = []
  let inCode = false
  let listType: 'ul' | 'ol' | null = null

  const closeList = () => {
    if (listType) {
      out.push(`</${listType}>`)
      listType = null
    }
  }

  for (const line of lines) {
    const trimmed = line.trim()
    if (trimmed.startsWith('```')) {
      if (inCode) {
        out.push('<pre><code>' + escapeHtml(codeBuf.join('\n')) + '</code></pre>')
        codeBuf = []
        inCode = false
      } else {
        closeList()
        inCode = true
      }
      continue
    }
    if (inCode) {
      codeBuf.push(line)
      continue
    }
    if (trimmed.startsWith('# ')) {
      closeList()
      out.push(`<h3>${inline(trimmed.slice(2))}</h3>`)
      continue
    }
    if (trimmed.startsWith('## ')) {
      closeList()
      out.push(`<h4>${inline(trimmed.slice(3))}</h4>`)
      continue
    }
    if (trimmed.startsWith('- ') || trimmed.startsWith('* ')) {
      if (listType !== 'ul') {
        closeList()
        listType = 'ul'
        out.push('<ul>')
      }
      out.push(`<li>${inline(trimmed.slice(2))}</li>`)
      continue
    }
    if (/^\d+[.、] /.test(trimmed)) {
      if (listType !== 'ol') {
        closeList()
        listType = 'ol'
        out.push('<ol>')
      }
      out.push(`<li>${inline(trimmed.replace(/^\d+[.、] /, ''))}</li>`)
      continue
    }
    if (trimmed === '') {
      closeList()
      continue
    }
    closeList()
    out.push(`<p>${inline(trimmed)}</p>`)
  }
  closeList()
  if (inCode) {
    out.push('<pre><code>' + escapeHtml(codeBuf.join('\n')) + '</code></pre>')
  }
  return out.join('\n')
}

export default function Markdown({ text }: { text: string }) {
  return (
    <div
      className="chat-md"
      dangerouslySetInnerHTML={{ __html: renderBlock(text) }}
    />
  )
}