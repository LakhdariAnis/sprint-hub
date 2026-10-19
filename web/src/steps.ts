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
  runs: { minutes: number | null }[]
  tasks: Task[]
  spec?: string | null
  path?: string
}

// API order is by file name, which is step order.
export const loadSteps = (project: string): Promise<Step[]> =>
  fetch(`/projects/${encodeURIComponent(project)}/steps`).then((r) => (r.ok ? r.json() : Promise.reject(r.status)))

export const loadStep = (project: string, id: string): Promise<Step> =>
  fetch(`/steps/${encodeURIComponent(project)}/${encodeURIComponent(id)}`).then((r) => (r.ok ? r.json() : Promise.reject(r.status)))

// Starts the run; the reply is the step's new frontmatter. A refused start throws hubd's reason.
export async function startStep(project: string, id: string): Promise<Step> {
  const r = await fetch(`/steps/${encodeURIComponent(project)}/${encodeURIComponent(id)}/start`, { method: 'POST' })
  const body = await r.json().catch(() => null)
  if (!r.ok) throw new Error(body?.detail ?? `hubd answered ${r.status}`)
  return body
}

// The text under `## Goal` in the repo spec, up to the next heading.
export const goal = (spec: string | null | undefined) => spec?.match(/^## Goal\s*\n([\s\S]*?)(?=^## |(?![\s\S]))/m)?.[1].trim() ?? ''
