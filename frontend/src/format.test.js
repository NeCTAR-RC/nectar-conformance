import { describe, expect, it } from 'vitest'
import { fmtAge, fmtValue } from './format.js'

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
