import { useApi } from '../useApi.js'
import { Async, CheckLink, fmtValue } from '../ui.jsx'

// Requirement 3: list all changes, when they are due, with history (grouped per check).
export default function Changes() {
  const state = useApi('/changes')
  return (
    <section>
      <h2>Changes</h2>
      <p className="muted">
        Checks with a scheduled (dated) change, each showing its full directive
        history and due dates.
      </p>
      <Async state={state} empty={(d) => d.changes.length === 0}>
        {(data) => {
          // Only show a check's section if it has at least one dated (due) directive.
          const sections = Object.entries(groupByCheck(data.changes)).filter(
            ([, entries]) => entries.some((e) => e.due),
          )
          if (sections.length === 0) {
            return <p className="muted">No changes with a due date.</p>
          }
          return (
            <div className="timeline">
              {sections.map(([checkId, entries]) => (
                <div key={checkId} className="timeline-group">
                  <h3>
                    <CheckLink id={checkId} />
                  </h3>
                  <table className="grid">
                    <thead>
                      <tr>
                        <th>Effective</th>
                        <th>Due</th>
                        <th>Tier</th>
                        <th>Value</th>
                        <th>Note</th>
                      </tr>
                    </thead>
                    <tbody>
                      {entries.map((e, i) => (
                        <tr key={i}>
                          <td>{e.effective}</td>
                          <td>{e.due || <span className="muted">—</span>}</td>
                          <td>
                            <span className={`badge tier-${e.tier}`}>
                              {e.tier}
                            </span>
                          </td>
                          <td>{fmtValue(e.value)}</td>
                          <td className="muted small">{e.note || ''}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ))}
            </div>
          )
        }}
      </Async>
    </section>
  )
}

function groupByCheck(changes) {
  const out = {}
  for (const change of changes) {
    ;(out[change.check_id] ||= []).push(change)
  }
  return out
}
