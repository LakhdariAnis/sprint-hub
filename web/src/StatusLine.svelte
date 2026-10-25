<script lang="ts">
  import { keys } from './keys.svelte'
  import { hub } from './hub.svelte'
  import { router } from './route.svelte'
  import { key, steps } from './store.svelte'

  const r = $derived(router.route)
  // Only keys that do something now: start and approve depend on the step's state.
  const cur = $derived(
    r.name === 'step' ? steps[key(r.project, r.id)]
    : r.name === 'review' && r.project && r.id ? steps[key(r.project, r.id)]
    : undefined,
  )
  const canStart = $derived(!!cur && (cur.state === 'todo' || cur.state === 'changes') && cur.by !== 'me')
  // Review without a step in the URL shows the oldest waiting one.
  const canReview = $derived(cur ? cur.state === 'done' : r.name === 'review' && hub.review > 0)
  const when = (on: boolean, h: [string, string][]) => (on ? h : [])
  const hints = $derived<Record<string, [string, string][]>>({
    today: [['p n m w q d', 'pane'], ['j k', 'move'], ['↵', 'open']],
    projects: [['↑ ↓', 'move'], ['→ ↵', 'open project']],
    project: [['j k', 'move'], ['h l', 'column'], ['↵', 'open step'], ['Esc', 'back']],
    step: [...when(canStart, [['s', 'start']]), ...when(cur?.by === 'me', [['x', 'tick']]), ['Esc', 'back']],
    questions: [['j k', 'move'], ['↵', 'open step']],
    review: [['j k', 'move'], ...when(canReview, [['a', 'approve'], ['c', 'request changes'], ['Esc', 'cancel']])],
  })
  const common: [string, string][] = [['1 2 3 4', 'tab'], ['b', 'sidebar'], ['?', 'help']]
  const list = $derived([...(hints[r.name] ?? []), ...common])
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
  /* Below 1200 px the hints fill the line: drop the focus name rather than cut it mid-word. */
  @media (max-width: 1200px) { .keys > .fc { display: none; } }
</style>
