import { test } from 'node:test'
import assert from 'node:assert/strict'
import { filter, options, slashQuery, split } from '../src/slash.ts'

test('a lone / opens the menu with all 6 commands', () => {
  assert.equal(slashQuery('/'), '')
  assert.deepEqual(filter('').map((c) => c.name), ['model', 'effort', 'project', 'sprint', 'step', 'clear'])
})
test('/mo keeps /model, the match is split for the underline', () => {
  assert.deepEqual(filter(slashQuery('/mo')!).map((c) => c.name), ['model'])
  assert.deepEqual(split('model', 'mo'), ['mo', 'del'])
})
test('prefix only, case free, nothing found = empty', () => {
  assert.deepEqual(filter('s').map((c) => c.name), ['sprint', 'step'])
  assert.deepEqual(filter(slashQuery('/MO')!).map((c) => c.name), ['model'])
  assert.deepEqual(filter('del'), [])
})
test('no menu unless the box holds only a command', () => {
  for (const t of ['', 'hi /', 'hi', '/model x', '/ ', '/a/b', '\n/']) assert.equal(slashQuery(t), null, t)
})
test('options: models in order, projects with none first, steps and sprints of the project', () => {
  const ctx = { projects: [{ id: 'hub', name: 'sprint-hub v2' }], steps: [{ step: '605', title: 'Pills', sprint: 6 }, { step: '606', title: 'Ctx', sprint: 6 }, { step: '1', title: 'x', sprint: null }] }
  assert.deepEqual(options('model', ctx).map((o) => o.value), ['opus', 'sonnet', 'haiku'])
  assert.deepEqual(options('effort', ctx).map((o) => o.value), ['low', 'medium', 'high'])
  assert.deepEqual(options('project', ctx).map((o) => o.label), ['none', 'sprint-hub v2'])
  assert.deepEqual(options('sprint', ctx).map((o) => o.value), ['', '6'])
  assert.deepEqual(options('step', ctx).map((o) => o.value), ['', '605', '606', '1'])
  assert.deepEqual(options('clear', ctx), [])
})
