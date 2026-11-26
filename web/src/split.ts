// The chat + graph split (658b): chat's share of the width in %, and whether it is open. Kept in localStorage.
export const MIN = 28
export const MAX = 75
export const DEFAULT = 44
const key = 'sprint-hub:split'

export const clamp = (n: number) => Math.min(MAX, Math.max(MIN, n))

export type Saved = { open: boolean; left: number }

// Anything unreadable (nothing saved, bad JSON, a private window) gives the default: closed, 44 %.
export function parse(raw: string | null): Saved {
  try {
    const v = JSON.parse(raw ?? '')
    return { open: v.open === true, left: typeof v.left === 'number' && isFinite(v.left) ? clamp(v.left) : DEFAULT }
  } catch {
    return { open: false, left: DEFAULT }
  }
}

export const read = (): Saved => {
  try { return parse(localStorage.getItem(key)) } catch { return parse(null) }
}
export const write = (s: Saved) => {
  try { localStorage.setItem(key, JSON.stringify(s)) } catch {}
}
