import { mkdir, rm, writeFile } from 'node:fs/promises'
import { join } from 'node:path'
import { expect, test, type Page } from '@playwright/test'

// Step 514d. Its own project in the demo's throwaway vault, with a sprint table dated from today.
test.describe.configure({ mode: 'serial' })
let vault = ''
const readme = () => join(vault, 'weekly-repo', 'sprint', 'README.md')

// ISO week of a date, as the table writes it.
function weekOf(d: Date): string {
  const t = new Date(Date.UTC(d.getFullYear(), d.getMonth(), d.getDate()))
  t.setUTCDate(t.getUTCDate() + 4 - (t.getUTCDay() || 7))
  const week = Math.ceil(((+t - Date.UTC(t.getUTCFullYear(), 0, 1)) / 86_400_000 + 1) / 7)
  return `${t.getUTCFullYear()}-W${String(week).padStart(2, '0')}`
}
const inWeeks = (n: number) => weekOf(new Date(Date.now() + n * 7 * 86_400_000))
const HEAD = '## Sprints\n\n| Sprint | Track | Week | Version | Goal | Planned | Actual | Status |\n|---|---|---|---|---|---|---|---|\n'
const table = (...rows: string[]) => HEAD + rows.join('\n') + '\n'
const row = (n: number, track: string, week: string, planned: string, status: string, actual = '') => `| ${n} | ${track} | ${week} | 0.1.0 | Goal of weekly ${n} | ${planned} | ${actual} | ${status} |`

test.beforeAll(async ({ request }) => {
  vault = (await (await request.get('/health')).json()).vault
  await mkdir(join(vault, 'weekly-repo', 'sprint'), { recursive: true })
  await mkdir(join(vault, 'projects', 'weekly', 'steps'), { recursive: true })
  await writeFile(join(vault, 'projects', 'weekly', 'project.md'), '---\nname: weekly\nrepo: weekly-repo\nmodel: haiku\nmerge: manual\n---\n')
  await expect.poll(async () => (await request.get('/projects/weekly/steps')).status()).toBe(200)
})

test.afterAll(async () => {
  await rm(join(vault, 'projects', 'weekly'), { recursive: true })
  await rm(join(vault, 'weekly-repo'), { recursive: true })
})

test('This week lists the work and the personal sprint of the demo', async ({ page }) => {
  await page.goto('/#/today')
  await page.keyboard.press('w')
  const pane = page.locator('.pn', { hasText: 'This week' })
  await expect(pane).toContainText('Search the notes') // notes: work
  await expect(pane).toContainText('Show the list and serve the API') // demo: personal
  await expect(pane.locator('.sp', { hasText: 'Search the notes' })).toContainText(/\d\/2 steps/) // other specs approve notes steps
  await expect(pane.locator('.sp', { hasText: 'Search the notes' })).toContainText('0 / 8 h')
  await expect(pane.locator('.sp', { hasText: 'Search the notes' })).toContainText(/[1-7] d left/)
})

test('two sprints in one track warn, and so does a week without work', async ({ page, request }) => {
  await page.goto('/#/today')
  const pane = page.locator('.pn', { hasText: 'This week' })
  // The demo has one work sprint this week: no warning. A second one makes two.
  await expect(pane.locator('.wn')).toHaveCount(0)
  await writeFile(readme(), table(row(1, 'work', inWeeks(0), '4 h', 'current')))
  await expect(pane.locator('.wn')).toHaveText(/2 work sprints in \d{4}-W\d\d \(notes 3, weekly 1\)\. One per track\./, { timeout: 5000 })
  expect((await (await request.get('/week')).json()).warnings).toHaveLength(1)
  await rm(readme())
  await expect(pane.locator('.wn')).toHaveCount(0, { timeout: 5000 })
})

test('the ETA line, its factor, a live edit and the flags', async ({ page }) => {
  const rows = (planned: string) => [
    row(1, 'personal', inWeeks(-3), '10 h', 'closed', '5 h'),
    row(2, 'personal', inWeeks(-1), '8 h', 'current'), // late
    row(3, 'personal', inWeeks(1), planned, 'planned'),
    row(4, 'personal', inWeeks(2), '~6 h', 'planned'),
  ]
  await writeFile(readme(), table(...rows('~14 h')))
  await page.goto('/#/projects/weekly')
  const eta = page.locator('.eta')
  // 28 h open × 0.5 (5 h of 10 h) = 14 h.
  await expect(eta.locator('.line')).toHaveText(new RegExp(`^3 sprints, ~14 h, done ${inWeeks(2)} \\(Sun \\d{4}-\\d\\d-\\d\\d\\)$`))
  await expect(eta.locator('.note')).toHaveText('28 h planned × 0.5 (1 closed sprint)')
  await expect(eta.locator('.flag')).toHaveText(/Sprint 2 is overdue/)

  await writeFile(readme(), table(...rows('~24 h'))) // +10 h planned, no reload
  await expect(eta.locator('.line')).toContainText('~19 h', { timeout: 5000 })
  await expect(eta.locator('.note')).toContainText('38 h planned')
})

test('a broken row is a warning in the status line, the app keeps working', async ({ page }) => {
  await writeFile(readme(), table(row(1, 'personal', inWeeks(1), '4 h', 'planned'), '| x |'))
  await page.goto('/#/projects/weekly')
  await expect(page.getByRole('button', { name: /1 warning/ })).toBeVisible({ timeout: 5000 })
  await expect(page.locator('.eta .line')).toContainText('1 sprint,')
  await page.getByRole('button', { name: /1 warning/ }).click()
  await expect(page.getByRole('dialog')).toContainText('sprint row skipped')
  await page.keyboard.press('Escape')
  await writeFile(readme(), table(row(1, 'personal', inWeeks(1), '4 h', 'planned')))
  await expect(page.getByRole('button', { name: /warning/ })).toHaveCount(0, { timeout: 5000 })
})

test('no sprint table, no data, and no factor either', async ({ page }) => {
  await writeFile(readme(), '# weekly\n\nNo table here.\n')
  await page.goto('/#/projects/weekly')
  await expect(page.locator('.eta .line')).toHaveText('No sprint table, no estimate.')
  await writeFile(readme(), table(row(1, 'work', inWeeks(1), '4 h', 'planned', 'not recorded'))) // work: no closed sprint anywhere in the demo
  await expect(page.locator('.eta .note')).toHaveText('no closed sprint with recorded hours: factor 1.0')
})

async function fits(page: Page, selector: string, label: string) {
  const bad = await page.locator(selector).evaluateAll((els) =>
    els.flatMap((el) => {
      const r = el.getBoundingClientRect()
      const box = (el.closest('.pn') ?? document.body).getBoundingClientRect()
      return el.scrollWidth > el.clientWidth + 1 || r.right > box.right + 1 ? [el.textContent?.slice(0, 40)] : []
    }),
  )
  expect(bad, label).toEqual([])
}

test('Today and Project read in full at 743 px, 960 px and 1920 px', async ({ page }) => {
  await writeFile(readme(), table(row(1, 'work', inWeeks(0), '4 h', 'current'), row(2, 'personal', inWeeks(-1), '8 h', 'planned'), row(3, 'personal', inWeeks(1), '~14 h', 'planned')))
  for (const [width, height] of [[743, 730], [743, 540], [960, 540], [1920, 1080]]) {
    const label = `${width}x${height}`
    await page.setViewportSize({ width, height })
    await page.goto('/#/today')
    await page.keyboard.press('w')
    const pane = page.locator('.pn', { hasText: 'This week' })
    await expect(pane.locator('.sp').first()).toBeVisible()
    await pane.locator('.sp').last().scrollIntoViewIfNeeded()
    await expect(pane.locator('.wn')).toBeVisible() // two work sprints
    await fits(page, '.wp .sp, .wp .wn, .wp .goal', label)
    await page.keyboard.press('b')
    await fits(page, '.wp .sp, .wp .wn, .wp .goal', label + ' rail')
    await page.keyboard.press('b')

    await page.goto('/#/projects/weekly')
    await expect(page.locator('.eta .line')).toBeVisible()
    await fits(page, '.eta .line, .eta .note, .eta .flag', label)
    const eta = await page.locator('.eta').boundingBox()
    const body = await page.locator('.body').boundingBox()
    expect(eta!.y + eta!.height, label).toBeLessThanOrEqual(body!.y + 1)
    expect(body!.height, label).toBeGreaterThan(200) // the columns keep room
  }
})
