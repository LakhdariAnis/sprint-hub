import { test } from 'node:test'
import assert from 'node:assert/strict'
import { inline, parse, type Run } from '../src/markdown.ts'

const txt = (s: string): Run => ({ t: 'text', s })

test('inline: code, bold, italic, link, nesting', () => {
  assert.deepEqual(inline('a `x*y` **b `c`** *d* [e](https://x.org/p?q=1)'), [
    txt('a '), { t: 'code', s: 'x*y' }, txt(' '), { t: 'b', kids: [txt('b '), { t: 'code', s: 'c' }] }, txt(' '),
    { t: 'i', kids: [txt('d')] }, txt(' '), { t: 'a', href: 'https://x.org/p?q=1', kids: [txt('e')] },
  ])
})
test('inline: stars around spaces and globs stay text; javascript: is not a link', () => {
  assert.deepEqual(inline('2 * 3 * 4'), [txt('2 * 3 * 4')])
  assert.deepEqual(inline('*.py and *.ts'), [txt('*.py and *.ts')])
  assert.deepEqual(inline('[x](javascript:alert(1))'), [txt('[x](javascript:alert(1))')])
})
test('fenced code keeps its lines and language', () => {
  assert.deepEqual(parse('before\n```python\nprint("hi")\n\n  x = 1\n```\nafter'), [
    { t: 'p', runs: [txt('before')] }, { t: 'code', lang: 'python', text: 'print("hi")\n\n  x = 1' }, { t: 'p', runs: [txt('after')] },
  ])
})
test('an unclosed fence is code to the end (streaming)', () => {
  assert.deepEqual(parse('look:\n```js\nlet a = 1\nlet b'), [{ t: 'p', runs: [txt('look:')] }, { t: 'code', lang: 'js', text: 'let a = 1\nlet b' }])
  assert.deepEqual(parse('```'), [{ t: 'code', lang: '', text: '' }])
})
test('headings # to ###; deeper ones stay ###', () => {
  assert.deepEqual(parse('# A\n## B\n### C\n###### D').map((b) => b.t === 'h' && b.n), [1, 2, 3, 3])
})
test('lists: bullets, numbers, one nesting level, wrapped item', () => {
  const [ul, ol] = parse('- one\n  wraps\n- two\n  - sub a\n  - sub b\n\n1. x\n2. y')
  assert.deepEqual(ul, {
    t: 'list', ordered: false, items: [
      { runs: [txt('one wraps')] },
      { runs: [txt('two')], sub: { t: 'list', ordered: false, items: [{ runs: [txt('sub a')] }, { runs: [txt('sub b')] }] } },
    ],
  })
  assert.deepEqual(ol, { t: 'list', ordered: true, items: [{ runs: [txt('x')] }, { runs: [txt('y')] }] })
})
test('table: header, rule, rows; no rule yet (streaming) is a paragraph', () => {
  const [t] = parse('| a | **b** |\n|---|:--:|\n| 1 | 2 |\n| 3 | 4 |')
  assert.deepEqual(t, { t: 'table', head: [[txt('a')], [{ t: 'b', kids: [txt('b')] }]], rows: [[[txt('1')], [txt('2')]], [[txt('3')], [txt('4')]]] })
  assert.equal(parse('| a | b |')[0].t, 'p')
})
test('paragraphs: blank line splits, a wrapped line joins', () => {
  assert.deepEqual(parse('one\ntwo\n\nthree'), [{ t: 'p', runs: [txt('one two')] }, { t: 'p', runs: [txt('three')] }])
})
test('markup in the text is text: no tag becomes a node', () => {
  assert.deepEqual(parse('<b>hi</b><script>alert(1)</script>'), [{ t: 'p', runs: [txt('<b>hi</b><script>alert(1)</script>')] }])
  assert.deepEqual(parse('- <img src=x onerror=alert(1)>')[0], { t: 'list', ordered: false, items: [{ runs: [txt('<img src=x onerror=alert(1)>')] }] })
})
