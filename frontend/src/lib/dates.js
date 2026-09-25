// All dates are plain 'YYYY-MM-DD' strings in the student's local calendar.

export const todayISO = () => new Date().toLocaleDateString('en-CA')

export function addDays(iso, n) {
  const d = new Date(`${iso}T00:00:00Z`)
  d.setUTCDate(d.getUTCDate() + n)
  return d.toISOString().slice(0, 10)
}

export function diffDays(a, b) {
  return Math.round((new Date(`${a}T00:00:00Z`) - new Date(`${b}T00:00:00Z`)) / 86400000)
}

const fmt = (iso, opts) => new Date(`${iso}T00:00:00Z`).toLocaleDateString('en-IN', { timeZone: 'UTC', ...opts })

export const fmtShort = (iso) => fmt(iso, { day: 'numeric', month: 'short' })
export const fmtDay = (iso) => fmt(iso, { weekday: 'short' })
export const fmtLong = (iso) => fmt(iso, { weekday: 'long', day: 'numeric', month: 'long' })

export function relDay(iso, today) {
  const d = diffDays(iso, today)
  if (d === 0) return 'Today'
  if (d === 1) return 'Tomorrow'
  if (d === -1) return 'Yesterday'
  return d > 0 ? `in ${d} days` : `${-d} days ago`
}
