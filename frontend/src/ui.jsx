// Small shared presentational helpers used across views.
import { Link } from 'react-router-dom'
// Re-export the pure formatters so views can keep importing them from here.
export {
  DUE_SOON_DAYS,
  daysUntil,
  fmtAge,
  fmtDueIn,
  fmtValue,
  groupBySection,
} from './format.js'

// A link to the per-check detail page (status of this check at every site).
export function CheckLink({ id, children }) {
  return <Link to={`/checks/${id}`}>{children ?? id}</Link>
}

export function Loading() {
  return <p className="muted">Loading…</p>
}

export function ErrorBox({ message }) {
  return <p className="error-box">Error: {message}</p>
}

// Render the loading / error / empty / ready states of a useApi() result uniformly.
export function Async({ state, empty, children }) {
  if (state.loading) return <Loading />
  if (state.error) return <ErrorBox message={state.error} />
  if (empty && empty(state.data)) return <p className="muted">Nothing to show.</p>
  return children(state.data)
}

export function StatusBadge({ status }) {
  return <span className={`badge status-${status}`}>{status}</span>
}

export function Score({ value }) {
  if (value == null) return <span className="muted">—</span>
  const pct = Math.round(value * 100)
  const cls = pct === 100 ? 'good' : pct >= 80 ? 'warn' : 'bad'
  return <span className={`score score-${cls}`}>{pct}%</span>
}
