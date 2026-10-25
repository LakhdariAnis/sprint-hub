import { tick } from 'svelte'
import { keys, release } from './keys.svelte'
import { loadProjects } from './projects'
import { router, type Route } from './route.svelte'
import { loadStep, loadSteps, needsWork } from './steps'
import { key, lists, put, steps } from './store.svelte'

// The screen on show. It lags the URL until the new screen's data is in, then swaps in one go: no blank page, no jump.
// `failed`: why that load failed (an HTTP status or an error), for the screen's own error line. `slow`: the load passed 300 ms.
export const nav = $state({ route: null as Route | null, failed: null as unknown, slow: false })

const project = (p: string) =>
  loadSteps(p).then((l) => {
    for (const s of l) put(p, s)
    lists.steps[p] = l.map((s) => key(p, s.step))
    // The info column opens on this step: have its spec too.
    const w = needsWork(l)
    return w && !('spec' in steps[key(p, w.step)]) ? loadStep(p, w.step).then((d) => put(p, d)) : undefined
  })

// Cached data shows at once and refreshes behind it; SSE keeps it fresh after that.
const cached = (have: unknown, load: () => Promise<unknown>) => (have ? (load().catch(() => {}), Promise.resolve()) : load())

function data(r: Route): Promise<unknown> {
  if (r.name === 'projects' || r.name === 'today') return cached(lists.projects, () => loadProjects().then((d) => (lists.projects = d)))
  if (r.name === 'project') return cached(lists.steps[r.project], () => project(r.project))
  if (r.name === 'step') {
    const s = steps[key(r.project, r.id)]
    return cached(s && 'spec' in s, () => loadStep(r.project, r.id).then((d) => put(r.project, d)))
  }
  // The review queue spans every project. j/k there only change the URL's selection.
  if (r.name === 'review') {
    if (nav.route?.name === 'review') return Promise.resolve()
    const all = () => fetch('/projects').then((x) => x.json()).then((ps: { id: string }[]) => Promise.all(ps.map((p) => project(p.id))))
    return cached(lists.projects && lists.projects.every((p) => lists.steps[p.id]), all)
  }
  return Promise.resolve()
}

let n = 0
function go(r: Route) {
  const me = ++n
  keys.hold = true
  const slow = setTimeout(() => me === n && (nav.slow = true), 300)
  const show = (failed: unknown) => {
    if (me !== n) return
    clearTimeout(slow)
    Object.assign(nav, { route: r, failed, slow: false })
    tick().then(release)
  }
  data(r).then(() => show(null), show)
}

go(router.route)
addEventListener('hashchange', () => go(router.route))
