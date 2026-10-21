// `at`: when hubd saw the task reach its state (ISO time); missing if that was before hubd started.
export type Task = { text: string; state: 'todo' | 'doing' | 'done'; at?: string }
export type Step = {
  project: string
  step: string
  title: string
  state: string
  by: 'claude' | 'me'
  model: string | null
  branch: string | null
  runs: { started?: string; minutes: number | null }[]
  tasks: Task[]
  review?: { verdict: 'approve' | 'changes' | null; comment: string } | null
  spec?: string | null
  path?: string
}

// API order is by file name, which is step order.
export const loadSteps = (project: string): Promise<Step[]> =>
  fetch(`/projects/${encodeURIComponent(project)}/steps`).then((r) => (r.ok ? r.json() : Promise.reject(r.status)))

export const loadStep = (project: string, id: string): Promise<Step> =>
  fetch(`/steps/${encodeURIComponent(project)}/${encodeURIComponent(id)}`).then((r) => (r.ok ? r.json() : Promise.reject(r.status)))

// POSTs a move; the reply is the step's new frontmatter. A refused move throws hubd's reason.
async function post(project: string, id: string, move: string, body?: object): Promise<Step> {
  const r = await fetch(`/steps/${encodeURIComponent(project)}/${encodeURIComponent(id)}/${move}`, {
    method: 'POST',
    ...(body && { headers: { 'content-type': 'application/json' }, body: JSON.stringify(body) }),
  })
  const reply = await r.json().catch(() => null)
  if (!r.ok) throw new Error(typeof reply?.detail === 'string' ? reply.detail : `hubd answered ${r.status}`)
  return reply
}

export const startStep = (project: string, id: string) => post(project, id, 'start')
export const approveStep = (project: string, id: string) => post(project, id, 'approve')
export const requestChanges = (project: string, id: string, comment: string) => post(project, id, 'changes', { comment })

// The text under `## Goal` in the repo spec, up to the next heading.
// Time since `started` as one short unit (12m, 3h, 5d), the same on every screen.
export const ago = (started: string | undefined, now: number) => {
  const d = now - Date.parse(started ?? '')
  if (Number.isNaN(d)) return '–'
  const m = Math.max(0, Math.floor(d / 60_000))
  return m < 60 ? `${m}m` : m < 1440 ? `${Math.floor(m / 60)}h` : `${Math.floor(m / 1440)}d`
}

export const goal = (spec: string | null | undefined) => spec?.match(/^## Goal\s*\n([\s\S]*?)(?=^## |(?![\s\S]))/m)?.[1].trim() ?? ''

// `git diff --stat main...branch` of the step; a refused read throws hubd's reason.
export async function loadDiffstat(project: string, id: string): Promise<string> {
  const r = await fetch(`/steps/${encodeURIComponent(project)}/${encodeURIComponent(id)}/diffstat`)
  const body = await r.json().catch(() => null)
  if (!r.ok) throw new Error(body?.detail ?? `hubd answered ${r.status}`)
  return body.stat
}
