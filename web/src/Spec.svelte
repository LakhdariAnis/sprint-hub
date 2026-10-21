<script lang="ts">
  import Copy from './Copy.svelte'
  import Inline from './Inline.svelte'

  let { text }: { text: string } = $props()

  type Block =
    | { t: 'code'; text: string }
    | { t: 'h'; n: number; text: string }
    | { t: 'ul' | 'ol'; items: string[] }
    | { t: 'p'; text: string }

  // shortcut: headings, lists, fenced code and paragraphs only (no tables, quotes or nested lists); upgrade if a spec needs them.
  function parse(src: string): Block[] {
    const out: Block[] = []
    const lines = src.split('\n')
    for (let i = 0; i < lines.length; i++) {
      const l = lines[i]
      let m: RegExpMatchArray | null
      if (l.startsWith('```')) {
        const code: string[] = []
        while (++i < lines.length && !lines[i].startsWith('```')) code.push(lines[i])
        out.push({ t: 'code', text: code.join('\n') })
      } else if ((m = l.match(/^(#{1,6})\s+(.*)/))) out.push({ t: 'h', n: m[1].length, text: m[2] })
      else if ((m = l.match(/^\s*([-*]|\d+\.)\s+(.*)/))) {
        const t = /\d/.test(m[1]) ? 'ol' : 'ul'
        const last = out.at(-1)
        // A list line without its own bullet (wrapped text) continues the previous item.
        if (last?.t === t) last.items.push(m[2])
        else out.push({ t, items: [m[2]] })
      } else if (!l.trim()) continue
      else {
        const last = out.at(-1)
        if (last?.t === 'p' && lines[i - 1].trim()) last.text += ' ' + l.trim()
        else if (last && (last.t === 'ul' || last.t === 'ol') && /^\s+\S/.test(l) && lines[i - 1].trim()) last.items[last.items.length - 1] += ' ' + l.trim()
        else out.push({ t: 'p', text: l.trim() })
      }
    }
    return out
  }
  // A leading `# Step NN — title` repeats the page title: every screen that shows a spec already has it.
  const blocks = $derived(parse(text).filter((b, i) => !(i === 0 && b.t === 'h' && b.n === 1)))
</script>

<div class="md">
  {#each blocks as b}
    {#if b.t === 'code'}
      <div class="code"><Copy text={b.text} label="code" /><pre>{b.text}</pre></div>
    {:else if b.t === 'h'}
      <p class="h h{Math.min(b.n, 3)}"><Inline text={b.text} /></p>
    {:else if b.t === 'ul'}
      <ul>{#each b.items as it}<li><Inline text={it} /></li>{/each}</ul>
    {:else if b.t === 'ol'}
      <ol>{#each b.items as it}<li><Inline text={it} /></li>{/each}</ol>
    {:else if b.t === 'p'}
      <p><Inline text={b.text} /></p>
    {/if}
  {/each}
</div>

<style>
  .md { line-height: 1.65; }
  .md > :first-child { margin-top: 0; }
  p { margin: 0 0 10px; }
  .h { font-weight: 600; margin: 16px 0 6px; }
  .h1 { font-size: 20px; }
  .h2 { font-size: 17px; }
  .h3 { font-size: 15px; }
  ul, ol { margin: 0 0 10px; padding-left: 22px; }
  li { margin: 2px 0; }
  pre { margin: 0; white-space: pre-wrap; word-break: break-word; font: 12.5px/1.6 var(--mono); }
  .code { position: relative; margin: 6px 0 10px; padding: 10px 14px; background: var(--dkr); border: 1px solid var(--sel); border-radius: 8px; }
  .code :global(.cp) { position: absolute; top: 6px; right: 6px; }
</style>
