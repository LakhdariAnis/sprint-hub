import { expect, test } from '@playwright/test'

// Step 510c: the Settings screen on the demo hubd (its vault is a throwaway folder, so hub.toml is the demo's own).
const noPageScroll = (page: import('@playwright/test').Page) => page.evaluate(() => document.documentElement.scrollHeight <= innerHeight && document.documentElement.scrollWidth <= innerWidth)

// Steps toward the row, up or down: other specs add projects meanwhile, which moves the rows.
async function moveTo(page: import('@playwright/test').Page, name: string) {
  await expect(page.locator('main')).toHaveAttribute('data-shown', '#/settings') // keys before that are held, then run at once
  for (let i = 0; i < 60; i++) {
    const [names, at] = await page.evaluate(() => {
      const rows = [...document.querySelectorAll('.row')]
      return [rows.map((r) => r.querySelector('.nm')?.textContent), rows.findIndex((r) => r.classList.contains('f'))] as const
    })
    const to = names.indexOf(name)
    if (to === at) return
    await page.keyboard.press(to > at ? 'j' : 'k')
  }
  throw new Error(`no row ${name}`)
}

test('5 opens Settings, the tab is lit, ? lists the key', async ({ page }) => {
  await page.goto('/#/projects')
  await page.keyboard.press('5')
  await expect(page).toHaveURL(/#\/settings$/)
  await expect(page.locator('nav.sb a.tb.on')).toContainText('Settings')
  await expect(page.locator('.gr', { hasText: 'HEALTH' })).toBeVisible()
  await expect(page.locator('.gr', { hasText: 'PROJECTS' })).toBeVisible()
  await expect(page.locator('.row.project', { hasText: 'demo' })).toContainText('base main')
  await expect(page.locator('.row.info', { hasText: 'service' })).toBeVisible()
  await page.keyboard.press('?')
  await expect(page.getByRole('dialog', { name: 'Key help' })).toContainText('Settings')
  await page.keyboard.press('Escape')
  await page.keyboard.press('1')
  await page.keyboard.press('Control+5')
  await expect(page).toHaveURL(/#\/settings$/)
})

test('reminder_hour: 99 is refused with the reason, 8 saves; terminal without {cwd} is refused', async ({ page }) => {
  await page.goto('/#/settings')
  await moveTo(page, 'reminder_hour')
  await page.keyboard.press('Enter')
  const box = page.getByRole('textbox', { name: 'reminder_hour' })
  await box.fill('99')
  await box.press('Enter')
  await expect(page.getByRole('alert').filter({ hasText: '0–23' })).toBeVisible()
  await box.fill('8')
  await box.press('Enter')
  await expect(page.getByRole('status')).toContainText('saved')
  expect((await (await page.request.get('/settings')).json()).reminder_hour).toBe(8)

  await page.keyboard.press('k')
  await expect(page.locator('.row.f .nm')).toHaveText('terminal')
  await page.keyboard.press('Enter')
  const term = page.getByRole('textbox', { name: 'terminal' })
  const before = await term.inputValue()
  await term.fill(before.replace('{cwd}', ''))
  await term.press('Enter')
  await expect(page.getByRole('alert').filter({ hasText: '{cwd}' })).toBeVisible()
  expect((await (await page.request.get('/settings')).json()).terminal.join(' ')).toBe(before)
  await term.press('Escape')
  await expect(term).toHaveCount(0)

  // Put the demo back.
  await moveTo(page, 'reminder_hour')
  await page.keyboard.press('Enter')
  await box.fill('9')
  await box.press('Enter')
  await expect(page.getByRole('status')).toContainText('saved')
})

test('notify_waiting: Enter turns it off, a click turns it on, the label reads in full at half screen', async ({ page }) => {
  await page.setViewportSize({ width: 960, height: 1080 })
  await page.goto('/#/settings')
  await moveTo(page, 'notify_waiting')
  const sw = page.getByRole('switch', { name: 'Notify when Claude waits' })
  await expect(sw).toHaveAttribute('aria-checked', 'true')
  await page.keyboard.press('Enter')
  await expect(sw).toHaveAttribute('aria-checked', 'false')
  await expect(page.getByRole('status')).toContainText('saved')
  expect((await (await page.request.get('/settings')).json()).notify_waiting).toBe(false)
  const hint = page.locator('.row.f .hint')
  await expect(hint).toContainText('Notify when Claude waits')
  expect(await hint.evaluate((el) => el.scrollWidth <= el.clientWidth)).toBe(true)
  await sw.click()
  await expect(sw).toHaveAttribute('aria-checked', 'true')
  expect((await (await page.request.get('/settings')).json()).notify_waiting).toBe(true)
})

for (const [w, h] of [[743, 730], [743, 540]]) {
  for (const rail of [false, true]) {
    test(`Settings at ${w}x${h}${rail ? ' rail' : ''}: j and k reach every row, none cut, no page scroll`, async ({ page }) => {
      await page.setViewportSize({ width: w, height: h })
      await page.goto('/#/settings')
      await expect(page.locator('.row').first()).toBeVisible()
      if (rail) await page.keyboard.press('b')
      const n = await page.locator('.row').count()
      for (let i = 0; i < n; i++) {
        await expect(page.locator('.row.f')).toBeInViewport()
        const bb = (await page.locator('.row.f').boundingBox())!
        const pane = (await page.locator('.pn').boundingBox())!
        expect(bb.y + bb.height).toBeLessThanOrEqual(pane.y + pane.height + 1)
        await page.keyboard.press('j')
      }
      expect(await page.locator('.row').last().evaluate((e) => e.classList.contains('f'))).toBe(true)
      expect(await noPageScroll(page)).toBe(true)
      expect(await page.locator('.pn').evaluate((e) => e.scrollWidth <= e.clientWidth)).toBe(true)
    })
  }
}

// Step 611a: a project removed between the list and its steps (another spec's afterAll) is left out, the screen still shows.
test('a project gone since the list was read is left out, Settings still shows', async ({ page }) => {
  await page.route('**/projects/notes/steps', (route) => route.fulfill({ status: 404, json: { detail: 'no project notes' } }))
  await page.goto('/#/settings')
  await expect(page.locator('.row.project', { hasText: 'demo' })).toBeVisible()
  await expect(page.locator('.row.project', { hasText: 'notes' })).toHaveCount(0)
})

test('Settings that cannot load shows a line, not a blank screen', async ({ page }) => {
  await page.route('**/settings', (route) => route.abort())
  await page.goto('/#/settings')
  await expect(page.locator('main')).toContainText('Cannot load settings')
})
