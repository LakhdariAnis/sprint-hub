import { rm, writeFile } from 'node:fs/promises'
import { dirname, join } from 'node:path'
import { expect, test } from '@playwright/test'

// Step 505a: hubd refuses a start with a 409 and a reason. The demo's FakeRunner never refuses, so the reply is faked here.
// Its own step file: loop.spec.ts starts and approves notes/301, so 301 is `todo` only if this test happens to run first.
test('a refused start shows the reason and the step stays todo', async ({ page, request }) => {
  const { path } = await (await request.get('/steps/notes/301')).json()
  const file = join(dirname(path), '998.md')
  await writeFile(file, '---\nstep: 998\ntitle: Refused start\nstate: todo\nby: claude\n---\n')
  try {
    await expect.poll(async () => (await request.get('/steps/notes/998')).status()).toBe(200)
    const reason = 'step 998: no /repo/.claude/commands/sprint-998.md: without it, /sprint-998 is not a command'
    await page.route('**/steps/notes/998/start', (route) => route.fulfill({ status: 409, json: { detail: reason } }))
    await page.goto('/#/steps/notes/998')
    await expect(page.locator('.chip.s-todo')).toBeVisible()
    await page.keyboard.press('s')
    await expect(page.getByText(`Start failed: ${reason}`)).toBeVisible()
    await expect(page.locator('.chip.s-todo')).toBeVisible()
    await expect(page.getByRole('button', { name: /Start/ })).toBeEnabled()
  } finally {
    await rm(file)
  }
})

test('the Step screen says when the vault model differs from the command', async ({ page }) => {
  await page.goto('/#/steps/notes/301') // vault step: sonnet, command: haiku
  const fact = page.locator('.meta div', { hasText: 'MODEL' })
  await expect(fact).toContainText('sonnet')
  await expect(fact).toContainText('not haiku')
  await page.goto('/#/steps/notes/302') // no command file: no note
  await expect(page.locator('.meta div', { hasText: 'MODEL' })).not.toContainText('not ')
})

test('the Step screen lists the latest run with its start time', async ({ page }) => {
  await page.goto('/#/steps/notes/302')
  await expect(page.getByText('1 run · last started 2026-10-19 09:00 · sonnet')).toBeVisible()
})
