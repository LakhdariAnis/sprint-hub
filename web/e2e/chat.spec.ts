import { expect, test, type Page } from '@playwright/test'

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

// hubd --demo answers with FakeChat.
test('New chat: a message gets an answer', async ({ page }) => {
  await page.goto('/#/chat')
  await expect(page.getByRole('heading', { name: 'New chat' })).toBeVisible()
  await expect(page.getByText('What are we working on?')).toBeVisible()
  const box = page.getByRole('textbox', { name: 'Message' })
  await expect(box).toBeFocused()

  await box.fill('say hi')
  await box.press('Shift+Enter') // a new line, nothing sent
  await box.pressSequentially('twice')
  await expect(box).toHaveValue('say hi\ntwice')
  await box.press('Enter')

  await expect(page).toHaveURL(/#\/chat\/[0-9a-f-]+$/)
  await expect(page.locator('.me', { hasText: 'say hi' })).toBeVisible()
  await expect(page.getByText('What are we working on?')).toBeHidden()
  await expect(page.locator('.ai').first()).not.toBeEmpty()
  await expect(page.getByText('thinking…')).toBeHidden()

  // Esc leaves the box, then the plain keys work: 2 = Today, n = New chat.
  await box.press('Escape')
  await page.keyboard.press('2')
  await expect(page).toHaveURL(/#\/today$/)
  await page.keyboard.press('n')
  await expect(page).toHaveURL(/#\/chat$/)
  await expect(page.getByText('What are we working on?')).toBeVisible()
  await expect(page.getByRole('textbox', { name: 'Message' })).toBeFocused()
})

test('a chat that hubd refuses shows the reason in the pane', async ({ page }) => {
  await page.route('**/chats', (route) => route.fulfill({ status: 409, json: { detail: '3 chats are open already' } }))
  await page.goto('/#/chat')
  const box = page.getByRole('textbox', { name: 'Message' })
  await box.fill('hello')
  await box.press('Enter')
  await expect(page.getByRole('alert').filter({ hasText: '3 chats are open already' })).toBeVisible()
  await expect(box).toHaveValue('hello') // not lost
})

// Step 605: pills and the / menu.
// hubd refuses a model change while Claude answers: wait for the turn to end.
const answered = (page: Page) => expect.poll(async () => (await (await page.request.get(`/chats/${page.url().split('/').pop()}`)).json()).busy).toBe(false)

test('/mo ↵ 1 sets opus; the menu filters, Esc keeps the text', async ({ page }) => {
  await page.goto('/#/chat')
  const box = page.getByRole('textbox', { name: 'Message' })
  const pill = (name: string) => page.locator('.pill', { hasText: name })
  await expect(pill('model')).toContainText('sonnet')
  await expect(pill('effort')).toContainText('medium')
  await expect(pill('project')).toContainText('none')

  await box.press('/')
  await expect(page.getByRole('listbox', { name: 'Commands' }).getByRole('option')).toHaveCount(6)
  await box.pressSequentially('mo')
  await expect(page.getByRole('listbox', { name: 'Commands' }).getByRole('option')).toHaveCount(1)
  await expect(page.locator('.menu u')).toHaveText('mo')

  await box.press('Escape') // closes the menu, the text stays, the box keeps the cursor
  await expect(page.locator('.menu')).toBeHidden()
  await expect(box).toHaveValue('/mo')
  await expect(box).toBeFocused()
  await box.press('Backspace')
  await expect(page.locator('.menu')).toBeVisible()
  await box.pressSequentially('o')

  await box.press('Enter') // on a command: its options
  const options = page.getByRole('listbox', { name: 'Options of /model' }).getByRole('option')
  await expect(options).toHaveText([/1\s*opus/, /2\s*sonnet\s*current/, /3\s*haiku/])
  await box.press('1')
  await expect(pill('model')).toContainText('opus')
  await expect(box).toHaveValue('')
  await expect(page.locator('.menu')).toBeHidden()
})

test('model changes after the first message, the chat goes on; project pill; /clear keeps pills', async ({ page }) => {
  await page.goto('/#/chat')
  const box = page.getByRole('textbox', { name: 'Message' })
  const pill = (name: string) => page.locator('.pill', { hasText: name })

  await pill('project').click() // opens /project with the options column
  await page.getByRole('listbox', { name: 'Options of /project' }).getByRole('option', { name: /demo/ }).click()
  await expect(pill('project')).toContainText('demo')

  await box.fill('first')
  await box.press('Enter')
  await expect(page).toHaveURL(/#\/chat\/[0-9a-f-]+$/)
  await expect(page.getByText('thinking…')).toBeHidden()
  await expect(pill('project')).toBeDisabled()
  await answered(page)

  const patch = page.waitForRequest((r) => r.method() === 'PATCH')
  await box.pressSequentially('/model')
  await box.press('Tab')
  await box.press('3')
  expect((await patch).postDataJSON()).toEqual({ model: 'haiku' })
  await expect(pill('model')).toContainText('haiku')
  await box.fill('second')
  await box.press('Enter')
  await expect(page.getByText('second', { exact: true })).toBeVisible()
  await expect(page.locator('.me', { hasText: /^first$/ })).toBeVisible() // same chat

  await box.fill('/clear')
  await box.press('Enter')
  await expect(page).toHaveURL(/#\/chat$/)
  await expect(page.getByText('What are we working on?')).toBeVisible()
  await expect(pill('model')).toContainText('haiku')
  await expect(pill('project')).toContainText('demo')
  await expect(pill('project')).toBeEnabled()
})

test('a change hubd refuses shows its reason and keeps the pill', async ({ page }) => {
  await page.route('**/chats/*', (route) => (route.request().method() === 'PATCH' ? route.fulfill({ status: 409, json: { detail: 'Claude is answering' } }) : route.continue()))
  await page.goto('/#/chat')
  const box = page.getByRole('textbox', { name: 'Message' })
  await box.fill('hi')
  await box.press('Enter')
  await expect(page.getByText('thinking…')).toBeHidden()
  await answered(page)
  await box.pressSequentially('/effort')
  await box.press('Tab')
  await box.press('3')
  await expect(page.getByRole('alert').filter({ hasText: 'Claude is answering' })).toBeVisible()
  await expect(page.locator('.pill', { hasText: 'effort' })).toContainText('medium')
})

// Step 606: a chat knows its project, sprint or step; hubd says what it loaded in the chip.
test('/project from a starter card, then the chip shows what is loaded; it stays after the send', async ({ page }) => {
  await page.goto('/#/chat')
  const chip = page.locator('.chip')
  await expect(chip).toBeHidden() // a plain chat is told nothing
  await page.locator('.starter', { hasText: '/project' }).click()
  await page.getByRole('listbox', { name: 'Options of /project' }).getByRole('option', { name: /demo/ }).click()
  await expect(chip).toHaveText(/^context sprints \(\d+\.\d kB\) · no README\.md$/)

  await page.locator('.starter', { hasText: '/sprint' }).click()
  await page.getByRole('listbox', { name: 'Options of /sprint' }).getByRole('option', { name: /sprint 1/ }).click()
  await expect(page.locator('.pill', { hasText: 'sprint' })).toContainText('1')
  await expect(chip).toContainText('sprint 1 + ')

  // Earlier tests hold the demo's 3 live chats: answer the open and the message here (pytest covers hubd's side).
  const id = '00000000-0000-4000-8000-000000000606'
  const told = { label: 'sprint 1 + steps + sprints', size: 2100, notes: [] }
  await page.route('**/chats', (route) => route.fulfill({ json: { id, context: told } }))
  await page.route(`**/chats/${id}/message`, (route) => route.fulfill({ json: {} }))
  const opened = page.waitForRequest((r) => r.method() === 'POST' && r.url().endsWith('/chats'))
  const box = page.getByRole('textbox', { name: 'Message' })
  await box.fill('what is the sprint goal?')
  await box.press('Enter')
  expect((await opened).postDataJSON()).toMatchObject({ project: 'demo', sprint: '1', step: null })
  await expect(page).toHaveURL(/#\/chat\/[0-9a-f-]+$/)
  await expect(chip).toHaveText('context sprint 1 + steps + sprints (2.1 kB)') // what hubd told this chat
  await expect(page.locator('.pill', { hasText: 'sprint' })).toBeDisabled()
})

test('c on a Step opens New chat with that step set; c on a Project with the project', async ({ page }) => {
  await page.goto('/#/steps/demo/104')
  await expect(page.getByText('Checklist')).toBeVisible()
  await page.keyboard.press('c')
  await expect(page).toHaveURL(/#\/chat$/)
  await expect(page.locator('.pill', { hasText: 'step' })).toContainText('104')
  await expect(page.locator('.pill', { hasText: 'project' })).toContainText('demo')
  await expect(page.locator('.chip')).toContainText(/spec \+ checklist \+ .*diffstat/)

  await page.goto('/#/projects/notes')
  await expect(page.getByRole('heading', { name: /notes/ })).toBeVisible()
  await page.keyboard.press('c')
  await expect(page).toHaveURL(/#\/chat$/)
  await expect(page.locator('.pill', { hasText: 'project' })).toContainText('notes')
  await expect(page.locator('.pill', { hasText: 'step' })).toBeHidden()
  await expect(page.locator('.chip')).toContainText('sprints')
})

// Step 607: Claude asks before a command; FakeChat asks on "run …". A chat with no project is refused without a card.
test('permission card: d denies, a allows, A allows for the chat; a plain chat is refused', async ({ page }) => {
  await page.setViewportSize({ width: 960, height: 1000 }) // half of a 1920 screen
  await page.goto('/#/chat')
  const box = page.getByRole('textbox', { name: 'Message' })
  await page.locator('.pill', { hasText: 'project' }).click()
  await page.getByRole('listbox', { name: 'Options of /project' }).getByRole('option', { name: /demo/ }).click()
  const cards = page.getByRole('group', { name: 'Permission: Bash' })
  const ask = async (text: string) => {
    await box.fill(text)
    await box.press('Enter')
  }

  await ask('run rm -rf build')
  const card = cards.last()
  await expect(card).toContainText('rm -rf build')
  for (const name of ['Allow', 'Deny', 'Allow for this chat']) {
    const b = card.getByRole('button', { name, exact: true })
    await expect(b).toBeInViewport({ ratio: 1 }) // reads in full at half screen
  }
  await expect(box).toBeFocused()
  await page.keyboard.press('d') // the box is empty: the key answers the card
  await expect(card).toContainText('Denied')
  await expect(page.locator('.ai').last()).toContainText('Not run: Anis denied')
  await expect(box).toBeFocused()

  await ask('run ls')
  await expect(cards).toHaveCount(2)
  await box.press('Escape')
  await page.keyboard.press('a')
  await expect(cards.last()).toContainText('Allowed')
  await expect(page.locator('.ai').last()).toContainText('has one file.')

  await ask('run ls -a')
  await expect(cards).toHaveCount(3)
  await page.keyboard.press('Shift+A')
  await expect(cards.last()).toContainText('Allowed for this chat')
  await answered(page)
  await ask('run pwd')
  await answered(page)
  await expect(page.locator('.me')).toHaveCount(4)
  await expect(cards).toHaveCount(3) // no card for pwd

  await page.goto('/#/chat')
  await page.locator('.pill', { hasText: 'project' }).click()
  await page.getByRole('listbox', { name: 'Options of /project' }).getByRole('option').first().click()
  await expect(page.locator('.pill', { hasText: 'project' })).toContainText('none')
  await ask('run cat ~/.bashrc')
  await expect(cards.last()).toContainText('Refused: A chat with no project never runs commands')
  await expect(page.locator('.ai').last()).toContainText('Not run:')
})

// Step 608: tool lines, the cost line, j k, Stop. FakeChat runs `Bash ls` in every answer; "stall …" takes 40 times longer.
test('a tool line opens with ↵ or a click; the cost line; j k pick turns', async ({ page }) => {
  await page.goto('/#/chat')
  const box = page.getByRole('textbox', { name: 'Message' })
  await box.fill('say hi')
  await box.press('Enter')
  await answered(page)

  const line = page.locator('.tl')
  await expect(line).toHaveText(/Bash ls/)
  await expect(line).toHaveAttribute('aria-expanded', 'false')
  await expect(page.getByLabel('Input')).toBeHidden()
  await expect(line.locator('.tn')).toHaveCSS('text-overflow', 'ellipsis')
  await line.click()
  await expect(page.getByLabel('Input')).toHaveText('command: ls')
  await expect(page.getByLabel('Result')).toHaveText('README.md')
  await line.click()
  await expect(page.getByLabel('Input')).toBeHidden()

  await expect(page.locator('.cost')).toHaveText(/^sonnet · [\d.]+ s · 4\.1k in \/ 380 out · \$0\.02$/)

  // NORMAL mode: j picks the turn, ↵ opens its tool lines, ↵ again closes them, k stays on the first turn.
  await box.fill('second')
  await box.press('Enter')
  await answered(page)
  await box.press('Escape')
  const turns = page.locator('.turn')
  await expect(turns.locator('.tool')).toHaveCount(2)
  await page.keyboard.press('j')
  await expect(turns.nth(0)).toHaveClass(/foc/)
  await page.keyboard.press('j')
  await expect(turns.nth(1)).toHaveClass(/foc/)
  await expect(turns.nth(0)).not.toHaveClass(/foc/)
  await page.keyboard.press('Enter')
  await expect(page.getByLabel('Input')).toHaveCount(1)
  await expect(turns.nth(1).getByLabel('Input')).toBeVisible()
  await page.keyboard.press('Enter')
  await expect(page.getByLabel('Input')).toHaveCount(0)
  await page.keyboard.press('k')
  await page.keyboard.press('k')
  await expect(turns.nth(0)).toHaveClass(/foc/)
})

test('Stop and Esc Esc end a turn mid-way, the text stays marked stopped, the chat goes on', async ({ page }) => {
  await page.goto('/#/chat')
  const box = page.getByRole('textbox', { name: 'Message' })
  const stop = page.getByRole('button', { name: /^Stop/ })
  await expect(stop).toBeHidden()

  await box.fill('stall essay')
  await box.press('Enter')
  await expect(page.locator('.ai').first()).toContainText('This is') // the first piece came
  await stop.click()
  await expect(page.getByRole('status').filter({ hasText: /^stopped$/ })).toHaveCount(1)
  await expect(page.locator('.ai').first()).toContainText('This is') // text kept
  await expect(page.locator('.ai').first()).not.toContainText('has one file.')
  await expect(stop).toBeHidden()
  await expect(page.locator('.cost')).toHaveCount(0) // no turn_end came

  await box.fill('stall again')
  await box.press('Enter')
  await expect(page.locator('.ai').nth(1)).toContainText('This is')
  await box.press('Escape') // the first Esc leaves the box, the second one stops
  await expect(stop).toBeVisible()
  await page.keyboard.press('Escape')
  await expect(page.getByRole('status').filter({ hasText: /^stopped$/ })).toHaveCount(2)

  await box.fill('after')
  await box.press('Enter')
  await answered(page)
  await expect(page.locator('.ai').last()).toContainText('has one file.')
  await expect(page.locator('.cost')).toHaveCount(1)
})

// Step 609: chats stay in the sidebar's OPEN next to the steps, can be renamed and closed. hubd's restart is covered in pytest (the demo cannot restart).
test('two chats under OPEN: 6 and 7 open them, R renames one, x closes one and the vault keeps it', async ({ page, request }) => {
  const tag = Math.random().toString(36).slice(2, 7)
  const box = page.getByRole('textbox', { name: 'Message' })
  const row = (name: string | RegExp) => page.getByRole('navigation', { name: 'Tabs' }).getByRole('link', { name })
  const send = async (text: string) => {
    await box.fill(text)
    await box.press('Enter')
    await expect(page).toHaveURL(/#\/chat\/[0-9a-f-]+$/)
    await expect(page.locator('.ai').first()).not.toBeEmpty()
  }

  await page.goto('/#/chat')
  await expect(row('New chat, unsaved')).toContainText('new') // not saved until you send
  await send(`alpha ${tag}`)
  const first = page.url()
  await expect(row(`Chat: alpha ${tag}`)).toBeVisible()
  await expect(row('New chat, unsaved')).toBeHidden()

  await box.press('Escape')
  await page.keyboard.press('n')
  await expect(page).toHaveURL(/#\/chat$/)
  await send(`beta ${tag}`)
  const second = page.url()
  const [alpha, beta] = [row(`Chat: alpha ${tag}`), row(`Chat: beta ${tag}`)]
  await expect(beta).toBeVisible()
  const digit = async (r: typeof alpha) => (await r.locator('.k').innerText()).trim()
  expect(Number(await digit(beta))).toBeLessThan(Number(await digit(alpha))) // newest first

  // A reload keeps both under OPEN, in the same order, and the chat on show.
  await page.reload()
  await expect(page.locator('.me', { hasText: `beta ${tag}` })).toBeVisible()
  await expect(alpha).toBeVisible()
  expect(Number(await digit(beta))).toBeLessThan(Number(await digit(alpha)))

  // The digit of a row opens its chat.
  await box.press('Escape')
  await page.keyboard.press(await digit(alpha))
  await expect(page).toHaveURL(first)
  await expect(page.locator('.me', { hasText: `alpha ${tag}` })).toBeVisible()
  await box.press('Escape') // a chat on show takes the cursor
  await page.keyboard.press(await digit(beta))
  await expect(page).toHaveURL(second)

  // R renames it: the sidebar, the header and the vault's list show the new name.
  await box.press('Escape')
  await page.keyboard.press('Shift+R')
  const name = page.getByRole('textbox', { name: 'Chat name' })
  await expect(name).toBeFocused()
  await name.fill(`Renamed ${tag}`)
  await name.press('Enter')
  await expect(row(`Chat: Renamed ${tag}`)).toBeVisible()
  await expect(row(`Chat: beta ${tag}`)).toBeHidden()
  await expect(page.getByRole('heading', { name: `Renamed ${tag}` })).toBeVisible()
  const id = second.split('/').pop()!
  const listed = async () => ((await (await request.get('/chats')).json()) as { id: string; title: string; open: boolean }[]).find((c) => c.id === id)
  expect((await listed())?.title).toBe(`Renamed ${tag}`)

  // Esc in the name box keeps the old name.
  await box.press('Escape')
  await page.keyboard.press('Shift+R')
  await name.fill('nope')
  await name.press('Escape')
  await expect(page.getByRole('heading', { name: `Renamed ${tag}` })).toBeVisible()

  // x closes it: out of OPEN, still in the vault, back on New chat.
  await box.press('Escape')
  await page.keyboard.press('x')
  await expect(page).toHaveURL(/#\/chat$/)
  await expect(row(`Chat: Renamed ${tag}`)).toBeHidden()
  await expect(alpha).toBeVisible()
  expect(await listed()).toMatchObject({ title: `Renamed ${tag}`, open: false })
})

// Step 610: the answer is drawn from markdown, never as HTML.
test('answers show code, lists, a table and links; markup stays text; wide code scrolls in its block', async ({ page }) => {
  await page.goto('/#/chat')
  const box = page.getByRole('textbox', { name: 'Message' })
  await box.fill('md please')
  await box.press('Enter')
  const ai = page.locator('.ai')
  await expect(ai.getByRole('heading', { name: 'Hello' }).or(ai.locator('.h2', { hasText: 'Hello' }))).toBeVisible()
  await expect(ai.locator('b', { hasText: 'bold' })).toBeVisible()
  await expect(ai.locator('li', { hasText: 'two' })).toBeVisible()
  await expect(ai.locator('li li', { hasText: 'nested' })).toBeVisible()
  await expect(ai.locator('td')).toHaveText(['1', '2'])
  const code = ai.locator('.code')
  await expect(code.locator('pre')).toHaveText("print('hi')")

  // The link opens outside the app: a new tab, this page stays.
  const link = ai.getByRole('link', { name: 'a link' })
  await expect(link).toHaveAttribute('href', 'https://example.org/x')
  await expect(link).toHaveAttribute('target', '_blank')
  await expect(link).toHaveAttribute('rel', /noopener/)

  // Markup in the answer is text.
  await expect(ai).toContainText('<b>hi</b><script>window.__xss = 1</script>')
  await expect(ai.locator('script')).toHaveCount(0)
  expect(await page.evaluate(() => (window as unknown as { __xss?: number }).__xss)).toBeUndefined()

  // The copy button and `y` on the focused block put the code on the clipboard.
  await page.context().grantPermissions(['clipboard-read', 'clipboard-write'])
  await code.getByRole('button', { name: 'Copy code' }).click()
  expect(await page.evaluate(() => navigator.clipboard.readText())).toBe("print('hi')")
  await page.evaluate(() => navigator.clipboard.writeText(''))
  await code.focus()
  await page.keyboard.press('y')
  await expect(code.getByRole('button', { name: 'Copy code' })).toHaveText('copied')
  expect(await page.evaluate(() => navigator.clipboard.readText())).toBe("print('hi')")

  // Wide code scrolls inside the block; the page does not.
  await code.locator('pre').evaluate((el) => (el.textContent = 'x'.repeat(400)))
  expect(await code.locator('pre').evaluate((el) => el.scrollWidth > el.clientWidth)).toBe(true)
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
})

// Step 611a: a chat with an answer (markdown, a tool line, the cost line) in the Sprint 4 sizes.
for (const [w, h] of [[1920, 1080], [960, 1080], [743, 730], [743, 540]]) {
  test(`a chat at ${w}x${h}: the box and the last answer in view, nothing wider than the window, no page scroll`, async ({ page }) => {
    await page.setViewportSize({ width: w, height: h })
    await page.goto('/#/chat')
    const box = page.getByRole('textbox', { name: 'Message' })
    await expect(box).toBeInViewport({ ratio: 1 })
    for (const text of ['say hi', 'md please']) { // a tool line, then the markdown
      await box.fill(text)
      await box.press('Enter')
      await answered(page)
    }
    const ai = page.locator('.ai').last()
    await expect(ai.locator('.code')).toBeVisible()
    await expect(page.locator('.tl').last()).toBeVisible()
    await expect(page.locator('.cost').last()).toBeInViewport()
    await expect(box).toBeInViewport({ ratio: 1 })
    await expect(page.getByRole('heading', { name: 'say hi' })).toBeInViewport()
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
    expect(await page.locator('main').evaluate((m) => m.scrollHeight <= m.clientHeight && m.scrollWidth <= m.clientWidth)).toBe(true)
    expect(await ai.evaluate((a) => a.scrollWidth <= a.clientWidth)).toBe(true)
  })
}

// Step 612b: hubd's popup (the demo records it) shows when no focused window shows the chat.
test('Claude answered pops up when the window looks elsewhere, not when it shows the chat', async ({ page, request }) => {
  const popups = async () => (await (await request.get('/demo/notifications')).json()) as { title: string; body: string }[]
  const box = page.getByRole('textbox', { name: 'Message' })
  await page.goto('/#/chat')
  const before = (await popups()).length

  await box.fill('say quiet')
  await box.press('Enter')
  await expect(page.locator('.cost')).toHaveCount(1) // the turn ended
  expect(await popups()).toHaveLength(before)

  await page.goto('/#/chat')
  await box.fill('stall away')
  await box.press('Enter')
  await expect(page).toHaveURL(/#\/chat\/[0-9a-f-]+$/)
  await page.evaluate(() => (location.hash = '#/today')) // reports "no chat shown"
  await expect.poll(async () => (await popups()).slice(before), { timeout: 20_000 }).toEqual([{ title: 'Claude answered', body: 'stall away' }])
})

// Step 652: the home state, the soft card, the floating menu.
test('home: greeting and box in the middle, round chips; the box moves to the bottom after the first send', async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 900 })
  await page.goto('/#/chat')
  const hi = page.getByText('What are we working on?')
  const form = page.locator('form.cmp')
  await expect(hi).toBeVisible()
  await expect(hi).toHaveCSS('font-size', '36px')
  await expect(page.locator('.starter')).toHaveText(['/project', '/sprint', '/step'])
  await expect(page.locator('.starter').first()).toHaveCSS('border-radius', '999px')
  const mid = async () => {
    const f = (await form.boundingBox())!, b = (await page.locator('.body').boundingBox())!
    return (f.y + f.height / 2 - b.y) / b.height
  }
  expect(await mid()).toBeGreaterThan(0.35)
  expect(await mid()).toBeLessThan(0.65)
  expect((await hi.boundingBox())!.y).toBeLessThan((await page.locator('.box').boundingBox())!.y)
  await expect(page.locator('.meta')).toBeHidden() // no chat yet: the pills say model and project

  await page.locator('.starter', { hasText: '/sprint' }).click() // the menu opens above the box with the options column ready
  const menu = page.locator('.menu')
  await expect(menu).toBeVisible()
  await expect(menu).toHaveCSS('border-radius', '14px')
  await expect(menu).not.toHaveCSS('box-shadow', 'none')
  expect((await menu.boundingBox())!.y + (await menu.boundingBox())!.height).toBeLessThanOrEqual((await page.locator('.box').boundingBox())!.y)
  await page.keyboard.press('Escape')

  const box = page.getByRole('textbox', { name: 'Message' })
  await box.fill('say hi')
  await box.press('Enter')
  await expect(page.locator('.me', { hasText: 'say hi' })).toBeVisible()
  await expect(page.locator('.starter')).toHaveCount(0)
  await expect.poll(mid).toBeGreaterThan(0.85) // bottom of the page
  await expect(page.locator('.meta')).toHaveText(/^sonnet · none$/)
  await answered(page)
  await expect(page.locator('.tl .ts').first()).toHaveText('✓')
  await expect(page.locator('.tl').first()).toHaveCSS('border-top-width', '0px')
  await expect(page.locator('.cost')).toHaveCSS('font-size', '12px')
})

test('the card is a soft block with a filled Allow; the chip sits inside the box', async ({ page }) => {
  await page.goto('/#/chat')
  await page.locator('.pill', { hasText: 'project' }).click()
  await page.getByRole('listbox', { name: 'Options of /project' }).getByRole('option', { name: /demo/ }).click()
  await expect(page.locator('.box .chip')).toBeVisible()
  await expect(page.locator('.box .chip')).toHaveCSS('font-size', '12.5px')
  const box = page.getByRole('textbox', { name: 'Message' })
  await box.fill('run ls')
  await box.press('Enter')
  const card = page.getByRole('group', { name: 'Permission: Bash' }).last()
  await expect(card).toContainText('ls')
  await expect(card).toHaveCSS('border-top-width', '0px')
  await expect(card.getByRole('button', { name: 'Allow', exact: true })).not.toHaveCSS('background-color', 'rgba(0, 0, 0, 0)')
  await expect(card.getByRole('button', { name: 'Deny' })).toHaveCSS('background-color', 'rgba(0, 0, 0, 0)')
  await expect(page.locator('.meta')).toHaveText(/sonnet · demo/)
  await page.keyboard.press('a')
  await expect(card).toContainText('Allowed')
})
