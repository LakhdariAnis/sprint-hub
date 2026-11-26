import { expect, test } from '@playwright/test'

// Step 658a: the graph pane on the demo's FakeGraph (10 nodes, 13 links, 3 groups), at #/graph/<project>.
test('the pane draws the map, the legend hides a group, search lights matches', async ({ page }) => {
  await page.goto('/#/graph/demo')
  const pane = page.getByRole('region', { name: 'Code graph' })
  await expect(pane.getByText('10 nodes · 13 links · 3 groups')).toBeVisible()
  await expect(pane.locator('canvas')).toHaveAttribute('data-top-at', /^\d+,\d+$/)

  const api = pane.getByRole('group', { name: 'Groups' }).getByRole('button', { name: 'api · 4' })
  await api.click()
  await expect(api).toHaveAttribute('aria-pressed', 'false')
  await api.click()
  await expect(api).toHaveAttribute('aria-pressed', 'true')

  await pane.getByLabel('Find in graph').fill('store')
  await expect(pane.getByRole('status')).toHaveText(/3 match “store”/)
  await pane.getByRole('button', { name: 'Show all' }).click()
  await expect(pane.getByRole('status')).toHaveCount(0)
  await expect(pane.getByLabel('Find in graph')).toHaveValue('')
})

test('a click on a node opens its card, What depends on it lights its dependents', async ({ page }) => {
  await page.goto('/#/graph/demo')
  const canvas = page.locator('canvas')
  const [x, y] = (await canvas.getAttribute('data-top-at'))!.split(',').map(Number)
  await canvas.click({ position: { x, y } })
  const card = page.getByRole('dialog', { name: 'list_items()' })
  await expect(card).toContainText('src/api.py:14')
  await expect(card).toContainText('api · 2 in · 1 out')
  await card.getByRole('button', { name: 'What depends on it' }).click()
  await expect(page.getByRole('status')).toHaveText(/4 nodes depend on list_items\(\)/)
  await card.getByRole('button', { name: 'Close' }).click()
  await expect(card).toHaveCount(0)
})

test('the Report tab lists the most connected nodes and the groups', async ({ page }) => {
  await page.goto('/#/graph/demo')
  await page.getByRole('button', { name: 'Report' }).click()
  const gods = page.locator('.gods code')
  await expect(gods.first()).toHaveText('list_items()')
  await expect(page.getByText('No import cycle.')).toBeVisible()
  await expect(page.locator('.grp')).toHaveCount(3)
})

test('a project with the graph off says how to turn it on', async ({ page }) => {
  await page.goto('/#/graph/notes')
  await expect(page.getByText('Code graph is off · G turns it on')).toBeVisible()
})
