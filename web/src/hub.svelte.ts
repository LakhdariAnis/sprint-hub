// Live numbers for the frame: hubd health and the counts shown in the bar and the tabs.
export const hub = $state({ live: null as boolean | null, running: 0, review: 0, next: 0, projects: 0 })

async function load() {
  try {
    const [h, t, p] = await Promise.all([fetch('/health'), fetch('/today'), fetch('/projects')])
    hub.live = h.ok && (await h.json())?.ok === true
    const today = await t.json()
    hub.running = today.running.length
    hub.review = today.review.length
    hub.next = today.next.length
    hub.projects = (await p.json()).length
  } catch {
    hub.live = false
  }
}

load()
// A step event means counts may have changed. Step 207 handles the events themselves.
new EventSource('/events').addEventListener('step', load)
