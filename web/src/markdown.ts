// The markdown subset of Claude's answers and the specs: text in, blocks and inline runs out. Svelte draws them, so no HTML is ever built from the text.

export type Run =
  | { t: 'text'; s: string }
  | { t: 'code'; s: string }
  | { t: 'b' | 'i'; kids: Run[] }
  | { t: 'a'; href: string; kids: Run[] }
export type Item = { runs: Run[]; sub?: List }
export type List = { t: 'list'; ordered: boolean; items: Item[] }
export type Block =
  | { t: 'code'; lang: string; text: string }
  | { t: 'h'; n: 1 | 2 | 3; runs: Run[] }
  | List
  | { t: 'table'; head: Run[][]; rows: Run[][][] }
  | { t: 'p'; runs: Run[] }

// `code`, [text](url), **bold**, *italic*. A closing `*` follows a non-space, so `a * b * c` and `*.py and *.ts` stay text.
const INLINE = /`([^`]+)`|\[([^\]]+)\]\(([^)\s]+)\)|\*\*(.+?)\*\*|\*([^*\s](?:[^*]*[^*\s])?)\*/g
// Only these links are links: a `javascript:` target stays text.
const SAFE = /^(https?:\/\/|mailto:)/i

export function inline(src: string): Run[] {
  const out: Run[] = []
  let at = 0
  const text = (s: string) => {
    const l = out.at(-1)
    if (!s) return
    if (l?.t === 'text') l.s += s
    else out.push({ t: 'text', s })
  }
  for (const m of src.matchAll(INLINE)) {
    text(src.slice(at, m.index))
    at = m.index + m[0].length
    if (m[1] !== undefined) out.push({ t: 'code', s: m[1] })
    else if (m[2] !== undefined) {
      if (SAFE.test(m[3])) out.push({ t: 'a', href: m[3], kids: inline(m[2]) })
      else text(m[0])
    } else if (m[4] !== undefined) out.push({ t: 'b', kids: inline(m[4]) })
    else out.push({ t: 'i', kids: inline(m[5]) })
  }
  text(src.slice(at))
  return out
}

const FENCE = /^\s*```\s*([\w+-]*)/
const HEAD = /^(#{1,6})\s+(.*)/
const ITEM = /^(\s*)([-*]|\d+\.)\s+(.*)/
const ROW = /^\s*\|.*\|\s*$/
const RULE = /^\s*\|(\s*:?-+:?\s*\|)+\s*$/
const cells = (l: string) => l.trim().replace(/^\||\|$/g, '').split('|').map((c) => inline(c.trim()))

// An open fence at the end (the answer is still streaming) is a code block too.
export function parse(src: string): Block[] {
  const out: Block[] = []
  const lines = src.split('\n')
  for (let i = 0; i < lines.length; i++) {
    const l = lines[i]
    const last = out.at(-1)
    let m: RegExpMatchArray | null
    if ((m = l.match(FENCE))) {
      const code: string[] = []
      while (++i < lines.length && !FENCE.test(lines[i])) code.push(lines[i])
      out.push({ t: 'code', lang: m[1], text: code.join('\n') })
    } else if ((m = l.match(HEAD))) out.push({ t: 'h', n: Math.min(m[1].length, 3) as 1 | 2 | 3, runs: inline(m[2]) })
    else if (ROW.test(l) && RULE.test(lines[i + 1] ?? '')) {
      const rows: Run[][][] = []
      const head = cells(l)
      for (i += 2; i < lines.length && ROW.test(lines[i]); i++) rows.push(cells(lines[i]))
      i--
      out.push({ t: 'table', head, rows })
    } else if ((m = l.match(ITEM))) {
      const ordered = /\d/.test(m[2])
      const item: Item = { runs: inline(m[3]) }
      // One nesting level: an indented item goes under the last one, deeper ones sit beside it.
      if (m[1].length >= 2 && last?.t === 'list') {
        ;(last.items.at(-1)!.sub ??= { t: 'list', ordered, items: [] }).items.push(item)
      } else if (last?.t === 'list' && last.ordered === ordered && !m[1]) last.items.push(item)
      else out.push({ t: 'list', ordered, items: [item] })
    } else if (!l.trim()) continue
    else if (lines[i - 1]?.trim() && last?.t === 'p') last.runs = inline(joined(last) + ' ' + l.trim())
    // A line with no bullet right under an item is that item's wrapped text.
    else if (lines[i - 1]?.trim() && last?.t === 'list' && /^\s+\S/.test(l)) {
      const item = (last.items.at(-1)!.sub ?? last).items.at(-1)!
      item.runs = inline(plain(item.runs) + ' ' + l.trim())
    } else out.push({ t: 'p', runs: inline(l.trim()) })
  }
  return out
}

// Source text of runs, to extend a paragraph with its next line and re-read it as one.
const plain = (rs: Run[]): string =>
  rs.map((r) => (r.t === 'text' ? r.s : r.t === 'code' ? '`' + r.s + '`' : r.t === 'b' ? '**' + plain(r.kids) + '**' : r.t === 'i' ? '*' + plain(r.kids) + '*' : '[' + plain(r.kids) + '](' + r.href + ')')).join('')
const joined = (p: { runs: Run[] }) => plain(p.runs)
