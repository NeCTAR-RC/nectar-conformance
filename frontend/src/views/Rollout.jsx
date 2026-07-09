import { Link } from 'react-router-dom'
import { useApi } from '../useApi.js'
import { Async, CheckLink, fmtValue } from '../ui.jsx'

// Requirement 4: pending changes, plus which sites are behind (and which are overdue).
export default function Rollout() {
  const state = useApi('/changes/rollout')
  const sitesState = useApi('/sites')
  return (
    <section>
      <h2>Rollout</h2>
      <p className="muted">
        Dated changes still in flight: who has adopted the new value, who has
        not yet, and who is past the due date.
      </p>
      <h3>By site</h3>
      <Async state={sitesState}>
        {(data) => <BySiteTable sites={data.sites} />}
      </Async>
      <h3>By change</h3>
      <Async state={state} empty={(d) => d.rollout.length === 0}>
        {(data) => (
          <div className="rollout">
            {data.rollout.map((change, i) => (
              <ChangeCard key={i} change={change} />
            ))}
          </div>
        )}
      </Async>
    </section>
  )
}

// The same per-check tooltip the Sites list uses on its rollout badges.
function refsTitle(refs) {
  return refs.map((r) => `${r.check_id} (due ${r.due})`).join('\n')
}

// The per-site pivot of the change cards below: which sites need to act, worst first.
function BySiteTable({ sites }) {
  const judged = sites.filter((s) => s.rollout)
  const exposed = judged
    .filter(
      (s) => s.rollout.counts.overdue + s.rollout.counts.pending > 0,
    )
    .sort(
      (a, b) =>
        b.rollout.counts.overdue - a.rollout.counts.overdue ||
        b.rollout.counts.due_soon - a.rollout.counts.due_soon ||
        a.site.localeCompare(b.site),
    )
  if (exposed.length === 0) {
    return <p className="muted">Every site is up to date.</p>
  }
  const upToDate = judged.length - exposed.length
  return (
    <>
      <table className="grid">
        <thead>
          <tr>
            <th>Site</th>
            <th>Overdue</th>
            <th>Due soon</th>
            <th>Pending</th>
            <th>Next due</th>
          </tr>
        </thead>
        <tbody>
          {exposed.map((s) => (
            <tr key={s.site}>
              <td>
                <Link to={`/sites/${s.site}`}>{s.site}</Link>
              </td>
              <td>
                {s.rollout.counts.overdue > 0 ? (
                  <span
                    className="badge sev-error"
                    title={refsTitle(s.rollout.overdue)}
                  >
                    {s.rollout.counts.overdue}
                  </span>
                ) : (
                  <span className="muted">—</span>
                )}
              </td>
              <td>
                {s.rollout.counts.due_soon > 0 ? (
                  <span
                    className="badge sev-warning"
                    title={refsTitle(s.rollout.pending)}
                  >
                    {s.rollout.counts.due_soon}
                  </span>
                ) : (
                  <span className="muted">—</span>
                )}
              </td>
              <td>{s.rollout.counts.pending}</td>
              <td className="muted">{s.rollout.next_due || '—'}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {upToDate > 0 && (
        <p className="muted small">
          {upToDate} other site{upToDate === 1 ? ' is' : 's are'} up to date.
        </p>
      )}
    </>
  )
}

function ChangeCard({ change }) {
  const overdue = change.counts.overdue > 0
  return (
    <div className={`card ${overdue ? 'card-overdue' : ''}`}>
      <div className="card-head">
        <strong>
          <CheckLink id={change.check_id} />
        </strong>
        <span className={`badge ${change.due_passed ? 'sev-error' : 'sev-warning'}`}>
          {change.due_passed ? 'enforced' : 'pending'}
        </span>
        <span className="muted">
          → {fmtValue(change.target)} (due {change.due})
        </span>
      </div>
      {change.note && <p className="muted small">{change.note}</p>}
      <div className="buckets">
        <Bucket name="overdue" sites={change.buckets.overdue} cls="bad" />
        <Bucket name="pending" sites={change.buckets.pending} cls="warn" />
        <Bucket name="adopted" sites={change.buckets.adopted} cls="good" />
        <Bucket
          name="n/a"
          sites={change.buckets.not_applicable}
          cls="muted-bucket"
        />
      </div>
    </div>
  )
}

function Bucket({ name, sites, cls }) {
  return (
    <div className={`bucket bucket-${cls}`}>
      <div className="bucket-head">
        {name} <span className="count">{sites.length}</span>
      </div>
      <ul>
        {sites.map((s) => (
          <li key={s}>{s}</li>
        ))}
      </ul>
    </div>
  )
}
