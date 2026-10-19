import { defineConfig } from '@playwright/test'

export default defineConfig({
  testDir: 'e2e',
  outputDir: 'test-results',
  // FakeRunner ticks each task every 0.5 s: one loop takes a few seconds.
  timeout: 60_000,
  retries: 0,
  use: {
    baseURL: 'http://127.0.0.1:8765',
    video: 'retain-on-failure',
    trace: 'retain-on-failure',
  },
  // hubd serves web/dist, so build first (`npm run build`). Fails if 8765 is taken: never test against a real hubd.
  webServer: {
    command: 'uv run hubd --demo',
    cwd: '..',
    url: 'http://127.0.0.1:8765/health',
    reuseExistingServer: false,
    timeout: 60_000,
  },
})
