import { Link } from 'react-router-dom'
import { useApi } from '../useApi.js'
import { Async, Score, SeverityBadge } from '../ui.jsx'

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
