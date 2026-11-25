import { expect, test } from '@playwright/test'

// Step 655: the demo builds with FakeGraph (10 nodes, no graphify). `demo` starts with the graph off.
test('G turns the graph on through a popup, the header shows the build, G again turns it off', async ({ page }) => {
  await page.goto('/#/projects/demo')
  await expect(page.getByRole('heading', { name: 'demo' })).toBeVisible()
  const graph = page.locator('.eta .graph')
  await expect(graph).toHaveCount(0)

  await page.keyboard.press('G')
  const popup = page.getByRole('alertdialog', { name: 'Turn the graph of demo on?' })
  await expect(popup).toBeVisible()
  await page.keyboard.press('y')
  await expect(graph).toHaveText(/^graph: 10 nodes · \dm ago$/)

  await page.reload() // the status comes back from /projects
  await expect(graph).toHaveText(/^graph: 10 nodes/)

  await page.keyboard.press('G')
  await expect(page.getByRole('alertdialog', { name: 'Turn the graph of demo off?' })).toBeVisible()
  await page.keyboard.press('y')
  await expect(graph).toHaveCount(0)
  await page.reload()
  await expect(page.getByRole('heading', { name: 'demo' })).toBeVisible()
  await expect(graph).toHaveCount(0)
})

test('n in the popup leaves the graph off', async ({ page }) => {
  await page.goto('/#/projects/notes')
  await expect(page.getByRole('heading', { name: 'notes' })).toBeVisible()
  await page.keyboard.press('G')
  await page.keyboard.press('n')
  await expect(page.getByRole('alertdialog')).toHaveCount(0)
  await expect(page.locator('.eta .graph')).toHaveCount(0)
})

test('the status wraps under the title at half screen', async ({ page }) => {
  await page.setViewportSize({ width: 743, height: 730 })
  await page.goto('/#/projects/notes')
  await expect(page.getByRole('heading', { name: 'notes' })).toBeVisible()
  await page.keyboard.press('G')
  await page.keyboard.press('y')
  const graph = page.locator('.eta .graph')
  await expect(graph).toHaveText(/^graph: 10 nodes/)
  const box = (await graph.boundingBox())!
  expect(box.x + box.width).toBeLessThanOrEqual(743)
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(743)
  await page.keyboard.press('G')
  await page.keyboard.press('y')
  await expect(graph).toHaveCount(0)
})
