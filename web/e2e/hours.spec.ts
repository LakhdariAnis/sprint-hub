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
