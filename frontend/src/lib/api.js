const BASE = (import.meta.env.VITE_API_URL || '').replace(/\/$/, '')

async function request(path, options = {}) {
  const res = await fetch(`${BASE}${path}`, options)
  let data = null
  try {
    data = await res.json()
  } catch {
    /* non-JSON error page */
  }
  if (!res.ok) {
    const detail = data?.detail
    const msg = Array.isArray(detail)
      ? detail.map((d) => `${d.loc?.slice(1).join('.')}: ${d.msg}`).join('; ')
      : detail || `Request failed (${res.status})`
    throw new Error(msg)
  }
  return data
}

const post = (path, body) =>
  request(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })

export const api = {
  health: () => request('/api/health'),
  parseSyllabus: (text) => post('/api/syllabus/parse', { text }),
  uploadSyllabus: (file) => {
    const fd = new FormData()
    fd.append('file', file)
    return request('/api/syllabus/upload', { method: 'POST', body: fd })
  },
  plan: (body) => post('/api/plan', body),
  quiz: (body) => post('/api/quiz', body),
  explain: (body) => post('/api/explain', body),
  coach: (body) => post('/api/coach', body),
}
