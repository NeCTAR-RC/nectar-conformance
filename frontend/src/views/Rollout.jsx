import { useApi } from '../useApi.js'
import { Async, CheckLink, fmtValue } from '../ui.jsx'

// Requirement 4: pending changes, plus which sites are behind (and which are overdue).
export default function Rollout() {
  const state = useApi('/changes/rollout')
  return (
    <section>
      <h2>Rollout</h2>
      <p className="muted">
        Dated changes still in flight: who has adopted the new value, who has
        not yet, and who is past the due date.
      </p>
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
