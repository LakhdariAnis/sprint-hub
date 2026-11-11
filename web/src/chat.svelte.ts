import type { End } from './cost'

// Chats of this session, by id (hubd keeps them in memory; 609 makes them last). A turn is the message sent and the answer to it: text, tool lines and permission cards in the order Claude produced them.
export type Turn = { me: string; blocks: Block[]; done: boolean; error?: string; stopped?: boolean; end?: End }
export type Block = ({ kind: 'text'; text: string }) | ({ kind: 'tool' } & Tool) | ({ kind: 'ask' } & Ask)
// A tool call (608): `line` is the collapsed line, `input` and `result` show when `open`. `result` is undefined until the call returns.
export type Tool = { id?: string; name: string; line: string; input: string; result?: string; error?: boolean; open: boolean }
export const answerOf = (t: Turn) => t.blocks.flatMap((b) => (b.kind === 'text' ? [b.text] : [])).join('')
export const asksOf = (t: Turn) => t.blocks.filter((b): b is { kind: 'ask' } & Ask => b.kind === 'ask')
export const toolsOf = (t: Turn) => t.blocks.filter((b): b is { kind: 'tool' } & Tool => b.kind === 'tool')
// A permission card (607): Claude wants to run `tool` on `target`. `answer` once Anis (or the 10 min wait) decided; `refused`: hubd said no without asking. `wide`: "Allow for this chat" can cover it.
export type Ask = { request?: string; tool: string; target: string; diff: string | null; wide?: boolean; answer?: string; refused?: string }

// What hubd told Claude about the project, sprint or step (606): the chip above the box.
export type Context = { label: string; size: number; notes: string[] }
export type Meta = { model: string; effort: string; project: string | null; context: Context | null; title?: string; earlier_hidden?: boolean }
export const chats = $state<Record<string, { turns: Turn[] } & Partial<Meta>>>({})

// What the next new chat opens with (the pills). Kept when the page starts another chat (/clear, n). With a project, `sprint` and `step` add their context.
export const pills = $state({ project: null as string | null, model: 'sonnet', effort: 'medium', sprint: null as string | null, step: null as string | null })

// What hubd sends on `/events` for a chat (`chat` events) and in GET /chats/<id> turns, less the fields 608 uses.
type Ev = { kind: string; text?: string; message?: string; answer?: string; tool_id?: string; name?: string; line?: string; input?: string; error?: boolean } & Partial<Ask> & End

// Events of a message sent mid-turn wait for the turn before it, as in hubd.
function take(turn: Turn, e: Ev) {
  const last = turn.blocks.at(-1)
  if (e.kind === 'text') {
    if (last?.kind === 'text') last.text += e.text ?? ''
    else turn.blocks.push({ kind: 'text', text: e.text ?? '' })
  } else if (e.kind === 'tool') turn.blocks.push({ kind: 'tool', id: e.tool_id, name: e.name ?? 'tool', line: e.line ?? e.name ?? 'tool', input: e.input ?? '', open: false })
  else if (e.kind === 'tool_result') {
    const tool = toolsOf(turn).find((t) => t.id === e.tool_id)
    if (tool) Object.assign(tool, { result: e.text ?? '', error: !!e.error })
  } else if (e.kind === 'turn_end') {
    turn.done = true
    turn.end = { model: e.model, cost_usd: e.cost_usd, input_tokens: e.input_tokens, output_tokens: e.output_tokens, duration_ms: e.duration_ms }
  } else if (e.kind === 'stopped') Object.assign(turn, { done: true, stopped: true })
  else if (e.kind === 'error') Object.assign(turn, { error: e.message || 'Claude failed', done: true })
  else if (e.kind === 'permission') turn.blocks.push({ kind: 'ask', request: e.request, tool: e.tool!, target: e.target!, diff: e.diff ?? null, wide: e.wide })
  else if (e.kind === 'permission_refused') turn.blocks.push({ kind: 'ask', tool: e.tool!, target: e.target!, diff: e.diff ?? null, refused: e.message })
  else if (e.kind === 'permission_answer') {
    const ask = asksOf(turn).find((a) => a.request === e.request)
    if (ask) ask.answer = e.answer
  }
}

// Anis's answer to a card: `allow`, `deny`, or `chat` (Allow for this chat). The card changes when hubd's `permission_answer` comes back.
export async function answer(id: string, request: string, choice: 'allow' | 'deny' | 'chat') {
  await post(`/chats/${id}/permission/${request}`, { answer: choice }).catch((e) => {
    throw e instanceof TypeError ? new Error('hubd is not running. Start it with `uv run hubd`.') : e
  })
}

export function onChat(e: Ev & { id: string }) {
  const turns = chats[e.id]?.turns.filter((t) => !t.done) ?? []
  // A stop ends every turn waiting, as in hubd; any other event belongs to the oldest.
  for (const turn of e.kind === 'stopped' ? turns : turns.slice(0, 1)) take(turn, e)
}

const reason = async (r: Response) => {
  const body = await r.json().catch(() => null)
  return new Error(typeof body?.detail === 'string' ? body.detail : `hubd answered ${r.status}`)
}

// Re-reads a chat from hubd: after a dropped event stream, or when its page is opened by link.
export async function loadChat(id: string) {
  const r = await fetch(`/chats/${id}`)
  if (!r.ok) throw r.status === 404 ? new Error('This chat is gone: hubd was restarted.') : await reason(r)
  const { turns, model, effort, project, context, title, earlier_hidden } = (await r.json()) as Meta & { turns: { text: string; events: Ev[]; done: boolean }[] }
  chats[id] = {
    model,
    effort,
    project,
    context,
    title,
    earlier_hidden,
    turns: turns.map((t) => {
      const turn: Turn = { me: t.text, blocks: [], done: false }
      t.events.forEach((e) => take(turn, e))
      turn.done = t.done
      return turn
    }),
  }
}

async function post(path: string, body: object, method = 'POST'): Promise<{ id?: string; context?: Context | null }> {
  const r = await fetch(path, { method, headers: { 'content-type': 'application/json' }, body: JSON.stringify(body) })
  if (!r.ok) throw await reason(r)
  return r.json()
}

// Sends `text`; opens the chat first when `id` is none. Returns the chat's id. A failure throws a message for the pane, and the turn is gone again.
export async function send(id: string | undefined, text: string): Promise<string> {
  try {
    if (!id) {
      const { project, model, effort, sprint, step } = pills
      const opened = await post('/chats', { project, model, effort, ...(project && { sprint, step }) })
      id = opened.id!
      chats[id] = { turns: [], project, model, effort, context: opened.context ?? null }
    }
    const turns = (chats[id] ??= { turns: [] }).turns
    turns.push({ me: text, blocks: [], done: false })
    try {
      await post(`/chats/${id}/message`, { text })
    } catch (e) {
      turns.pop()
      throw e
    }
    return id
  } catch (e) {
    throw e instanceof TypeError ? new Error('hubd is not running. Start it with `uv run hubd`, then send again.') : e
  }
}

// Stop button, Esc Esc: hubd ends the claude process. The turn keeps its text and is marked stopped when hubd's `stopped` event comes; the next message resumes the chat.
export async function stop(id: string) {
  await post(`/chats/${id}/stop`, {}).catch((e) => {
    throw e instanceof TypeError ? new Error('hubd is not running. Start it with `uv run hubd`.') : e
  })
}

// `c` on a Step or Project screen: New chat with that project (and step) set.
export function chatAbout(project: string, step: string | null = null) {
  Object.assign(pills, { project, sprint: null, step })
  location.hash = '#/chat'
}

// What a new chat with these pills would be told, before it opens.
export async function contextOf(project: string, sprint: string | null, step: string | null): Promise<Context> {
  const q = new URLSearchParams({ ...(sprint && { sprint }), ...(step && { step }) })
  const r = await fetch(`/projects/${encodeURIComponent(project)}/context?${q}`)
  if (!r.ok) throw await reason(r)
  return r.json()
}

// The chip's text: "README + sprints (12 kB) · no PROGRESS.md".
export function chip(c: Context) {
  const kb = c.size < 10_000 ? (c.size / 1000).toFixed(1) : Math.round(c.size / 1000)
  return `${c.label || 'nothing found'} (${kb} kB)${c.notes.length ? ' · ' + c.notes.join(' · ') : ''}`
}

// New model or effort for a chat that has started: hubd resumes it with the flag. A failure throws its reason.
export async function change(id: string, patch: Partial<Pick<Meta, 'model' | 'effort'>>) {
  await post(`/chats/${id}`, patch, 'PATCH').catch((e) => {
    throw e instanceof TypeError ? new Error('hubd is not running. Start it with `uv run hubd`.') : e
  })
  Object.assign(chats[id], patch)
}

// The chats hubd keeps in the vault (609), last used first. `open`: in the sidebar; `x` sets it off and the entry stays. `used` is in ms, like Date.now().
export type Saved = { id: string; project: string | null; title: string; model: string; effort: string; used: number; open: boolean }
export const saved = $state<{ list: Saved[] | null }>({ list: null })

export async function loadSaved() {
  const r = await fetch('/chats')
  if (r.ok) saved.list = await r.json()
}

// `title`: the new name (kept in the vault, never in Claude's files); `open: false`: out of the sidebar. The list comes back on hubd's `chats` event.
export async function edit(id: string, patch: { title?: string; open?: boolean }) {
  await post(`/chats/${id}`, patch, 'PATCH').catch((e) => {
    throw e instanceof TypeError ? new Error('hubd is not running. Start it with `uv run hubd`.') : e
  })
  if (patch.title !== undefined && chats[id]) chats[id].title = patch.title.trim().replace(/\s+/g, ' ')
  await loadSaved()
}
