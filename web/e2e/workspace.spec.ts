import { rm, writeFile } from 'node:fs/promises'
import { dirname, join } from 'node:path'
import { expect, test, type Page } from '@playwright/test'

// Step 613b: the demo's `notes` project has `workspace: 2`, `demo` has none. FakeRunner only records the switch: hyprctl is never called.
const status = (page: Page) => page.locator('footer.keys .nt')
const ws = (page: Page) => page.locator('.chip.ws')

test('the chip shows on the Projects row, the Project header, the Step header and the sidebar', async ({ page }) => {
  await page.goto('/#/projects')
  await expect(page.locator('.row', { hasText: 'notes' }).locator('.chip.ws')).toHaveText('2')
  await expect(page.locator('.row', { hasText: 'demo' }).locator('.chip.ws')).toHaveCount(0)
  await page.goto('/#/projects/notes')
  await expect(page.locator('header.hd .chip.ws')).toHaveText('2')
  await page.goto('/#/steps/notes/302')
  await expect(page.locator('.hd .chip.ws')).toHaveText('2')
  await expect(page.locator('nav.sb .chip.ws')).toHaveText('2')
  await page.goto('/#/projects/demo')
  await expect(page.getByRole('heading', { name: 'demo' })).toBeVisible()
  await expect(page.locator('header.hd .chip.ws')).toHaveCount(0)
})

test('w jumps through hubd, and says why when the project has no workspace', async ({ page }) => {
  await page.goto('/#/projects/notes')
  const sent = page.waitForResponse((r) => r.url().endsWith('/projects/notes/focus') && r.request().method() === 'POST')
  await page.keyboard.press('w')
  const r = await sent
  expect(r.status()).toBe(200)
  expect(await r.json()).toEqual({ workspace: 2 })
  await page.goto('/#/steps/notes/302')
  const again = page.waitForResponse((r) => r.url().endsWith('/projects/notes/focus'))
  await page.keyboard.press('w')
  expect((await again).status()).toBe(200)

  await page.goto('/#/projects/demo')
  await expect(page.getByRole('heading', { name: 'demo' })).toBeVisible()
  await page.keyboard.press('w')
  await expect(status(page)).toHaveText(/demo has no workspace/)
  await expect(status(page)).toHaveClass(/bad/)
})

test('key help lists w', async ({ page }) => {
  await page.goto('/#/projects')
  await page.keyboard.press('?')
  await expect(page.getByRole('dialog', { name: 'Key help' }).locator('kbd', { hasText: /^w$/ })).toBeVisible()
})

// Its own step: loop.spec starts and approves notes/301.
for (const [w, h] of [[1920, 1080], [743, 730]]) {
  test(`${w}px: a start says on which workspace the run opened, chip and line read in full`, async ({ page, request }) => {
    const id = w > 1000 ? '997' : '996'
    const { path } = await (await request.get('/steps/notes/301')).json()
    const file = join(dirname(path), `${id}.md`)
    await writeFile(file, `---\nstep: ${id}\ntitle: Workspace start\nstate: todo\nby: claude\n---\n`)
    try {
      await expect.poll(async () => (await request.get(`/steps/notes/${id}`)).status()).toBe(200)
      await page.setViewportSize({ width: w, height: h })
      await page.goto(`/#/steps/notes/${id}`)
      await expect(page.locator('.chip.s-todo')).toBeVisible()
      await page.keyboard.press('s')
      await expect(status(page)).toHaveText('Started on workspace 2')
      for (const el of [status(page), ws(page).first()]) {
        await expect(el).toBeVisible()
        expect(await el.evaluate((n) => n.scrollWidth <= n.clientWidth)).toBe(true)
      }
    } finally {
      await rm(file)
    }
  })
}
