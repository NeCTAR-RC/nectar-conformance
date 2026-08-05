import { useState } from 'react'
import { useApi } from '../useApi.js'
import { Async, CheckLink, fmtValue } from '../ui.jsx'

// Requirement 4: pending changes, plus which sites are behind (and which are overdue).
// The API returns changes earliest-due first; fully adopted ones are hidden until the
// toggle reveals them, so the page leads with what still needs action.
export default function Rollout() {
  const state = useApi('/changes/rollout')
  const [showComplete, setShowComplete] = useState(false)
  return (
    <section>
      <h2>Rollout</h2>
      <p className="muted">
        Dated changes in due-date order, earliest first: who has adopted the
        new value, who has not yet, and who is past the due date.
      </p>
      <Async state={state} empty={(d) => d.rollout.length === 0}>
        {(data) => {
          const completed = data.rollout.filter((c) => c.complete).length
          const visible = showComplete
            ? data.rollout
            : data.rollout.filter((c) => !c.complete)
          return (
            <>
              {completed > 0 && (
                <label className="show-complete">
                  <input
                    type="checkbox"
                    checked={showComplete}
                    onChange={(e) => setShowComplete(e.target.checked)}
                  />
                  Show fully adopted rollouts ({completed})
                </label>
              )}
              {visible.length === 0 ? (
                <p className="muted">
                  All rollouts have been adopted by every applicable site.
                </p>
              ) : (
                <div className="rollout">
                  {visible.map((change) => (
                    <ChangeCard
                      key={`${change.check_id}:${change.tier}:${change.effective}`}
                      change={change}
                    />
                  ))}
                </div>
              )}
            </>
          )
        }}
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
        <span
          className={`badge ${change.due_passed ? 'badge-enforced' : 'badge-pending'}`}
        >
          {change.due_passed ? 'enforced' : 'pending'}
        </span>
        {change.complete && (
          <span className="badge badge-adopted">fully adopted</span>
        )}
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
