import { Link } from 'react-router-dom'
import { useApi } from '../useApi.js'
import { Async, Score, SeverityBadge } from '../ui.jsx'

// The check_ids behind a rollout count, as a plain-text tooltip.
function refsTitle(refs) {
  return refs.map((r) => `${r.check_id} (due ${r.due})`).join('\n')
}

// Requirement: surface each site's rollout exposure at a glance — overdue screams,
// due-soon warns, quiet pending stays muted. Links go to the Rollout page for detail.
function RolloutCell({ rollout }) {
  if (!rollout) return <span className="muted">—</span>
  const { counts, next_due: nextDue } = rollout
  if (counts.overdue > 0) {
    return (
      <Link to="/rollout" title={refsTitle(rollout.overdue)}>
        <span className="badge sev-error">{counts.overdue} overdue</span>
      </Link>
    )
  }
  if (counts.due_soon > 0) {
    return (
      <Link to="/rollout" title={refsTitle(rollout.pending)}>
        <span className="badge sev-warning">{counts.due_soon} due soon</span>
      </Link>
    )
  }
  if (counts.pending > 0) {
    return (
      <span className="muted small" title={refsTitle(rollout.pending)}>
        {counts.pending} pending · next {nextDue}
      </span>
    )
  }
  return <span className="muted small">up to date</span>
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
                <th>Worst</th>
                <th>Rollout</th>
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
                    <SeverityBadge severity={s.worst_severity} />
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
