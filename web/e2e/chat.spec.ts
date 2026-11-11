import { expect, test } from '@playwright/test'

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
