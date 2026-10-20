<script lang="ts">
  // Inline markdown: `code` and **bold**. Plain text otherwise (no {@html}).
  let { text }: { text: string } = $props()
  const parts = $derived(text.split(/(`[^`]+`|\*\*[^*]+\*\*)/))
</script>

{#each parts as p}{#if p.startsWith('`') && p.length > 2}<code>{p.slice(1, -1)}</code>{:else if p.startsWith('**') && p.length > 4}<b>{p.slice(2, -2)}</b>{:else}{p}{/if}{/each}

<style>
  code { font: 0.9em var(--mono); background: var(--bg); padding: 1px 6px; border-radius: 4px; color: var(--c); }
</style>
