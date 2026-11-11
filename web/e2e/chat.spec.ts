import { expect, test, type Page } from '@playwright/test'

// Step 604: the app opens on New chat; hubd --demo answers with FakeChat.
test('opens on New chat, a message gets an answer', async ({ page }) => {
  await page.goto('/')
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
  await expect(page.getByText('say hi\ntwice')).toBeVisible()
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
  await expect(page.getByText('first', { exact: true })).toBeVisible() // same chat

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
