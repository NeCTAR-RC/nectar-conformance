import { Link, useParams } from 'react-router-dom'
import { useApi } from '../useApi.js'
import {
  Async,
  CheckLink,
  Score,
  SeverityBadge,
  StatusBadge,
  fmtValue,
} from '../ui.jsx'

// Requirement 1 (detail): the full conformance result for one site.
export default function SiteDetail() {
  const { site } = useParams()
  const state = useApi(`/sites/${site}`)
  return (
    <section>
      <p>
        <Link to="/">← Sites</Link>
      </p>
      <h2>{site}</h2>
      <Async state={state}>
        {(report) => (
          <>
            <div className="summary-row">
              <Score value={report.summary.score} />
              <span className={`badge status-${report.summary.result}`}>
                {report.summary.result}
              </span>
              <span className="muted">
                {report.summary.pass} pass · {report.summary.fail} fail ·{' '}
                {report.summary.skip} skip · {report.summary.advisory} advisory
              </span>
              <span className="muted">
                {report.conformance_version} · {report.generated_at}
              </span>
            </div>
            <table className="grid">
              <thead>
                <tr>
                  <th>Status</th>
                  <th>Severity</th>
                  <th>Check</th>
                  <th>Detail</th>
                </tr>
              </thead>
              <tbody>
                {report.results.map((rule) => (
                  <RuleRow key={rule.rule_id} rule={rule} />
                ))}
              </tbody>
            </table>
          </>
        )}
      </Async>
    </section>
  )
}

function RuleRow({ rule }) {
  const failing = rule.checks.filter((c) => c.status === 'fail')
  const advisory = rule.checks.find((c) => c.advisory)?.advisory
  return (
    <tr className={`rule-${rule.status}`}>
      <td>
        <StatusBadge status={rule.status} />
      </td>
      <td>
        <SeverityBadge severity={rule.severity} />
      </td>
      <td>
        <div>
          <CheckLink id={rule.rule_id}>{rule.title}</CheckLink>
        </div>
        <div className="muted small">{rule.rule_id}</div>
      </td>
      <td>
        {failing.slice(0, 6).map((c, i) => (
          <div key={i} className="small">
            {c.node && <span className="node">{c.node}: </span>}
            <span>{c.message}</span>
          </div>
        ))}
        {failing.length > 6 && (
          <div className="muted small">+{failing.length - 6} more</div>
        )}
        {advisory && (
          <div className="advisory small">
            upcoming: {fmtValue(advisory.upcoming_value)} (due {advisory.due}
            {advisory.days != null ? `, ${advisory.days} days` : ''})
          </div>
        )}
      </td>
    </tr>
  )
}
