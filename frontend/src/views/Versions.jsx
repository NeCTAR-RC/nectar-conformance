import { useEffect, useState } from 'react'
import { useApi } from '../useApi.js'
import { Async, CheckLink, fmtValue, groupBySection } from '../ui.jsx'

// Requirement 2: list all requirements for a version (tag).
export default function Versions() {
  const versions = useApi('/versions')
  const [selected, setSelected] = useState(null)

  // Default to the most recent version once the list loads.
  useEffect(() => {
    if (!selected && versions.data?.versions?.length) {
      const all = versions.data.versions
      setSelected(all[all.length - 1].name)
    }
  }, [versions.data, selected])

  return (
    <section>
      <h2>Versions</h2>
      <Async state={versions} empty={(d) => d.versions.length === 0}>
        {(data) => (
          <div className="cols">
            <ul className="picker">
              {data.versions.map((v) => (
                <li key={v.name}>
                  <button
                    className={selected === v.name ? 'active' : ''}
                    onClick={() => setSelected(v.name)}
                  >
                    {v.name}
                    <span className="muted small"> {v.date}</span>
                  </button>
                </li>
              ))}
            </ul>
            <div className="grow">
              {selected && <Requirements tag={selected} />}
            </div>
          </div>
        )}
      </Async>
    </section>
  )
}

function Requirements({ tag }) {
  const state = useApi(`/versions/${tag}/requirements`)
  return (
    <Async state={state} empty={(d) => d.requirements.length === 0}>
      {(data) => (
        <table className="grid">
          <thead>
            <tr>
              <th>Requirement</th>
              <th>Expected</th>
              <th>Pending</th>
            </tr>
          </thead>
          {groupBySection(data.requirements).map(([section, rules]) => (
            <tbody key={section}>
              <tr className="section-row">
                <td colSpan={3}>{section}</td>
              </tr>
              {rules.map((r) => (
                <tr key={r.id}>
                  <td>
                    <div>
                      <CheckLink id={r.id}>{r.title}</CheckLink>
                    </div>
                    <div className="muted small">{r.id}</div>
                  </td>
                  <td>{fmtValue(r.expected)}</td>
                  <td>
                    {r.has_pending ? (
                      <span className="advisory small">
                        {fmtValue(r.pending_value)} (due {r.pending_due})
                      </span>
                    ) : (
                      <span className="muted">—</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          ))}
        </table>
      )}
    </Async>
  )
}
