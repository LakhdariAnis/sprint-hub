import { expect, test } from '@playwright/test'

// Step 510c: the Settings screen on the demo hubd (its vault is a throwaway folder, so hub.toml is the demo's own).
const noPageScroll = (page: import('@playwright/test').Page) => page.evaluate(() => document.documentElement.scrollHeight <= innerHeight && document.documentElement.scrollWidth <= innerWidth)

async function moveTo(page: import('@playwright/test').Page, name: string) {
  for (let i = 0; i < 60; i++) {
    if ((await page.evaluate(() => document.querySelector('.row.f .nm')?.textContent)) === name) return
    await page.keyboard.press('j')
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
