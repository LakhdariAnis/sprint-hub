import { test } from 'node:test'
import assert from 'node:assert/strict'
import { clamp, parse } from '../src/split.ts'

test('clamp keeps the chat between 28 and 75 %', () => {
  assert.equal(clamp(10), 28)
  assert.equal(clamp(90), 75)
  assert.equal(clamp(50), 50)
})

test('parse: default when nothing or junk is saved, clamped width when it is', () => {
  assert.deepEqual(parse(null), { open: false, left: 44 })
  assert.deepEqual(parse('{nope'), { open: false, left: 44 })
  assert.deepEqual(parse('{"open":true,"left":60}'), { open: true, left: 60 })
  assert.deepEqual(parse('{"open":true,"left":5}'), { open: true, left: 28 })
  assert.deepEqual(parse('{"open":"yes","left":"x"}'), { open: false, left: 44 })
})
