<script lang="ts">
  import Header from '../Header.svelte'
  import Copy from '../Copy.svelte'
  import Spec from '../Spec.svelte'
  import { useKeys } from '../keys.svelte'
  import { approveStep, loadDiffstat, loadStep, loadSteps, requestChanges } from '../steps'
  import { put, steps } from '../store.svelte'

  let { project, id }: { project?: string; id?: string } = $props()
  let error = $state('')

  // The store only holds steps a screen loaded: read every project once; SSE events keep them fresh.
  fetch('/projects')
    .then((r) => r.json())
    .then((ps: { id: string }[]) => Promise.all(ps.map((p) => loadSteps(p.id).then((l) => l.forEach((s) => put(p.id, s))))))
    .catch(() => (error = 'Cannot load steps. Is hubd running?'))

  const started = (s: { runs: { started?: string }[] }) => s.runs.at(-1)?.started ?? ''
  // Oldest first: the step that has waited longest is on top.
  const waiting = $derived(Object.values(steps).filter((s) => s.state === 'done').sort((a, b) => started(a).localeCompare(started(b))))
  const changes = $derived(Object.values(steps).filter((s) => s.state === 'changes'))
  const approved = $derived(Object.values(steps).filter((s) => s.state === 'approved'))
  const groups = $derived([
    { state: 'done', title: 'Waiting for you', list: waiting, empty: 'Nothing to review.' },
    { state: 'changes', title: 'Changes requested', list: changes, empty: 'None.' },
    { state: 'approved', title: 'Approved', list: approved, empty: 'None yet.' },
  ])

  // No step in the URL: the first waiting one.
  const sel = $derived(project && id ? steps[`${project}/${id}`] : waiting[0])
  const open = (p: string, i: string) => (location.hash = `#/review/${encodeURIComponent(p)}/${encodeURIComponent(i)}`)
  const done = $derived(sel?.tasks.filter((t) => t.state === 'done').length ?? 0)

  // Both moves are only valid from `done`; hubd's refusal (e.g. a merge conflict) shows under the buttons.
  let confirming = $state(false)
  let comment = $state('')
  let busy = $state(false)
  let moveError = $state('')
  const move = (run: () => Promise<unknown>) => {
    if (!sel) return
    busy = true
    moveError = ''
    run().then(() => ((confirming = false), (comment = '')), (e: Error) => (moveError = e.message)).finally(() => (busy = false))
  }
  const approve = () => sel && move(() => approveStep(sel.project, sel.step).then((d) => put(sel.project, d)))
  const changesRequested = () => sel && move(() => requestChanges(sel.project, sel.step, comment.trim()).then((d) => put(sel.project, d)))

  // j/k walk the three groups as one list; the URL holds the selection.
  const flat = $derived(groups.flatMap((g) => g.list))
  const step = (d: number) => {
    const n = flat[Math.max(0, Math.min(flat.length - 1, flat.indexOf(sel!) + d))]
    if (n) open(n.project, n.step)
  }
  let box = $state<HTMLInputElement>()
  const confirmKey = () => confirming && !busy && approve()
  useKeys({
    j: () => step(1),
    k: () => step(-1),
    a: () => (sel?.state !== 'done' ? undefined : confirming ? confirmKey() : (confirming = true)),
    y: confirmKey,
    c: () => sel?.state === 'done' && box?.focus(),
    Escape: () => (confirming = false),
  })

  let stat = $state<string | null>(null)
  let statError = $state('')
  // Keyed on strings, not on `sel`: `put` makes a new object, so reading `sel` here would reload forever.
  const selProject = $derived(sel?.project)
  const selStep = $derived(sel?.step)
  $effect(() => {
    if (!selProject || !selStep) return
    const [p, i] = [selProject, selStep]
    stat = null
    confirming = false
    moveError = ''
    statError = ''
    loadStep(p, i).then((d) => put(p, d), () => {})
    loadDiffstat(p, i).then((d) => (stat = d), (e: Error) => (statError = e.message))
  })
</script>

<Header>
  {#snippet crumb()}{waiting.length} waiting for you{/snippet}
  Review
</Header>

{#if error}<p class="err">{error}</p>{/if}
<div class="grid">
  <section class="pn queue">
    {#each groups as g}
      <div class="gr"><span class="dot s-{g.state}"></span>{g.title.toUpperCase()}<span class="cnt">{g.list.length}</span></div>
      {#each g.list as s (s.project + '/' + s.step)}
        <!-- svelte-ignore a11y_click_events_have_key_events -->
        <div class="row" class:on={sel === s} role="link" tabindex="0" onclick={() => open(s.project, s.step)} onfocus={() => open(s.project, s.step)}>
          <span class="id">{s.step}</span>
          <span class="t">{s.title}</span>
          <span class="id">{s.project}</span>
        </div>
      {:else}
        <p class="dim pad">{g.empty}</p>
      {/each}
    {/each}
  </section>

  {#if sel}
    <div class="detail">
      <section class="pn head">
        <div class="top">
          <h2><span class="id">{sel.step}</span> {sel.title}</h2>
          <span class="chip s-{sel.state}">{sel.state}</span>
        </div>
        <div class="meta">
          <span>{sel.project}</span>
          <span class="mono">{sel.branch ?? '–'}</span>{#if sel.branch}<Copy text={sel.branch} label="branch" />{/if}
          <span>{done}/{sel.tasks.length} tasks</span>
        </div>
        {#if sel.state === 'done'}
          <div class="act">
            {#if confirming}
              <span>Merge <span class="mono">{sel.branch ?? 'nothing'}</span> into main?</span>
              <button class="btn" type="button" disabled={busy} onclick={approve}>Yes, approve <span class="kb">y</span></button>
              <button class="btn ghost" type="button" disabled={busy} onclick={() => (confirming = false)}>Cancel <span class="kb">Esc</span></button>
            {:else}
              <button class="btn" type="button" disabled={busy} onclick={() => (confirming = true)}>Approve <span class="kb">a</span></button>
            {/if}
            <form onsubmit={(e) => (e.preventDefault(), changesRequested())}>
              <input bind:this={box} bind:value={comment} onkeydown={(e) => e.key === 'Escape' && box?.blur()} placeholder="Request changes: what should change? (c)" aria-label="Review comment" />
              <button class="btn ghost" type="submit" disabled={busy || !comment.trim()}>Request changes</button>
            </form>
            {#if moveError}<p class="err in">{moveError}</p>{/if}
          </div>
        {/if}
      </section>

      <div class="two">
        <section class="pn">
          <div class="ph">Report</div>
          <div class="pad">
            {#each sel.runs as r}
              <p class="mono dim">{r.started?.slice(0, 16).replace('T', ' ')} · {r.minutes ?? '?'} min</p>
            {:else}
              <p class="dim">No runs.</p>
            {/each}
            {#if sel.review?.comment}<p><span class="dim">Your last comment:</span> {sel.review.comment}</p>{/if}
            {#if sel.spec}<Spec text={sel.spec} />{/if}
          </div>
        </section>
        <div class="col">
          <section class="pn">
            <div class="ph">Diffstat <span class="n">main...{sel.branch ?? '–'}</span></div>
            {#if statError}<p class="err in">{statError}</p>
            {:else if stat === null}<p class="dim pad">Loading…</p>
            {:else if stat}<pre class="pad">{stat}</pre>
            {:else}<p class="dim pad">No changes against main.</p>{/if}
          </section>
          <section class="pn">
            <div class="ph">Checklist <span class="n">{done}/{sel.tasks.length}</span></div>
            {#each sel.tasks as t}
              <div class="task {t.state}"><span class="mono">{t.state === 'done' ? '[x]' : t.state === 'doing' ? '[~]' : '[ ]'}</span> {t.text}</div>
            {:else}
              <p class="dim pad">No checklist.</p>
            {/each}
          </section>
        </div>
      </div>
    </div>
  {:else}
    <p class="dim pad">Select a step.</p>
  {/if}
</div>

<style>
  .dim { color: var(--fgd); }
  .pad { padding: 12px 16px; margin: 0; }
  .id { font: 12.5px var(--mono); color: var(--fg2); }
  .err { margin: 0 20px 14px; padding: 8px 12px; border: 1px solid var(--r); border-radius: 6px; color: var(--r); }
  .err.in { margin: 12px 16px; }
  .grid { display: grid; grid-template-columns: minmax(0, 4fr) minmax(0, 8fr); gap: 20px; padding: 8px 28px 22px; align-items: start; }
  .detail, .col { display: grid; gap: 20px; min-width: 0; }
  .two { display: grid; grid-template-columns: minmax(0, 3fr) minmax(0, 2fr); gap: 20px; align-items: start; }
  .gr:not(:first-child) { margin-top: 6px; border-top: 1px solid var(--sel); }
  .cnt { margin-left: auto; }
  .row { display: grid; grid-template-columns: 36px minmax(0, 1fr) auto; align-items: center; column-gap: 12px; min-height: 44px; padding: 0 16px; border-bottom: 1px solid var(--sel); cursor: pointer; font-size: 14px; }
  .row:hover, .row:focus { background: var(--lt); }
  .row.on { background: var(--sel); box-shadow: inset 3px 0 0 var(--ac); }
  .head { padding: 16px 20px; gap: 10px; }
  .top { display: flex; align-items: center; gap: 12px; }
  h2 { font-size: 20px; font-weight: 500; margin: 0; flex: 1; min-width: 0; }
  h2 .id { font-size: 15px; margin-right: 6px; }
  .meta { display: flex; align-items: center; gap: 14px; flex-wrap: wrap; font-size: 13px; color: var(--fg2); }
  .act { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; padding-top: 10px; border-top: 1px solid var(--sel); }
  .act form { display: flex; flex: 1; gap: 8px; min-width: 260px; }
  .act input { flex: 1; height: 32px; padding: 0 10px; border: 1px solid var(--mu); border-radius: 6px; background: var(--bg); }
  .act .err { flex-basis: 100%; margin: 0; }
  .btn { height: 32px; padding: 0 14px; display: inline-flex; align-items: center; gap: 8px; border-radius: 6px; border: 1px solid var(--g); background: var(--g); color: var(--bg); font-weight: 600; cursor: pointer; }
  .btn .kb { background: color-mix(in srgb, var(--bg) 25%, transparent); color: var(--bg); }
  .btn.ghost { background: transparent; color: var(--fg); border-color: var(--mu); font-weight: 400; }
  .btn:disabled { opacity: 0.6; cursor: default; }
  pre { margin: 0; font: 12px var(--mono); white-space: pre-wrap; }
  .task { padding: 8px 16px; border-bottom: 1px solid var(--sel); font-size: 13.5px; }
  .task:last-child { border-bottom: 0; }
  .task.done { color: var(--fgd); }
</style>
