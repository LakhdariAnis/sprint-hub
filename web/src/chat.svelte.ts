// Chats of this session, by id (hubd keeps them in memory; 609 makes them last). A turn is the message sent and the answer to it.
export type Turn = { me: string; ai: string; done: boolean; error?: string }

export const chats = $state<Record<string, { turns: Turn[] }>>({})

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
  const { turns } = (await r.json()) as { turns: { text: string; events: Ev[]; done: boolean }[] }
  chats[id] = {
    turns: turns.map((t) => {
      const turn: Turn = { me: t.text, ai: '', done: false }
      t.events.forEach((e) => take(turn, e))
      turn.done = t.done
      return turn
    }),
  }
}

async function post(path: string, body: object): Promise<{ id?: string }> {
  const r = await fetch(path, { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(body) })
  if (!r.ok) throw await reason(r)
  return r.json()
}

// Sends `text`; opens the chat first when `id` is none. Returns the chat's id. A failure throws a message for the pane, and the turn is gone again.
export async function send(id: string | undefined, text: string): Promise<string> {
  try {
    // 605 picks these with the pills.
    id ??= (await post('/chats', { model: 'sonnet', effort: 'medium' })).id!
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
