import type { Row } from './projects'
import type { Step } from './steps'
import type { Eta } from './week'

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

// The ETA of each project a screen asked for, by project id; hub.svelte.ts keeps them fresh.
export const etas = $state<Record<string, Eta | null>>({})

// The Hyprland workspace of a project's runs; null when it has none or the rows are not loaded.
export const archivedOf = (project: string) => !!lists.projects?.find((p) => p.id === project)?.archived
export const accountOf = (project: string) => lists.projects?.find((p) => p.id === project)?.account ?? 'claude'
export const graphOf = (project: string) => lists.projects?.find((p) => p.id === project)?.graph ?? false
export const graphStatusOf = (project: string) => lists.projects?.find((p) => p.id === project)?.graphStatus ?? null
export const workspaceOf = (project: string) => lists.projects?.find((p) => p.id === project)?.workspace ?? null
