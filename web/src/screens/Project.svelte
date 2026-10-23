<script lang="ts">
  import Header from '../Header.svelte'
  import Copy from '../Copy.svelte'
  import Inline from '../Inline.svelte'
  import { useKeys } from '../keys.svelte'
  import { goal, groupBySprint, loadStep, loadSteps, type Group, type Step } from '../steps'

  let { project }: { project: string } = $props()
  let steps = $state<Step[]>([])
  let status = $state<'loading' | 'ready' | 'failed'>('loading')

  // Hours = time of the recorded runs; the vault has no planned hours.
  const hours = (s: Step) => {
    const m = s.runs.reduce((a, r) => a + (r.minutes ?? 0), 0)
    return m ? (m / 60).toFixed(1) : '–'
  }

  const hrs = (min: number) => (min ? (min / 60).toFixed(1) : '–')

  // Fold state per project: {sprint key: open}. A group without an entry is open only when it is the current one.
  const foldKey = () => `sprint-hub:folds:${project}`
  let folds = $state<Record<string, boolean>>({})
  const isOpen = (g: Group) => folds[g.key] ?? g.state === 'current'
  const toggle = (g: Group, open = !isOpen(g)) => {
    folds[g.key] = open
    try { localStorage.setItem(foldKey(), JSON.stringify(folds)) } catch {}
  }

  const groups = $derived(groupBySprint(steps))
  type Row = { g: Group; s?: Step }
  const rows = $derived(groups.flatMap((g): Row[] => [{ g }, ...(isOpen(g) ? g.steps.map((s) => ({ g, s })) : [])]))

  let sel = $state(0)
  const href = (s: Step) => `#/steps/${encodeURIComponent(project)}/${encodeURIComponent(s.step)}`
  const row = $derived(rows[sel])
  const cur = $derived(row?.s)
  useKeys({
    j: () => (sel = Math.min(sel + 1, rows.length - 1)),
    k: () => (sel = Math.max(sel - 1, 0)),
    Enter: () => (cur ? (location.hash = href(cur)) : row && toggle(row.g)),
    l: () => row && !cur && toggle(row.g, true),
    h: () => row && !cur && toggle(row.g, false),
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
    sel = 0
    try { folds = JSON.parse(localStorage.getItem(foldKey()) ?? '{}') } catch { folds = {} }
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
    <section class="pn f list">
      <div class="ph">Steps<span class="n">{steps.length}</span><span class="r"><span class="kb">↵</span> open</span></div>
      <div class="lh grid"><span></span><span>id</span><span>title</span><span>model</span><span>hours</span><span>tasks</span><span>state</span></div>
      {#each rows as r, i (r.s ? r.s.step : 'g' + r.g.key)}
        {#if r.s}
          {@const s = r.s}
          {@const done = s.tasks.filter((t) => t.state === 'done').length}
          <!-- svelte-ignore a11y_click_events_have_key_events -->
          <div class="lr grid row" class:f={i === sel} role="link" tabindex="0" onclick={() => (sel = i)} ondblclick={() => (location.hash = href(s))} onfocus={() => (sel = i)}>
            <span class="dot s-{s.state}"></span>
            <span class="id">{s.step}</span>
            <span class="tt">{s.title}</span>
            <span>{#if s.model}<span class="mdl">{s.model}</span>{/if}</span>
            <span class="id">{hours(s)}</span>
            {#if s.state === 'doing' && s.tasks.length}
              <span class="prog"><span class="pbar" style="--x: var(--b)"><i style="width: {(done / s.tasks.length) * 100}%"></i></span><span class="id">{done}/{s.tasks.length}</span></span>
            {:else}
              <span class="id">{done}/{s.tasks.length}</span>
            {/if}
            <span><span class="chip s-{s.state}">{s.state}</span></span>
          </div>
        {:else}
          {@const g = r.g}
          <!-- svelte-ignore a11y_click_events_have_key_events -->
          <div class="lr gh row" class:f={i === sel} role="button" tabindex="0" aria-expanded={isOpen(g)} onclick={() => (sel = i, toggle(g))} onfocus={() => (sel = i)}>
            <span class="arrow">{isOpen(g) ? '▾' : '▸'}</span>
            <b>{g.sprint === null ? 'Steps' : `Sprint ${g.sprint}`}</b>
            <span class="chip g-{g.state}">{g.state}</span>
            <span class="id">{g.done}/{g.steps.length}</span>
            <span class="id">{g.minutes ? `${hrs(g.minutes)} h` : ''}</span>
          </div>
        {/if}
      {:else}
        <p class="dim pad">No steps in this project.</p>
      {/each}
    </section>

    {#if row && !cur}
      <section class="pn">
        <div class="ph">Sprint summary</div>
        <div class="pv">
          <h2>{row.g.sprint === null ? 'Steps' : `Sprint ${row.g.sprint}`}</h2>
          <div class="kv">
            <div><span>STATE</span>{row.g.state}</div>
            <div><span>STEPS</span>{row.g.done}/{row.g.steps.length}</div>
            <div><span>HOURS</span>{hrs(row.g.minutes)}</div>
          </div>
          <p class="dim"><span class="kb">↵</span> fold / unfold</p>
        </div>
      </section>
    {:else if cur}
      <section class="pn">
        <div class="ph">Step preview<span class="r"><span class="kb">↵</span> open</span></div>
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
      </section>
    {/if}
  </div>
{/if}

<style>
  .dim { color: var(--fgd); }
  .pad { padding: 12px 16px; margin: 0; }
  .body { padding: 8px 28px 22px; display: grid; grid-template-columns: minmax(0, 8fr) minmax(0, 4fr); gap: 20px; align-items: start; }
  /* Narrow windows: the fixed columns leave the title no room beside the preview, so the preview goes below. */
  @media (max-width: 1300px) { .body { grid-template-columns: minmax(0, 1fr); } }
  .grid { display: grid; align-items: center; column-gap: 12px; padding: 0 16px; grid-template-columns: 10px 40px minmax(0, 1fr) 76px 56px 120px 96px; }
  .gh { display: flex; align-items: center; gap: 12px; padding: 0 16px; }
  .gh .arrow { width: 10px; color: var(--fg2); }
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
