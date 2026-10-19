import type { FileError } from './projects'
import { put } from './store.svelte'

// Live numbers for the frame: hubd health, the counts shown in the bar and the tabs, and broken vault files.
export const hub = $state({ live: null as boolean | null, running: 0, review: 0, next: 0, projects: 0, errors: [] as FileError[] })

async function load() {
  try {
    const [h, t, p, e] = await Promise.all([fetch('/health'), fetch('/today'), fetch('/projects'), fetch('/errors')])
    hub.live = h.ok && (await h.json())?.ok === true
    const today = await t.json()
    hub.running = today.running.length
    hub.review = today.review.length
    hub.next = today.next.length
    hub.projects = (await p.json()).length
    hub.errors = await e.json()
  } catch {
    hub.live = false
  }
}

load()

// The one `/events` stream of the app. `step` and `tasks` carry the whole step; the store takes it as is.
const events = new EventSource('/events')
const take = (e: MessageEvent) => {
  const { type: _, ...s } = JSON.parse(e.data)
  put(s.project, s)
}
events.addEventListener('tasks', take)
events.addEventListener('step', (e) => (take(e), load()))
// A fixed file comes back as a `step` event, so every load re-reads the error list.
for (const type of ['error', 'removed', 'reload']) events.addEventListener(type, load)
