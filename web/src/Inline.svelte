<script lang="ts">
  // Inline markdown: `code`, **bold**, *italic*, [link](https://…). Never {@html}: a run is text or a Svelte element.
  // A chat answer sets `chips` (659): a code span that names a node of the project graph is a chip that shows it on the map.
  import { getContext } from 'svelte'
  import { inline, type Run } from './markdown'
  import type { Chips } from './links'
  const chips = getContext<Chips | undefined>('chips')
  let { text = '', runs: given }: { text?: string; runs?: Run[] } = $props()
  const runs = $derived(given ?? inline(text))
</script>

{#snippet draw(rs: Run[])}
  {#each rs as r}
    {#if r.t === 'code'}
      {@const ids = chips?.ids(r.s) ?? []}
      {#if ids.length}
        <!-- A span, not a button: it wraps inside the line like text. -->
        <span class="node" role="button" tabindex="0" title="Show on the map" onclick={() => chips!.show(ids, r.s)} onkeydown={(e) => (e.key === 'Enter' || e.key === ' ') && (e.preventDefault(), chips!.show(ids, r.s))}><code>{r.s}</code></span>
      {:else}<code>{r.s}</code>{/if}
    {:else if r.t === 'b'}<b>{@render draw(r.kids)}</b>
    {:else if r.t === 'i'}<em>{@render draw(r.kids)}</em>
    {:else if r.t === 'a'}<a href={r.href} target="_blank" rel="noopener noreferrer">{@render draw(r.kids)}</a>
    {:else}{r.s}{/if}
  {/each}
{/snippet}
{@render draw(runs)}

<style>
  code { font: 0.9em var(--mono); background: var(--bg); padding: 1px 6px; border-radius: 4px; color: var(--c); }
  a { color: var(--ac); }
  .node { cursor: pointer; border-radius: 4px; }
  .node code { color: var(--ac); background: color-mix(in srgb, var(--ac) 14%, var(--bg)); }
  .node:hover code, .node:focus-visible code { background: color-mix(in srgb, var(--ac) 28%, var(--bg)); }
  .node:focus-visible { outline: 2px solid var(--ac); outline-offset: 1px; }
</style>
