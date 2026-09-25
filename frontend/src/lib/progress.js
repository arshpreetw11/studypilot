import { diffDays } from './dates'

export const topicKey = (subject, topic) => `${subject}::${topic}`

export const SUBJECT_COLORS = ['#4f46e5', '#0891b2', '#d97706', '#db2777', '#059669', '#7c3aed', '#dc2626', '#65a30d']

export function subjectColor(subjects, name) {
  const i = subjects.findIndex((s) => s.name === name)
  return SUBJECT_COLORS[(i < 0 ? 0 : i) % SUBJECT_COLORS.length]
}

const allTasks = (plan) => (plan?.days || []).flatMap((d) => d.tasks.map((t) => ({ ...t, date: d.date })))

/** Estimated mastery used by the scheduler. Quiz scores win; otherwise inferred from activity. */
export function effectiveMastery(state, subject, topic) {
  const key = topicKey(subject, topic)
  if (state.mastery[key] != null) return state.mastery[key]
  const tasks = allTasks(state.plan).filter((t) => t.subject === subject && t.topic === topic && state.done[t.id])
  const learned = tasks.some((t) => t.type === 'learn')
  const reviews = tasks.filter((t) => t.type === 'review').length
  if (!learned && !reviews) return 0
  return Math.min(0.8, 0.5 + 0.1 * reviews)
}

/** Build the /api/plan request from current progress, starting at `today`. */
export function buildPlanRequest(state, today) {
  const done = state.done
  const tasks = allTasks(state.plan)
  const learnedHours = {}
  for (const t of tasks) {
    if (t.type === 'learn' && done[t.id]) {
      const k = topicKey(t.subject, t.topic)
      learnedHours[k] = (learnedHours[k] || 0) + t.hours
    }
  }
  const usedToday = tasks.filter((t) => t.date === today && done[t.id]).reduce((a, t) => a + t.hours, 0)
  return {
    start_date: today,
    hours_per_day: state.settings.hours_per_day,
    rest_weekdays: state.settings.rest_weekdays,
    first_day_used_hours: Math.min(usedToday, 14),
    subjects: state.subjects
      .filter((s) => s.exam_date && s.exam_date > today)
      .map((s) => ({
        name: s.name,
        exam_date: s.exam_date,
        topics: s.topics.map((t) => ({
          name: t.name,
          difficulty: t.difficulty,
          hours: t.hours,
          mastery: effectiveMastery(state, s.name, t.name),
          completed_hours: learnedHours[topicKey(s.name, t.name)] || 0,
        })),
      })),
  }
}

/** Keep history (and anything done today); replace the future with the new plan. */
export function mergePlan(oldPlan, newPlan, today, done) {
  if (!oldPlan) return newPlan
  const past = oldPlan.days.filter((d) => d.date < today)
  const oldToday = oldPlan.days.find((d) => d.date === today)
  const keptToday = oldToday ? oldToday.tasks.filter((t) => done[t.id]) : []
  const days = newPlan.days.map((d) => {
    if (d.date !== today) return d
    const ids = new Set(keptToday.map((t) => t.id))
    return { ...d, tasks: [...keptToday, ...d.tasks.filter((t) => !ids.has(t.id))] }
  })
  if (!days.length && oldToday) days.push({ ...oldToday, tasks: keptToday })
  return { ...newPlan, days: [...past, ...days] }
}

export function computeStats(state, today) {
  const tasks = allTasks(state.plan).filter((t) => t.type !== 'exam')
  const doneTasks = tasks.filter((t) => state.done[t.id])
  const since = state.replannedOn || ''
  const missed = tasks.filter((t) => t.date < today && t.date >= since && !state.done[t.id])
  const hoursTotal = tasks.reduce((a, t) => a + t.hours, 0)
  const hoursDone = doneTasks.reduce((a, t) => a + t.hours, 0)

  // streak: consecutive days (ending today or yesterday) where every task was done
  let streak = 0
  const days = (state.plan?.days || []).filter((d) => d.date <= today && d.tasks.some((t) => t.type !== 'exam'))
  for (let i = days.length - 1; i >= 0; i--) {
    const study = days[i].tasks.filter((t) => t.type !== 'exam')
    const complete = study.every((t) => state.done[t.id])
    if (complete) streak++
    else if (days[i].date === today) continue
    else break
  }

  const subjects = state.subjects.map((s) => {
    const st = tasks.filter((t) => t.subject === s.name)
    const planned = st.reduce((a, t) => a + t.hours, 0)
    const dn = st.filter((t) => state.done[t.id]).reduce((a, t) => a + t.hours, 0)
    const topics = s.topics.map((t) => ({ name: t.name, mastery: effectiveMastery(state, s.name, t.name), quizzed: state.mastery[topicKey(s.name, t.name)] != null }))
    return {
      name: s.name,
      exam_date: s.exam_date,
      daysLeft: s.exam_date ? diffDays(s.exam_date, today) : null,
      planned,
      done: dn,
      pct: planned ? Math.round((100 * dn) / planned) : 0,
      mastery: topics.length ? topics.reduce((a, t) => a + t.mastery, 0) / topics.length : 0,
      weak: topics.filter((t) => t.quizzed && t.mastery < 0.5).map((t) => t.name),
    }
  })

  const upcoming = subjects.filter((s) => s.daysLeft != null && s.daysLeft >= 0).sort((a, b) => a.daysLeft - b.daysLeft)
  return {
    pct: hoursTotal ? Math.round((100 * hoursDone) / hoursTotal) : 0,
    hoursDone,
    hoursTotal,
    missed,
    missedHours: missed.reduce((a, t) => a + t.hours, 0),
    streak,
    subjects,
    nextExam: upcoming[0] || null,
    weakTopics: subjects.flatMap((s) => s.weak),
  }
}
