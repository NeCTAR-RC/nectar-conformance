// Pure display formatters (no React), so they are unit-testable on their own.

// Format any value (scalars, lists) for compact display in a cell.
export function fmtValue(value) {
  if (value == null) return '—'
  if (Array.isArray(value)) return value.join(', ')
  return String(value)
}

// A human relative age from a number of seconds (or null -> "never").
export function fmtAge(seconds) {
  if (seconds == null) return 'never'
  if (seconds < 90) return 'just now'
  const mins = Math.round(seconds / 60)
  if (mins < 90) return `${mins} min ago`
  const hours = Math.round(mins / 60)
  if (hours < 48) return `${hours} h ago`
  return `${Math.round(hours / 24)} d ago`
}

// A pending change due within this many days is "due soon" (mirrors the API default).
export const DUE_SOON_DAYS = 30

// Whole days from now until an ISO date (UTC midnights), or null when unparsable.
// Countdowns baked into stored reports go stale between refreshes, so urgency is
// always recomputed from the absolute due date.
export function daysUntil(iso, now = new Date()) {
  if (!iso) return null
  const due = Date.parse(`${iso}T00:00:00Z`)
  if (Number.isNaN(due)) return null
  const today = Date.UTC(
    now.getUTCFullYear(),
    now.getUTCMonth(),
    now.getUTCDate(),
  )
  return Math.round((due - today) / 86400000)
}

// Group rows by their spec_section into [section, rows[]] entries. "All Nodes"
// applies to every machine so it leads; rows without a section land in
// "general", which trails; the rest sort by name (numeric per dotted segment,
// so a "2.10" follows a "2.9").
export function groupBySection(rows) {
  const groups = new Map()
  for (const row of rows) {
    const section = row.spec_section || 'general'
    if (!groups.has(section)) groups.set(section, [])
    groups.get(section).push(row)
  }
  return [...groups.entries()].sort(([a], [b]) => compareSections(a, b))
}

function sectionRank(section) {
  const s = section.toLowerCase()
  if (s === 'all nodes') return 0
  if (s === 'general') return 2
  return 1
}

function compareSections(a, b) {
  const rank = sectionRank(a) - sectionRank(b)
  if (rank !== 0) return rank
  const as = a.split('.')
  const bs = b.split('.')
  for (let i = 0; i < Math.max(as.length, bs.length); i++) {
    if (as[i] === undefined) return -1
    if (bs[i] === undefined) return 1
    const an = Number(as[i])
    const bn = Number(bs[i])
    if (!Number.isNaN(an) && !Number.isNaN(bn)) {
      if (an !== bn) return an - bn
    } else if (as[i] !== bs[i]) {
      return as[i] < bs[i] ? -1 : 1
    }
  }
  return 0
}

// A human phrase for a day countdown (negative = past due, null = date unknown).
export function fmtDueIn(days) {
  if (days == null) return 'soon'
  if (days === 0) return 'today'
  if (days < 0) return `${-days} day${days === -1 ? '' : 's'} overdue`
  return `in ${days} day${days === 1 ? '' : 's'}`
}
