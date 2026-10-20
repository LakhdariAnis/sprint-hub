<script lang="ts">
  import Spec from '../Spec.svelte'
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
  const close = () => {
    router.open = router.open.filter((k) => k !== key(project, id))
    location.hash = '#/today'
  }
  const est = '–' // shortcut: the step file has no estimate field yet; show it when hubd serves one
  // First paragraph under `## Goal`, else the first paragraph of the spec.
  const lead = $derived((goal(s?.spec) || s?.spec || '').split(/\n\s*\n/)[0].replace(/^#+\s.*\n?/, '').trim())

  useKeys({ s: () => canStart && !busy && start(), Escape: () => (location.hash = `#/projects/${encodeURIComponent(project)}`) })

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

    <section class="pn f ck">
      <div class="ph">Checklist <span class="mono dim">{done}/{s.tasks.length}</span></div>
      <div class="pb">
        {#each s.tasks as t, i}
          <div class="task {t.state}">
            <span class="mono dim">{i + 1}</span>
            <span class="box" aria-label={t.state}></span>
            <span>{t.text}</span>
            <span class="mono tm" class:dim={t.state !== 'doing'}>{time(t)}</span>
          </div>
        {:else}
          <p class="dim pad">No checklist yet.</p>
        {/each}
      </div>
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
  .task { display: grid; grid-template-columns: 20px 22px minmax(0, 1fr) auto; gap: 12px; align-items: center; padding: 10px 16px; border-bottom: 1px solid var(--lt); font-size: 14px; }
  .task.done { color: var(--fgd); }
  .tm { font-size: 12px; font-weight: 400; }
  .task.doing { background: var(--sel); box-shadow: inset 3px 0 0 var(--ac); font-weight: 600; }
  .box { width: 22px; height: 22px; border-radius: 6px; border: 2px solid var(--mu); display: grid; place-items: center; }
  .done .box { background: var(--g); border-color: var(--g); }
  .done .box::after { content: ''; width: 10px; height: 5px; border: 2.5px solid var(--bg); border-top: 0; border-right: 0; transform: translateY(-2px) rotate(-45deg); }
  .doing .box { border-color: var(--ac); border-right-color: transparent; border-radius: 50%; }
</style>
