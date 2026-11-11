// The `/` menu of the chat box. Pure: the screen feeds it the store.
export type Opt = { value: string; label: string; desc?: string }
export type Cmd = { name: string; desc: string }

export const COMMANDS: Cmd[] = [
  { name: 'model', desc: 'Pick the model' },
  { name: 'effort', desc: 'How hard Claude thinks' },
  { name: 'project', desc: 'Chat inside a project' },
  { name: 'sprint', desc: 'Pick a sprint of the project' },
  { name: 'step', desc: 'Pick a step of the project' },
  { name: 'clear', desc: 'New chat, same settings' },
]

export const MODELS: Opt[] = [
  { value: 'opus', label: 'opus', desc: 'hardest problems, slowest' },
  { value: 'sonnet', label: 'sonnet', desc: 'everyday work' },
  { value: 'haiku', label: 'haiku', desc: 'quick questions, cheapest' },
]
// `claude --effort` also takes xhigh and max; the menu offers the three.
export const EFFORTS: Opt[] = [
  { value: 'low', label: 'low', desc: 'fast, little thinking' },
  { value: 'medium', label: 'medium', desc: 'the default' },
  { value: 'high', label: 'high', desc: 'slower, thinks longer' },
]

// What follows the `/` while the box holds only a command being typed; null = no menu.
export const slashQuery = (text: string) => (/^\/[a-z]*$/i.test(text) ? text.slice(1).toLowerCase() : null)

export const filter = (q: string) => COMMANDS.filter((c) => c.name.startsWith(q))

// `name` split around the typed part, for the underline.
export const split = (name: string, q: string) => [name.slice(0, q.length), name.slice(q.length)] as const

export type Ctx = { projects: { id: string; name: string }[]; steps: { step: string; title: string; sprint: number | null }[] }

// The options of a command; none for /clear.
export function options(name: string, ctx: Ctx): Opt[] {
  if (name === 'model') return MODELS
  if (name === 'effort') return EFFORTS
  if (name === 'project') return [{ value: '', label: 'none', desc: 'plain chat' }, ...ctx.projects.map((p) => ({ value: p.id, label: p.name }))]
  if (name === 'sprint') {
    const ns = [...new Set(ctx.steps.map((s) => s.sprint).filter((n): n is number => n !== null))].sort((a, b) => a - b)
    return [{ value: '', label: 'none' }, ...ns.map((n) => ({ value: String(n), label: `sprint ${n}` }))]
  }
  if (name === 'step') return [{ value: '', label: 'none' }, ...ctx.steps.map((s) => ({ value: s.step, label: s.step, desc: s.title }))]
  return []
}
