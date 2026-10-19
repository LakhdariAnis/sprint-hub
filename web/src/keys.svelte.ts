import { onMount } from 'svelte'

// The one key handler of the app. Screens add their own keys with `useKeys`; `g` + letter and `?` live here.
export const keys = $state({ help: false, pending: false })

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
}
const alias: Record<string, string> = { ArrowDown: 'j', ArrowUp: 'k' }
let timer: ReturnType<typeof setTimeout>

addEventListener('keydown', (e) => {
  const el = e.target as HTMLElement
  // Off while typing; Enter on a focused button or link keeps its own click.
  if (el.closest('input, textarea, select, [contenteditable]') || e.ctrlKey || e.metaKey || e.altKey) return
  if (e.key === 'Enter' && el.closest('a, button')) return
  const k = alias[e.key] ?? e.key

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
    run = current[k]
  }
  if (keys.pending && k !== 'g') keys.pending = false
  if (run) run()
  if (run || k === 'g' || k === '?' || keys.help) e.preventDefault()
})
