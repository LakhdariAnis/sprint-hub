import { rm, writeFile } from 'node:fs/promises'
import { dirname, join } from 'node:path'
import { expect, test } from '@playwright/test'

// Step 503: a spec written in a repo shows in the open app, a deleted one says it is missing. The demo vault is a throwaway folder; the step's own path tells where.
test('a new spec appears in the open Project screen, a deleted one is marked missing', async ({ page, request }) => {
  const { path } = await (await request.get('/steps/notes/301')).json()
  const vault = dirname(dirname(dirname(dirname(path)))) // <vault>/projects/notes/steps/301.md
  const spec = join(vault, 'notes-repo', 'sprint', '999-live-test.md')

  await page.goto('/#/projects/notes')
  await expect(page.getByRole('button', { name: /Sprint 3/ })).toBeVisible()
  await expect(page.getByRole('button', { name: /Sprint 9/ })).toHaveCount(0)

  await writeFile(spec, '# Step 999 — Live test\n\n## Goal\nSee it appear.\n')
  await expect(page.getByRole('button', { name: /Sprint 9/ })).toBeVisible({ timeout: 5000 })
  await page.getByRole('button', { name: /Sprint 9/ }).click()
  await expect(page.locator('.pn', { hasText: /^Steps/ }).getByText('Live test')).toBeVisible()

  await page.goto('/#/steps/notes/999')
  await expect(page.getByText('See it appear.').first()).toBeVisible()
  await rm(spec)
  await expect(page.getByText(/Spec missing/)).toBeVisible({ timeout: 5000 })

  // A vault file goes only by hand; then the step leaves the app.
  await rm(join(vault, 'projects', 'notes', 'steps', '999.md'))
  await page.goto('/#/projects/notes')
  await expect(page.getByRole('button', { name: /Sprint 9/ })).toHaveCount(0, { timeout: 5000 })
})
