<script lang="ts">
  import Copy from './Copy.svelte'

  let { text }: { text: string } = $props()
  // Odd parts are fenced code blocks, each with its own copy button.
  const parts = $derived(text.split(/(```[^\n]*\n[\s\S]*?```)/))
  const code = (block: string) => block.replace(/^```[^\n]*\n/, '').replace(/\n?```$/, '')
</script>

{#each parts as p, i}
  {#if i % 2}
    <div class="code"><Copy text={code(p)} label="code" /><pre>{code(p)}</pre></div>
  {:else}<pre class="txt">{p}</pre>{/if}
{/each}

<style>
  pre { margin: 0; white-space: pre-wrap; word-break: break-word; }
  .txt { font-family: var(--sans); }
  .code { position: relative; margin: 6px 0; padding: 10px 12px; background: var(--dk); border: 1px solid var(--lt); border-radius: 6px; font-size: 12px; }
  .code :global(.cp) { position: absolute; top: 6px; right: 6px; }
</style>
