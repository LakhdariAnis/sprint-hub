<script lang="ts">
  import { keys } from './keys.svelte'
  import { router } from './route.svelte'

  const hints: Record<string, [string, string][]> = {
    today: [['j k', 'move'], ['↵', 'open']],
    projects: [['j k', 'move'], ['↵', 'open project']],
    project: [['j k', 'move'], ['↵', 'open step'], ['Esc', 'back']],
    step: [['s', 'start'], ['Esc', 'back']],
    review: [['j k', 'move'], ['a', 'approve'], ['c', 'request changes'], ['Esc', 'cancel']],
  }
  const common: [string, string][] = [['^1 ^2 ^3', 'tab'], ['^B', 'sidebar'], ['?', 'help']]
  const list = $derived([...hints[router.route.name], ...common])
  const r = $derived(router.route)
  const mode = $derived(keys.pending ? 'GO' : r.name === 'step' ? `STEP ${r.id}` : r.name.toUpperCase())
  // shortcut: focus names the route, not the selected row; screens set their own focus from step 213c on.
  const focus = $derived(
    r.name === 'step' ? `${r.project} › ${r.id}`
    : r.name === 'review' && r.id ? `Review › ${r.id}`
    : r.name === 'project' ? r.project
    : r.name[0].toUpperCase() + r.name.slice(1),
  )
</script>

<footer class="keys">
  <span class="md">{mode}</span>
  {#each list as [key, text]}
    <span>{#each key.split(' ') as k}<span class="kb">{k}</span> {/each}{text}</span>
  {/each}
  <span class="fc">focus: {focus}</span>
</footer>

<style>
  .keys {
    height: 32px; flex: none; display: flex; align-items: center; gap: 18px; padding: 0 28px; overflow: hidden;
    background: var(--dk); border-top: 1px solid var(--sel); font: 12px var(--mono); color: var(--fg2); white-space: nowrap;
  }
  .md { background: var(--ac); color: var(--bg); font-weight: 700; padding: 0 8px; border-radius: 3px; line-height: 18px; }
  .keys > span { display: flex; align-items: center; gap: 4px; }
  .fc { margin-left: auto; }
</style>
