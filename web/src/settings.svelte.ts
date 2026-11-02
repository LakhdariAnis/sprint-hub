export type Check = { ok: boolean; text: string; fix: string | null }
export type Doctor = { vault: string; version: string; service: string; checks: Check[] }
export type Settings = { path: string; terminal: string[]; reminder_hour: number; error: string | null; comments: boolean; restart: string[] }

// What the Settings screen shows: hub.toml as hubd runs with it, and the `hubd doctor` lines. Loaded before the screen shows (nav.svelte.ts).
export const sx = $state({ settings: null as Settings | null, doctor: null as Doctor | null })

export async function loadSettings() {
  const [s, d] = await Promise.all([fetch('/settings'), fetch('/doctor')])
  if (!s.ok || !d.ok) throw new Error(`settings ${s.status}, doctor ${d.status}`)
  sx.settings = await s.json()
  sx.doctor = await d.json()
}

// null = saved; else why it was refused.
export async function saveSettings(change: Partial<Pick<Settings, 'terminal' | 'reminder_hour'>>): Promise<string | null> {
  const cur = sx.settings!
  const r = await fetch('/settings', {
    method: 'PUT',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ terminal: cur.terminal, reminder_hour: cur.reminder_hour, ...change }),
  })
  const body = await r.json()
  if (!r.ok) return typeof body.detail === 'string' ? body.detail : 'refused'
  sx.settings = body
  return null
}
