<script lang="ts">
  import { hub } from './hub.svelte'
  import { keys } from './keys.svelte'
</script>

{#if keys.errors}
  <div class="back" role="presentation" onclick={() => (keys.errors = false)}>
    <div class="box" role="dialog" aria-label="Broken files">
      <h2>Broken files <span class="n">{hub.errors.length}</span></h2>
      {#each hub.errors as e}
        <div class="er"><span class="at">{e.path}{e.line ? `:${e.line}` : ''}</span><span class="msg">{e.message}</span></div>
      {:else}
        <p class="dim">No broken files.</p>
      {/each}
      <p class="dim">Fix the file and save: it leaves this list by itself. <span class="kb">Esc</span> closes.</p>
    </div>
  </div>
{/if}

<style>
  .back { position: fixed; inset: 0; background: color-mix(in srgb, var(--bg) 70%, transparent); display: grid; place-items: center; z-index: 10; }
  .box { background: var(--dkr); border: 1px solid var(--mu); border-radius: 8px; padding: 16px 22px; width: min(720px, calc(100vw - 32px)); max-height: calc(100vh - 32px); overflow-y: auto; }
  h2 { font-size: 15px; margin: 0 0 10px; }
  .n { color: var(--y); font: 13px var(--mono); margin-left: 6px; }
  .er { display: flex; flex-direction: column; gap: 2px; padding: 8px 0; border-top: 1px solid var(--sel); overflow-wrap: anywhere; }
  .at { font: 12.5px var(--mono); color: var(--fg2); }
  .msg { color: var(--y); }
  .dim { color: var(--fgd); margin: 12px 0 0; }
</style>
