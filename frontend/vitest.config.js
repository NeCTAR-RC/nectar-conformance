import { defineConfig } from 'vitest/config'

// Unit tests for the SPA. Pure modules (src/format.js etc.) run in a plain node
// environment, so no jsdom is needed. Run with `npm test` or `tox -e frontend`.
export default defineConfig({
  test: {
    environment: 'node',
    include: ['src/**/*.test.{js,jsx}'],
  },
})
