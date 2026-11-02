import { demo } from './demo'
import { loadProjects, type FileError } from './projects'
import { loadStep, loadSteps, type OpenQuestion, type Step } from './steps'
import { key, lists, put, steps } from './store.svelte'
import { applyTheme, loadTheme } from './theme'

// Live numbers for the frame: hubd health, the fake demo data (`--demo` only), the counts shown in the bar and the tabs, and broken vault files.
export type Deadline = { date: string; text: string; tags: string[]; link: string | null; overdue: boolean }

export const hub = $state({ live: null as boolean | null, version: '', demo: null as typeof demo | null, running: 0, review: 0, next: 0, projects: 0, errors: [] as FileError[], deadlines: [] as Deadline[],
  // Open questions of every step (GET /questions), in hubd's order.
  questions: [] as OpenQuestion[],
  // `project/id` of the steps in each Today pane, in hubd's order; the steps themselves are in the store.
  today: { running: [], review: [], next: [] } as Record<'running' | 'review' | 'next', string[]>,
})

async function load() {
  try {
    const [h, t, p, e, q, dl] = await Promise.all([fetch('/health'), fetch('/today'), fetch('/projects'), fetch('/errors'), fetch('/questions'), fetch('/deadlines')])
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
    hub.deadlines = await dl.json()
  } catch {
    hub.live = false
  }
}

// Re-reads the lists a screen opened with: a step or project that appeared or went (new spec, projects.toml, a deleted file) is not in them otherwise.
async function relist() {
  try {
    if (lists.projects) lists.projects = await loadProjects()
  } catch {}
  for (const p of Object.keys(lists.steps)) {
    try {
      const l = await loadSteps(p)
      for (const s of l) put(p, s)
      lists.steps[p] = l.map((s) => key(p, s.step))
    } catch {
      delete lists.steps[p] // the project is gone
    }
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
  events.addEventListener('step', (e) => {
    const { project, step } = JSON.parse(e.data)
    const known = key(project, step) in steps
    take(e)
    load()
    if (!known) relist()
  })
  // A fixed file comes back as a `step` event, so every load re-reads the error list.
  for (const type of ['error', 'reload']) events.addEventListener(type, load)
  events.addEventListener('reload', relist)
  events.addEventListener('removed', (e) => {
    const { project, step } = JSON.parse(e.data)
    // Gone from the lists first, then from the store: a screen still holding the key would read nothing.
    Promise.all([load(), relist()]).then(() => delete steps[key(project, step)])
  })
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
