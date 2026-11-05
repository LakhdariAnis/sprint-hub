import { type ChildProcess, spawn } from 'node:child_process'
import { mkdir, mkdtemp, readFile, rm, writeFile } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { dirname, join } from 'node:path'
import { expect, test } from '@playwright/test'

// Step 504a: the app says what is wrong. The demo hubd on 8765 stays untouched; the first-run tests start their own hubd on another port, with an empty home.
const PORT = 8799
const url = `http://127.0.0.1:${PORT}`
const python = join(process.cwd(), '..', '.venv', 'bin', 'python')

async function hubd(vault: string, home: string): Promise<ChildProcess> {
  const proc = spawn(python, ['-m', 'hubd'], { env: { ...process.env, HOME: home, HUB_VAULT: vault, HUBD_PORT: String(PORT) }, stdio: 'ignore' })
  for (let i = 0; i < 100; i++) {
    try {
      if ((await fetch(`${url}/health`)).ok) return proc
    } catch {}
    await new Promise((r) => setTimeout(r, 100))
  }
  proc.kill()
  throw new Error('hubd did not start')
}

const stop = (proc: ChildProcess) => new Promise((done) => (proc.exitCode !== null ? done(null) : (proc.once('exit', done), proc.kill('SIGTERM'))))

test('no vault: Projects says how to init, the others point to it, the vault appears by itself, hubd down shows a banner that clears', async ({ page }) => {
  const home = await mkdtemp(join(tmpdir(), 'hub-first-'))
  const vault = join(home, 'Hub')
  let proc = await hubd(vault, home)
  try {
    await page.goto(`${url}/#/projects`)
    await expect(page.getByText(`No vault at ${vault}`)).toBeVisible()
    await expect(page.getByText('uv run hubd init')).toBeVisible()
    // A missing vault is not a broken file (the theme notice of this empty home is the only one).
    expect((await (await fetch(`${url}/errors`)).json()).filter((e: { path: string }) => e.path.startsWith(vault))).toEqual([])
    for (const key of ['2', '3', '4']) {
      await page.keyboard.press(key)
      await expect(page.getByText(/No projects yet. Run uv run hubd init/).first()).toBeVisible()
    }
    await page.keyboard.press('1')

    // `hubd init` makes the vault: the project shows, with no reload, and says to import.
    const repo = join(home, 'repo')
    await mkdir(repo)
    await mkdir(join(vault, 'projects', 'late', 'steps'), { recursive: true })
    await writeFile(join(vault, 'projects', 'late', 'project.md'), `---\nname: late\nrepo: ${repo}\nmodel: sonnet\nmerge: manual\n---\n`)
    await expect(page.getByText('uv run hubd import').first()).toBeVisible({ timeout: 8000 })
    await expect(page.getByText('late', { exact: true })).toBeVisible()

    // The repo goes: the project says so.
    await rm(repo, { recursive: true })
    await page.reload()
    await expect(page.getByText(/repo not found/)).toBeVisible()

    await stop(proc)
    await expect(page.getByRole('alert')).toContainText('hubd is not running', { timeout: 10000 })
    await page.setViewportSize({ width: 743, height: 730 })
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
    proc = await hubd(vault, home)
    await expect(page.getByRole('alert')).toHaveCount(0, { timeout: 20000 })
  } finally {
    await stop(proc)
    await rm(home, { recursive: true, force: true })
  }
})

test('a broken step file counts in the status line, lists with file, line and field, and leaves when fixed', async ({ page, request }) => {
  // A copy of 301 under its own id: loop.spec.ts runs 301 in another worker, restoring it here would undo that run.
  const { path: from } = await (await request.get('/steps/notes/301')).json()
  const path = join(dirname(from), '398.md')
  const original = (await readFile(from, 'utf8')).replace(/^step: .*$/m, 'step: 398')
  const before = (await (await request.get('/errors')).json()).filter((e: { level?: string }) => e.level !== 'warning').length // warnings have their own button
  const count = (n: number) => page.getByRole('button', { name: new RegExp(`⚠ ${n} broken file`) })
  await page.goto('/#/projects/notes')
  await expect(page.getByRole('button', { name: /Sprint 3/ })).toBeVisible()
  try {
    await writeFile(path, original.replace(/^state: .*$/m, 'state: banana'))
    await expect(count(before + 1)).toBeVisible({ timeout: 5000 })
    await count(before + 1).click()
    const row = page.getByRole('dialog').locator('.er', { hasText: '398.md' })
    await expect(row).toContainText(/398\.md:\d+/)
    await expect(row).toContainText('state')
    await page.setViewportSize({ width: 743, height: 730 })
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
    await page.keyboard.press('Escape')
    await expect(page.getByRole('dialog')).toHaveCount(0)
    await page.keyboard.press('e') // the key opens it too
    await expect(page.getByRole('dialog')).toBeVisible()
    await page.keyboard.press('Escape')
  } finally {
    await rm(path, { force: true })
  }
  await expect(page.getByRole('dialog')).toHaveCount(0)
  if (before) await expect(count(before)).toBeVisible({ timeout: 5000 })
  else await expect(page.getByText(/broken file/)).toHaveCount(0, { timeout: 5000 })
  await expect(page.getByText('Parse the notes').first()).toBeVisible()
})
