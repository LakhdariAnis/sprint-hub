import { onMount } from 'svelte'
import { router } from './route.svelte'

// The one key handler of the app. Screens add their own keys with `useKeys`; `g` + letter and `?` live here.
// `rail`: the sidebar is collapsed to its icon rail (^B).
const railKey = 'sprint-hub:rail'
const saved = (() => { try { return localStorage.getItem(railKey) === '1' } catch { return false } })()
export const keys = $state({ help: false, pending: false, rail: saved })
export function toggleRail() {
  keys.rail = !keys.rail
  try { localStorage.setItem(railKey, keys.rail ? '1' : '0') } catch {}
}

type Handlers = Record<string, () => void>
let current: Handlers = {}

// Keys of the screen on show, by `KeyboardEvent.key`. Handlers read state when called, so pass the map once.
export function useKeys(map: Handlers) {
  onMount(() => {
    current = map
    return () => current === map && (current = {})
  })
}

const go: Handlers = {
  t: () => (location.hash = '#/today'),
  p: () => (location.hash = '#/projects'),
  r: () => (location.hash = '#/review'),
  q: () => (location.hash = '#/questions'),
}
// Plain digits and `b`: 1–4 tabs, 6–9 the OPEN steps, b the icon rail. Ctrl+1–4 (app window only, see below) = the tabs too.
const openStep = (n: number) => {
  const k = router.open[n]
  if (!k) return
  const i = k.lastIndexOf('/')
  location.hash = `#/steps/${encodeURIComponent(k.slice(0, i))}/${encodeURIComponent(k.slice(i + 1))}`
}
const plain: Handlers = { '1': go.p, '2': go.t, '3': go.r, '4': go.q, b: toggleRail }
for (const n of [6, 7, 8, 9]) plain[n] = () => openStep(n - 6)
// A normal Chrome tab keeps Ctrl+1…9 for its own tabs; the `--app` window (bin/sprint-hub-app) has none, so the page gets them.
const ctrl: Handlers = { '1': go.p, '2': go.t, '3': go.r, '4': go.q }
const alias: Record<string, string> = { ArrowDown: 'j', ArrowUp: 'k', ArrowRight: 'Enter', ArrowLeft: 'Escape' }
let timer: ReturnType<typeof setTimeout>

// A clicked sidebar tab keeps focus, so the next Enter would click it again instead of opening the selected row.
addEventListener('hashchange', () => {
  const el = document.activeElement
  if (el instanceof HTMLElement && el.closest('nav')) el.blur()
})

addEventListener('keydown', (e) => {
  const el = e.target as HTMLElement
  // Off while typing; Enter on a focused button or link keeps its own click.
  if (el.closest('input, textarea, select, [contenteditable]') || e.metaKey || e.altKey) return
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
  if (keys.help) {
    if (k === 'Escape' || k === '?') keys.help = false
  } else if (keys.pending) {
    run = go[k]
  } else if (k === 'g') {
    keys.pending = true
    clearTimeout(timer)
    timer = setTimeout(() => (keys.pending = false), 1500)
  } else if (k === '?') {
    keys.help = true
  } else {
    run = plain[k] ?? current[k]
  }
  if (keys.pending && k !== 'g') keys.pending = false
  if (run) run()
  if (run || k === 'g' || k === '?' || keys.help) e.preventDefault()
})
