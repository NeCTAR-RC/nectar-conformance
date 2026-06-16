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
