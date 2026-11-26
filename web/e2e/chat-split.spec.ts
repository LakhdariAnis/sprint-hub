import { expect, test, type Page } from '@playwright/test'

// Step 658b: the chat and the graph side by side (demo project has the graph on, notes has it off).
async function pickProject(page: Page, name: string) {
  await page.goto('/#/chat')
  await page.locator('.pill', { hasText: 'project' }).click()
  await page.getByRole('listbox', { name: 'Options of /project' }).getByRole('option', { name: new RegExp(name) }).click()
  await page.getByRole('textbox', { name: 'Message' }).press('Escape') // out of the box: keys act on the screen
}
// hubd keeps 3 chat processes at most: each test stops the chats it opened.
let opened: Promise<string>[] = []
test.beforeEach(({ page }) => {
  opened = []
  page.on('response', (r) => {
    if (r.request().method() === 'POST' && new URL(r.url()).pathname === '/chats' && r.ok()) opened.push(r.json().then((b) => b.id))
  })
})
test.afterEach(async ({ request }) => {
  for (const id of await Promise.all(opened)) await request.post(`/chats/${id}/stop`)
})
const handle = (page: Page) => page.getByRole('separator', { name: 'Chat and graph width' })
const sidebar = (page: Page) => page.getByRole('navigation', { name: 'Tabs' })
const railWidth = async (page: Page) => (await sidebar(page).boundingBox())!.width

test('g opens and closes the split, the sidebar folds and comes back', async ({ page }) => {
  await pickProject(page, 'demo')
  const layout = page.getByRole('group', { name: 'Layout' })
  await expect(layout.getByRole('button', { name: 'Chat', exact: true })).toHaveAttribute('aria-pressed', 'true')
  const wide = await railWidth(page)
  expect(wide).toBeGreaterThan(200)

  await page.keyboard.press('g')
  await expect(page.getByRole('region', { name: 'Code graph' })).toBeVisible()
  await expect(handle(page)).toBeVisible()
  await expect(layout.getByRole('button', { name: /^Chat \+ Graph/ })).toHaveAttribute('aria-pressed', 'true')
  await expect.poll(() => railWidth(page)).toBeLessThan(80)

  await page.keyboard.press('g')
  await expect(page.getByRole('region', { name: 'Code graph' })).toHaveCount(0)
  await expect.poll(() => railWidth(page)).toBe(wide)

  await layout.getByRole('button', { name: /^Chat \+ Graph/ }).click() // the switch does the same
  await expect(handle(page)).toBeVisible()
})

test('the handle moves with the arrows and the width survives a reload', async ({ page }) => {
  await pickProject(page, 'demo')
  // The pills do not survive a reload, a sent chat keeps its project: send first.
  const box = page.getByRole('textbox', { name: 'Message' })
  await box.focus()
  await box.fill('hi')
  await box.press('Enter')
  await expect(page).toHaveURL(/#\/chat\/[0-9a-f-]+$/)
  await box.press('Escape')
  await page.keyboard.press('g')
  const h = handle(page)
  await expect(h).toHaveAttribute('aria-valuenow', '44')
  await h.focus()
  await page.keyboard.press('ArrowRight')
  await expect(h).toHaveAttribute('aria-valuenow', '47')
  await page.keyboard.press('ArrowLeft')
  await page.keyboard.press('ArrowLeft')
  await expect(h).toHaveAttribute('aria-valuenow', '41')
  for (let i = 0; i < 20; i++) await page.keyboard.press('ArrowLeft')
  await expect(h).toHaveAttribute('aria-valuenow', '28') // never below 28
  for (let i = 0; i < 20; i++) await page.keyboard.press('ArrowRight')
  await expect(h).toHaveAttribute('aria-valuenow', '75')

  const grid = (await page.locator('.split').boundingBox())!
  const x = (await h.boundingBox())!.x
  expect((x - grid.x) / grid.width).toBeCloseTo(0.75, 1)

  await page.reload()
  await expect(h).toHaveAttribute('aria-valuenow', '75')
  await expect(page.getByRole('region', { name: 'Code graph' })).toBeVisible()
  await expect.poll(() => railWidth(page)).toBeLessThan(80) // folded again after the reload
})

test('dragging the handle resizes both sides', async ({ page }) => {
  await pickProject(page, 'demo')
  await page.keyboard.press('g')
  await expect.poll(() => railWidth(page)).toBeLessThan(80) // the sidebar's slide moves the grid
  const b = (await handle(page).boundingBox())!
  const grid = (await page.locator('.split').boundingBox())!
  await page.mouse.move(b.x + 3, b.y + 100)
  await page.mouse.down()
  await page.mouse.move(grid.x + grid.width * 0.6, b.y + 100, { steps: 5 })
  await page.mouse.up()
  await expect(handle(page)).toHaveAttribute('aria-valuenow', /^(59|60|61)$/)
})

test('a project with the graph off has no switch and g does nothing', async ({ page }) => {
  await pickProject(page, 'notes')
  await expect(page.getByRole('group', { name: 'Layout' })).toHaveCount(0)
  await page.keyboard.press('g')
  await expect(page.getByRole('region', { name: 'Code graph' })).toHaveCount(0)
  await page.keyboard.press('g') // g p still goes to Projects
  await page.keyboard.press('p')
  await expect(page).toHaveURL(/#\/projects$/)
})

test('g typed in the message box is a letter', async ({ page }) => {
  await pickProject(page, 'demo')
  const box = page.getByRole('textbox', { name: 'Message' })
  await box.focus()
  await box.pressSequentially('graph')
  await expect(box).toHaveValue('graph')
  await expect(page.getByRole('region', { name: 'Code graph' })).toHaveCount(0)
})

test('a narrow window stacks the chat over the graph', async ({ page }) => {
  await page.setViewportSize({ width: 800, height: 900 })
  await pickProject(page, 'demo')
  await page.keyboard.press('g')
  const chat = (await page.locator('.split > .body').boundingBox())!
  const graph = (await page.getByRole('region', { name: 'Code graph' }).boundingBox())!
  expect(graph.y).toBeGreaterThanOrEqual(chat.y + chat.height - 1)
  expect(graph.height).toBeGreaterThan(200)
  await expect(handle(page)).toBeHidden()
})

test('Ask Claude about it puts the question in the message box', async ({ page }) => {
  await pickProject(page, 'demo')
  await page.keyboard.press('g')
  const canvas = page.locator('canvas')
  await expect(canvas).toHaveAttribute('data-top-at', /^\d+,\d+$/)
  const [x, y] = (await canvas.getAttribute('data-top-at'))!.split(',').map(Number)
  await canvas.click({ position: { x, y } })
  await page.getByRole('button', { name: 'Ask Claude about it' }).click()
  await expect(page.getByRole('textbox', { name: 'Message' })).toHaveValue(/^Explain list_items\(\)/)
})
