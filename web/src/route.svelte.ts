export type Route =
  | { name: 'chat'; id?: string }
  | { name: 'today' }
  | { name: 'projects' }
  | { name: 'project'; project: string }
  | { name: 'step'; project: string; id: string }
  | { name: 'review'; project?: string; id?: string }
  | { name: 'questions' }
  | { name: 'settings' }

export function parse(hash: string): Route {
  const [a, b, c] = hash.replace(/^#\/?/, '').split('/').map(decodeURIComponent)
  if (!a || a === 'chat') return { name: 'chat', id: b || undefined }
  if (a === 'projects') return b ? { name: 'project', project: b } : { name: 'projects' }
  if (a === 'steps' && b && c) return { name: 'step', project: b, id: c }
  if (a === 'questions') return { name: 'questions' }
  if (a === 'settings') return { name: 'settings' }
  if (a === 'review') return { name: 'review', project: b, id: c }
  return a === 'today' ? { name: 'today' } : { name: 'projects' }
}

export const router = $state({ route: parse(location.hash), open: [] as string[], at: {} as Record<string, number> })

// Steps opened this session, as `project/id`, oldest first: the sidebar's OPEN section (open.svelte.ts orders it). `at`: when each was opened.
function track(r: Route) {
  const k = r.name === 'step' ? `${r.project}/${r.id}` : ''
  if (k && !router.open.includes(k)) {
    router.open.push(k)
    router.at[k] = Date.now()
  }
}
track(router.route)
addEventListener('hashchange', () => track((router.route = parse(location.hash))))
