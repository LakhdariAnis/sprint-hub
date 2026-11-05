import type { Step } from './steps'

// The command palette's items and search. Pure: the component feeds it the store.
// `go`: the URL hash to open; `key`: a screen key to press there (an action runs the same code as the key).
export type Item = {
  kind: 'action' | 'screen' | 'project' | 'step'
  label: string
  sub: string
  state?: string
  go: string
  key?: string
  // Text fields to match, with a penalty on each (a project name matches a step weaker than its title).
  hay: [string, number][]
  // Step order: project/id.
  at: string
}

const enc = encodeURIComponent
export const stepHash = (p: string, i: string) => `#/steps/${enc(p)}/${enc(i)}`
const reviewHash = (p: string, i: string) => `#/review/${enc(p)}/${enc(i)}`

const SCREENS: [string, string, string][] = [
  ['Today', '#/today', 'g t'],
  ['Projects', '#/projects', 'g p'],
  ['Review', '#/review', 'g r'],
  ['Questions', '#/questions', 'g q'],
  ['Settings', '#/settings', 'g s'],
]

// The moves valid on this step right now, by the keys of the screen they run on.
export function actions(s: Step | undefined): Item[] {
  if (!s) return []
  const at = `${s.project}/${s.step}`
  const act = (label: string, go: string, key: string): Item => ({ kind: 'action', label, sub: at, go, key, hay: [[label, 0]], at })
  const out: Item[] = []
  const claude = s.by !== 'me'
  if (claude && (s.state === 'todo' || s.state === 'changes')) out.push(act('Start', stepHash(s.project, s.step), 's'))
  if (s.state === 'done') {
    out.push(act('Approve', reviewHash(s.project, s.step), 'a'))
    out.push(act('Request changes', reviewHash(s.project, s.step), 'c'))
  }
  if (!claude && s.tasks.length) out.push(act('Tick task', stepHash(s.project, s.step), 'x'))
  if (claude && s.state === 'doing') out.push(act('Finish run', stepHash(s.project, s.step), 'f'))
  return out
}

export function items(steps: Step[], projects: { id: string; name: string }[], current?: Step): Item[] {
  const out: Item[] = actions(current)
  for (const [label, go, sub] of SCREENS) out.push({ kind: 'screen', label, sub, go, hay: [[label, 0]], at: label })
  for (const p of projects) out.push({ kind: 'project', label: p.name, sub: p.id, go: `#/projects/${enc(p.id)}`, hay: [[p.name, 0], [p.id, 0]], at: p.id })
  for (const s of steps) {
    const at = `${s.project}/${s.step}`
    out.push({ kind: 'step', label: s.title, sub: at, state: s.state, go: stepHash(s.project, s.step), hay: [[s.step, 0], [s.title, 0], [s.project, 10]], at })
  }
  return out
}

// 0 = no match. Whole start 100, a word start 80, inside 60, letters in order (fuzzy) 10–40 by how far apart they are.
export function score(q: string, text: string): number {
  const t = text.toLowerCase()
  if (t.startsWith(q)) return 100
  const i = t.indexOf(q)
  if (i >= 0) return /[a-z0-9]/.test(t[i - 1]) ? 60 : 80
  let at = -1
  let first = -1
  for (const c of q) {
    at = t.indexOf(c, at + 1)
    if (at < 0) return 0
    if (first < 0) first = at
  }
  return 10 + Math.max(0, 30 - (at - first + 1 - q.length))
}

// Every word of the query must match some field; the weakest word sets the score.
const rate = (words: string[], it: Item) =>
  Math.min(...words.map((w) => Math.max(0, ...it.hay.map(([t, pen]) => { const n = score(w, t); return n && Math.max(1, n - pen) }))))

const STATE = ['doing', 'done', 'changes', 'todo', 'approved']
const KIND = ['action', 'screen', 'project', 'step']
const byState = (a: Item, b: Item) => STATE.indexOf(a.state ?? '') - STATE.indexOf(b.state ?? '')
const natural = (a: Item, b: Item) => a.at.localeCompare(b.at, undefined, { numeric: true })

// Empty query: the steps that need you (running, waiting for review, changes asked). Else best match first, then open work first.
export function search(all: Item[], query: string): Item[] {
  const words = query.toLowerCase().split(/\s+/).filter(Boolean)
  if (!words.length) return all.filter((it) => it.kind === 'step' && STATE.indexOf(it.state!) < 3).sort((a, b) => byState(a, b) || natural(a, b))
  return all
    .map((it) => [rate(words, it), it] as const)
    .filter(([n]) => n > 0)
    .sort(([m, a], [n, b]) => n - m || KIND.indexOf(a.kind) - KIND.indexOf(b.kind) || byState(a, b) || natural(a, b))
    .map(([, it]) => it)
}
