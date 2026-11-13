<script lang="ts">
  // Inline markdown: `code`, **bold**, *italic*, [link](https://…). Never {@html}: a run is text or a Svelte element.
  import { inline, type Run } from './markdown'
  let { text = '', runs: given }: { text?: string; runs?: Run[] } = $props()
  const runs = $derived(given ?? inline(text))
</script>

{#snippet draw(rs: Run[])}
  {#each rs as r}
    {#if r.t === 'code'}<code>{r.s}</code>
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
</style>
