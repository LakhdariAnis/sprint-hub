import { expect, test } from '@playwright/test'

// Step 505a: hubd refuses a start with a 409 and a reason. The demo's FakeRunner never refuses, so the reply is faked here.
test('a refused start shows the reason and the step stays todo', async ({ page }) => {
  const reason = 'step 301: no /repo/.claude/commands/sprint-301.md: without it, /sprint-301 is not a command'
  await page.route('**/steps/notes/301/start', (route) => route.fulfill({ status: 409, json: { detail: reason } }))
  await page.goto('/#/steps/notes/301')
  await expect(page.locator('.chip.s-todo')).toBeVisible()
  await page.keyboard.press('s')
  await expect(page.getByText(`Start failed: ${reason}`)).toBeVisible()
  await expect(page.locator('.chip.s-todo')).toBeVisible()
  await expect(page.getByRole('button', { name: /Start/ })).toBeEnabled()
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
  await expect(page.getByText('Run 1 · started 2026-10-19 09:00 · sonnet')).toBeVisible()
})
