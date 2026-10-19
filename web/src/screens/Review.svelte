<script lang="ts">
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
    { title: 'Waiting for you', list: waiting, empty: 'Nothing to review.' },
    { title: 'Changes requested', list: changes, empty: 'None.' },
    { title: 'Approved', list: approved, empty: 'None yet.' },
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
  $effect(() => {
    if (!sel) return
    const [p, i] = [sel.project, sel.step]
    stat = null
    confirming = false
    moveError = ''
    statError = ''
    loadStep(p, i).then((d) => put(p, d), () => {})
    loadDiffstat(p, i).then((d) => (stat = d), (e: Error) => (statError = e.message))
  })
</script>

<header class="hd"><h1>Review</h1></header>

{#if error}<p class="err">{error}</p>{/if}
<div class="grid">
  <div class="queue">
    {#each groups as g}
      <section class="pane">
        <div class="ph">{g.title} <span class="mono dim">{g.list.length}</span></div>
        {#each g.list as s (s.project + '/' + s.step)}
          <!-- svelte-ignore a11y_click_events_have_key_events -->
          <div class="row" class:on={sel === s} role="link" tabindex="0" onclick={() => open(s.project, s.step)}
            onfocus={() => open(s.project, s.step)}>
            <span class="mono dim">{s.project}</span>
            <span class="mono">{s.step}</span>
            <span class="t">{s.title}</span>
          </div>
        {:else}
          <p class="dim pad">{g.empty}</p>
        {/each}
      </section>
    {/each}
  </div>

  {#if sel}
    <div class="detail">
      <div class="meta">
        <h2><span class="mono dim">{sel.step}</span> {sel.title}</h2>
        <span class="mi"><span class="dim">state</span> {sel.state}</span>
        <span class="mi"><span class="dim">branch</span> <span class="mono">{sel.branch ?? '–'}</span> {#if sel.branch}<Copy text={sel.branch} label="branch" />{/if}</span>
      </div>
      {#if sel.state === 'done'}
        <section class="pane">
          <div class="ph">Decide</div>
          <div class="pad act">
            {#if confirming}
              <span>Merge <span class="mono">{sel.branch ?? 'nothing'}</span> into main?</span>
              <button class="btn" type="button" disabled={busy} onclick={approve}>Yes, approve</button>
              <button class="btn ghost" type="button" disabled={busy} onclick={() => (confirming = false)}>Cancel</button>
            {:else}
              <button class="btn" type="button" disabled={busy} onclick={() => (confirming = true)}>Approve</button>
            {/if}
            <form onsubmit={(e) => (e.preventDefault(), changesRequested())}>
              <input bind:this={box} bind:value={comment} onkeydown={(e) => e.key === 'Escape' && box?.blur()} placeholder="What should change? (one line)" aria-label="Review comment" />
              <button class="btn ghost" type="submit" disabled={busy || !comment.trim()}>Request changes</button>
            </form>
            {#if moveError}<p class="err in">{moveError}</p>{/if}
          </div>
        </section>
      {/if}
      <section class="pane">
        <div class="ph">Diffstat <span class="mono dim">main...{sel.branch ?? '–'}</span></div>
        {#if statError}<p class="err in">{statError}</p>
        {:else if stat === null}<p class="dim pad">Loading…</p>
        {:else if stat}<pre class="pad">{stat}</pre>
        {:else}<p class="dim pad">No changes against main.</p>{/if}
      </section>
      <section class="pane">
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
      <section class="pane">
        <div class="ph">Checklist <span class="mono dim">{done}/{sel.tasks.length}</span></div>
        {#each sel.tasks as t}
          <div class="task {t.state}"><span class="mono">{t.state === 'done' ? '[x]' : t.state === 'doing' ? '[~]' : '[ ]'}</span> {t.text}</div>
        {:else}
          <p class="dim pad">No checklist.</p>
        {/each}
      </section>
    </div>
  {:else}
    <p class="dim pad">Select a step.</p>
  {/if}
</div>

<style>
  .hd { padding: 16px 20px 14px; }
  h1 { font-size: 22px; font-weight: 600; margin: 3px 0 0; letter-spacing: -0.01em; line-height: 1.2; }
  h2 { font-size: 18px; font-weight: 600; margin: 0; flex-basis: 100%; }
  .dim { color: var(--fgd); }
  .pad { padding: 12px 16px; margin: 0; }
  .err { margin: 0 20px 14px; padding: 8px 12px; border: 1px solid var(--r); border-radius: 6px; color: var(--r); }
  .err.in { margin: 12px 16px; }
  .grid { display: grid; grid-template-columns: minmax(0, 4fr) minmax(0, 8fr); gap: 12px; padding: 0 20px 14px; align-items: start; }
  .queue, .detail { display: grid; gap: 12px; min-width: 0; }
  .pane { background: var(--bg); border: 1px solid var(--sel); border-radius: 8px; min-width: 0; }
  .ph { height: 38px; display: flex; align-items: center; gap: 8px; padding: 0 12px; border-bottom: 1px solid var(--lt); font-weight: 600; }
  .row { display: grid; grid-template-columns: auto auto minmax(0, 1fr); gap: 12px; padding: 10px 16px; border-bottom: 1px solid var(--lt); cursor: pointer; }
  .row:last-child { border-bottom: 0; }
  .row:hover, .row:focus { background: var(--lt); outline: none; }
  .row.on { background: var(--sel); box-shadow: inset 3px 0 0 var(--ac); }
  .meta { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }
  .mi { display: inline-flex; align-items: center; gap: 6px; height: 26px; padding: 0 10px; border: 1px solid var(--lt); border-radius: 6px; font-size: 12px; background: var(--bg); }
  .act { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
  .act form { display: flex; flex: 1; gap: 8px; min-width: 260px; }
  .act input { flex: 1; height: 30px; padding: 0 10px; border: 1px solid var(--mu); border-radius: 6px; background: var(--dk); }
  .act .err { flex-basis: 100%; }
  .btn { height: 30px; padding: 0 12px; border-radius: 6px; border: 1px solid var(--ac); background: var(--ac); color: var(--bg); font-weight: 500; cursor: pointer; }
  .btn.ghost { background: transparent; color: var(--fg); border-color: var(--mu); }
  .btn:disabled { opacity: 0.6; cursor: default; }
  pre { margin: 0; font: 12px var(--mono); white-space: pre-wrap; }
  .task { padding: 8px 16px; border-bottom: 1px solid var(--lt); }
  .task.done { color: var(--fgd); }
</style>
