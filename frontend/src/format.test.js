import { describe, expect, it } from 'vitest'
import {
  daysUntil,
  fmtAge,
  fmtDueIn,
  fmtStatusCounts,
  fmtValue,
  groupBySection,
  sectionStatus,
} from './format.js'

describe('fmtValue', () => {
  it('renders a dash for null/undefined', () => {
    expect(fmtValue(null)).toBe('—')
    expect(fmtValue(undefined)).toBe('—')
  })
  it('joins lists and stringifies scalars', () => {
    expect(fmtValue(['24.04', '22.04'])).toBe('24.04, 22.04')
    expect(fmtValue('3.13.7-1')).toBe('3.13.7-1')
    expect(fmtValue(3)).toBe('3')
  })
})

describe('fmtAge', () => {
  it('handles missing and very recent timestamps', () => {
    expect(fmtAge(null)).toBe('never')
    expect(fmtAge(10)).toBe('just now')
  })
  it('formats minutes, hours and days', () => {
    expect(fmtAge(600)).toBe('10 min ago')
    expect(fmtAge(7200)).toBe('2 h ago')
    expect(fmtAge(3 * 24 * 3600)).toBe('3 d ago')
  })
})

describe('daysUntil', () => {
  const now = new Date('2026-07-09T13:45:00Z')
  it('counts whole days between UTC midnights', () => {
    expect(daysUntil('2026-07-19', now)).toBe(10)
    expect(daysUntil('2026-07-09', now)).toBe(0)
  })
  it('is negative once the date has passed', () => {
    expect(daysUntil('2026-07-01', now)).toBe(-8)
  })
  it('returns null for missing or unparsable dates', () => {
    expect(daysUntil(null, now)).toBeNull()
    expect(daysUntil('not-a-date', now)).toBeNull()
  })
})

describe('groupBySection', () => {
  it('groups rows by spec_section in numeric section order', () => {
    const rows = [
      { id: 'c', spec_section: '2.2.1' },
      { id: 'a', spec_section: '2.1' },
      { id: 'd', spec_section: '2.10' },
      { id: 'b', spec_section: '2.1' },
      { id: 'e', spec_section: '2.2.1' },
    ]
    expect(groupBySection(rows)).toEqual([
      ['2.1', [rows[1], rows[3]]],
      ['2.2.1', [rows[0], rows[4]]],
      ['2.10', [rows[2]]],
    ])
  })
  it('puts rows without a section under "general", last', () => {
    const rows = [
      { id: 'a', spec_section: null },
      { id: 'b', spec_section: '2.4' },
    ]
    expect(groupBySection(rows).map(([s]) => s)).toEqual(['2.4', 'general'])
  })
  it('pins "All Nodes" first and "general" last among named sections', () => {
    const rows = [
      { id: 'a', spec_section: 'Compute Node' },
      { id: 'b' },
      { id: 'c', spec_section: 'All Nodes' },
      { id: 'd', spec_section: 'Admin Proxy' },
    ]
    expect(groupBySection(rows).map(([s]) => s)).toEqual([
      'All Nodes',
      'Admin Proxy',
      'Compute Node',
      'general',
    ])
  })
})

describe('sectionStatus', () => {
  const rows = (...statuses) => statuses.map((status) => ({ status }))
  it('rolls up with fail > unknown > pass > skip precedence', () => {
    expect(sectionStatus(rows('pass', 'fail', 'unknown'))).toBe('fail')
    expect(sectionStatus(rows('pass', 'unknown', 'skip'))).toBe('unknown')
    expect(sectionStatus(rows('pass', 'skip'))).toBe('pass')
    expect(sectionStatus(rows('skip', 'skip'))).toBe('skip')
  })
  it('treats an empty section as skip', () => {
    expect(sectionStatus([])).toBe('skip')
  })
})

describe('fmtStatusCounts', () => {
  it('tallies statuses in precedence order, omitting zeros', () => {
    const rows = [
      { status: 'pass' },
      { status: 'fail' },
      { status: 'pass' },
      { status: 'skip' },
    ]
    expect(fmtStatusCounts(rows)).toBe('1 fail · 2 pass · 1 skip')
    expect(fmtStatusCounts([{ status: 'pass' }])).toBe('1 pass')
    expect(fmtStatusCounts([])).toBe('')
  })
})

describe('fmtDueIn', () => {
  it('phrases future, today, past and unknown', () => {
    expect(fmtDueIn(11)).toBe('in 11 days')
    expect(fmtDueIn(1)).toBe('in 1 day')
    expect(fmtDueIn(0)).toBe('today')
    expect(fmtDueIn(-1)).toBe('1 day overdue')
    expect(fmtDueIn(-38)).toBe('38 days overdue')
    expect(fmtDueIn(null)).toBe('soon')
  })
})
