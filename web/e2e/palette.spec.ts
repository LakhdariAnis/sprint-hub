import { mkdir, rm, writeFile } from 'node:fs/promises'
import { join } from 'node:path'
import { expect, test, type Page } from '@playwright/test'

// Step 512d: the command palette on the demo hubd. Its own project (`pal`) holds the steps the tests act on, so other specs keep theirs.
const step = (id: string, state: string, title: string) => `---\nstep: ${id}\ntitle: ${title}\nstate: ${state}\nby: claude\nmodel: haiku\nbranch: step/${id}-x\n---\n\n## Runs\n- 2099-01-01 09:00 · haiku · session s-${id} · 5 min · task all\n\n## Review\nverdict:\ncomment:\n`
const LONG = 'A very long title that cannot fit a half tile with the sidebar open and a state chip and the project id next to it'
let vault = ''

test.beforeAll(async ({ request }) => {
  vault = (await (await request.get('/health')).json()).vault
  await mkdir(join(vault, 'pal-repo', 'sprint', 'progress'), { recursive: true })
  const dir = join(vault, 'projects', 'pal', 'steps')
  await mkdir(dir, { recursive: true })
  await writeFile(join(vault, 'projects', 'pal', 'project.md'), '---\nname: pal\nrepo: pal-repo\nmodel: haiku\nmerge: manual\n---\n')
  await writeFile(join(dir, '951.md'), step('951', 'done', 'Waiting for you'))
  await writeFile(join(dir, '952.md'), step('952', 'todo', 'Not started'))
  await writeFile(join(dir, '953.md'), step('953', 'approved', LONG))
  await expect.poll(async () => (await request.get('/projects/pal/steps')).status()).toBe(200)
  await expect.poll(async () => (await (await request.get('/projects/pal/steps')).json()).length).toBe(3)
})

test.afterAll(async () => {
  await rm(join(vault, 'projects', 'pal'), { recursive: true })
  await rm(join(vault, 'pal-repo'), { recursive: true })
})

const box = (page: Page) => page.getByRole('dialog', { name: 'Command palette' })
const first = (page: Page) => box(page).getByRole('option').first()

for (const [w, h] of [[1920, 1080], [743, 730]]) {
  test(`${w}px: Ctrl+K opens, search, jump, / and the header box, Esc`, async ({ page }) => {
    await page.setViewportSize({ width: w, height: h })
    await page.goto('/#/today')
    await expect(page.locator('main h1, main .hd').first()).toBeVisible()
    await page.keyboard.press('Control+k')
    await expect(box(page)).toBeVisible()
    await expect(box(page).getByRole('combobox')).toBeFocused()
    // Empty query: the steps that need you, open work first (demo 102 is doing, 103 done).
    await expect(first(page)).toContainText('demo/102')
    await expect(box(page).getByRole('option').filter({ hasText: 'pal/952' })).toHaveCount(0)

    await page.keyboard.type('951')
    await expect(first(page)).toContainText('pal/951')
    await page.keyboard.press('Enter')
    await expect(page).toHaveURL(/#\/steps\/pal\/951$/)
    await expect(box(page)).toHaveCount(0)

    await page.keyboard.press('/')
    await expect(box(page)).toBeVisible()
    await page.keyboard.type('notes')
    await expect(first(page)).toContainText('project')
    await page.keyboard.press('Enter')
    await expect(page).toHaveURL(/#\/projects\/notes$/)

    await page.keyboard.press('Control+k')
    await page.keyboard.type('settings')
    await page.keyboard.press('Enter')
    await expect(page).toHaveURL(/#\/settings$/)

    // No match, then Esc.
    await page.keyboard.press('Control+k')
    await page.keyboard.type('xyzzy')
    await expect(box(page)).toContainText('No match.')
    await page.keyboard.press('Escape')
    await expect(box(page)).toHaveCount(0)
    await expect(page).toHaveURL(/#\/settings$/)

    // j and k are letters in the box; nothing behind it moves.
    await page.keyboard.press('Control+k')
    await page.keyboard.type('jk')
    await expect(box(page).getByRole('combobox')).toHaveValue('jk')
    await expect(page).toHaveURL(/#\/settings$/)
    await page.keyboard.press('Escape')

    // Down twice, Enter: the third row.
    await page.goto('/#/projects')
    await page.keyboard.press('Control+k')
    const third = box(page).getByRole('option').nth(2)
    await expect(third).toBeVisible()
    const id = (await third.locator('.sub').first().innerText()).split('/')
    await page.keyboard.press('ArrowDown')
    await page.keyboard.press('ArrowDown')
    await expect(third).toHaveAttribute('aria-selected', 'true')
    await page.keyboard.press('Enter')
    await expect(page).toHaveURL(new RegExp(`#/steps/${id[0]}/${id[1]}$`))

    // The header search box opens it too (Ctrl+N moves down, Ctrl+P up).
    await page.goto('/#/projects')
    await page.getByRole('button', { name: /Search, jump or run/ }).click()
    await expect(box(page)).toBeVisible()
    await page.keyboard.press('Control+n')
    await expect(box(page).getByRole('option').nth(1)).toHaveAttribute('aria-selected', 'true')
    await page.keyboard.press('Control+p')
    await expect(first(page)).toHaveAttribute('aria-selected', 'true')
    await page.keyboard.press('Escape')
    await expect(box(page)).toHaveCount(0)
  })
}

test('Esc gives focus back to where it was', async ({ page }) => {
  await page.goto('/#/projects')
  const search = page.getByRole('button', { name: /Search, jump or run/ })
  await search.focus()
  await page.keyboard.press('Control+k')
  await expect(box(page)).toBeVisible()
  await page.keyboard.press('Escape')
  await expect(search).toBeFocused()
})

test('actions: Approve only for a done step, and it still asks to confirm', async ({ page }) => {
  await page.goto('/#/steps/pal/951')
  await expect(page.locator('.chip.s-done')).toBeVisible()
  await page.keyboard.press('Control+k')
  await page.keyboard.type('approve')
  await expect(first(page)).toContainText('Approve')
  await expect(first(page)).toContainText('pal/951')
  await page.keyboard.press('Enter')
  await expect(page).toHaveURL(/#\/review\/pal\/951$/)
  await expect(page.getByText(/ into main\?/)).toBeVisible()
  await page.keyboard.press('Escape')
  await expect(page.getByText(/ into main\?/)).toHaveCount(0)
  await expect(page.locator('.head .chip')).toHaveText(/done/)

  // Request changes lands in the comment box, on the screen already open.
  await page.keyboard.press('Control+k')
  await page.keyboard.type('request')
  await expect(first(page)).toContainText('Request changes')
  await page.keyboard.press('Enter')
  await expect(page.getByRole('textbox').last()).toBeFocused()

  // A step that is not done offers no Approve.
  await page.goto('/#/steps/pal/952')
  await expect(page.locator('.chip.s-todo')).toBeVisible()
  await page.keyboard.press('Control+k')
  await page.keyboard.type('approve')
  await expect(box(page).getByRole('option').filter({ hasText: /^do/ })).toHaveCount(0)
  await page.keyboard.press('Control+k')
  await page.keyboard.press('Control+k')
  await page.keyboard.type('start')
  await expect(first(page)).toContainText('Start')
  await expect(first(page)).toContainText('pal/952')
})

test('743 px: rows fit, a long title ends with an ellipsis only in the list', async ({ page }) => {
  await page.setViewportSize({ width: 743, height: 730 })
  await page.goto('/#/today')
  await page.keyboard.press('Control+k')
  await page.keyboard.type('very long')
  const row = first(page)
  await expect(row).toContainText('pal/953')
  const m = await page.evaluate(() => {
    const list = document.querySelector('.list') as HTMLElement
    const t = document.querySelector('.row .t') as HTMLElement
    const b = document.querySelector('[role=dialog]') as HTMLElement
    return { listOver: list.scrollWidth > list.clientWidth, cut: t.scrollWidth > t.clientWidth, ellipsis: getComputedStyle(t).textOverflow, boxInside: b.getBoundingClientRect().right <= innerWidth, page: document.documentElement.scrollWidth <= innerWidth }
  })
  expect(m).toEqual({ listOver: false, cut: true, ellipsis: 'ellipsis', boxInside: true, page: true })
})

test('500 steps: a key press is instant', async ({ page }) => {
  const rows = Array.from({ length: 500 }, (_, i) => ({ project: 'pal', step: String(2000 + i), title: `Generated step number ${i}`, state: ['todo', 'approved', 'doing'][i % 3], by: 'claude', model: null, branch: null, sprint: null, runs: [], tasks: [], questions: [] }))
  await page.route('**/projects/pal/steps', (route) => route.fulfill({ json: rows }))
  await page.goto('/#/today')
  await page.keyboard.press('Control+k')
  await expect(box(page).getByRole('option').first()).toBeVisible()
  await expect.poll(() => page.evaluate(() => document.querySelectorAll('[role=option]').length)).toBeGreaterThan(0)
  await page.keyboard.type('step')
  await expect(box(page).getByRole('option')).toHaveCount(50)
  const ms = await page.evaluate(async () => {
    const input = document.querySelector('input[role=combobox]') as HTMLInputElement
    const t = performance.now()
    for (const c of 'number 4') {
      input.value += c
      input.dispatchEvent(new InputEvent('input', { bubbles: true }))
      await new Promise((r) => requestAnimationFrame(() => r(null)))
    }
    return (performance.now() - t) / 8
  })
  expect(ms).toBeLessThan(50)
})
