import { Link, useParams } from 'react-router-dom'
import { useApi } from '../useApi.js'
import {
  Async,
  CheckLink,
  DUE_SOON_DAYS,
  Score,
  StatusBadge,
  daysUntil,
  fmtDueIn,
  fmtStatusCounts,
  fmtValue,
  groupBySection,
  sectionStatus,
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
            {groupBySection(report.results).map(([section, rules]) => (
              <div key={section} className="section-group">
                <h3>
                  <span
                    className={`dot dot-${sectionStatus(rules)}`}
                    title={fmtStatusCounts(rules)}
                  />
                  {section}
                </h3>
                <table className="grid">
                  <thead>
                    <tr>
                      <th>Status</th>
                      <th>Check</th>
                      <th>Detail</th>
                    </tr>
                  </thead>
                  <tbody>
                    {rules.map((rule) => (
                      <RuleRow key={rule.rule_id} rule={rule} />
                    ))}
                  </tbody>
                </table>
              </div>
            ))}
          </>
        )}
      </Async>
    </section>
  )
}

function RuleRow({ rule }) {
  const failing = rule.checks.filter((c) => c.status === 'fail')
  const advisory = rule.checks.find((c) => c.advisory)?.advisory
  // Recompute the countdown from the absolute due date: the days baked into a stored
  // report go stale between refreshes. A passing rule due soon will fail — flag it.
  const days = advisory ? (daysUntil(advisory.due) ?? advisory.days) : null
  const urgent = rule.status === 'pass' && days != null && days <= DUE_SOON_DAYS
  return (
    <tr className={`rule-${rule.status}`}>
      <td>
        <StatusBadge status={rule.status} />
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
          <div className={`advisory small${urgent ? ' advisory-urgent' : ''}`}>
            upcoming: {fmtValue(advisory.upcoming_value)} (due {advisory.due},{' '}
            {fmtDueIn(days)}){urgent && ' · will fail'}
          </div>
        )}
      </td>
    </tr>
  )
}
