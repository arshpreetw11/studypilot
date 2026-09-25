import { useEffect, useMemo, useState } from 'react'
import { api } from '../lib/api'
import { addDays, diffDays, fmtDay, fmtLong, fmtShort, relDay, todayISO } from '../lib/dates'
import { computeStats, effectiveMastery, subjectColor } from '../lib/progress'
import QuizModal from './QuizModal'
import TutorDrawer from './TutorDrawer'
import { Sparkle } from './Setup'

const TYPE_LABEL = { learn: 'Learn', review: 'Review', revision: 'Revision', exam: 'Exam' }

export default function Dashboard({ state, today, busy, onToggle, onReplan, onQuizResult, onDemoDate, onError }) {
  const [selected, setSelected] = useState(today)
  const [quiz, setQuiz] = useState(null)
  const [tutor, setTutor] = useState(null)
  const [coach, setCoach] = useState(null)
  const [justReplanned, setJustReplanned] = useState(false)

  const stats = useMemo(() => computeStats(state, today), [state, today])
  const days = state.plan?.days || []
  const day = days.find((d) => d.date === selected)
  const color = (name) => subjectColor(state.subjects, name)

  useEffect(() => setSelected(today), [today])

  // AI coach refreshes when the day, plan or weak topics change (not on every checkbox)
  const coachKey = `${today}|${state.plan?.total_hours}|${days.length}|${stats.weakTopics.join(',')}|${stats.missed.length}`
  useEffect(() => {
    if (!state.plan) return
    let cancelled = false
    setCoach(null)
    api
      .coach({ plan: state.plan, today, completed_task_ids: Object.keys(state.done), weak_topics: stats.weakTopics })
      .then((r) => !cancelled && setCoach(r))
      .catch(() => !cancelled && setCoach({ message: 'Coach unavailable right now.', source: 'offline' }))
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [coachKey])

  const replan = async (override) => {
    const ok = await onReplan(override)
    if (ok) {
      setJustReplanned(true)
      setTimeout(() => setJustReplanned(false), 2500)
    }
    return ok
  }

  const stripDays = useMemo(() => {
    const start = days.findIndex((d) => d.date >= addDays(today, -2))
    return start < 0 ? [] : days.slice(start, start + 14)
  }, [days, today])

  const dayHours = (d) => d.tasks.filter((t) => t.type !== 'exam').reduce((a, t) => a + t.hours, 0)
  const dayDone = (d) => d.tasks.filter((t) => t.type !== 'exam' && state.done[t.id]).reduce((a, t) => a + t.hours, 0)

  return (
    <div className="dash">
      <div className="dash-main">
        {stats.missed.length > 0 && (
          <div className="banner warn">
            <div>
              <b>{stats.missed.length} task{stats.missed.length > 1 ? 's' : ''} ({stats.missedHours}h) slipped.</b> No stress: replan to spread them over the coming days.
            </div>
            <button className="btn primary sm" onClick={() => replan()} disabled={busy}>{busy ? <span className="spinner" /> : null} Replan</button>
          </div>
        )}
        {justReplanned && <div className="banner ok">Plan updated around your progress and quiz results.</div>}

        <section className="card coach">
          <div className="coach-icon"><Sparkle /></div>
          <div>
            <div className="coach-title">Your study coach <span className="src">{coach?.source === 'ai' ? 'Gemini' : coach ? 'offline' : ''}</span></div>
            {coach ? <p>{coach.message}</p> : <p className="skeleton">Thinking about your day…</p>}
          </div>
        </section>

        <section className="card">
          <div className="strip" role="tablist" aria-label="Plan days">
            {stripDays.map((d) => {
              const h = dayHours(d)
              const exam = d.tasks.find((t) => t.type === 'exam')
              const pct = h ? dayDone(d) / h : 0
              return (
                <button
                  key={d.date}
                  role="tab"
                  aria-selected={d.date === selected}
                  className={`strip-day ${d.date === selected ? 'sel' : ''} ${d.date === today ? 'today' : ''} ${d.date < today ? 'past' : ''}`}
                  onClick={() => setSelected(d.date)}
                >
                  <span className="sd-dow">{fmtDay(d.date)}</span>
                  <span className="sd-num">{d.date.slice(8)}</span>
                  {exam ? (
                    <span className="sd-exam" style={{ background: color(exam.subject) }}>Exam</span>
                  ) : d.is_rest ? (
                    <span className="sd-rest">rest</span>
                  ) : (
                    <span className="sd-bar"><i style={{ width: `${pct * 100}%` }} /></span>
                  )}
                </button>
              )
            })}
          </div>

          <div className="day-head">
            <div>
              <h2>{fmtLong(selected)}</h2>
              <span className="muted">{relDay(selected, today)}{day ? ` · ${dayDone(day)}/${dayHours(day)}h done` : ''}</span>
            </div>
            <button className="btn ghost sm" onClick={() => replan()} disabled={busy} title="Rebuild the rest of the plan from today using your progress">
              {busy ? <span className="spinner" /> : '↻'} Replan
            </button>
          </div>

          {!day || day.tasks.length === 0 ? (
            <div className="empty">{day?.is_rest ? 'Rest day. Recharge, you earned it.' : 'Nothing scheduled. A free buffer day for catching up or practice papers.'}</div>
          ) : (
            <ul className="tasks">
              {day.tasks.map((t) => {
                const isDone = !!state.done[t.id]
                const m = t.topic ? effectiveMastery(state, t.subject, t.topic) : null
                return (
                  <li key={t.id} className={`task ${t.type} ${isDone ? 'done' : ''} ${!isDone && t.type !== 'exam' && selected < today ? 'moved' : ''}`} style={{ '--c': color(t.subject) }}>
                    {t.type === 'exam' ? (
                      <span className="exam-flag">🎯</span>
                    ) : (
                      <input type="checkbox" checked={isDone} onChange={() => onToggle(t.id)} aria-label={`Mark ${t.topic || t.subject} done`} disabled={selected > today} />
                    )}
                    <div className="task-body">
                      <div className="task-title">
                        <span className={`type-pill ${t.type}`}>{TYPE_LABEL[t.type]}</span>
                        {t.topic || `${t.subject}: ${t.type === 'exam' ? 'exam' : 'full revision'}`}
                      </div>
                      <div className="task-meta">
                        <span className="subj-dot" /> {t.subject}
                        {t.hours > 0 && <> · {t.hours}h</>}
                        {t.note && <> · {t.note}</>}
                        {!isDone && t.type !== 'exam' && selected < today && <> · <b>{selected < (state.replannedOn || '') ? 'moved to later days' : 'missed'}</b></>}
                        {m != null && m > 0 && <> · mastery {Math.round(m * 100)}%</>}
                      </div>
                    </div>
                    {t.topic && (
                      <div className="task-actions">
                        <button className="btn sm ghost" onClick={() => setTutor({ subject: t.subject, topic: t.topic })}>Explain</button>
                        <button className="btn sm" onClick={() => setQuiz({ subject: t.subject, topic: t.topic })}>Quiz me</button>
                      </div>
                    )}
                  </li>
                )
              })}
            </ul>
          )}
          {selected > today && day?.tasks.length > 0 && <p className="muted small">You can tick tasks off on the day. Quiz yourself early to skip topics you already know.</p>}
        </section>

        {state.plan.warnings.length > 0 && (
          <section className="card warnings">
            <h3>Heads up</h3>
            <ul>{state.plan.warnings.map((w) => <li key={w}>{w}</li>)}</ul>
          </section>
        )}
      </div>

      <aside className="dash-side">
        <section className="card stats">
          <Ring pct={stats.pct} />
          <div className="stat-grid">
            <Stat label="Hours done" value={`${stats.hoursDone}h`} sub={`of ${stats.hoursTotal}h`} />
            <Stat label="Streak" value={`${stats.streak}🔥`} sub={stats.streak === 1 ? 'day' : 'days'} />
            <Stat
              label="Next exam"
              value={stats.nextExam ? (stats.nextExam.daysLeft === 0 ? 'Today' : `${stats.nextExam.daysLeft}d`) : '—'}
              sub={stats.nextExam?.name}
            />
          </div>
        </section>

        <section className="card">
          <h3>Subjects</h3>
          <ul className="subj-list">
            {stats.subjects.map((s) => (
              <li key={s.name} style={{ '--c': color(s.name) }}>
                <div className="subj-row">
                  <span className="subj-name"><span className="subj-dot" />{s.name}</span>
                  <span className="muted small">{s.exam_date ? `${fmtShort(s.exam_date)} · ${s.daysLeft >= 0 ? `${s.daysLeft}d` : 'done'}` : ''}</span>
                </div>
                <div className="bar"><i style={{ width: `${s.pct}%` }} /></div>
                <div className="subj-meta small muted">
                  {s.pct}% of plan · avg mastery {Math.round(s.mastery * 100)}%
                </div>
                {s.weak.length > 0 && (
                  <div className="weak small">Weak: {s.weak.join(', ')} <span className="muted">(extra reviews added)</span></div>
                )}
              </li>
            ))}
          </ul>
        </section>

        <section className="card demo">
          <h3>Demo: time travel</h3>
          <p className="muted small">Simulate days passing to see missed-task recovery and replanning.</p>
          <div className="row gap wrap">
            <button className="btn sm" onClick={() => onDemoDate(addDays(today, -1))}>← Day</button>
            <button className="btn sm" onClick={() => onDemoDate(addDays(today, 1))}>Day →</button>
            {state.demoDate && <button className="btn sm ghost" onClick={() => onDemoDate(null)}>Back to real today</button>}
          </div>
          {state.demoDate && <p className="small">Simulating <b>{fmtShort(today)}</b> ({diffDays(today, todayISO()) > 0 ? '+' : ''}{diffDays(today, todayISO())} days)</p>}
        </section>
      </aside>

      {quiz && (
        <QuizModal
          {...quiz}
          mastery={effectiveMastery(state, quiz.subject, quiz.topic)}
          onClose={() => setQuiz(null)}
          onError={onError}
          onResult={(score) => onQuizResult(quiz.subject, quiz.topic, score)}
          onReplan={async (next) => {
            const ok = await replan(next)
            if (ok) setQuiz(null)
          }}
          busy={busy}
        />
      )}
      {tutor && (
        <TutorDrawer
          {...tutor}
          mastery={effectiveMastery(state, tutor.subject, tutor.topic)}
          onClose={() => setTutor(null)}
          onQuiz={() => {
            setQuiz(tutor)
            setTutor(null)
          }}
        />
      )}
    </div>
  )
}

function Stat({ label, value, sub }) {
  return (
    <div className="stat">
      <span className="stat-label">{label}</span>
      <span className="stat-value">{value}</span>
      {sub && <span className="stat-sub">{sub}</span>}
    </div>
  )
}

function Ring({ pct }) {
  const r = 34
  const c = 2 * Math.PI * r
  return (
    <div className="ring" aria-label={`${pct}% of plan complete`}>
      <svg viewBox="0 0 80 80" width="88" height="88">
        <circle cx="40" cy="40" r={r} className="ring-bg" />
        <circle cx="40" cy="40" r={r} className="ring-fg" strokeDasharray={c} strokeDashoffset={c * (1 - pct / 100)} transform="rotate(-90 40 40)" />
      </svg>
      <div className="ring-label"><b>{pct}%</b><span>of plan</span></div>
    </div>
  )
}
