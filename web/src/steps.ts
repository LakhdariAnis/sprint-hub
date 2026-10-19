export type Task = { text: string; state: 'todo' | 'doing' | 'done' }
export type Step = {
  project: string
  step: string
  title: string
  state: string
  model: string | null
  branch: string | null
  runs: { minutes: number | null }[]
  tasks: Task[]
  spec?: string | null
}

// API order is by file name, which is step order.
export const loadSteps = (project: string): Promise<Step[]> =>
  fetch(`/projects/${encodeURIComponent(project)}/steps`).then((r) => (r.ok ? r.json() : Promise.reject(r.status)))

export const loadStep = (project: string, id: string): Promise<Step> =>
  fetch(`/steps/${encodeURIComponent(project)}/${encodeURIComponent(id)}`).then((r) => (r.ok ? r.json() : Promise.reject(r.status)))

// The text under `## Goal` in the repo spec, up to the next heading.
export const goal = (spec: string | null | undefined) => spec?.match(/^## Goal\s*\n([\s\S]*?)(?=^## |(?![\s\S]))/m)?.[1].trim() ?? ''
