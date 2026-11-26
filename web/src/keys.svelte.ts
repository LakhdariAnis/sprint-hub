import { onMount } from 'svelte'
import { hashOf, rows } from './open.svelte'
import { focusProject } from './steps'

// The one key handler of the app. Screens add their own keys with `useKeys`; `g` + letter and `?` live here.
// `rail`: the sidebar is collapsed to its icon rail (^B). `shown`: the URL hash of the screen on show (nav.svelte.ts).
const railKey = 'sprint-hub:rail'
const saved = (() => { try { return localStorage.getItem(railKey) === '1' } catch { return false } })()
export const keys = $state({ help: false, errors: false, palette: false, pending: false, rail: saved, shown: null as string | null, notice: null as { text: string; bad: boolean } | null, confirm: null as Ask | null })
// A yes / no popup (Confirm.svelte): y or Enter runs `run`, n or Esc closes; every other key waits.
export type Ask = { title: string; text: string; yes: string; run: () => void }
export const ask = (a: Ask) => (keys.confirm = a)
export function answer(yes: boolean) {
  const a = keys.confirm
  keys.confirm = null
  if (yes) a?.run()
}

export function toggleRail() {
  keys.rail = !keys.rail
  try { localStorage.setItem(railKey, keys.rail ? '1' : '0') } catch {}
}

// One line in the status line (a toast): a result or a reason, gone after a few seconds.
let noticeTimer: ReturnType<typeof setTimeout> | undefined
export function say(text: string | null, bad = false) {
  if (!text) return
  keys.notice = { text, bad }
  clearTimeout(noticeTimer)
  noticeTimer = setTimeout(() => (keys.notice = null), 6000)
}
// `w`: the project's workspace; the status line says why when hubd cannot.
export const jump = (project: string) => focusProject(project).then((why) => why && say(why, true))

export const openPalette = () => (keys.palette = true)
// `n`: a screen with its own `n` (the Step screen's fresh chat) wins; elsewhere it opens New chat.
export const newChat = () => (location.hash = '#/chat')

type Handlers = Record<string, () => void>
let current: Handlers = {}
// Screen keys pressed while the URL is ahead of the screen (hashchange fires late, then the data loads): they belong to the next screen.
let held: string[] = []
// The handler of a screen key; `n` falls back on New chat.
const screenKey = (key: string) => current[key] ?? current[alias[key] ?? key] ?? (key === 'n' ? newChat : undefined)

// The screen of `hash` is on show: run what was typed meanwhile on it.
export function release(hash: string) {
  keys.shown = hash
  if (location.hash !== hash) return
  for (const key of held.splice(0)) screenKey(key)?.()
}

// Runs a key of the screen at `hash` (a palette action): at once if it is on show, else when it shows.
export function press(hash: string, key: string) {
  if (keys.shown === hash && location.hash === hash) return void screenKey(key)?.()
  held.push(key)
  location.hash = hash
}

// Keys of the screen on show, by `KeyboardEvent.key`; an arrow can have its own handler, else it acts as j / k / Enter / Esc. Handlers read state when called, so pass the map once.
export function useKeys(map: Handlers) {
  onMount(() => {
    current = map
    return () => current === map && (current = {})
  })
}

const go: Handlers = {
  t: () => (location.hash = '#/today'),
  s: () => (location.hash = '#/settings'),
  p: () => (location.hash = '#/projects'),
  r: () => (location.hash = '#/review'),
  q: () => (location.hash = '#/questions'),
}
// Plain digits, `b` and `e`: 1–5 tabs, 6–9 the OPEN steps and chats, b the icon rail, e the broken-files list. Ctrl+1–5 (app window only, see below) = the tabs too.
const openRow = (n: number) => {
  const row = rows()[n]
  if (row) location.hash = hashOf(row)
}
const plain: Handlers = { '/': openPalette, '1': go.p, '2': go.t, '3': go.r, '4': go.q, '5': go.s, b: toggleRail, e: () => (keys.errors = true) }
for (const n of [6, 7, 8, 9]) plain[n] = () => openRow(n - 6)
// A normal Chrome tab keeps Ctrl+1…9 for its own tabs; the `--app` window (bin/sprint-hub-app) has none, so the page gets them.
const ctrl: Handlers = { '1': go.p, '2': go.t, '3': go.r, '4': go.q, '5': go.s }
const alias: Record<string, string> = { ArrowDown: 'j', ArrowUp: 'k', ArrowRight: 'Enter', ArrowLeft: 'Escape' }
let timer: ReturnType<typeof setTimeout>

// A clicked sidebar tab keeps focus, so the next Enter would click it again instead of opening the selected row.
addEventListener('hashchange', () => {
  const el = document.activeElement
  if (el instanceof HTMLElement && el.closest('nav')) el.blur()
})

addEventListener('keydown', (e) => {
  // The palette's box has its own keys.
  if (keys.palette) return
  if (keys.confirm) {
    if (e.key === 'y' || e.key === 'Enter') answer(true)
    else if (e.key === 'n' || e.key === 'Escape') answer(false)
    return e.preventDefault()
  }
  // Ctrl+K opens it, also from a box.
  if (e.ctrlKey && !e.shiftKey && !e.metaKey && !e.altKey && (e.key.toLowerCase() === 'k' || e.code === 'KeyK')) {
    keys.palette = true
    return e.preventDefault()
  }
  const el = e.target as HTMLElement
  // Off while typing, and on the split's handle (its arrows are its own); Enter on a focused button or link keeps its own click.
  if (el.closest('input, textarea, select, [contenteditable], [role="separator"]') || e.metaKey || e.altKey) return
  if (e.ctrlKey) {
    if (!e.shiftKey && ctrl[e.key]) {
      ctrl[e.key]()
      e.preventDefault()
    }
    return
  }
  if (e.key === 'Enter' && el.closest('a, button')) return
  // Non-Latin layout (Arabic…): `e.key` is not "b", but the physical key is still KeyB.
  const k = alias[e.key] ?? (/^[^\x00-\x7f]$/.test(e.key) && /^Key[A-Z]$/.test(e.code) ? e.code[3].toLowerCase() : e.key)

  let run: (() => void) | undefined
  if (keys.help || keys.errors) {
    if (k === 'Escape' || k === (keys.help ? '?' : 'e')) keys.help = keys.errors = false
  } else if (keys.pending) {
    run = go[k]
  } else if (k === 'g') {
    keys.pending = true
    clearTimeout(timer)
    timer = setTimeout(() => (keys.pending = false), 1500)
  } else if (k === '?') {
    keys.help = true
  } else {
    run = plain[k] ?? (location.hash !== keys.shown ? () => held.push(e.key) : current[e.key] ?? screenKey(k))
  }
  if (keys.pending && k !== 'g') keys.pending = false
  if (run) run()
  if (run || k === 'g' || k === '?' || keys.help || keys.errors) e.preventDefault()
})
