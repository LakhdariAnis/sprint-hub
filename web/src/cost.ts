// The dim line under an answer (608): "sonnet · 12 s · 4.1k in / 380 out · $0.02". Only what Claude gave.
export type End = { model?: string | null; cost_usd?: number | null; input_tokens?: number | null; output_tokens?: number | null; duration_ms?: number | null }

const tokens = (n: number) => (n < 1000 ? String(n) : `${(n / 1000).toFixed(1)}k`.replace('.0k', 'k'))
const secs = (ms: number) => (ms < 10_000 ? `${(ms / 1000).toFixed(1)} s`.replace('.0 s', ' s') : ms < 60_000 ? `${Math.round(ms / 1000)} s` : `${Math.floor(ms / 60_000)} min ${Math.round((ms % 60_000) / 1000)} s`)

export function costLine(end: End): string {
  const parts: string[] = []
  // "claude-sonnet-5-5" -> "sonnet"
  if (end.model) parts.push(end.model.replace(/^claude-/, '').replace(/-\d.*$/, ''))
  if (end.duration_ms) parts.push(secs(end.duration_ms))
  const io = [end.input_tokens ? `${tokens(end.input_tokens)} in` : '', end.output_tokens ? `${tokens(end.output_tokens)} out` : ''].filter(Boolean)
  if (io.length) parts.push(io.join(' / '))
  if (end.cost_usd) parts.push(`$${end.cost_usd.toFixed(end.cost_usd < 0.01 ? 3 : 2)}`)
  return parts.join(' · ')
}
