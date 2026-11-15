import { saved } from './chat.svelte'
import { router } from './route.svelte'

// The sidebar's OPEN section: steps opened this session and the chats kept in the vault, newest first. Keys 6 to 9 open the first four.
export type Row =
  | { kind: 'step'; key: string; project: string; id: string; at: number }
  | { kind: 'chat'; id: string; title: string; at: number }

export function rows(): Row[] {
  const steps = router.open.map((key): Row => {
    const i = key.lastIndexOf('/')
    return { kind: 'step', key, project: key.slice(0, i), id: key.slice(i + 1), at: router.at[key] ?? 0 }
  })
  const chats = (saved.list ?? []).filter((c) => c.open).map((c): Row => ({ kind: 'chat', id: c.id, title: c.title, at: c.used }))
  return [...steps, ...chats].sort((a, b) => b.at - a.at)
}

export const hashOf = (r: Row) => (r.kind === 'chat' ? `#/chat/${r.id}` : `#/steps/${encodeURIComponent(r.project)}/${encodeURIComponent(r.id)}`)
