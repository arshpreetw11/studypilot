import { useEffect, useState } from 'react'
import { marked } from 'marked'
import DOMPurify from 'dompurify'
import { api } from '../lib/api'

const render = (md) => DOMPurify.sanitize(marked.parse(md || ''))

export default function TutorDrawer({ subject, topic, mastery, onClose, onQuiz }) {
  const [thread, setThread] = useState([])
  const [loading, setLoading] = useState(true)
  const [q, setQ] = useState('')

  const ask = async (question) => {
    setLoading(true)
    if (question) setThread((t) => [...t, { role: 'user', text: question }])
    try {
      const r = await api.explain({ subject, topic, mastery, question: question || null })
      setThread((t) => [...t, { role: 'ai', text: r.markdown, source: r.source }])
    } catch (e) {
      setThread((t) => [...t, { role: 'ai', text: `**Couldn't reach the tutor:** ${e.message}` }])
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    api
      .explain({ subject, topic, mastery, question: null })
      .then((r) => !cancelled && setThread([{ role: 'ai', text: r.markdown, source: r.source }]))
      .catch((e) => !cancelled && setThread([{ role: 'ai', text: `**Couldn't reach the tutor:** ${e.message}` }]))
      .finally(() => !cancelled && setLoading(false))
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [subject, topic])

  useEffect(() => {
    const onKey = (e) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  const submit = (e) => {
    e.preventDefault()
    if (!q.trim() || loading) return
    ask(q.trim())
    setQ('')
  }

  return (
    <div className="overlay right" onClick={onClose}>
      <aside className="drawer" role="dialog" aria-modal="true" aria-label={`Tutor: ${topic}`} onClick={(e) => e.stopPropagation()}>
        <div className="modal-head">
          <div>
            <span className="eyebrow">{subject} · AI tutor</span>
            <h2>{topic}</h2>
          </div>
          <button className="icon-btn" onClick={onClose} aria-label="Close">×</button>
        </div>
        <div className="drawer-body">
          {thread.map((m, i) =>
            m.role === 'user' ? (
              <div key={i} className="bubble user">{m.text}</div>
            ) : (
              <div key={i} className="md" dangerouslySetInnerHTML={{ __html: render(m.text) }} />
            ),
          )}
          {loading && <div className="loading"><span className="spinner" /> Explaining…</div>}
        </div>
        <form className="drawer-foot" onSubmit={submit}>
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder={`Ask anything about ${topic}…`} aria-label="Ask the tutor" />
          <button className="btn primary" disabled={loading || !q.trim()}>Ask</button>
          <button type="button" className="btn" onClick={onQuiz}>Quiz me</button>
        </form>
      </aside>
    </div>
  )
}
