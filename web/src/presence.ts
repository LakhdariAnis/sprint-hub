import { parse } from './route.svelte'

// hubd keeps its popups quiet while a focused window shows the chat: this window tells it where it is.
export const windowId = Math.random().toString(36).slice(2)

function report(gone = false) {
  const r = parse(location.hash)
  const body = { window: windowId, focused: !gone && document.hasFocus() && !document.hidden, chat: r.name === 'chat' ? (r.id ?? null) : null }
  // hubd forgets a window 60 s after its last report, so a focused one repeats itself.
  fetch('/presence', { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(body), keepalive: true }).catch(() => {})
}

export function reportPresence() {
  for (const e of ['focus', 'blur', 'hashchange', 'visibilitychange']) addEventListener(e, () => report())
  addEventListener('pagehide', () => report(true))
  setInterval(report, 20_000)
  report()
}
