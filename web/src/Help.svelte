<script lang="ts">
  import { keys } from './keys.svelte'

  const all: [string, string][] = [
    ['j  k', 'move down / up'],
    ['Enter', 'open'],
    ['Esc', 'back'],
    ['g t', 'go to Today'],
    ['g p', 'go to Projects'],
    ['g r', 'go to Review'],
    ['s', 'start the step (Step screen)'],
    ['a', 'approve; press a or y again to merge (Review)'],
    ['c', 'request changes: type the comment, Enter sends, Esc leaves the box (Review)'],
    ['?', 'show / hide this help'],
  ]
</script>

{#if keys.help}
  <div class="back" role="presentation" onclick={() => (keys.help = false)}>
    <div class="box" role="dialog" aria-label="Key help">
      <h2>Keys</h2>
      <dl>
        {#each all as [k, text]}<dt><kbd>{k}</kbd></dt><dd>{text}</dd>{/each}
      </dl>
      <p class="dim">Keys are off while you type in a box.</p>
    </div>
  </div>
{/if}

<style>
  .back { position: fixed; inset: 0; background: color-mix(in srgb, var(--bg) 70%, transparent); display: grid; place-items: center; z-index: 10; }
  .box { background: var(--dkr); border: 1px solid var(--mu); border-radius: 8px; padding: 16px 22px; max-width: 520px; }
  h2 { font-size: 15px; margin: 0 0 10px; }
  dl { display: grid; grid-template-columns: 70px 1fr; gap: 6px 14px; margin: 0; }
  dd { margin: 0; }
  .dim { color: var(--fgd); margin: 12px 0 0; }
</style>
