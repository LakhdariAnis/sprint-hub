// Chats of this session, by id (hubd keeps them in memory; 609 makes them last). A turn is the message sent and the answer to it.
export type Turn = { me: string; ai: string; done: boolean; error?: string }

export type Meta = { model: string; effort: string; project: string | null }
export const chats = $state<Record<string, { turns: Turn[] } & Partial<Meta>>>({})

// What the next new chat opens with (the pills). Kept when the page starts another chat (/clear, n). `sprint` and `step` only show here: 606 loads their context.
export const pills = $state({ project: null as string | null, model: 'sonnet', effort: 'medium', sprint: null as string | null, step: null as string | null })

// What hubd sends on `/events` for a chat (`chat` events) and in GET /chats/<id> turns, less the fields 608 uses.
type Ev = { kind: string; text?: string; message?: string }

// Events of a message sent mid-turn wait for the turn before it, as in hubd.
function take(turn: Turn, e: Ev) {
  if (e.kind === 'text') turn.ai += e.text ?? ''
  else if (e.kind === 'turn_end' || e.kind === 'stopped') turn.done = true
  else if (e.kind === 'error') Object.assign(turn, { error: e.message || 'Claude failed', done: true })
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
  const { turns, model, effort, project } = (await r.json()) as Meta & { turns: { text: string; events: Ev[]; done: boolean }[] }
  chats[id] = {
    model,
    effort,
    project,
    turns: turns.map((t) => {
      const turn: Turn = { me: t.text, ai: '', done: false }
      t.events.forEach((e) => take(turn, e))
      turn.done = t.done
      return turn
    }),
  }
}

async function post(path: string, body: object, method = 'POST'): Promise<{ id?: string }> {
  const r = await fetch(path, { method, headers: { 'content-type': 'application/json' }, body: JSON.stringify(body) })
  if (!r.ok) throw await reason(r)
  return r.json()
}

// Sends `text`; opens the chat first when `id` is none. Returns the chat's id. A failure throws a message for the pane, and the turn is gone again.
export async function send(id: string | undefined, text: string): Promise<string> {
  try {
    if (!id) {
      const { project, model, effort } = pills
      id = (await post('/chats', { project, model, effort })).id!
      chats[id] = { turns: [], project, model, effort }
    }
    const turns = (chats[id] ??= { turns: [] }).turns
    turns.push({ me: text, ai: '', done: false })
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

// New model or effort for a chat that has started: hubd resumes it with the flag. A failure throws its reason.
export async function change(id: string, patch: Partial<Pick<Meta, 'model' | 'effort'>>) {
  await post(`/chats/${id}`, patch, 'PATCH').catch((e) => {
    throw e instanceof TypeError ? new Error('hubd is not running. Start it with `uv run hubd`.') : e
  })
  Object.assign(chats[id], patch)
}
