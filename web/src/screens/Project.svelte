<script module lang="ts">
  // Where Escape on a Step screen must land: set when a step is opened, used once by the next load.
  const back = new Map<string, { sprint: string; step: string }>()
</script>

<script lang="ts">
  import Header from '../Header.svelte'
  import Copy from '../Copy.svelte'
  import Inline from '../Inline.svelte'
  import { hub } from '../hub.svelte'
  import { useKeys } from '../keys.svelte'
  import { untrack } from 'svelte'
  import { goal, groupBySprint, loadStep, needsWork, type Step } from '../steps'
  import { key, lists, put, steps as store } from '../store.svelte'

  let { project }: { project: string } = $props()
  // Loaded before the screen shows (nav.svelte.ts), then live from the store: no keys means that load failed.
  const ids = $derived(lists.steps[project])
  const steps = $derived((ids ?? []).map((k) => store[k]))

  // Hours = time of the recorded runs; the vault has no planned hours.
  const hours = (s: Step) => {
    const m = s.runs.reduce((a, r) => a + (r.minutes ?? 0), 0)
    return m ? (m / 60).toFixed(1) : '–'
  }

  const groups = $derived(groupBySprint(steps))
  const work = $derived.by(() => {
    const w = needsWork(steps)
    return groups.find((g) => w && g.steps.includes(w))
  })
  let gi = $state(0)
  let si = $state(0)
  let col = $state<'s' | 't'>('t')
  const group = $derived(groups[gi])
  const cur = $derived(group?.steps[si])
  const pick = (i: number) => {
    col = 's'
    if (i !== gi) (gi = i), (si = 0)
  }
  const clamp = (n: number, len: number) => Math.max(0, Math.min(n, len - 1))
  const href = (s: Step) => `#/steps/${encodeURIComponent(project)}/${encodeURIComponent(s.step)}`
  const open = (s: Step) => {
    back.set(project, { sprint: group.key, step: s.step })
    location.hash = href(s)
  }
  const move = (d: number) => (col === 's' ? pick(clamp(gi + d, groups.length)) : (si = clamp(si + d, group?.steps.length ?? 0)))
  const left = () => (col = 's')
  const right = () => (col = 't')
  useKeys({
    j: () => move(1),
    k: () => move(-1),
    h: left,
    ArrowLeft: left,
    l: right,
    ArrowRight: right,
    Enter: () => (col === 's' ? right() : cur && open(cur)),
    Escape: () => (location.hash = '#/projects'),
  })
  // The list has no spec text, so the preview loads the selected step once; the store keeps it.
  // Its neighbours too, so j/k land on a loaded goal instead of a "…" frame.
  // Keyed on the string: `put` makes a new object, so reading `cur` here would reload forever.
  const near = $derived([si, si - 1, si + 1].flatMap((i) => (group?.steps[i] ? [key(project, group.steps[i].step)] : [])).join(' '))
  $effect(() => {
    const ks = near
    untrack(() => {
      for (const k of ks.split(' ')) if (k && !('spec' in store[k])) loadStep(project, store[k].step).then((d) => put(project, d), () => {})
    })
  })
  const detail = $derived(cur && 'spec' in cur ? cur : null)

  // Before the first paint of each project: back from a step, the same place. Otherwise the step that needs work.
  $effect.pre(() => {
    void project
    untrack(() => {
      col = 't'
      const gs = groups
      const was = back.get(project)
      back.delete(project)
      let g = gs.findIndex((x) => x.key === was?.sprint)
      let i = gs[g]?.steps.findIndex((x) => x.step === was?.step) ?? -1
      if (i < 0) {
        const w = needsWork(steps)
        g = gs.findIndex((x) => w && x.steps.includes(w))
        i = gs[g]?.steps.indexOf(w!) ?? 0
      }
      gi = Math.max(g, 0)
      si = Math.max(i, 0)
    })
  })

  // The selected rows stay in view, instantly.
  $effect(() => {
    void [gi, si, col]
    for (const el of document.querySelectorAll('.body .lr.f')) el.scrollIntoView({ block: 'nearest' })
  })

  // The task list is the only scroller of the info column: show the current task.
  $effect(() => {
    void cur
    document.querySelector('.tl .ck.doing')?.scrollIntoView({ block: 'nearest' })
  })
</script>

<div class="page">
<Header>
  {#snippet crumb()}<a href="#/projects">Projects</a> › {project}{/snippet}
  {project}
</Header>

{#if !ids}
  <p class="dim pad">Cannot load {project}. Is hubd running?</p>
{:else}
  <div class="body">
    <section class="pn list" class:f={col === 's'}>
      <div class="ph"><span class="full">Sprints</span><span class="short">#</span><span class="n">{groups.length}</span></div>
      {#each groups as g, i (g.key)}
        <!-- svelte-ignore a11y_click_events_have_key_events -->
        <div class="lr gh row" class:f={i === gi} role="button" tabindex="0" aria-label={g.sprint === null ? "Steps" : `Sprint ${g.sprint}`} aria-pressed={i === gi} onclick={() => pick(i)} onfocus={() => pick(i)}>
          <span class="nb g-{g.state}">{g.sprint ?? '–'}{#if g === work}<span class="mark" title="Holds the step that needs work">●</span>{/if}</span>
          <span class="gt full">
            <b>{g.sprint === null ? 'Steps' : `Sprint ${g.sprint}`}</b>
            <span class="gs">{g.done}/{g.steps.length} steps · {g.state}</span>
          </span>
        </div>
      {:else}
        <p class="dim pad">No steps in this project.</p>
      {/each}
    </section>

    <section class="pn list" class:f={col === 't'}>
      <div class="ph">Steps<span class="n">{group?.steps.length ?? 0}</span><span class="r"><span class="kb">↵</span> open</span></div>
      {#each group?.steps ?? [] as s, i (s.step)}
        {@const done = s.tasks.filter((t) => t.state === 'done').length}
        <!-- svelte-ignore a11y_click_events_have_key_events -->
        <div class="lr grid row" class:f={i === si} role="link" tabindex="0" onclick={() => ((col = 't'), (si = i))} ondblclick={() => open(s)} onfocus={() => ((col = 't'), (si = i))}>
          <span class="dot s-{s.state}"></span>
          <span class="id">{s.step}</span>
          <span class="tt">{s.title}</span>
          {#if s.state === 'doing' && s.tasks.length}
            <span class="prog"><span class="pbar" style="--x: var(--b)"><i style="width: {(done / s.tasks.length) * 100}%"></i></span><span class="id">{done}/{s.tasks.length}</span></span>
          {:else}
            <span class="id">{done}/{s.tasks.length}</span>
          {/if}
          <span class="sc"><span class="chip s-{s.state}">{s.state}</span></span>
        </div>
      {/each}
    </section>

    <section class="pn">
      <div class="ph">Step info<span class="r"><span class="kb">↵</span> open</span></div>
      {#if cur}
        {@const done = cur.tasks.filter((t) => t.state === 'done').length}
        {@const nq = hub.questions.filter((q) => q.project === cur.project && q.step === cur.step).length}
        <div class="pv">
          <div class="ti"><span class="id">{cur.step}</span> · {cur.title}</div>
          <div class="st">
            <span class="chip s-{cur.state}">{cur.state}</span><span>{cur.model ?? '–'}</span><span>{hours(cur)} h</span><span>{done}/{cur.tasks.length} tasks</span>
          </div>
          <div class="br"><span class="mono">{cur.branch ?? ''}</span>{#if cur.branch}<Copy text={cur.branch} label="branch" />{/if}</div>
          <div class="lb">GOAL</div>
          <p class="desc">{#if detail}<Inline text={goal(detail.spec) || 'No goal in the spec.'} />{:else}…{/if}</p>
          <div class="lb">TASKS<span>{done}/{cur.tasks.length}</span></div>
          <div class="tl">
            {#each cur.tasks as t}
              <div class="ck {t.state}"><span class="box">{#if t.state === 'done'}✓{/if}</span><span><Inline text={t.text} />{#if t.state === 'doing'} <em>← now</em>{/if}</span></div>
            {:else}
              <p class="dim">No checklist yet.</p>
            {/each}
          </div>
          <div class="bar">
            <a class="btn pri" href={href(cur)} onclick={() => back.set(project, { sprint: group.key, step: cur.step })}>Open <span class="kb">↵</span></a>
            <span class="nq">{nq} open {nq === 1 ? 'question' : 'questions'}</span>
          </div>
        </div>
      {:else}
        <p class="dim pad">No step selected.</p>
      {/if}
    </section>
  </div>
{/if}
</div>

<style>
  .dim { color: var(--fgd); }
  .pad { padding: 12px 16px; margin: 0; }
  /* Fixed fractions: the columns keep their width whatever is selected. */
  .body { flex: 1; min-height: 0; padding: 8px 28px 22px; display: grid; grid-template-columns: 220px minmax(0, 5fr) minmax(0, 4fr); gap: 20px; align-items: stretch; }
  .page { height: 100%; display: flex; flex-direction: column; container-type: size; }
  .short { display: none; }
  .list { overflow-y: auto; }
  .ph { position: sticky; top: 0; background: var(--dk); z-index: 1; }
  .grid { display: grid; align-items: center; column-gap: 12px; padding: 0 16px; grid-template-columns: 10px 40px minmax(0, 1fr) 96px 80px; }
  /* A sprint: its number in a badge coloured by state, then name and progress. Half screen keeps the badge only. */
  .lr.gh { display: flex; align-items: center; gap: 12px; padding: 0 14px; min-height: 52px; }
  .nb {
    position: relative; flex: none; width: 28px; height: 28px; border-radius: 7px; display: flex; align-items: center; justify-content: center;
    font: 600 13px var(--mono); color: var(--fg2); box-shadow: inset 0 0 0 1px var(--mu);
  }
  .nb.g-current { color: var(--ac); box-shadow: inset 0 0 0 1.5px var(--ac); }
  .nb.g-done { background: var(--g); color: var(--bg); box-shadow: none; }
  .gt { display: flex; flex-direction: column; gap: 2px; min-width: 0; }
  .gt b { font-size: 13px; font-weight: 600; }
  .gs { font: 11px var(--mono); color: var(--fgm); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .mark { position: absolute; top: -5px; right: -5px; font-size: 9px; line-height: 1; color: var(--ac); }
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
  .pv { padding: 16px; display: flex; flex-direction: column; gap: 10px; flex: 1; min-height: 0; }
  .pv p.dim { margin: 0; }
  .ti { font-size: 17px; font-weight: 600; line-height: 1.3; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; flex: none; }
  .ti .id { font-size: 14px; }
  .st { display: flex; align-items: center; gap: 8px; flex: none; font: 12.5px var(--mono); color: var(--fg2); white-space: nowrap; overflow: hidden; }
  .st > span + span::before { content: "·"; margin-right: 8px; }
  .lb { flex: none; display: flex; gap: 10px; font: 10.5px var(--mono); color: var(--fg2); }
  .desc { margin: 0; flex: none; font-size: 13.5px; color: var(--fg2); line-height: 1.55; height: calc(3 * 1.55em); display: -webkit-box; -webkit-line-clamp: 3; line-clamp: 3; -webkit-box-orient: vertical; overflow: hidden; }
  .br { flex: none; height: 22px; display: flex; align-items: center; gap: 8px; font-size: 12.5px; color: var(--fg2); min-width: 0; }
  .br .mono { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .tl { flex: 1; min-height: 0; overflow-y: scroll; }
  .ck em { font-style: normal; font-size: 12px; }
  .bar { flex: none; display: flex; align-items: center; justify-content: space-between; border-top: 1px solid var(--sel); padding-top: 10px; }
  .nq { font: 12.5px var(--mono); color: var(--fg2); }
  .ck { display: grid; grid-template-columns: 20px 1fr; gap: 10px; padding: 6px 0; border-bottom: 1px solid var(--sel); font-size: 13.5px; align-items: center; }
  .ck:last-child { border-bottom: 0; }
  .ck.todo { color: var(--fg2); }
  .ck.doing { color: var(--ac); font-weight: 500; }
  .box { width: 18px; height: 18px; border-radius: 5px; display: flex; align-items: center; justify-content: center; font-size: 11px; border: 1px solid var(--mu); }
  .done .box { background: var(--g); border-color: var(--g); color: var(--bg); }
  .doing .box { border: 2px solid var(--ac); }
  .btn { height: 34px; padding: 0 12px; border-radius: 7px; display: inline-flex; align-items: center; gap: 8px; font-size: 13px; text-decoration: none; }
  .btn.pri { background: var(--ac); color: var(--bg); font-weight: 500; }
  .btn.pri .kb { background: var(--bg); color: var(--ac); }
  /* Half screen (sidebar open: ~720 px of content): Sprints shrink to a strip, Steps drop the state chip. */
  @container (max-width: 1060px) {
    .body { grid-template-columns: 56px minmax(0, 5fr) minmax(0, 4fr); gap: 12px; padding: 8px 16px 14px; }
    .full, .ph .n { display: none; }
    .short { display: inline; }
    .lr.gh { padding: 0; justify-content: center; }
    .grid { grid-template-columns: 10px 36px minmax(0, 1fr) 56px; padding: 0 12px; column-gap: 8px; }
    .grid .sc, .ph .r, .prog .pbar { display: none; }
    .prog { justify-content: flex-end; }
    .pv { padding: 12px; gap: 8px; }
  }
  /* Short windows: the header and gaps give back room, the columns scroll alone. */
  @container (max-height: 640px) {
    .body { padding-bottom: 10px; }
    .pv { gap: 6px; }
    .desc { font-size: 13px; }
  }
</style>
