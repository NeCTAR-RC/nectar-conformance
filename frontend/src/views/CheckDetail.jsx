import { Link, useParams } from 'react-router-dom'
import { useApi } from '../useApi.js'
import { Async, StatusBadge, fmtValue } from '../ui.jsx'

// The status of one check at every site (linked to from anywhere a check is shown).
export default function CheckDetail() {
  const { checkId } = useParams()
  const state = useApi(`/checks/${checkId}`)
  return (
    <section>
      <h2>{checkId}</h2>
      <Async state={state}>
        {(data) => (
          <>
            <div className="summary-row">
              <span>{data.title}</span>
              {data.spec_section && (
                <span className="muted small">§{data.spec_section}</span>
              )}
            </div>
            {data.requirement && (
              <p className="muted">
                Required ({data.tier}): <strong>{fmtValue(data.requirement.expected)}</strong>
                {data.requirement.has_pending && (
                  <span className="advisory">
                    {' '}
                    → {fmtValue(data.requirement.pending_value)} due{' '}
                    {data.requirement.pending_due}
                  </span>
                )}
              </p>
            )}
            <table className="grid">
              <thead>
                <tr>
                  <th>Site</th>
                  <th>Status</th>
                  <th>Observed</th>
                </tr>
              </thead>
              <tbody>
                {data.sites.map((s) => (
                  <SiteRow key={s.site} site={s} />
                ))}
              </tbody>
            </table>
          </>
        )}
      </Async>
    </section>
  )
}

function SiteRow({ site }) {
  return (
    <tr className={`rule-${site.status}`}>
      <td>
        <Link to={`/sites/${site.site}`}>{site.site}</Link>
      </td>
      <td>
        {site.status === 'absent' ? (
          <span className="badge status-skip" title="not in this site's report">
            absent
          </span>
        ) : (
          <StatusBadge status={site.status} />
        )}
      </td>
      <td>
        {site.checks.length === 0 ? (
          <span className="muted">—</span>
        ) : (
          site.checks.map((c, i) => (
            <div key={i} className="small">
              {c.node && <span className="node">{c.node}: </span>}
              <span>{fmtValue(c.observed)}</span>
              {c.status === 'fail' && c.message && (
                <span className="muted"> — {c.message}</span>
              )}
            </div>
          ))
        )}
      </td>
    </tr>
  )
}
