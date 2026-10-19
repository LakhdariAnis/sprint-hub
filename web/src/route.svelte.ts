export type Route =
  | { name: 'today' }
  | { name: 'projects' }
  | { name: 'project'; project: string }
  | { name: 'step'; project: string; id: string }
  | { name: 'review' }

export function parse(hash: string): Route {
  const [a, b, c] = hash.replace(/^#\/?/, '').split('/').map(decodeURIComponent)
  if (a === 'projects') return b ? { name: 'project', project: b } : { name: 'projects' }
  if (a === 'steps' && b && c) return { name: 'step', project: b, id: c }
  if (a === 'review') return { name: 'review' }
  return { name: 'today' }
}

export const router = $state({ route: parse(location.hash) })
addEventListener('hashchange', () => (router.route = parse(location.hash)))
