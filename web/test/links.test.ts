import { test } from 'node:test'
import assert from 'node:assert/strict'
import { matcher } from '../src/links.ts'

const nodes = [
  { id: 'api', label: 'api.py', file: 'src/api.py' },
  { id: 'serve', label: 'serve()', file: 'src/api.py' },
  { id: 'load', label: 'load()', file: 'src/store.py' },
  { id: 'load2', label: 'load()', file: 'src/other.py' },
  { id: 'fastapi', label: 'fastapi', file: '' },
]
const links = [
  { source: 'api', target: 'serve' },
  { source: 'serve', target: 'load' },
]
const m = matcher(nodes, links)

test('a label matches exactly, with every node that has it', () => {
  assert.deepEqual(m.ids('serve()'), ['serve'])
  assert.deepEqual(m.ids('load()'), ['load', 'load2'])
  assert.deepEqual(m.ids('fastapi'), ['fastapi'])
})

test('case, spaces and a missing "()" do not match', () => {
  assert.deepEqual(m.ids('Serve()'), [])
  assert.deepEqual(m.ids('serve'), [])
  assert.deepEqual(m.ids(' serve() '), [])
  assert.deepEqual(m.ids(''), [])
})

test('a file path matches its file node only, a bare file name too', () => {
  assert.deepEqual(m.ids('src/api.py'), ['api'])
  assert.deepEqual(m.ids('api.py'), ['api'])
  assert.deepEqual(m.ids('src/api'), [])
})

test('around: the node and one link each way', () => {
  assert.deepEqual([...m.around(['serve'])].sort(), ['api', 'load', 'serve'])
  assert.deepEqual([...m.around(['fastapi'])], ['fastapi'])
})
