import type { Step } from './steps'

// Every step a screen has loaded, by `project/id`. Screens read it; Start and SSE events (step 207) write it.
export const steps = $state<Record<string, Step>>({})

export const key = (project: string, id: string) => `${project}/${id}`

// Merges into what is known: a start reply has no project, tasks or spec.
export function put(project: string, s: Partial<Step> & { step: string }) {
  const k = key(project, s.step)
  steps[k] = { ...steps[k], ...s, project } as Step
}
