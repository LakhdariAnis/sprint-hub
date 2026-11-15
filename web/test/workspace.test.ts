import { test } from 'node:test'
import assert from 'node:assert/strict'
import { focusProject, startedOn, workspaceTitle } from '../src/steps.ts'

test('the chip has a title only for a project with a workspace', () => {
  assert.equal(workspaceTitle(3), 'Workspace 3')
  assert.equal(workspaceTitle(null), null)
  assert.equal(workspaceTitle(undefined), null)
})
test('the start line names the workspace, and is absent without one', () => {
  assert.equal(startedOn(3), 'Started on workspace 3')
  assert.equal(startedOn(null), null)
})

const reply = (status: number, body: unknown) => async () => new Response(JSON.stringify(body), { status })
test('focusProject posts to the project and is null when hubd switched', async () => {
  let seen = ''
  globalThis.fetch = (async (url: string, init: RequestInit) => ((seen = `${init.method} ${url}`), reply(200, { workspace: 3 })())) as typeof fetch
  assert.equal(await focusProject('my proj'), null)
  assert.equal(seen, 'POST /projects/my%20proj/focus')
})
test('focusProject gives hubd reason, or a fallback when there is none', async () => {
  globalThis.fetch = reply(404, { detail: 'demo has no workspace' }) as typeof fetch
  assert.equal(await focusProject('demo'), 'demo has no workspace')
  globalThis.fetch = reply(503, 'nope') as typeof fetch
  assert.equal(await focusProject('demo'), 'hubd answered 503')
  globalThis.fetch = (async () => { throw new TypeError('fetch failed') }) as typeof fetch
  assert.equal(await focusProject('demo'), 'Cannot reach hubd')
})
