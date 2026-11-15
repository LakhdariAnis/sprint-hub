import { test } from 'node:test'
import assert from 'node:assert/strict'
import { costLine } from '../src/cost.ts'

test('every field Claude gives', () => {
  assert.equal(costLine({ model: 'claude-sonnet-5-5', duration_ms: 12_400, input_tokens: 4100, output_tokens: 380, cost_usd: 0.02 }), 'sonnet · 12 s · 4.1k in / 380 out · $0.02')
})
test('only the fields given: nothing for null, zero or missing', () => {
  assert.equal(costLine({ model: null, duration_ms: 800, input_tokens: 0, output_tokens: 12, cost_usd: null }), '0.8 s · 12 out')
  assert.equal(costLine({}), '')
})
test('small cost keeps 3 decimals, long turns show minutes, round thousands drop the .0', () => {
  assert.equal(costLine({ cost_usd: 0.0039, duration_ms: 72_000, input_tokens: 52_000 }), '1 min 12 s · 52k in · $0.004')
})
