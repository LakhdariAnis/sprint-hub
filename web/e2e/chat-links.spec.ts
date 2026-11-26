import { expect, test, type Page } from '@playwright/test'

// Step 659: a graph query in a chat lights its nodes, code in answers that names a node is a chip.
// The demo's FakeChat answers a message that starts with "graph" with a graph tool line (2 nodes) and an answer with
// `list_items()` and `src/ui.py` (in the graph) and `not_a_node()` (not). `demo` has the graph on, `notes` off.
async function ask(page: Page, project: string) {
  await page.goto('/#/chat')
  await page.locator('.pill', { hasText: 'project' }).click()
  await page.getByRole('listbox', { name: 'Options of /project' }).getByRole('option', { name: new RegExp(project) }).click()
  const box = page.getByRole('textbox', { name: 'Message' })
  await box.fill('graph what depends on list_items?')
  await box.press('Enter')
  await expect(page.locator('.cost')).toBeVisible() // the turn ended
  await box.press('Escape') // out of the box: keys act on the screen
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
const map = (page: Page) => page.getByRole('region', { name: 'Code graph' })
const banner = (page: Page) => map(page).getByRole('status')

test('the tool line lights its nodes, Show all clears, the line lights them again', async ({ page }) => {
  await ask(page, 'demo')
  await expect(map(page)).toHaveCount(0)
  const line = page.locator('.tl .tn')
  await line.click() // opens the split and lights
  await expect(banner(page)).toHaveText(/2 nodes read list_items\(\)/)
  await banner(page).getByRole('button', { name: 'Show all' }).click()
  await expect(banner(page)).toHaveCount(0)
  await line.click()
  await expect(banner(page)).toHaveText(/2 nodes read list_items\(\)/)
})

test('the newest query lights by default when the split opens', async ({ page }) => {
  await ask(page, 'demo')
  await page.keyboard.press('g')
  await expect(banner(page)).toHaveText(/2 nodes read list_items\(\)/)
  await page.locator('.tl .tw').click() // the arrow opens the input and result
  await expect(page.getByLabel('Result', { exact: true })).toContainText('serve()')
})

test('a chip opens the split and lights the node with its links, other code stays plain', async ({ page }) => {
  await ask(page, 'demo')
  const ai = page.locator('.ai')
  await expect(ai.locator('.node')).toHaveText(['list_items()', 'draw_list()', 'src/ui.py'])
  await expect(ai.locator('code', { hasText: 'not_a_node()' })).toBeVisible()
  await expect(ai.locator('.node', { hasText: 'not_a_node()' })).toHaveCount(0)
  await expect(ai.locator('.node', { hasText: 'draw_list()' })).toHaveCount(1) // a label in the graph is a chip too
  await expect(map(page)).toHaveCount(0)
  await ai.locator('.node', { hasText: 'list_items()' }).click()
  await expect(banner(page)).toHaveText(/list_items\(\) and its links · 5 nodes/)
  await banner(page).getByRole('button', { name: 'Show all' }).click()
  await expect(banner(page)).toHaveCount(0)
  await ai.locator('.node', { hasText: 'src/ui.py' }).focus()
  await page.keyboard.press('Enter') // a chip works from the keyboard
  await expect(banner(page)).toHaveText(/src\/ui\.py and its links/)
})

test('a chat with the graph off has no chips and a plain tool line', async ({ page }) => {
  await ask(page, 'notes')
  await expect(page.locator('.ai code', { hasText: 'list_items()' })).toBeVisible()
  await expect(page.locator('.node')).toHaveCount(0)
  await expect(page.locator('.tl .lit')).toHaveCount(0)
})

test('at half screen the chips wrap inside the text', async ({ page }) => {
  await page.setViewportSize({ width: 743, height: 730 })
  await ask(page, 'demo')
  const ai = (await page.locator('.ai').first().boundingBox())!
  for (const chip of await page.locator('.ai .node').all()) {
    const b = (await chip.boundingBox())!
    expect(b.x + b.width).toBeLessThanOrEqual(ai.x + ai.width + 1)
  }
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
})
