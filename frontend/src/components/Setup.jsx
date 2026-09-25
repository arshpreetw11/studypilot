import { useRef, useState } from 'react'
import { api } from '../lib/api'
import { addDays, diffDays } from '../lib/dates'
import { sampleSyllabus } from '../lib/sample'
import { subjectColor } from '../lib/progress'

const WEEKDAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
const DIFF = { 1: 'Easy', 2: 'Medium', 3: 'Hard' }

export default function Setup({ initialSubjects, initialSettings, today, busy, onError, onGenerate, hasPlan }) {
  const [text, setText] = useState('')
  const [subjects, setSubjects] = useState(initialSubjects)
  const [settings, setSettings] = useState(initialSettings)
  const [parsing, setParsing] = useState(false)
  const [source, setSource] = useState(null)
  const fileRef = useRef(null)

  const handleParsed = (res) => {
    setSource(res.source)
    setSubjects(
      res.subjects.map((s, i) => ({
        name: s.name,
        exam_date: s.exam_date || addDays(today, 14 + i * 4),
        dateGuessed: !s.exam_date,
        topics: s.topics,
      })),
    )
  }

  const extract = async () => {
    if (text.trim().length < 3) return onError('Paste your syllabus first (or load the sample).')
    setParsing(true)
    try {
      handleParsed(await api.parseSyllabus(text))
    } catch (e) {
      onError(e.message)
    } finally {
      setParsing(false)
    }
  }

  const upload = async (file) => {
    if (!file) return
    setParsing(true)
    try {
      handleParsed(await api.uploadSyllabus(file))
      setText(`(Imported from ${file.name})`)
    } catch (e) {
      onError(e.message)
    } finally {
      setParsing(false)
      fileRef.current.value = ''
    }
  }

  const updSubject = (i, patch) => setSubjects((ss) => ss.map((s, j) => (j === i ? { ...s, ...patch, dateGuessed: patch.exam_date ? false : s.dateGuessed } : s)))
  const updTopic = (i, k, patch) =>
    setSubjects((ss) => ss.map((s, j) => (j === i ? { ...s, topics: s.topics.map((t, m) => (m === k ? { ...t, ...patch } : t)) } : s)))
  const delTopic = (i, k) => setSubjects((ss) => ss.map((s, j) => (j === i ? { ...s, topics: s.topics.filter((_, m) => m !== k) } : s)))
  const addTopic = (i) => setSubjects((ss) => ss.map((s, j) => (j === i ? { ...s, topics: [...s.topics, { name: '', difficulty: 2, hours: 2 }] } : s)))
  const delSubject = (i) => setSubjects((ss) => ss.filter((_, j) => j !== i))
  const addSubject = () => setSubjects((ss) => [...ss, { name: '', exam_date: addDays(today, 21), topics: [{ name: '', difficulty: 2, hours: 2 }] }])

  const toggleRest = (d) =>
    setSettings((s) => ({
      ...s,
      rest_weekdays: s.rest_weekdays.includes(d) ? s.rest_weekdays.filter((x) => x !== d) : [...s.rest_weekdays, d],
    }))

  const totalHours = subjects.reduce((a, s) => a + s.topics.reduce((b, t) => b + (Number(t.hours) || 0), 0), 0)
  const lastExam = subjects.map((s) => s.exam_date).sort().at(-1)
  const studyDays = lastExam ? Math.max(0, diffDays(lastExam, today)) * ((7 - settings.rest_weekdays.length) / 7) : 0
  const capacity = studyDays * settings.hours_per_day

  const submit = () => {
    const clean = subjects
      .map((s) => ({ ...s, name: s.name.trim(), topics: s.topics.filter((t) => t.name.trim()).map((t) => ({ name: t.name.trim(), difficulty: Number(t.difficulty), hours: Number(t.hours) || 1 })) }))
      .filter((s) => s.name && s.topics.length)
    if (!clean.length) return onError('Add at least one subject with a topic.')
    const bad = clean.find((s) => !s.exam_date || s.exam_date <= today)
    if (bad) return onError(`Set a future exam date for ${bad.name}.`)
    const names = new Set()
    for (const s of clean) {
      if (names.has(s.name)) return onError(`Two subjects are called "${s.name}". Rename one.`)
      names.add(s.name)
    }
    onGenerate(clean.map(({ dateGuessed: _d, ...s }) => s), settings)
  }

  return (
    <div className="setup">
      {!subjects.length && (
        <section className="hero">
          <p className="eyebrow">AI study planner for college exams</p>
          <h1>Paste your syllabus. Get a day‑by‑day plan that adapts to you.</h1>
          <p className="lede">
            StudyPilot reads your syllabus, estimates effort per topic, and schedules learning, spaced‑repetition reviews and
            final revision around your exam dates. Quiz yourself and the plan re‑balances toward what you haven't mastered yet.
          </p>
        </section>
      )}

      <section className="card step">
        <div className="step-head">
          <span className="step-num">1</span>
          <div>
            <h2>Add your syllabus</h2>
            <p className="muted">Paste it as‑is (units, bullets, messy PDFs copy‑pasted), or upload a PDF / TXT. Include exam dates if you know them.</p>
          </div>
        </div>
        <textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder={'Data Structures — Exam: 14 Oct\nUnit 1: Arrays, Linked Lists, Stacks\nUnit 2: Trees, Graphs\n\nDBMS — Exam: 18 Oct\n- ER Model\n- Normalization\n- SQL'}
          rows={9}
          aria-label="Syllabus text"
        />
        <div className="row gap wrap">
          <button className="btn primary" onClick={extract} disabled={parsing}>
            {parsing ? <span className="spinner" /> : <Sparkle />} {parsing ? 'Reading syllabus…' : 'Extract topics'}
          </button>
          <button className="btn" onClick={() => fileRef.current.click()} disabled={parsing}>Upload PDF / TXT</button>
          <input ref={fileRef} type="file" accept=".pdf,.txt,.md,text/plain,application/pdf" hidden onChange={(e) => upload(e.target.files[0])} />
          <button className="btn ghost" onClick={() => setText(sampleSyllabus())}>Try a sample syllabus</button>
        </div>
      </section>

      {subjects.length > 0 && (
        <section className="card step">
          <div className="step-head">
            <span className="step-num">2</span>
            <div>
              <h2>Check subjects & topics</h2>
              <p className="muted">
                {source === 'ai' ? 'Gemini estimated difficulty and study hours for each topic. ' : source === 'heuristic' ? 'Parsed offline. Adjust difficulty and hours if needed. ' : ''}
                Edit anything that looks off.
              </p>
            </div>
          </div>
          <div className="subjects-edit">
            {subjects.map((s, i) => (
              <div key={i} className="subject-edit" style={{ '--c': subjectColor(subjects, s.name) }}>
                <div className="subject-edit-head">
                  <input className="subject-name" value={s.name} placeholder="Subject name" onChange={(e) => updSubject(i, { name: e.target.value })} aria-label="Subject name" />
                  <label className="date-field">
                    Exam
                    <input type="date" value={s.exam_date || ''} min={addDays(today, 1)} onChange={(e) => updSubject(i, { exam_date: e.target.value })} />
                  </label>
                  {s.dateGuessed && <span className="pill warn" title="No date found in the syllabus">date guessed</span>}
                  <button className="icon-btn" onClick={() => delSubject(i)} aria-label={`Remove ${s.name}`} title="Remove subject">×</button>
                </div>
                <table className="topics-table">
                  <thead>
                    <tr><th>Topic</th><th>Difficulty</th><th>Hours</th><th /></tr>
                  </thead>
                  <tbody>
                    {s.topics.map((t, k) => (
                      <tr key={k}>
                        <td><input value={t.name} placeholder="Topic" onChange={(e) => updTopic(i, k, { name: e.target.value })} aria-label="Topic name" /></td>
                        <td>
                          <select value={t.difficulty} onChange={(e) => updTopic(i, k, { difficulty: Number(e.target.value) })} className={`diff d${t.difficulty}`} aria-label="Difficulty">
                            {[1, 2, 3].map((d) => <option key={d} value={d}>{DIFF[d]}</option>)}
                          </select>
                        </td>
                        <td><input type="number" min="0.5" max="20" step="0.5" value={t.hours} onChange={(e) => updTopic(i, k, { hours: e.target.value })} className="hours" aria-label="Hours" /></td>
                        <td><button className="icon-btn" onClick={() => delTopic(i, k)} aria-label="Remove topic">×</button></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                <button className="link-btn" onClick={() => addTopic(i)}>+ Add topic</button>
              </div>
            ))}
          </div>
          <button className="btn ghost sm" onClick={addSubject}>+ Add subject</button>
        </section>
      )}

      {subjects.length > 0 && (
        <section className="card step">
          <div className="step-head">
            <span className="step-num">3</span>
            <div>
              <h2>Your routine</h2>
              <p className="muted">How much can you realistically study on top of classes?</p>
            </div>
          </div>
          <div className="routine">
            <label className="slider">
              <span>Study hours per day <b>{settings.hours_per_day}h</b></span>
              <input type="range" min="1" max="10" step="0.5" value={settings.hours_per_day} onChange={(e) => setSettings((s) => ({ ...s, hours_per_day: Number(e.target.value) }))} />
            </label>
            <div>
              <span className="label">Rest days</span>
              <div className="chips">
                {WEEKDAYS.map((w, d) => (
                  <button key={w} className={`chip ${settings.rest_weekdays.includes(d) ? 'active' : ''}`} onClick={() => toggleRest(d)} aria-pressed={settings.rest_weekdays.includes(d)}>
                    {w}
                  </button>
                ))}
              </div>
            </div>
          </div>
          <div className={`capacity ${capacity < totalHours * 1.25 ? 'tight' : ''}`}>
            <b>{totalHours.toFixed(1)}h</b> of new material · about <b>{Math.floor(capacity)}h</b> of study time before your last exam
            {capacity < totalHours * 1.25 && <span> · tight! Reviews need ~25% extra. Consider more hours per day.</span>}
          </div>
          <div className="row gap wrap">
            <button className="btn primary lg" onClick={submit} disabled={busy}>
              {busy ? <span className="spinner" /> : null} Generate my study plan
            </button>
            {hasPlan && <span className="muted small">Regenerating starts a new calendar. Your quiz results are kept.</span>}
          </div>
        </section>
      )}
    </div>
  )
}

export function Sparkle() {
  return (
    <svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor" aria-hidden>
      <path d="M12 2l1.9 5.6L19.5 9.5l-5.6 1.9L12 17l-1.9-5.6L4.5 9.5l5.6-1.9L12 2zm7 12l.9 2.6 2.6.9-2.6.9L19 21l-.9-2.6-2.6-.9 2.6-.9L19 14z" />
    </svg>
  )
}
