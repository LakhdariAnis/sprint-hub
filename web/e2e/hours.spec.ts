import { mkdir, readFile, rm, writeFile } from 'node:fs/promises'
import { join } from 'node:path'
import { expect, test, type APIRequestContext, type Page } from '@playwright/test'

// Step 513c. Its own project in the demo's throwaway vault: other specs keep their steps and sprints.
test.describe.configure({ mode: 'serial' })
let vault = ''
const steps = () => join(vault, 'projects', 'hours', 'steps')
const repo = () => join(vault, 'hours-repo')

async function add(request: APIRequestContext, id: string, state: string, sprint: number, minutes: number | null) {
  const run = minutes === null ? '' : `- 2026-11-02 09:00 · haiku · session s-${id} · ${minutes} min · task all\n`
  const text = `---\nstep: ${id}\ntitle: Hours ${id}\nstate: ${state}\nby: me\nsprint: ${sprint}\n---\n\n## Runs\n${run}\n## Tasks\n- [x] Do it\n`
  await writeFile(join(steps(), `${id}.md`), text)
  await expect.poll(async () => (await request.get(`/steps/hours/${id}`)).status()).toBe(200)
}

test.beforeAll(async ({ request }) => {
  vault = (await (await request.get('/health')).json()).vault
  await mkdir(join(repo(), 'sprint'), { recursive: true })
  await mkdir(steps(), { recursive: true })
  await writeFile(join(vault, 'projects', 'hours', 'project.md'), '---\nname: hours\nrepo: hours-repo\nmodel: haiku\nmerge: manual\n---\n')
  await expect.poll(async () => (await request.get('/projects/hours/steps')).status()).toBe(200)
  await add(request, '801', 'done', 8, 30)
  await add(request, '802', 'done', 8, 30)
  await add(request, '803', 'done', 8, null)
})

test.afterAll(async () => {
  await rm(join(vault, 'projects', 'hours'), { recursive: true })
  await rm(repo(), { recursive: true })
})

const progress = () => readFile(join(repo(), 'sprint', 'PROGRESS.md'), 'utf8')

async function confirm(page: Page, id: string) {
  await page.goto(`/#/review/hours/${id}`)
  await expect(page.locator('.head h2')).toContainText(id)
  await page.keyboard.press('a')
  const field = page.getByLabel(/Your hours/)
  await expect(field).toHaveValue('')
  await expect(field).toBeFocused()
  return field
}

test('approve with the hours field empty merges, and says not recorded', async ({ page }) => {
  await confirm(page, '801')
  await page.keyboard.press('y')
  await expect(page.getByRole('status')).toHaveText(/801 approved/)
  await expect(page.locator('.head .chip')).toHaveText(/approved/)
  expect(await progress()).toContain('Time: 0.5 h (agent 0.5 h, Anis not recorded)')
})

test('hours typed in the field are added to the agent hours', async ({ page }) => {
  await (await confirm(page, '802')).fill('0,5')
  await page.keyboard.press('Enter')
  await expect(page.getByRole('status')).toHaveText(/802 approved/)
  expect(await progress()).toContain('Time: 1 h (agent 0.5 h)')
})

test('hours it cannot read never block the merge, and it says so', async ({ page }) => {
  await (await confirm(page, '803')).fill('soon')
  await page.getByRole('button', { name: /^Yes, approve/ }).click()
  await expect(page.getByRole('status')).toHaveText(/803 approved.*"soon" not understood: not recorded/)
  expect(await progress()).toContain('Time: 0 h (agent 0 h, Anis not recorded)')
})

test('Escape in the field cancels, nothing moves', async ({ page, request }) => {
  await add(request, '804', 'done', 8, null)
  await confirm(page, '804')
  await page.keyboard.press('Escape')
  await expect(page.getByLabel(/Your hours/)).toHaveCount(0)
  await expect(page.locator('.head .chip')).toHaveText(/done/)
})

const command = (id: string, hours: number) => writeFile(join(repo(), '.claude', 'commands', `sprint-${id}.md`), `---\nmodel: haiku\nhours: ${hours}\n---\nDo it.\n`)
const planned = (page: Page) => page.locator('.budget .m', { hasText: 'planned' })
const actual = (page: Page) => page.locator('.budget .m', { hasText: 'actual' })

test('the sprint bar turns red over budget, live, and back', async ({ page, request }) => {
  await mkdir(join(repo(), '.claude', 'commands'), { recursive: true })
  await add(request, '701', 'todo', 7, null)
  await add(request, '702', 'todo', 7, 1140) // 19 h: actual over 18
  await add(request, '703', 'todo', 7, null) // no command file
  await command('701', 7)
  await command('702', 8)
  await page.goto('/#/projects/hours')
  await expect(page.getByRole('button', { name: 'Sprint 7' })).toBeVisible()
  await page.getByRole('button', { name: 'Sprint 7' }).click()
  await expect(planned(page)).toHaveText('15 h / 15 h planned')
  await expect(planned(page)).not.toHaveClass(/over/)
  await expect(actual(page)).toHaveText('19 h / 18 h actual')
  await expect(actual(page)).toHaveClass(/over/)

  await command('702', 9)
  await expect(planned(page)).toHaveText('16 h / 15 h planned')
  await expect(planned(page)).toHaveClass(/over/)
  await command('702', 8)
  await expect(planned(page)).toHaveText('15 h / 15 h planned')
  await expect(planned(page)).not.toHaveClass(/over/)
})

test('Step info: planned, agent and Anis; a missing value is a dash, a run with no end is flagged', async ({ page, request }) => {
  await writeFile(join(steps(), '704.md'), '---\nstep: 704\ntitle: Hours 704\nstate: done\nby: me\nsprint: 7\n---\n\n## Runs\n- 2026-11-02 09:00 · haiku · session s-704 · task all\n\n## Tasks\n- [x] Do it\n')
  await expect.poll(async () => (await request.get('/steps/hours/704')).status()).toBe(200)
  await page.goto('/#/projects/hours')
  await page.getByRole('button', { name: 'Sprint 7' }).click()
  const row = (id: string) => page.locator('.lr.grid', { hasText: `Hours ${id}` })
  await row('702').click()
  await expect(page.locator('.tm')).toHaveText(/planned 8 h.*agent 19 h.*Anis –/)
  await row('703').click()
  await expect(page.locator('.tm')).toHaveText(/planned –.*agent 0 h.*Anis –/)
  await row('704').click()
  await expect(page.locator('.tm')).toContainText('1 run with no end')
  // Approved in the first tests, with 0.5 h of its own and 0.5 h of agent.
  await page.getByRole('button', { name: 'Sprint 8' }).click()
  await row('802').click()
  await expect(page.locator('.tm')).toHaveText(/agent 0.5 h.*Anis 0.5 h/)
})

test('the bar reads in full and is not cut at a half tile', async ({ page }) => {
  for (const [width, height] of [[743, 730], [743, 540], [960, 540], [1920, 1080]]) {
    await page.setViewportSize({ width, height })
    await page.goto('/#/projects/hours')
    await page.getByRole('button', { name: 'Sprint 7' }).click()
    for (const m of [planned(page), actual(page)]) {
      await expect(m).toBeVisible()
      const fits = await m.locator('.v').evaluate((el) => {
        const r = el.getBoundingClientRect()
        const pane = el.closest('.pn')!.getBoundingClientRect()
        return el.scrollWidth <= el.clientWidth + 1 && r.left >= pane.left && r.right <= pane.right
      })
      expect(fits, `${width}x${height}`).toBe(true)
    }
  }
})

test('the demo vault has a sprint over budget', async ({ page }) => {
  await page.goto('/#/projects/demo')
  await page.getByRole('button', { name: 'Sprint 2' }).click()
  await expect(planned(page)).toHaveText('16 h / 15 h planned')
  await expect(actual(page)).toHaveText('19.5 h / 18 h actual')
  await expect(actual(page)).toHaveClass(/over/)
})
