import { mkdir, rm, writeFile } from 'node:fs/promises'
import { join } from 'node:path'
import { expect, test } from '@playwright/test'

// Step 614. Its own project in the demo's throwaway vault: a FakeRunner run ends, which is a closed terminal, then `o` opens the chat again.
let vault = ''

test.beforeAll(async ({ request }) => {
  vault = (await (await request.get('/health')).json()).vault
  await mkdir(join(vault, 'reopen-repo', 'sprint', 'progress'), { recursive: true })
  await writeFile(join(vault, 'reopen-repo', 'sprint', '695-reopen.md'), '# Step 695\n\n## Tasks\n- One\n- Two\n- Three\n')
  await mkdir(join(vault, 'projects', 'reopen', 'steps'), { recursive: true })
  await writeFile(join(vault, 'projects', 'reopen', 'project.md'), '---\nname: reopen\nrepo: reopen-repo\nmodel: haiku\nmerge: manual\n---\n')
  await writeFile(join(vault, 'projects', 'reopen', 'steps', '695.md'), '---\nstep: 695\ntitle: Reopen test\nstate: todo\nby: claude\n---\n\n## Runs\n\n## Review\nverdict:\ncomment:\n')
  await expect.poll(async () => (await request.get('/steps/reopen/695')).status()).toBe(200)
})

test.afterAll(async () => {
  await rm(join(vault, 'projects', 'reopen'), { recursive: true })
  await rm(join(vault, 'reopen-repo'), { recursive: true })
})

test('a done step reopens with o and shows doing; a second open while it runs is refused', async ({ page, request }) => {
  await page.setViewportSize({ width: 743, height: 730 }) // half screen: the button and the resume line still fit
  expect((await request.post('/steps/reopen/695/start')).status()).toBe(200)
  await expect.poll(async () => (await (await request.get('/steps/reopen/695')).json()).state, { timeout: 15_000 }).toBe('done')
  const { runs } = await (await request.get('/steps/reopen/695')).json()

  await page.goto('/#/steps/reopen/695')
  await expect(page.locator('.chip.s-done')).toBeVisible()
  await expect(page.getByText(`claude --resume ${runs[0].session}`)).toBeVisible()
  await expect(page.getByRole('button', { name: /Reopen chat/ })).toBeVisible()
  await expect(page.locator('footer').getByText('oreopen chat')).toBeVisible()

  await page.keyboard.press('o')
  await expect(page.locator('.chip.s-doing')).toBeVisible()
  await expect(page.getByRole('button', { name: /Reopen chat/ })).toHaveCount(0)
  const after = await (await request.get('/steps/reopen/695')).json()
  expect(after.runs.map((r: { session: string }) => r.session)).toEqual([runs[0].session, runs[0].session])

  // The fake chat runs again: a second open is refused, the reason in the status line.
  const refused = await request.post('/steps/reopen/695/reopen')
  expect(refused.status()).toBe(409)
  expect((await refused.json()).detail).toBe('step 695: the chat is still open')
  await expect.poll(async () => (await (await request.get('/steps/reopen/695')).json()).state, { timeout: 15_000 }).toBe('done')
  await page.keyboard.press('?')
  await expect(page.getByRole('dialog').getByText(/reopen the chat of a run/)).toBeVisible()
})
