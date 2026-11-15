<script lang="ts">
  // A markdown text drawn as elements (the subset in markdown.ts). Specs and chat answers share it.
  import Copy from './Copy.svelte'
  import Inline from './Inline.svelte'
  import { parse, type List } from './markdown'

  let { text, skipTitle = false }: { text: string; skipTitle?: boolean } = $props()
  // A leading `# Step NN — title` repeats the page title: every screen that shows a spec already has it.
  const blocks = $derived(parse(text).filter((b, i) => !(skipTitle && i === 0 && b.t === 'h' && b.n === 1)))

  // `y` on a focused code block clicks its copy button.
  const yank = (e: KeyboardEvent) => e.key === 'y' && !e.ctrlKey && !e.metaKey && !e.altKey && (e.currentTarget as HTMLElement).querySelector<HTMLElement>('.cp')?.click()
</script>

{#snippet list(l: List)}
  <svelte:element this={l.ordered ? 'ol' : 'ul'}>
    {#each l.items as it}<li><Inline runs={it.runs} />{#if it.sub}{@render list(it.sub)}{/if}</li>{/each}
  </svelte:element>
{/snippet}

<div class="md">
  {#each blocks as b}
    {#if b.t === 'code'}
      <!-- svelte-ignore a11y_no_noninteractive_tabindex, a11y_no_noninteractive_element_interactions -->
      <div class="code" role="group" aria-label="Code{b.lang ? ' ' + b.lang : ''}" tabindex="0" onkeydown={yank}><Copy text={b.text} label="code" /><pre>{b.text}</pre></div>
    {:else if b.t === 'h'}
      <p class="h h{b.n}"><Inline runs={b.runs} /></p>
    {:else if b.t === 'list'}
      {@render list(b)}
    {:else if b.t === 'table'}
      <div class="tbl"><table>
        <thead><tr>{#each b.head as c}<th><Inline runs={c} /></th>{/each}</tr></thead>
        <tbody>{#each b.rows as r}<tr>{#each r as c}<td><Inline runs={c} /></td>{/each}</tr>{/each}</tbody>
      </table></div>
    {:else}
      <p><Inline runs={b.runs} /></p>
    {/if}
  {/each}
</div>

<style>
  .md { line-height: 1.65; min-width: 0; overflow-wrap: anywhere; }
  .md > :first-child { margin-top: 0; }
  p { margin: 0 0 10px; }
  .h { font-weight: 600; margin: 16px 0 6px; }
  .h1 { font-size: 20px; }
  .h2 { font-size: 17px; }
  .h3 { font-size: 15px; }
  ul, ol { margin: 0 0 10px; padding-left: 22px; }
  li ul, li ol { margin: 2px 0; }
  li { margin: 2px 0; }
  /* Wide code scrolls inside its block; the page does not. */
  pre { margin: 0; overflow-x: auto; white-space: pre; font: 12.5px/1.6 var(--mono); }
  .code { position: relative; margin: 6px 0 10px; padding: 10px 14px; background: var(--dkr); border: 1px solid var(--sel); border-radius: 8px; }
  .code:focus-visible { outline: 2px solid var(--ac); outline-offset: 1px; }
  .code :global(.cp) { position: absolute; top: 6px; right: 6px; }
  .tbl { overflow-x: auto; margin: 6px 0 10px; }
  table { border-collapse: collapse; font-size: 0.95em; }
  th, td { padding: 4px 12px; border: 1px solid var(--sel); text-align: left; }
  th { background: var(--dkr); font-weight: 600; }
</style>
