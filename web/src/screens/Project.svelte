<script lang="ts">
  import Copy from '../Copy.svelte'
  import { useKeys } from '../keys.svelte'
  import { goal, loadStep, loadSteps, type Step } from '../steps'

  let { project }: { project: string } = $props()
  let steps = $state<Step[]>([])
  let status = $state<'loading' | 'ready' | 'failed'>('loading')

  // Hours = time of the recorded runs; the vault has no planned hours.
  const hours = (s: Step) => {
    const m = s.runs.reduce((a, r) => a + (r.minutes ?? 0), 0)
    return m ? (m / 60).toFixed(1) : '–'
  }

  let sel = $state(0)
  useKeys({
    j: () => (sel = Math.min(sel + 1, steps.length - 1)),
    k: () => (sel = Math.max(sel - 1, 0)),
    Enter: () => cur && (location.hash = `#/steps/${encodeURIComponent(project)}/${encodeURIComponent(cur.step)}`),
    Escape: () => (location.hash = '#/projects'),
  })
  let detail = $state<Step | null>(null)
  const cur = $derived(steps[sel])

  // The list has no spec text, so the preview loads the selected step on its own.
  $effect(() => {
    const c = cur
    detail = null
    if (c) loadStep(c.project, c.step).then((d) => c === cur && (detail = d), () => {})
  })

  $effect(() => {
    sel = 0
    status = 'loading'
    loadSteps(project).then(
      (s) => ((steps = s), (status = 'ready')),
      () => (status = 'failed'),
    )
  })
</script>

<header class="hd">
  <div class="bc">Projects</div>
  <h1>{project}</h1>
</header>

{#if status === 'failed'}
  <p class="dim">Cannot load {project}. Is hubd running?</p>
{:else if status === 'ready'}
  <div class="body">
  <table>
    <thead>
      <tr><th>Id</th><th>Title</th><th>Model</th><th class="n">Hours</th><th class="n">Tasks</th><th>State</th></tr>
    </thead>
    <tbody>
      {#each steps as s, i (s.step)}
        <tr class="row" class:on={i === sel} onclick={() => (sel = i)}>
          <td class="mono">{s.step}</td>
          <td>{s.title}</td>
          <td class="mono dim">{s.model ?? '–'}</td>
          <td class="n mono">{hours(s)}</td>
          <td class="n mono">{s.tasks.filter((t) => t.state === 'done').length}/{s.tasks.length}</td>
          <td class="s-{s.state}" style="color: var(--x)"><span class="dot"></span> {s.state}</td>
        </tr>
      {/each}
    </tbody>
  </table>
  {#if cur}
    <aside class="pv">
      <h2>{cur.step} · {cur.title}</h2>
      <dl>
        <dt>Model</dt><dd class="mono">{cur.model ?? '–'}</dd>
        <dt>Branch</dt><dd class="mono">{cur.branch ?? '–'} {#if cur.branch}<Copy text={cur.branch} label="branch" />{/if}</dd>
        <dt>State</dt><dd class="s-{cur.state}" style="color: var(--x)"><span class="dot"></span> {cur.state}</dd>
      </dl>
      <h3>Goal</h3>
      <p>{detail ? goal(detail.spec) || 'No goal in the spec.' : '…'}</p>
      <h3>Checklist</h3>
      {#each cur.tasks as t}
        <div class="t"><span class="mono">{t.state === 'done' ? '[x]' : t.state === 'doing' ? '[~]' : '[ ]'}</span> {t.text}</div>
      {:else}
        <p class="dim">No checklist yet.</p>
      {/each}
    </aside>
  {/if}
  </div>
  {#if steps.length === 0}<p class="dim">No steps in this project.</p>{/if}
{/if}

<style>
  .hd { padding: 16px 20px 14px; }
  .bc { font-size: 12px; color: var(--fgd); }
  h1 { font-size: 22px; font-weight: 600; margin: 3px 0 0; letter-spacing: -0.01em; line-height: 1.2; }
  .dim { color: var(--fgd); }
  p.dim { padding: 0 20px; }
  .body { display: flex; align-items: flex-start; }
  table { flex: 1; min-width: 0; }
  .row { cursor: pointer; }
  .row:hover { background: var(--lt); }
  .row.on { background: var(--sel); box-shadow: inset 3px 0 0 var(--ac); }
  .pv { width: 340px; flex: none; padding: 0 20px 20px; border-left: 1px solid var(--lt); min-height: 100%; }
  .pv h2 { font-size: 15px; margin: 6px 0 10px; }
  .pv h3 { font-size: 11px; letter-spacing: 0.07em; text-transform: uppercase; color: var(--fgd); font-weight: 400; margin: 16px 0 6px; }
  .pv p { margin: 0; }
  dl { display: grid; grid-template-columns: 60px 1fr; gap: 4px 8px; margin: 0; }
  dt { color: var(--fgd); }
  dd { margin: 0; }
  .t { padding: 2px 0; }
  table { width: 100%; border-collapse: collapse; }
  th { text-align: left; font-size: 11px; letter-spacing: 0.07em; text-transform: uppercase; color: var(--fgd); font-weight: 400; padding: 6px 20px; border-bottom: 1px solid var(--lt); }
  .n { text-align: right; }
  td { padding: 0 20px; height: 34px; border-bottom: 1px solid var(--lt); }
</style>
