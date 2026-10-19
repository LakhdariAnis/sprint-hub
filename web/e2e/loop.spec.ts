import { expect, test } from '@playwright/test'

// The core loop on the demo vault: Today → start notes/301 → FakeRunner ticks it to done → approve.
test('start a step, wait for done, approve it', async ({ page }) => {
  await page.goto('/')
  await expect(page.getByRole('heading', { name: 'Today' })).toBeVisible()

  const next = page.locator('.pane', { hasText: 'Next up' })
  await next.getByRole('link', { name: /301\s+Parse the notes/ }).click()

  await expect(page).toHaveURL(/#\/steps\/notes\/301$/)
  const chip = page.locator('.chip')
  await expect(chip).toHaveText('todo')
  await page.getByRole('button', { name: /Start/ }).click()
  await expect(chip).toHaveText('doing')
  // Live over SSE: the checklist fills, then the run ends.
  await expect(page.getByText('Checklist 3/3')).toBeVisible({ timeout: 30_000 })
  await expect(chip).toHaveText('done', { timeout: 30_000 })

  await page.goto('/#/review/notes/301')
  await page.getByRole('button', { name: 'Approve', exact: true }).click()
  await page.getByRole('button', { name: 'Yes, approve' }).click()
  await expect(page.locator('.mi', { hasText: 'state' })).toHaveText(/approved/)
  await expect(page.locator('.pane', { hasText: 'Approved' }).getByRole('link', { name: /301/ })).toBeVisible()
})
