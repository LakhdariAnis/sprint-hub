export type Route =
  | { name: 'today' }
  | { name: 'projects' }
  | { name: 'project'; project: string }
  | { name: 'step'; project: string; id: string }
  | { name: 'review'; project?: string; id?: string }

export function parse(hash: string): Route {
  const [a, b, c] = hash.replace(/^#\/?/, '').split('/').map(decodeURIComponent)
  if (a === 'projects') return b ? { name: 'project', project: b } : { name: 'projects' }
  if (a === 'steps' && b && c) return { name: 'step', project: b, id: c }
  if (a === 'review') return { name: 'review', project: b, id: c }
  return a === 'today' ? { name: 'today' } : { name: 'projects' }
}

export const router = $state({ route: parse(location.hash), open: [] as string[] })

// Steps opened this session, as `project/id`, oldest first: the sidebar's OPEN section.
function track(r: Route) {
  if (r.name === 'step' && !router.open.includes(`${r.project}/${r.id}`)) router.open.push(`${r.project}/${r.id}`)
}
track(router.route)
addEventListener('hashchange', () => track((router.route = parse(location.hash))))
