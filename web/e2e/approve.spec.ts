import { expect, test } from '@playwright/test'

// Step 507b: a refused approve. The demo repo never refuses, so the reply is faked and no step changes.
for (const [name, reply] of [
  ['refusal', { detail: '/repo: uncommitted changes in CLAUDE.md' }],
  ['conflict', { detail: 'merge step/x: conflict in second.txt; merge aborted', files: ['second.txt'] }],
] as const) {
  test(`a merge ${name} is shown as text, the confirm stays and the step stays done`, async ({ page }) => {
    await page.route('**/approve', (route) => route.fulfill({ status: 409, json: reply }))
    await page.goto('/#/review')
    await expect(page.locator('.head .chip')).toHaveText(/done/)
    await page.keyboard.press('a')
    await expect(page.getByText(/ into main\?/)).toBeVisible()
    await page.keyboard.press('a')
    await expect(page.getByText(reply.detail)).toBeVisible()
    await expect(page.getByRole('button', { name: /^Yes, approve/ })).toBeEnabled()
    await expect(page.locator('.head .chip')).toHaveText(/done/)
    await expect(page.getByRole('status')).toHaveCount(0)
  })
}
