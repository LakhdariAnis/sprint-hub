// The week view and the project ETA, both read from the `## Sprints` tables (GET /week, GET /projects/<id>/eta).
export type WeekSprint = { project: string; name: string; sprint: number; goal: string; status: string; steps_done: number; steps_total: number; planned: number | null; hours_done: number }
export type Week = { week: string; monday: string; sunday: string; days_left: number; tracks: Record<'work' | 'personal', WeekSprint[]>; warnings: string[] }
export type Eta = {
  data: boolean; sprints: number; hours: number; raw_hours: number
  factor: number; factor_sprints: number; factor_from: 'project' | 'track' | 'none'
  week: string | null; sunday: string | null
  flags: { sprint: number; kind: 'overdue' | 'wrong_week'; text: string }[]
}

export const loadWeek = (): Promise<Week> => fetch('/week').then((r) => r.json())
export const loadEta = (project: string): Promise<Eta> => fetch(`/projects/${encodeURIComponent(project)}/eta`).then((r) => r.json())

const hours = (h: number) => String(+h.toFixed(1))
// `5 sprints, ~31 h, done 2026-W49 (Sun 2026-12-06)`: what the Project screen shows.
export function etaLine(e: Eta): string {
  if (!e.data) return 'No sprint table, no estimate.'
  if (!e.sprints) return 'No open sprints.'
  const n = `${e.sprints} ${e.sprints === 1 ? 'sprint' : 'sprints'}, ~${hours(e.hours)} h`
  return e.week && e.sunday ? `${n}, done ${e.week} (Sun ${e.sunday})` : `${n}, no week planned yet`
}
// The factor next to it: the raw hours, what they were multiplied by, and where the factor comes from.
export function factorNote(e: Eta): string {
  if (!e.data || !e.sprints) return ''
  if (e.factor_from === 'none') return 'no closed sprint with recorded hours: factor 1.0'
  const of = `${e.factor_sprints} closed ${e.factor_sprints === 1 ? 'sprint' : 'sprints'}${e.factor_from === 'track' ? ' of the track' : ''}`
  return `${hours(e.raw_hours)} h planned × ${e.factor} (${of})`
}
