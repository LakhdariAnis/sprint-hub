import { mkdir, rm, writeFile } from 'node:fs/promises'
import { join } from 'node:path'
import { expect, test, type APIRequestContext, type Page } from '@playwright/test'

// Step 506b. The tests write `doing` steps into their own project of the demo's throwaway vault: other specs keep their steps and sprints.
const step = (id: string) => `---\nstep: ${id}\ntitle: Finish test\nstate: doing\nby: claude\nmodel: haiku\n---\n\n## Runs\n- 2026-11-02 09:00 · haiku · session s-${id} · task all\n\n## Review\nverdict:\ncomment:\n`
let vault = ''

test.beforeAll(async ({ request }) => {
  vault = (await (await request.get('/health')).json()).vault
  await mkdir(join(vault, 'finish-repo', 'sprint', 'progress'), { recursive: true })
  await mkdir(join(vault, 'projects', 'finish', 'steps'), { recursive: true })
  await writeFile(join(vault, 'projects', 'finish', 'project.md'), '---\nname: finish\nrepo: finish-repo\nmodel: haiku\nmerge: manual\n---\n')
  await expect.poll(async () => (await request.get('/projects/finish/steps')).status()).toBe(200)
})

test.afterAll(async () => {
  await rm(join(vault, 'projects', 'finish'), { recursive: true })
  await rm(join(vault, 'finish-repo'), { recursive: true })
})

async function doing(request: APIRequestContext, id: string, progress: string) {
  const file = join(vault, 'finish-repo', 'sprint', 'progress', `${id}.md`)
  await writeFile(file, progress)
  await writeFile(join(vault, 'projects', 'finish', 'steps', `${id}.md`), step(id))
  await expect.poll(async () => (await request.get(`/steps/finish/${id}`)).status()).toBe(200)
  return file
}

const open = async (page: Page, id: string) => {
  await page.goto(`/#/steps/finish/${id}`)
  await expect(page.locator('.chip.s-doing')).toBeVisible()
}

test('the message to exit Claude shows once the last task is ticked', async ({ page, request }) => {
  const progress = await doing(request, '691', '# Step 691\n- [x] One\n- [~] Two\n')
  await open(page, '691')
  const message = page.getByText('All tasks ticked. Exit Claude (/exit) to send it to review.')
  await expect(page.getByText('Two')).toBeVisible()
  await expect(message).toHaveCount(0)
  // Written again until seen: the new project's `sprint/` is watched within a second or so.
  await expect(async () => {
    await writeFile(progress, '# Step 691\n- [x] One\n- [x] Two\n')
    await expect(message).toBeVisible({ timeout: 500 })
  }).toPass({ timeout: 8000 })
})

test('f asks first, Esc cancels and stays, f f sends the step to done', async ({ page, request }) => {
  await doing(request, '692', '# Step 692\n- [~] One\n')
  await open(page, '692')
  await expect(page.locator('footer').getByText('ffinish')).toBeVisible()

  await page.keyboard.press('f')
  const ask = page.getByText('Finish this run?')
  await expect(ask).toBeVisible()
  await expect(page.locator('.chip.s-doing')).toBeVisible() // nothing moved yet
  await page.keyboard.press('Escape')
  await expect(ask).toHaveCount(0)
  await expect(page).toHaveURL(/#\/steps\/finish\/692$/) // the first Esc only cancels

  await page.keyboard.press('f')
  await page.keyboard.press('f')
  await expect(page.locator('.chip.s-done')).toBeVisible()
  await expect(ask).toHaveCount(0)
  await expect(page.getByRole('button', { name: /Finish/ })).toHaveCount(0)
  await page.keyboard.press('f') // not `doing` any more: the key does nothing
  await expect(ask).toHaveCount(0)

  // The hook arrives after all: the step stays where it is, no error.
  const late = await request.post('/runs/ended', { data: { session_id: 's-692', step: '692' } })
  expect(late.status()).toBe(200)
  expect((await late.json()).state).toBe('done')
})

test('a run hubd found gone is flagged with the f hint; y confirms too', async ({ page, request }) => {
  await doing(request, '693', '# Step 693\n- [x] One\n')
  // The demo's FakeRunner says every session runs, so the flag is faked here; Today carries the step too.
  const gone = <T extends { step: string }>(s: T) => (s.step === '693' ? { ...s, run_gone: true } : s)
  await page.route(/\/(today|steps\/finish\/693)$/, async (route) => {
    const response = await route.fetch()
    const body = await response.json()
    await route.fulfill({ response, json: body.running ? { ...body, running: body.running.map(gone) } : gone(body) })
  })
  await open(page, '693')
  await expect(page.getByText(/The run is gone/)).toBeVisible()
  await expect(page.getByText(/All tasks ticked/)).toHaveCount(0) // no Claude to exit
  await page.keyboard.press('f')
  await page.keyboard.press('y')
  await expect(page.locator('.chip.s-done')).toBeVisible()
  await expect(page.getByText(/The run is gone/)).toHaveCount(0)
})

test('the app shows a refused finish, and ? lists the f key', async ({ page, request }) => {
  await doing(request, '694', '# Step 694\n- [~] One\n')
  await page.route('**/steps/finish/694/finish', (route) => route.fulfill({ status: 409, json: { detail: 'no' } }))
  await open(page, '694')
  await page.keyboard.press('f')
  await page.keyboard.press('f')
  await expect(page.getByText('Finish failed: no')).toBeVisible()
  await expect(page.locator('.chip.s-doing')).toBeVisible()
  await page.keyboard.press('?')
  await expect(page.getByRole('dialog').getByText(/finish a doing run/)).toBeVisible()
})
