import { expect, test } from '@playwright/test'

// Step 601: Ctrl+W / Alt+F4 / the close button end in `beforeunload`; the app asks first, but only after a key press or click.
const prevented = (page: import('@playwright/test').Page) =>
  page.evaluate(() => {
    const e = new Event('beforeunload', { cancelable: true })
    dispatchEvent(e)
    return e.defaultPrevented
  })

for (const gesture of ['key', 'click'] as const) {
  test(`beforeunload is set after a ${gesture}`, async ({ page }) => {
    await page.goto('/#/today')
    await expect(page.locator('main h1, main .hd').first()).toBeVisible()
    expect(await prevented(page)).toBe(false)
    if (gesture === 'key') await page.keyboard.press('j')
    else await page.locator('main').click({ position: { x: 5, y: 5 } })
    expect(await prevented(page)).toBe(true)
  })
}
