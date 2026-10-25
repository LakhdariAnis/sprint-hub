import { expect, test } from '@playwright/test'

// The core loop on the demo vault: Today → start notes/301 → FakeRunner ticks it to done → approve.
test('start a step, wait for done, approve it', async ({ page }) => {
  await page.goto('/')
  await expect(page).toHaveURL(/#\/projects$|\/$/)
  await page.goto('/#/today')
  await expect(page.getByRole('heading', { name: /^Good (morning|afternoon|evening), Anis$/ })).toBeVisible()

  const next = page.locator('.pn', { hasText: 'Now' })
  await next.getByRole('link', { name: /301\s+Parse the notes/ }).click()

  await expect(page).toHaveURL(/#\/steps\/notes\/301$/)
  const chip = page.locator('.hd .chip')
  await expect(chip).toHaveText(/todo/)
  await page.getByRole('button', { name: /Start/ }).click()
  await expect(chip).toHaveText(/running/)
  // Live over SSE: the checklist fills, then the run ends.
  await expect(page.locator('.big')).toHaveText(/3\s*\/\s*3/, { timeout: 30_000 })
  await expect(chip).toHaveText(/done/, { timeout: 30_000 })

  await page.goto('/#/review/notes/301')
  await page.getByRole('button', { name: /^Approve/ }).click()
  await page.getByRole('button', { name: /^Yes, approve/ }).click()
  await expect(page.locator('.head .chip')).toHaveText(/approved/)
  await expect(page.locator('.queue').getByRole('link', { name: /301/ })).toBeVisible()
})

test('plain keys switch tabs, open steps and the sidebar rail', async ({ page }) => {
  await page.goto('/#/steps/notes/301')
  const open = page.getByRole('link', { name: 'notes 301' })
  await expect(open).toBeVisible()
  await page.keyboard.press('1')
  await expect(page).toHaveURL(/#\/projects$/)
  await page.keyboard.press('6')
  await expect(page).toHaveURL(/#\/steps\/notes\/301$/)
  await page.keyboard.press('b')
  await expect(page.locator('nav.sb.rail')).toBeVisible()
  await expect(open).toContainText('6')
})

test('Enter opens the selected row after a sidebar click', async ({ page }) => {
  await page.goto('/#/today')
  await page.getByRole('link', { name: 'Projects' }).click()
  await expect(page).toHaveURL(/#\/projects$/)
  await page.keyboard.press('Enter')
  await expect(page).toHaveURL(/#\/projects\/demo$/)
})

test('Ctrl+2 opens Today, Ctrl+1 Projects', async ({ page }) => {
  await page.goto('/#/projects')
  await page.keyboard.press('Control+2')
  await expect(page).toHaveURL(/#\/today$/)
  await page.keyboard.press('Control+1')
  await expect(page).toHaveURL(/#\/projects$/)
})

test('Project screen folds done sprints and remembers it', async ({ page }) => {
  await page.goto('/#/projects/demo')
  const s2 = page.getByRole('button', { name: /Sprint 2/ })
  await expect(page.getByRole('button', { name: /Sprint 1/ })).toHaveAttribute('aria-expanded', 'true')
  await expect(s2).toHaveAttribute('aria-expanded', 'false')
  await expect(page.getByText('Tag the release')).toHaveCount(0)
  await s2.click()
  await expect(page.getByText('Tag the release')).toBeVisible()
  await page.reload()
  await expect(page.getByRole('button', { name: /Sprint 2/ })).toHaveAttribute('aria-expanded', 'true')
  await page.getByRole('button', { name: /Sprint 2/ }).focus()
  await page.keyboard.press('h')
  await expect(page.getByText('Tag the release')).toHaveCount(0)
})

test('x ticks the tasks of a manual step: todo, doing, done', async ({ page }) => {
  await page.goto('/#/today')
  await expect(page.locator('.pn', { hasText: 'Now' }).getByRole('link', { name: /101/ })).toContainText('demo · me')
  await page.goto('/#/steps/demo/101')
  const chip = page.locator('.hd .chip').first()
  await expect(chip).toHaveText(/todo/)
  await expect(page.locator('.hd .chip', { hasText: 'manual' })).toBeVisible()
  await expect(page.getByRole('button', { name: /Start/ })).toHaveCount(0)
  const tasks = page.locator('.task')
  await expect(tasks).toHaveCount(3)
  await page.keyboard.press('x')
  await expect(tasks.nth(0)).toHaveClass(/done/)
  await expect(chip).toHaveText(/running/)
  await page.keyboard.press('j')
  await page.keyboard.press('x')
  await expect(tasks.nth(1)).toHaveClass(/done/)
  await tasks.nth(2).click()
  await expect(page.locator('.big')).toHaveText(/3\s*\/\s*3/)
  await expect(chip).toHaveText(/done/)
  await page.keyboard.press('x') // unticks the third task again
  await expect(tasks.nth(2)).not.toHaveClass(/done/)
})

test('Today lists the overdue deadline first, in red', async ({ page }) => {
  await page.goto('/#/today')
  const rows = page.locator('.pn', { hasText: 'Deadlines' }).locator('.dl')
  await expect(rows.nth(2)).toBeVisible()
  await expect(rows.filter({ hasText: 'PFE topic form' })).toHaveCount(0) // done
  await expect(rows.first()).toContainText('Compilation TP report')
  await expect(rows.first()).toContainText('2 d late')
  await expect(rows.first()).toHaveAttribute('style', /var\(--r\)/)
  await expect(rows.nth(1)).toContainText('today')
})

test('Questions inbox lists the open demo questions', async ({ page }) => {
  await page.goto('/#/today')
  await page.keyboard.press('4')
  await expect(page).toHaveURL(/#\/questions$/)
  const rows = page.locator('.row')
  await expect(rows).toHaveCount(2) // the answered one is not listed
  await expect(rows.first()).toContainText('Should the search ignore case?')
  await expect(rows.nth(1)).toContainText('Index the note titles too?')
  await page.keyboard.press('Enter')
  await expect(page).toHaveURL(/#\/steps\/notes\/302$/)
})

test('sidebar: b and the hide button toggle the rail, which survives a reload', async ({ page }) => {
  await page.setViewportSize({ width: 1000, height: 400 })
  await page.goto('/#/today')
  const rail = page.locator('nav.sb.rail')
  await expect(rail).toHaveCount(0)
  await page.keyboard.press('b')
  await expect(rail).toBeVisible()
  await page.reload()
  await expect(rail).toBeVisible()
  await page.getByRole('button', { name: 'Expand sidebar' }).click()
  await expect(rail).toHaveCount(0)
  await page.getByRole('button', { name: 'Hide sidebar' }).click()
  await expect(rail).toBeVisible()
  // Short window: the button stays on screen.
  await expect(page.getByRole('button', { name: 'Expand sidebar' })).toBeInViewport()
})
