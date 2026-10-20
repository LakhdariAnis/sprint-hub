<script lang="ts">
  import Spec from '../Spec.svelte'
  import { hub } from '../hub.svelte'
  import { useKeys } from '../keys.svelte'
  import { goal, loadStep, startStep } from '../steps'
  import { router } from '../route.svelte'
  import { key, put, steps } from '../store.svelte'

  let { project, id }: { project: string; id: string } = $props()
  let error = $state('')

  const s = $derived(steps[key(project, id)])
  const done = $derived(s?.tasks.filter((t) => t.state === 'done').length ?? 0)

  // Only these states have a `start` move in the state table (src/hubd/states.py); hubd never runs `by: me` steps.
  const canStart = $derived(s && (s.state === 'todo' || s.state === 'changes') && s.by !== 'me')
  let busy = $state(false)
  const start = () => {
    busy = true
    error = ''
    startStep(project, id)
      .then((d) => put(project, d), (e: Error) => (error = `Start failed: ${e.message}`))
      .finally(() => (busy = false))
  }

  // Close the tab (the sidebar's OPEN entry) and fall back to Today.
  let focus = $state<'c' | 't'>('c')
  const q = $derived(hub.demo && hub.demo.question.step === key(project, id) ? hub.demo.question : null)

  const close = () => {
    router.open = router.open.filter((k) => k !== key(project, id))
    location.hash = '#/today'
  }
  const est = '–' // shortcut: the step file has no estimate field yet; show it when hubd serves one
  // First paragraph under `## Goal`, else the first paragraph of the spec.
  const lead = $derived((goal(s?.spec) || s?.spec || '').split(/\n\s*\n/)[0].replace(/^#+\s.*\n?/, '').trim())

  useKeys({ c: () => (focus = 'c'), t: () => (focus = 't'), s: () => canStart && !busy && start(), Escape: () => (location.hash = `#/projects/${encodeURIComponent(project)}`) })

  // Ticked tasks show the clock time, the current one its minutes so far (re-read every 30 s).
  let now = $state(Date.now())
  $effect(() => {
    const t = setInterval(() => (now = Date.now()), 30_000)
    return () => clearInterval(t)
  })
  const time = (t: { state: string; at?: string }) =>
    !t.at || t.state === 'todo' ? '—'
    : t.state === 'done' ? t.at.slice(11, 16)
    : `${Math.max(0, Math.floor((now - Date.parse(t.at)) / 60_000))}m`

  const label = $derived(
    s?.state === 'doing' ? `running · ${Math.max(0, Math.floor((now - Date.parse(s.runs.at(-1)?.started ?? '')) / 60_000)) || 0} min` : (s?.state ?? ''),
  )

  $effect(() => {
    error = ''
    loadStep(project, id).then(
      (d) => put(project, d),
      (status) => (error = status === 404 ? `No step ${id} in ${project}.` : `Cannot load ${project}/${id}. Is hubd running?`),
    )
  })
</script>

<div class="page">
<div class="hd">
  <div class="crumb"><a href="#/projects/{encodeURIComponent(project)}">{project}</a> › <span class="cur">{id}</span></div>
  {#if s}<span class="chip s-{s.state}">● {label}</span>{/if}
  <span class="acts">
    {#if canStart}
      <button class="btn pri" type="button" disabled={busy} onclick={start}>Start <span class="kb">s</span></button>
    {:else if s?.state === 'doing'}
      <!-- hubd has no stop API yet -->
      <button class="btn" type="button" disabled title="Stopping a run comes in a later sprint">Stop <span class="kb">s</span></button>
    {/if}
    <button class="btn dim" type="button" onclick={close}>Close tab <span class="kb">^W</span></button>
  </span>
</div>
{#if error}
  <p class="err">{error}</p>
{/if}
{#if s}
  <div class="body">
    <section class="pn head">
      <div class="crumb">STEP {s.step}</div>
      <h1>{s.title}</h1>
      {#if lead}<p>{lead}</p>{/if}
      <div class="meta">
        <div><span>MODEL</span>{s.model ?? '–'}</div>
        <div><span>EST.</span>{est}</div>
        <div title={s.branch ?? ''}><span>BRANCH</span>{s.branch ?? '–'}</div>
        <div><span>BY</span>{s.by}</div>
      </div>
    </section>

    <section class="pn ck" class:f={focus === 'c'}>
      <div class="ph"><span class="hk">c</span>Checklist<span class="n">from sprint/progress/{s.step}.md</span><span class="r">live</span></div>
      <div class="big">
        <b>{done}<span class="of"> / {s.tasks.length}</span></b>
        <div class="segs">
          {#each s.tasks as t}<i class={t.state}></i>{/each}
        </div>
      </div>
      <div class="rows">
        {#each s.tasks as t, i}
          <div class="task {t.state}">
            <span class="ix">{i + 1}</span>
            <span class="box" aria-label={t.state}>{#if t.state === 'done'}✓{:else if t.state === 'doing'}<span class="spin"></span>{/if}</span>
            <span class="tx">{t.text}</span>
            {#if t.state === 'doing'}<span class="chip" style="--x: var(--ac)">now</span>{:else}<span class="tm">{time(t)}</span>{/if}
          </div>
        {:else}
          <p class="dim pad">No checklist yet.</p>
        {/each}
      </div>
      {#if q}
        <div class="qa">
          <div class="l">? CLAUDE ASKS · {q.at}</div>
          <div class="qt">{q.text}</div>
          <!-- Answering comes with the chat in a later sprint. -->
          <div class="opt">
            {#each q.answers as a, i}<span class="o" class:f={i === 0}>{a} <span class="kb">{i + 1}</span></span>{/each}
          </div>
        </div>
      {/if}
    </section>

    <section class="pn right">
      <div class="ph">Spec</div>
      <div class="pb pad">
        {#if s.spec}
          <Spec text={s.spec} />
        {:else}
          <p class="dim">No spec in the repo.</p>
        {/if}
      </div>
    </section>
  </div>
{/if}
</div>

<style>
  .page { min-height: 100%; display: flex; flex-direction: column; }
  .dim { color: var(--fgd); }
  .pad { padding: 12px 16px; }
  .err { margin: 14px 20px 0; padding: 8px 12px; border: 1px solid var(--r); border-radius: 6px; color: var(--r); }
  .hd { height: 60px; flex: none; display: flex; align-items: center; gap: 12px; padding: 0 24px; border-bottom: 1px solid var(--sel); }
  .crumb { font: 12.5px var(--mono); color: var(--fg2); }
  .crumb a { color: var(--fg2); text-decoration: none; }
  .crumb a:hover, .crumb .cur { color: var(--fg); }
  .acts { margin-left: auto; display: flex; gap: 8px; }
  .btn {
    height: 34px; padding: 0 12px; border-radius: 7px; display: inline-flex; align-items: center; gap: 8px; font-size: 13px;
    border: 1px solid var(--sel); color: var(--fg); background: var(--dk); cursor: pointer;
  }
  .btn.pri { border-color: var(--ac); background: var(--ac); color: var(--bg); font-weight: 500; }
  .btn.pri .kb { background: var(--bg); color: var(--ac); }
  .btn.dim { color: var(--fg2); }
  .btn:disabled { opacity: 0.5; cursor: default; }
  .body { flex: 1; padding: 16px 20px; display: grid; grid-template-columns: 440px minmax(0, 1fr); grid-template-rows: auto 1fr; gap: 16px; min-height: 0; }
  .head { grid-column: 1; grid-row: 1; padding: 18px 20px; gap: 10px; }
  .head h1 { margin: 0; font-size: 23px; font-weight: 600; line-height: 1.25; }
  .head p { margin: 0; color: var(--fg2); font-size: 14px; line-height: 1.6; }
  .meta { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 8px; margin-top: 4px; }
  .meta div { border: 1px solid var(--sel); border-radius: 7px; padding: 6px 10px; background: var(--bg); font-size: 13px; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .meta span { display: block; font: 10.5px var(--mono); color: var(--fg2); letter-spacing: 0.05em; }
  .ck { grid-column: 1; grid-row: 2; }
  .right { grid-column: 2; grid-row: 1 / span 2; }
  .big { display: flex; align-items: center; gap: 14px; padding: 14px 16px; border-bottom: 1px solid var(--sel); }
  .big b { font-size: 26px; font-weight: 500; line-height: 1; }
  .of { color: var(--fg2); font-size: 16px; }
  .segs { flex: 1; display: flex; gap: 4px; }
  .segs i { flex: 1; height: 10px; border-radius: 3px; background: var(--sel); }
  .segs i.done { background: var(--g); }
  .segs i.doing { background: var(--ac); opacity: 0.6; }
  .rows { overflow: auto; min-height: 0; }
  .task {
    display: grid; grid-template-columns: 26px 24px minmax(0, 1fr) auto; align-items: center; gap: 10px; padding: 0 16px;
    min-height: 50px; border-bottom: 1px solid var(--sel); font-size: 14.5px; position: relative;
  }
  .ix { font: 12px var(--mono); color: var(--fg3); }
  .tm { font: 11.5px var(--mono); color: var(--fg2); }
  .task.done { color: var(--fg2); }
  .task.todo .tx { color: var(--fg2); }
  .task.doing { background: color-mix(in srgb, var(--ac) 12%, transparent); }
  .task.doing::before { content: ''; position: absolute; left: 0; top: 0; bottom: 0; width: 3px; background: var(--ac); }
  .task.doing .ix { color: var(--ac); }
  .task.doing .tx { font-weight: 600; }
  .box { width: 22px; height: 22px; border-radius: 6px; display: flex; align-items: center; justify-content: center; font-size: 13px; font-weight: 700; border: 1.5px solid var(--mu); }
  .done .box { background: var(--g); border-color: var(--g); color: var(--bg); }
  .doing .box { border: 2px solid var(--ac); }
  .spin { width: 10px; height: 10px; border-radius: 50%; border: 2px solid var(--sel); border-top-color: var(--ac); animation: spin 1s linear infinite; }
  @keyframes spin { to { transform: rotate(360deg); } }
  .qa { margin: 14px 16px; border: 1px solid var(--y); border-radius: 8px; padding: 12px 14px; background: color-mix(in srgb, var(--y) 8%, transparent); }
  .qa .l { font: 11px var(--mono); color: var(--y); letter-spacing: 0.06em; }
  .qt { margin-top: 4px; font-size: 14px; }
  .opt { display: flex; gap: 8px; margin-top: 10px; }
  .o { flex: 1; border: 1px solid var(--sel); border-radius: 6px; padding: 6px 10px; font-size: 13px; background: var(--dk); }
  .o.f { border-color: var(--ac); box-shadow: 0 0 0 1px var(--ac); }
</style>
