import { useCallback, useEffect, useState } from 'react'
import { api } from './lib/api'
import { todayISO } from './lib/dates'
import { buildPlanRequest, mergePlan, topicKey } from './lib/progress'
import Setup from './components/Setup'
import Dashboard from './components/Dashboard'
import './styles.css'

const STORE_KEY = 'studypilot:v1'

const EMPTY = {
  subjects: [],
  settings: { hours_per_day: 4, rest_weekdays: [6] },
  plan: null,
  done: {},
  mastery: {},
  quizLog: [],
  demoDate: null,
  replannedOn: null, // undone tasks before this date were carried forward by a replan
}

function load() {
  try {
    const raw = localStorage.getItem(STORE_KEY)
    return raw ? { ...EMPTY, ...JSON.parse(raw) } : EMPTY
  } catch {
    return EMPTY
  }
}

export default function App() {
  const [state, setState] = useState(load)
  const [view, setView] = useState(() => (load().plan ? 'dashboard' : 'setup'))
  const [health, setHealth] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  const today = state.demoDate || todayISO()

  useEffect(() => {
    try {
      localStorage.setItem(STORE_KEY, JSON.stringify(state))
    } catch {
      /* storage unavailable (private mode) - app still works in memory */
    }
  }, [state])

  useEffect(() => {
    api.health().then(setHealth).catch(() => setHealth({ status: 'down', ai: false }))
  }, [])

  const generate = useCallback(async (subjects, settings) => {
    setBusy(true)
    setError('')
    try {
      // quiz-based mastery survives a syllabus edit; the calendar starts fresh
      const fresh = { ...EMPTY, subjects, settings, demoDate: state.demoDate, mastery: state.mastery, quizLog: state.quizLog }
      const plan = await api.plan(buildPlanRequest(fresh, today))
      setState({ ...fresh, plan, replannedOn: today })
      setView('dashboard')
    } catch (e) {
      setError(e.message)
    } finally {
      setBusy(false)
    }
  }, [state.demoDate, state.mastery, state.quizLog, today])

  const replan = useCallback(async (override) => {
    const s = override || state
    setBusy(true)
    setError('')
    try {
      const plan = await api.plan(buildPlanRequest(s, today))
      setState({ ...s, plan: mergePlan(s.plan, plan, today, s.done), replannedOn: today })
      return true
    } catch (e) {
      setError(e.message)
      return false
    } finally {
      setBusy(false)
    }
  }, [state, today])

  const toggleDone = (id) =>
    setState((s) => {
      const done = { ...s.done }
      if (done[id]) delete done[id]
      else done[id] = true
      return { ...s, done }
    })

  const recordQuiz = (subject, topic, score) => {
    const key = topicKey(subject, topic)
    const prev = state.mastery[key]
    const mastery = prev == null ? score : Math.round((0.4 * prev + 0.6 * score) * 100) / 100
    const next = {
      ...state,
      mastery: { ...state.mastery, [key]: mastery },
      quizLog: [...state.quizLog, { subject, topic, score, date: today }],
    }
    setState(next)
    return next
  }

  const setDemoDate = (d) => setState((s) => ({ ...s, demoDate: d }))

  const reset = () => {
    if (!window.confirm('Delete your plan and progress on this device?')) return
    setState(EMPTY)
    setView('setup')
  }

  return (
    <div className="app">
      <header className="topbar">
        <button className="brand" onClick={() => state.plan && setView('dashboard')}>
          <span className="brand-mark" aria-hidden>
            <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round"><path d="M3 11l18-8-8 18-2-8-8-2z" /></svg>
          </span>
          StudyPilot
        </button>
        <div className="topbar-right">
          <span className={`ai-badge ${health?.ai ? 'on' : ''}`} title={health?.model || 'Running offline heuristics'}>
            <span className="dot" /> {health == null ? 'Connecting…' : health.status === 'down' ? 'API offline' : health.ai ? 'Gemini AI' : 'Offline mode'}
          </span>
          {state.plan && view === 'dashboard' && (
            <button className="btn ghost sm" onClick={() => setView('setup')}>Edit syllabus</button>
          )}
          {state.plan && (
            <button className="btn ghost sm" onClick={reset}>Reset</button>
          )}
        </div>
      </header>

      {error && (
        <div className="toast error" role="alert">
          {error}
          <button onClick={() => setError('')} aria-label="Dismiss">×</button>
        </div>
      )}

      <main>
        {view === 'setup' ? (
          <Setup
            initialSubjects={state.subjects}
            initialSettings={state.settings}
            today={today}
            busy={busy}
            onError={setError}
            onGenerate={generate}
            hasPlan={!!state.plan}
          />
        ) : (
          <Dashboard
            state={state}
            today={today}
            busy={busy}
            onToggle={toggleDone}
            onReplan={replan}
            onQuizResult={recordQuiz}
            onDemoDate={setDemoDate}
            onError={setError}
          />
        )}
      </main>
    </div>
  )
}
