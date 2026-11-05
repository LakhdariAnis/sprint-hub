import { test } from 'node:test'
import assert from 'node:assert/strict'
import { actions, items, search } from '../src/palette.ts'
import type { Step } from '../src/steps.ts'

const st = (project: string, step: string, state: string, title = step, by: 'claude' | 'me' = 'claude'): Step =>
  ({ project, step, title, state, by, model: null, branch: null, sprint: 1, runs: [], tasks: [], questions: [] })
const all = [
  st('hub', '409b', 'approved', 'Project and Step at a tile'),
  st('hub', '512d', 'doing', 'Command palette'),
  st('hub', '507b', 'done', 'Real approve: right branch'),
  st('hub', '508c', 'changes', 'Real request changes'),
  st('hub', '513c', 'todo', 'Hours'),
  st('tiny-app', '101', 'todo', 'Set up'),
]
const projects = [{ id: 'hub', name: 'hub' }, { id: 'tiny-app', name: 'tiny-app' }]
const pick = (q: string, cur?: Step) => search(items(all, projects, cur), q).map((i) => `${i.kind}:${i.sub}`)

test('empty query: running, review, changes, in that order; no todo, no approved', () => {
  assert.deepEqual(pick(''), ['step:hub/512d', 'step:hub/507b', 'step:hub/508c'])
})
test('an id finds its step first', () => assert.equal(pick('409b')[0], 'step:hub/409b'))
test('a project name puts the project above its steps', () => assert.equal(pick('tiny')[0], 'project:tiny-app'))
test('a screen is found by name', () => assert.equal(pick('settings')[0], 'screen:g s'))
test('no match gives nothing', () => assert.deepEqual(pick('xyzzy'), []))
test('letters in order match, words in any order', () => {
  assert.ok(pick('cmdpl').includes('step:hub/512d'))
  assert.ok(pick('palette command').includes('step:hub/512d'))
})
test('the Approve action beats a title that says approve, and only shows for a done step', () => {
  assert.equal(pick('approve', all[2])[0], 'action:hub/507b')
  assert.ok(!pick('approve', all[0]).some((i) => i.startsWith('action')))
})
test('actions follow the state and who works', () => {
  const names = (s: Step) => actions(s).map((a) => a.label)
  assert.deepEqual(names(all[2]), ['Approve', 'Request changes'])
  assert.deepEqual(names(all[1]), ['Finish run'])
  assert.deepEqual(names(all[3]), ['Start'])
  assert.deepEqual(names({ ...all[4], by: 'me', tasks: [{ text: 'a', state: 'todo' }] }), ['Tick task'])
  assert.deepEqual(names(all[0]), [])
})
