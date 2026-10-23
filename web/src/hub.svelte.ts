import { demo } from './demo'
import type { FileError } from './projects'
import { loadStep, type OpenQuestion, type Step } from './steps'
import { key, put, steps } from './store.svelte'
import { applyTheme, loadTheme } from './theme'

// Live numbers for the frame: hubd health, the fake demo data (`--demo` only), the counts shown in the bar and the tabs, and broken vault files.
export const hub = $state({ live: null as boolean | null, version: '', demo: null as typeof demo | null, running: 0, review: 0, next: 0, projects: 0, errors: [] as FileError[],
  // Open questions of every step (GET /questions), in hubd's order.
  questions: [] as OpenQuestion[],
  // `project/id` of the steps in each Today pane, in hubd's order; the steps themselves are in the store.
  today: { running: [], review: [], next: [] } as Record<'running' | 'review' | 'next', string[]>,
})

async function load() {
  try {
    const [h, t, p, e, q] = await Promise.all([fetch('/health'), fetch('/today'), fetch('/projects'), fetch('/errors'), fetch('/questions')])
    const health = h.ok ? await h.json() : null
    hub.live = health?.ok === true
    hub.version = health?.version ?? ''
    hub.demo = health?.demo === true ? demo : null
    const today: Record<'running' | 'review' | 'next', Step[]> = await t.json()
    for (const pane of ['running', 'review', 'next'] as const) {
      for (const s of today[pane]) put(s.project, s)
      hub.today[pane] = today[pane].map((s) => key(s.project, s.step))
    }
    hub.running = today.running.length
    hub.review = today.review.length
    hub.next = today.next.length
    hub.projects = (await p.json()).length
    hub.errors = await e.json()
    hub.questions = await q.json()
  } catch {
    hub.live = false
  }
}

// The one `/events` stream of the app. `step` and `tasks` carry the whole step; the store takes it as is.
function connect() {
  const events = new EventSource('/events')
  const take = (e: MessageEvent) => {
    const { type: _, ...s } = JSON.parse(e.data)
    put(s.project, s)
  }
  // Questions ride on `tasks` events, so the inbox re-reads there too.
  events.addEventListener('tasks', (e) => (take(e), load()))
  events.addEventListener('step', (e) => (take(e), load()))
  // A fixed file comes back as a `step` event, so every load re-reads the error list.
  for (const type of ['error', 'removed', 'reload']) events.addEventListener(type, load)
  events.addEventListener('theme', (e) => applyTheme(JSON.parse(e.data)))
  // (Re)connected: events missed while hubd was away are gone, so re-read what the app shows.
  events.onopen = () => {
    load()
    loadTheme()
    for (const s of Object.values(steps)) loadStep(s.project, s.step).then((d) => put(s.project, d), () => {})
  }
  events.onerror = () => {
    hub.live = false
    // The browser retries a dropped stream itself, but gives up on an error reply (e.g. the dev proxy's 502).
    if (events.readyState === EventSource.CLOSED) setTimeout(connect, 3000)
  }
}
connect()
