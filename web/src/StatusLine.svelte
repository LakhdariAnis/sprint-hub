<script lang="ts">
  import { router } from './route.svelte'

  // Hints only: the keys themselves arrive in step 212.
  const hints: Record<string, [string, string][]> = {
    today: [['j k', 'move'], ['↵', 'open'], ['Tab', 'next pane']],
    projects: [['j k', 'move'], ['↵', 'open project'], ['/', 'filter']],
    project: [['j k', 'move'], ['↵', 'open step'], ['Esc', 'back']],
    step: [['s', 'start'], ['Esc', 'back']],
    review: [['j k', 'move'], ['a', 'approve'], ['c', 'request changes']],
  }
  const list = $derived(hints[router.route.name])
</script>

<footer class="kb">
  <span class="mode">NORMAL</span>
  {#each list as [key, text]}
    <span><kbd>{key}</kbd> {text}</span>
  {/each}
</footer>

<style>
  .kb {
    height: 28px; flex: none; display: flex; align-items: center; gap: 14px; padding: 0 14px;
    background: var(--dkr); border-top: 1px solid var(--lt); font-size: 11.5px;
    color: var(--fgd); white-space: nowrap;
  }
  .mode { background: var(--ac); color: var(--bg); font: 700 11px/18px var(--mono); padding: 0 8px; border-radius: 4px; }
</style>
