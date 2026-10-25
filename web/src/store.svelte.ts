import type { Row } from './projects'
import type { Step } from './steps'

// Every step a screen has loaded, by `project/id`. Screens read it; Start and SSE events (step 207) write it.
export const steps = $state<Record<string, Step>>({})

export const key = (project: string, id: string) => `${project}/${id}`

// Merges into what is known: a start reply has no project, tasks or spec.
export function put(project: string, s: Partial<Step> & { step: string }) {
  const k = key(project, s.step)
  steps[k] = { ...steps[k], ...s, project } as Step
}

// Lists a screen opens with, so a switch shows them at once (step 406): the project rows, and each project's step keys in API order.
export const lists = $state({ projects: null as Row[] | null, steps: {} as Record<string, string[]> })
