import { expect, test } from '@playwright/test'

// Step 508c: the comment box. Nothing is sent, so no demo step changes.
test('an empty comment is refused in the box with a reason, the step stays done', async ({ page }) => {
  await page.goto('/#/review')
  await expect(page.locator('.head .chip')).toHaveText(/done/)
  await page.keyboard.press('c')
  await page.keyboard.press('Enter')
  await expect(page.getByText('Write what should change first.')).toBeVisible()
  await expect(page.locator('.head .chip')).toHaveText(/done/)
})

test('pasted lines land in the box as one line', async ({ page }) => {
  await page.goto('/#/review')
  const box = page.getByLabel('Review comment')
  await box.focus()
  await box.evaluate((el) => {
    const data = new DataTransfer()
    data.setData('text', 'first line\r\nsecond line\n\nthird')
    el.dispatchEvent(new ClipboardEvent('paste', { clipboardData: data, bubbles: true, cancelable: true }))
  })
  await expect(box).toHaveValue('first line second line third')
})
