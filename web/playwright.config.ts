import { defineConfig } from '@playwright/test'

// HUBD_PORT: run on another port while a hubd (or another run of this suite) holds 8765.
const port = process.env.HUBD_PORT ?? '8765'

export default defineConfig({
  testDir: 'e2e',
  outputDir: 'test-results',
  // FakeRunner ticks each task every 0.5 s: one loop takes a few seconds.
  timeout: 60_000,
  retries: 0,
  use: {
    baseURL: `http://127.0.0.1:${port}`,
    video: 'retain-on-failure',
    trace: 'retain-on-failure',
    // Google Fonts sometimes never answers, so `load` never fires and page.goto times out: tests use the fallback fonts.
    launchOptions: { args: ['--host-resolver-rules=MAP fonts.googleapis.com ~NOTFOUND, MAP fonts.gstatic.com ~NOTFOUND'] },
  },
  // hubd serves web/dist, so build first (`npm run build`). Fails if 8765 is taken: never test against a real hubd.
  webServer: {
    command: 'uv run hubd --demo',
    cwd: '..',
    url: `http://127.0.0.1:${port}/health`,
    reuseExistingServer: false,
    timeout: 60_000,
  },
})
