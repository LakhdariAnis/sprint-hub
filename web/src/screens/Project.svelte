<script lang="ts">
  import Header from '../Header.svelte'
  import Copy from '../Copy.svelte'
  import Inline from '../Inline.svelte'
  import { useKeys } from '../keys.svelte'
  import { goal, groupBySprint, loadStep, loadSteps, type Step } from '../steps'

  let { project }: { project: string } = $props()
  let steps = $state<Step[]>([])
  let status = $state<'loading' | 'ready' | 'failed'>('loading')

  // Hours = time of the recorded runs; the vault has no planned hours.
  const hours = (s: Step) => {
    const m = s.runs.reduce((a, r) => a + (r.minutes ?? 0), 0)
    return m ? (m / 60).toFixed(1) : '–'
  }

  const groups = $derived(groupBySprint(steps))
  // shortcut: groupBySprint puts the current sprint first, so it holds the work; 403 adds the real "needs work" helper.
  const work = $derived(groups[0])
  let gi = $state(0)
  let si = $state(0)
  const group = $derived(groups[gi])
  const cur = $derived(group?.steps[si])
  const pick = (i: number) => i !== gi && ((gi = i), (si = 0))
  const href = (s: Step) => `#/steps/${encodeURIComponent(project)}/${encodeURIComponent(s.step)}`
  useKeys({
    j: () => group && (si = Math.min(si + 1, group.steps.length - 1)),
    k: () => (si = Math.max(si - 1, 0)),
    Enter: () => cur && (location.hash = href(cur)),
    Escape: () => (location.hash = '#/projects'),
  })
  let detail = $state<Step | null>(null)

  // The list has no spec text, so the preview loads the selected step on its own.
  $effect(() => {
    const c = cur
    detail = null
    if (c) loadStep(c.project, c.step).then((d) => c === cur && (detail = d), () => {})
  })

  $effect(() => {
    gi = si = 0
    status = 'loading'
    loadSteps(project).then(
      (s) => ((steps = s), (status = 'ready')),
      () => (status = 'failed'),
    )
  })
</script>

<Header>
  {#snippet crumb()}<a href="#/projects">Projects</a> › {project}{/snippet}
  {project}
</Header>

{#if status === 'failed'}
  <p class="dim pad">Cannot load {project}. Is hubd running?</p>
{:else if status === 'ready'}
  <div class="body">
    <section class="pn list">
      <div class="ph">Sprints<span class="n">{groups.length}</span></div>
      {#each groups as g, i (g.key)}
        <!-- svelte-ignore a11y_click_events_have_key_events -->
        <div class="lr gh row" class:f={i === gi} role="button" tabindex="0" aria-pressed={i === gi} onclick={() => pick(i)} onfocus={() => pick(i)}>
          <b>{g.sprint === null ? 'Steps' : `Sprint ${g.sprint}`}</b>
          {#if g === work}<span class="mark" title="Holds the step that needs work">●</span>{/if}
          <span class="chip g-{g.state}">{g.state}</span>
          <span class="id">{g.done}/{g.steps.length}</span>
        </div>
      {:else}
        <p class="dim pad">No steps in this project.</p>
      {/each}
    </section>

    <section class="pn f list">
      <div class="ph">Steps<span class="n">{group?.steps.length ?? 0}</span><span class="r"><span class="kb">↵</span> open</span></div>
      {#each group?.steps ?? [] as s, i (s.step)}
        {@const done = s.tasks.filter((t) => t.state === 'done').length}
        <!-- svelte-ignore a11y_click_events_have_key_events -->
        <div class="lr grid row" class:f={i === si} role="link" tabindex="0" onclick={() => (si = i)} ondblclick={() => (location.hash = href(s))} onfocus={() => (si = i)}>
          <span class="dot s-{s.state}"></span>
          <span class="id">{s.step}</span>
          <span class="tt">{s.title}</span>
          {#if s.state === 'doing' && s.tasks.length}
            <span class="prog"><span class="pbar" style="--x: var(--b)"><i style="width: {(done / s.tasks.length) * 100}%"></i></span><span class="id">{done}/{s.tasks.length}</span></span>
          {:else}
            <span class="id">{done}/{s.tasks.length}</span>
          {/if}
          <span><span class="chip s-{s.state}">{s.state}</span></span>
        </div>
      {/each}
    </section>

    <section class="pn">
      <div class="ph">Step info<span class="r"><span class="kb">↵</span> open</span></div>
      {#if cur}
        <div class="pv">
          <div>
            <span class="id">{cur.step}</span>
            <h2>{cur.title}</h2>
          </div>
          <p class="desc">{#if detail}<Inline text={goal(detail.spec) || 'No goal in the spec.'} />{:else}…{/if}</p>
          <div class="kv">
            <div><span>STATE</span><b class="s-{cur.state}" style="color: var(--x)">{cur.state}</b></div>
            <div><span>MODEL</span>{cur.model ?? '–'}</div>
            <div><span>HOURS</span>{hours(cur)}</div>
          </div>
          {#if cur.branch}<div class="br"><span class="mono">{cur.branch}</span><Copy text={cur.branch} label="branch" /></div>{/if}
          <div>
            {#each cur.tasks as t}
              <div class="ck {t.state}"><span class="box">{#if t.state === 'done'}✓{/if}</span><span><Inline text={t.text} />{#if t.state === 'doing'} · now{/if}</span></div>
            {:else}
              <p class="dim">No checklist yet.</p>
            {/each}
          </div>
          <div class="sp"></div>
          <div><a class="btn pri" href={href(cur)}>Open <span class="kb">↵</span></a></div>
        </div>
      {:else}
        <p class="dim pad">No step selected.</p>
      {/if}
    </section>
  </div>
{/if}

<style>
  .dim { color: var(--fgd); }
  .pad { padding: 12px 16px; margin: 0; }
  /* Fixed fractions: the columns keep their width whatever is selected. Narrow windows are step 405. */
  .body { padding: 8px 28px 22px; display: grid; grid-template-columns: minmax(0, 3fr) minmax(0, 5fr) minmax(0, 4fr); gap: 20px; align-items: start; }
  .grid { display: grid; align-items: center; column-gap: 12px; padding: 0 16px; grid-template-columns: 10px 40px minmax(0, 1fr) 96px 80px; }
  .gh { display: flex; align-items: center; gap: 12px; padding: 0 16px; }
  .gh b { margin-right: auto; }
  .mark { color: var(--ac); font-size: 11px; }
  .chip.g-planned { background: none; box-shadow: inset 0 0 0 1px var(--mu); }
  .row { min-height: 40px; cursor: pointer; }
  .row:hover { background: var(--lt); }
  .row.f:hover { background: var(--sel); }
  .id { font: 12.5px var(--mono); color: var(--fg2); }
  .tt { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .mdl { font: 11.5px var(--mono); border: 1px solid var(--mu); border-radius: 4px; padding: 0 6px; color: var(--fg2); }
  .prog { display: flex; align-items: center; gap: 6px; }
  .prog .pbar { flex: 1; }
  /* Todo has not started: an outline, not a fill. */
  .chip.s-todo { background: none; box-shadow: inset 0 0 0 1px var(--mu); }
  .pv { padding: 16px; display: flex; flex-direction: column; gap: 12px; }
  .pv p.dim { margin: 0; }
  h2 { font-size: 18px; font-weight: 600; line-height: 1.3; margin: 2px 0 0; }
  .desc { margin: 0; font-size: 13.5px; color: var(--fg2); line-height: 1.55; }
  .kv { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 8px; }
  .kv div { border: 1px solid var(--sel); border-radius: 7px; padding: 7px 10px; background: var(--bg); min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .kv span { display: block; font: 10.5px var(--mono); color: var(--fg2); }
  .kv b { font-weight: 500; }
  .br { display: flex; align-items: center; gap: 8px; font-size: 12.5px; color: var(--fg2); }
  .ck { display: grid; grid-template-columns: 20px 1fr; gap: 10px; padding: 6px 0; border-bottom: 1px solid var(--sel); font-size: 13.5px; align-items: center; }
  .ck:last-child { border-bottom: 0; }
  .ck.todo { color: var(--fg2); }
  .ck.doing { color: var(--ac); font-weight: 500; }
  .box { width: 18px; height: 18px; border-radius: 5px; display: flex; align-items: center; justify-content: center; font-size: 11px; border: 1px solid var(--mu); }
  .done .box { background: var(--g); border-color: var(--g); color: var(--bg); }
  .doing .box { border: 2px solid var(--ac); }
  .sp { flex: 1; }
  .btn { height: 34px; padding: 0 12px; border-radius: 7px; display: inline-flex; align-items: center; gap: 8px; font-size: 13px; text-decoration: none; }
  .btn.pri { background: var(--ac); color: var(--bg); font-weight: 500; }
  .btn.pri .kb { background: var(--bg); color: var(--ac); }
</style>
