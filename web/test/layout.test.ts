import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { layout, type Point } from '../src/graph/layout.ts'

// The real graphify sample hubd's tests use (43 nodes, 112 links), plus a bigger made-up one.
const sample = JSON.parse(readFileSync(new URL('../../tests/fixtures/graphify/graph.json', import.meta.url), 'utf8'))
const ids: string[] = sample.nodes.map((n: { id: string }) => n.id)
const links: [number, number][] = sample.links.map((l: { source: string; target: string }) => [ids.indexOf(l.source), ids.indexOf(l.target)])
const deg = ids.map((_, i) => links.filter((l) => l.includes(i)).length)
const radius = deg.map((d) => 3.5 + Math.sqrt(d) * 1.9)

function overlaps(at: Point[], r: number[]) {
  let n = 0
  for (let i = 0; i < at.length; i++)
    for (let j = i + 1; j < at.length; j++) if (Math.hypot(at[i].x - at[j].x, at[i].y - at[j].y) < r[i] + r[j]) n++
  return n
}

test('the sample settles before the tick limit, with no two nodes overlapping', () => {
  const { at, ticks } = layout(radius, links)
  assert.ok(ticks < 400, `${ticks} ticks`)
  assert.equal(overlaps(at, radius), 0)
  assert.ok(at.every((p) => Number.isFinite(p.x) && Number.isFinite(p.y)))
})

test('linked nodes sit closer than unlinked ones', () => {
  const { at } = layout(radius, links)
  const d = (i: number, j: number) => Math.hypot(at[i].x - at[j].x, at[i].y - at[j].y)
  const linked = new Set(links.map(([s, t]) => `${Math.min(s, t)} ${Math.max(s, t)}`))
  const near: number[] = [], far: number[] = []
  for (let i = 0; i < at.length; i++)
    for (let j = i + 1; j < at.length; j++) (linked.has(`${i} ${j}`) ? near : far).push(d(i, j))
  const mean = (xs: number[]) => xs.reduce((a, b) => a + b, 0) / xs.length
  assert.ok(mean(near) < mean(far) / 2, `${mean(near)} vs ${mean(far)}`)
})

test('150 nodes, many on one hub: still no overlap, and the same input gives the same map', () => {
  const big: [number, number][] = Array.from({ length: 149 }, (_, i) => [i + 1, i % 5 ? (i * 7) % (i + 1) : 0])
  const r = Array.from({ length: 150 }, (_, i) => (i ? 4 : 30))
  const a = layout(r, big), b = layout(r, big)
  assert.equal(overlaps(a.at, r), 0)
  assert.deepEqual(a.at, b.at)
})

test('no links and one node: nothing breaks', () => {
  assert.deepEqual(layout([], []).at, [])
  assert.equal(layout([5], []).at.length, 1)
  assert.equal(overlaps(layout([5, 5, 5], []).at, [5, 5, 5]), 0)
})

test('a library 66 files import (numpy in tinyml) stays on the map', () => {
  const star: [number, number][] = Array.from({ length: 66 }, (_, i) => [i + 1, 0])
  const chain: [number, number][] = Array.from({ length: 65 }, (_, i) => [i + 1, i + 2])
  const { at } = layout(Array(67).fill(4), [...star, ...chain])
  assert.ok(at.every((p) => Math.abs(p.x) < 1000 && Math.abs(p.y) < 1000), JSON.stringify(at[0]))
})
