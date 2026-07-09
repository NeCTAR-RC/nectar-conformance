import { describe, expect, it } from 'vitest'
import { daysUntil, fmtAge, fmtDueIn, fmtValue } from './format.js'

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
