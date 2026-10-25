import { test } from 'node:test'
import assert from 'node:assert/strict'
import { needsWork, type Step } from '../src/steps.ts'

const st = (step: string, state: string, sprint: number | null = 1): Step =>
  ({ project: 'p', step, title: step, state, by: 'claude', model: null, branch: null, sprint, runs: [], tasks: [], questions: [] })
const pick = (...s: Step[]) => needsWork(s)?.step

test('doing beats changes, done and todo', () => {
  assert.equal(pick(st('101', 'todo'), st('102', 'done'), st('103', 'changes'), st('104', 'doing')), '104')
})
test('changes, then done, then todo', () => {
  assert.equal(pick(st('101', 'todo'), st('102', 'done'), st('103', 'changes')), '103')
  assert.equal(pick(st('101', 'todo'), st('102', 'done')), '102')
  assert.equal(pick(st('102', 'todo'), st('101', 'approved'), st('103', 'todo')), '102')
})
test('same state: lowest id, not file order', () => {
  assert.equal(pick(st('110', 'doing'), st('20', 'doing')), '20')
})
test('only the current sprint counts', () => {
  assert.equal(pick(st('101', 'approved', 1), st('201', 'todo', 2), st('202', 'doing', 3)), '201')
})
test('no current sprint: newest sprint, its first step', () => {
  assert.equal(pick(st('101', 'approved', 1), st('201', 'approved', 2), st('202', 'approved', 2)), '201')
})
test('no steps', () => assert.equal(pick(), undefined))
