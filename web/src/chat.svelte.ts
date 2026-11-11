// Chats of this session, by id (hubd keeps them in memory; 609 makes them last). A turn is the message sent and the answer to it.
export type Turn = { me: string; ai: string; done: boolean; error?: string; asks: Ask[] }
// A permission card (607): Claude wants to run `tool` on `target`. `answer` once Anis (or the 10 min wait) decided; `refused`: hubd said no without asking. `wide`: "Allow for this chat" can cover it.
export type Ask = { request?: string; tool: string; target: string; diff: string | null; wide?: boolean; answer?: string; refused?: string }

// What hubd told Claude about the project, sprint or step (606): the chip above the box.
export type Context = { label: string; size: number; notes: string[] }
export type Meta = { model: string; effort: string; project: string | null; context: Context | null }
export const chats = $state<Record<string, { turns: Turn[] } & Partial<Meta>>>({})

// What the next new chat opens with (the pills). Kept when the page starts another chat (/clear, n). With a project, `sprint` and `step` add their context.
export const pills = $state({ project: null as string | null, model: 'sonnet', effort: 'medium', sprint: null as string | null, step: null as string | null })

// What hubd sends on `/events` for a chat (`chat` events) and in GET /chats/<id> turns, less the fields 608 uses.
type Ev = { kind: string; text?: string; message?: string; answer?: string } & Partial<Ask>

// Events of a message sent mid-turn wait for the turn before it, as in hubd.
function take(turn: Turn, e: Ev) {
  if (e.kind === 'text') turn.ai += e.text ?? ''
  else if (e.kind === 'turn_end' || e.kind === 'stopped') turn.done = true
  else if (e.kind === 'error') Object.assign(turn, { error: e.message || 'Claude failed', done: true })
  else if (e.kind === 'permission') turn.asks.push({ request: e.request, tool: e.tool!, target: e.target!, diff: e.diff ?? null, wide: e.wide })
  else if (e.kind === 'permission_refused') turn.asks.push({ tool: e.tool!, target: e.target!, diff: e.diff ?? null, refused: e.message })
  else if (e.kind === 'permission_answer') {
    const ask = turn.asks.find((a) => a.request === e.request)
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
  const turn = chats[e.id]?.turns.find((t) => !t.done)
  if (turn) take(turn, e)
}

const reason = async (r: Response) => {
  const body = await r.json().catch(() => null)
  return new Error(typeof body?.detail === 'string' ? body.detail : `hubd answered ${r.status}`)
}

// Re-reads a chat from hubd: after a dropped event stream, or when its page is opened by link.
export async function loadChat(id: string) {
  const r = await fetch(`/chats/${id}`)
  if (!r.ok) throw r.status === 404 ? new Error('This chat is gone: hubd was restarted.') : await reason(r)
  const { turns, model, effort, project, context } = (await r.json()) as Meta & { turns: { text: string; events: Ev[]; done: boolean }[] }
  chats[id] = {
    model,
    effort,
    project,
    context,
    turns: turns.map((t) => {
      const turn: Turn = { me: t.text, ai: '', done: false, asks: [] }
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
    turns.push({ me: text, ai: '', done: false, asks: [] })
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
