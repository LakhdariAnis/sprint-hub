import { test } from 'node:test'
import assert from 'node:assert/strict'
import { startedOn, workspaceTitle } from '../src/steps.ts'

test('the chip has a title only for a project with a workspace', () => {
  assert.equal(workspaceTitle(3), 'Workspace 3')
  assert.equal(workspaceTitle(null), null)
  assert.equal(workspaceTitle(undefined), null)
})
test('the start line names the workspace, and is absent without one', () => {
  assert.equal(startedOn(3), 'Started on workspace 3')
  assert.equal(startedOn(null), null)
})
