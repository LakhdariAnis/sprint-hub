// A small force layout for the graph pane (no d3: ADR 0004 allows no package). Springs pull linked
// nodes to `length` apart, every pair repels, a weak pull keeps the map centred, and collision keeps
// circles of radius r[i] from overlapping. It runs to rest in one go: 130 nodes take a few ms.

export type Point = { x: number; y: number }

const GAP = 2 // px between two circles at rest

/** Where each node sits, centred on 0,0. Same input, same map: starts on a spiral, no randomness. */
export function layout(r: number[], links: [number, number][], { length = 38, maxTicks = 400 } = {}): { at: Point[]; ticks: number } {
  const n = r.length
  const at = r.map((_, i) => ({ x: 10 * Math.sqrt(i + 0.5) * Math.cos(i * 2.4), y: 10 * Math.sqrt(i + 0.5) * Math.sin(i * 2.4) }))
  const v = r.map(() => ({ x: 0, y: 0 }))
  const deg = r.map(() => 0)
  for (const [s, t] of links) (deg[s]++, deg[t]++)
  let ticks = 0
  for (let alpha = 1; ticks < maxTicks && alpha > 0.005; ticks++, alpha *= 0.985) {
    for (let i = 0; i < n; i++)
      for (let j = i + 1; j < n; j++) {
        const dx = at[i].x - at[j].x, dy = at[i].y - at[j].y
        const f = (70 * alpha) / Math.max(dx * dx + dy * dy, 25)
        v[i].x += dx * f; v[i].y += dy * f; v[j].x -= dx * f; v[j].y -= dy * f
      }
    for (const [s, t] of links) {
      const dx = at[t].x - at[s].x, dy = at[t].y - at[s].y
      const d = Math.hypot(dx, dy) || 1
      // weaker on a hub, and the hub moves less: numpy's 66 springs would throw it off the map
      const f = ((d - length) / d) * alpha * 0.5 / Math.min(deg[s], deg[t]), b = deg[s] / (deg[s] + deg[t])
      v[s].x += dx * f * (1 - b); v[s].y += dy * f * (1 - b); v[t].x -= dx * f * b; v[t].y -= dy * f * b
    }
    let moved = 0
    for (let i = 0; i < n; i++) {
      v[i].x = (v[i].x - at[i].x * 0.04 * alpha) * 0.6
      v[i].y = (v[i].y - at[i].y * 0.04 * alpha) * 0.6
      at[i].x += v[i].x; at[i].y += v[i].y
      moved = Math.max(moved, Math.abs(v[i].x) + Math.abs(v[i].y))
    }
    collide(at, r)
    if (moved < 0.02) break // still
  }
  for (let k = 0; k < 50 && collide(at, r); k++); // the forces may leave a last overlap
  return { at, ticks }
}

/** Pushes overlapping pairs apart; true when it had to move one. */
function collide(at: Point[], r: number[]): boolean {
  let hit = false
  for (let i = 0; i < at.length; i++)
    for (let j = i + 1; j < at.length; j++) {
      let dx = at[j].x - at[i].x, dy = at[j].y - at[i].y
      if (!dx && !dy) dx = (j - i) * 0.01 // same spot: pick a side
      const d = Math.hypot(dx, dy), min = r[i] + r[j] + GAP
      if (d >= min) continue
      const push = (min - d) / d / 2 + 1e-6
      at[i].x -= dx * push; at[i].y -= dy * push; at[j].x += dx * push; at[j].y += dy * push
      hit = true
    }
  return hit
}
