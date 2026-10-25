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

test('Project screen: a sprint lists only its steps, a step shows its info', async ({ page }) => {
  await page.goto('/#/projects/demo')
  const steps = page.locator('.pn', { hasText: /^Steps/ })
  const info = page.locator('.pn', { hasText: /^Step info/ })
  await expect(page.getByRole('button', { name: /Sprint 1/ })).toContainText('●')
  await expect(steps.getByText('Show the list')).toBeVisible()
  const box = await steps.boundingBox()

  await page.getByRole('button', { name: /Sprint 2/ }).click()
  await expect(steps.getByText('Tag the release')).toBeVisible()
  await expect(steps.getByText('Show the list')).toHaveCount(0)
  await steps.getByText('Write the changelog').click()
  await expect(info.getByText('Write the changelog')).toBeVisible()
  // Nothing jumps: the Steps column keeps its place and width.
  expect(await steps.boundingBox()).toMatchObject({ x: box!.x, y: box!.y, width: box!.width })
})

test('Project screen: the cursor starts on the doing step, h l j k move it', async ({ page }) => {
  await page.goto('/#/projects/demo')
  const steps = page.locator('.pn', { hasText: /^Steps/ })
  const sprints = page.locator('.pn', { hasText: /^Sprints/ })
  const info = page.locator('.pn', { hasText: /^Step info/ })
  // Entering: Sprint 1, the doing step 102, Steps column framed. No key pressed.
  await expect(steps.locator('.lr.f')).toContainText('102')
  await expect(sprints.locator('.lr.f')).toContainText('Sprint 1')
  await expect(steps).toHaveClass(/\bf\b/)
  await page.keyboard.press('j')
  await expect(steps.locator('.lr.f')).toContainText('103')
  await page.keyboard.press('k')
  await page.keyboard.press('k')
  await expect(steps.locator('.lr.f')).toContainText('101')
  // h: Sprints column, j moves to Sprint 2; l: back to Steps, which now list Sprint 2.
  await page.keyboard.press('h')
  await expect(sprints).toHaveClass(/\bf\b/)
  await page.keyboard.press('j')
  await expect(sprints.locator('.lr.f')).toContainText('Sprint 2')
  await page.keyboard.press('l')
  await expect(steps).toHaveClass(/\bf\b/)
  await expect(steps.locator('.lr.f')).toContainText('201')
  await page.keyboard.press('j')
  await page.keyboard.press('Enter')
  await expect(page).toHaveURL(/#\/steps\/demo\/202$/)
  // Escape returns to the same sprint and step, not the default.
  await page.keyboard.press('Escape')
  await expect(page).toHaveURL(/#\/projects\/demo$/)
  await expect(sprints.locator('.lr.f')).toContainText('Sprint 2')
  await expect(steps.locator('.lr.f')).toContainText('202')
  await expect(info.getByText('Write the changelog')).toBeVisible()
})

test('Project screen: the info column keeps its bottom bar in view', async ({ page }) => {
  await page.setViewportSize({ width: 1400, height: 520 })
  await page.goto('/#/projects/demo')
  const info = page.locator('.pn', { hasText: /^Step info/ })
  await expect(info.getByText('Open', { exact: false }).first()).toBeVisible()
  const bar = await info.locator('.bar').boundingBox()
  expect(bar!.y + bar!.height).toBeLessThanOrEqual(520)
  expect(await page.locator('main').evaluate((m) => m.scrollHeight <= m.clientHeight)).toBe(true)
  // Same place for every step.
  const y = (await info.locator('.ti').boundingBox())!.y
  await page.keyboard.press('j')
  expect((await info.locator('.ti').boundingBox())!.y).toBe(y)
})

for (const [w, h] of [[960, 1080], [960, 540]]) {
  test(`Project screen at ${w}x${h}: no horizontal scroll, bottom bar of the info column in view`, async ({ page }) => {
    await page.setViewportSize({ width: w, height: h })
    await page.goto('/#/projects/demo')
    const info = page.locator('.pn', { hasText: /^Step info/ })
    await expect(info.locator('.bar')).toBeVisible()
    const bar = await info.locator('.bar').boundingBox()
    expect(bar!.y + bar!.height).toBeLessThanOrEqual(h)
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
    expect(await page.locator('main').evaluate((m) => m.scrollWidth <= m.clientWidth && m.scrollHeight <= m.clientHeight)).toBe(true)
    // Sprints are a strip: short label, marker kept.
    const sprints = page.locator('.pn', { hasText: /^S/ }).first()
    expect((await sprints.boundingBox())!.width).toBeLessThanOrEqual(70)
    await expect(sprints.locator('.lr.f')).toContainText('S1')
    await expect(sprints.locator('.lr.f')).toContainText('●')
  })
}

test('Step screen: the cursor starts on the current task', async ({ page }) => {
  await page.goto('/#/steps/demo/102')
  await expect(page.locator('.task.sel')).toHaveClass(/\bdoing\b/)
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
