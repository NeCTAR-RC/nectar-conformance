import { Link } from 'react-router-dom'
import { useApi } from '../useApi.js'
import {
  Async,
  CheckLink,
  DUE_SOON_DAYS,
  Score,
  fmtDueIn,
  fmtValue,
} from '../ui.jsx'

// One outstanding rollout's status for this site: a colored dot, the check, and how
// urgent it is. `days` comes from the API, computed at request time, so it is fresh.
function RolloutLine({ change, kind }) {
  const status =
    kind === 'overdue'
      ? { cls: 'overdue', text: fmtDueIn(change.days) }
      : change.days != null && change.days <= DUE_SOON_DAYS
        ? { cls: 'due-soon', text: `due ${fmtDueIn(change.days)}` }
        : { cls: 'pending', text: `due ${fmtDueIn(change.days)}` }
  return (
    <div
      className="small roll-line"
      title={`${change.check_id} → ${fmtValue(change.target)} (due ${change.due})`}
    >
      <span className={`dot dot-${status.cls}`} />
      <CheckLink id={change.check_id} />{' '}
      <span className={kind === 'overdue' ? 'roll-overdue' : 'muted'}>
        {status.text}
      </span>
    </div>
  )
}

// Requirement: each rollout this site still has to act on — overdue screams,
// due-soon warns. Adopted changes need no action, so they are not listed; a site
// that has adopted every in-flight change reads "up to date".
function RolloutCell({ rollout }) {
  if (!rollout) return <span className="muted">—</span>
  const lines = [
    ...rollout.overdue.map((c) => [c, 'overdue']),
    ...rollout.pending.map((c) => [c, 'pending']),
  ]
  if (lines.length === 0) {
    return (
      <span className="muted small">
        {rollout.counts.adopted > 0 ? 'up to date' : 'no rollouts'}
      </span>
    )
  }
  return lines.map(([change, kind]) => (
    <RolloutLine
      key={`${change.check_id}:${change.due}`}
      change={change}
      kind={kind}
    />
  ))
}

// Requirement 1: list each site (for this instance's tier) with its conformance result.
export default function Sites() {
  const state = useApi('/sites')
  return (
    <section>
      <h2>Sites</h2>
      <Async state={state} empty={(d) => d.sites.length === 0}>
        {(data) => (
          <table className="grid">
            <thead>
              <tr>
                <th>Site</th>
                <th>Result</th>
                <th>Score</th>
                <th>Pass / Fail / Skip</th>
                <th>Rollouts</th>
                <th>Version</th>
              </tr>
            </thead>
            <tbody>
              {data.sites.map((s) => (
                <tr key={s.site}>
                  <td>
                    <Link to={`/sites/${s.site}`}>{s.site}</Link>
                  </td>
                  <td>
                    {s.summary && (
                      <span className={`badge status-${s.summary.result}`}>
                        {s.summary.result}
                      </span>
                    )}
                    {s.error && (
                      <span className="badge status-unknown" title={s.error}>
                        {s.summary ? 'stale' : 'error'}
                      </span>
                    )}
                  </td>
                  <td>{s.summary ? <Score value={s.summary.score} /> : '—'}</td>
                  <td>
                    {s.summary
                      ? `${s.summary.pass} / ${s.summary.fail} / ${s.summary.skip}`
                      : '—'}
                  </td>
                  <td>
                    <RolloutCell rollout={s.rollout} />
                  </td>
                  <td className="muted">{s.conformance_version || '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Async>
    </section>
  )
}
