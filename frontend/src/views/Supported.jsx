import { useApi } from '../useApi.js'
import {
  Async,
  CheckLink,
  DUE_SOON_DAYS,
  daysUntil,
  fmtDueIn,
  fmtOption,
  groupBySection,
} from '../ui.jsx'

// What each node type may run today: every value the engine accepts for each
// check, grouped by node type (the check's spec section). Every value shown is
// accepted now. One dropped by a pending change is "ending"; one added by a
// pending change is "new" (it only appeared when the change was announced, and
// stays accepted once the change falls due). Urgency is recomputed from the
// absolute due date so it never goes stale in an open tab.
export default function Supported() {
  const state = useApi('/supported')
  return (
    <section>
      <h2>Supported</h2>
      <p className="muted">
        What each node type may run today. Every value listed is accepted now;
        the colour says for how long. Checks with no bound value (presence
        checks) have nothing to list here; they appear on each site's page.
      </p>
      <Legend />
      <Async state={state} empty={(d) => d.checks.length === 0}>
        {(data) => {
          const groups = groupBySection(data.checks)
          return (
            <>
              <nav className="jump" aria-label="Node types">
                {groups.map(([section]) => (
                  <a key={section} href={`#${sectionId(section)}`}>
                    {section}
                  </a>
                ))}
              </nav>
              {groups.map(([section, checks]) => (
                <div
                  key={section}
                  id={sectionId(section)}
                  className="section-group"
                >
                  <h3>{section}</h3>
                  <table className="grid">
                    <thead>
                      <tr>
                        <th>Check</th>
                        <th>Supported values</th>
                      </tr>
                    </thead>
                    <tbody>
                      {checks.map((check) => (
                        <CheckRow key={check.id} check={check} />
                      ))}
                    </tbody>
                  </table>
                </div>
              ))}
            </>
          )
        }}
      </Async>
    </section>
  )
}

// An HTML id for a node-type heading, so the jump list can link to it.
function sectionId(section) {
  return `type-${section.toLowerCase().replace(/[^a-z0-9]+/g, '-')}`
}

function CheckRow({ check }) {
  return (
    <tr>
      <td>
        <div>
          <CheckLink id={check.id}>{check.title}</CheckLink>
          {check.optional && (
            <span className="muted small"> (optional service)</span>
          )}
        </div>
        <div className="muted small">{check.id}</div>
      </td>
      <td>
        <div className="options">
          {check.options.map((option, i) => (
            <OptionChip key={i} option={option} op={check.op} />
          ))}
        </div>
      </td>
    </tr>
  )
}

// One accepted value. Only an ending value carries a date on the chip: a new
// value is accepted from the moment its change is announced, so the only date
// that matters to it is when the values it replaces stop being accepted, and
// that is already on their chips. Ending values turn from amber to red once
// their end date is within the usual due-soon window.
function OptionChip({ option, op }) {
  const days = daysUntil(option.due)
  const urgent =
    option.status === 'ending' && days != null && days <= DUE_SOON_DAYS
  const cls = `opt opt-${option.status}${urgent ? ' opt-urgent' : ''}`
  return (
    <span className={cls} title={describeOption(option, days)}>
      {fmtOption(option.value, op)}
      {option.status === 'ending' && (
        <span className="opt-when">until {option.due}</span>
      )}
      {option.status === 'new' && <span className="opt-when">new</span>}
    </span>
  )
}

function describeOption(option, days) {
  if (option.status === 'ending') {
    return `Accepted until ${option.due} (${fmtDueIn(days)}); unsupported on and from that date`
  }
  if (option.status === 'new') {
    return `Accepted now; added by a change that falls due ${option.due} (${fmtDueIn(days)}) and stays accepted after it`
  }
  return 'Accepted now, with no change scheduled'
}

function Legend() {
  return (
    <div className="legend">
      <span>
        <span className="opt opt-current">value</span> accepted, nothing
        scheduled
      </span>
      <span>
        <span className="opt opt-ending">
          value <span className="opt-when">until date</span>
        </span>{' '}
        still accepted; unsupported on and from that date
      </span>
      <span>
        <span className="opt opt-ending opt-urgent">
          value <span className="opt-when">until date</span>
        </span>{' '}
        ends within {DUE_SOON_DAYS} days
      </span>
      <span>
        <span className="opt opt-new">
          value <span className="opt-when">new</span>
        </span>{' '}
        accepted now; newly added by a pending change
      </span>
    </div>
  )
}
