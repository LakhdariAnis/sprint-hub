<script lang="ts">
  import Inline from '../Inline.svelte'
  import Spec from '../Spec.svelte'
  import { hub } from '../hub.svelte'
  import { useKeys } from '../keys.svelte'
  import { nav } from '../nav.svelte'
  import { ago, finishStep, goal, startStep, tickTask } from '../steps'
  import { router } from '../route.svelte'
  import { key, put, steps } from '../store.svelte'

  let { project, id }: { project: string; id: string } = $props()
  let error = $state('')

  const s = $derived(steps[key(project, id)])
  const done = $derived(s?.tasks.filter((t) => t.state === 'done').length ?? 0)

  // Only these states have a `start` move in the state table (src/hubd/states.py); hubd never runs `by: me` steps.
  const manual = $derived(s?.by === 'me')
  const canStart = $derived(s && (s.state === 'todo' || s.state === 'changes') && !manual)
  let busy = $state(false)
  // From `changes`, `s` resumes the last chat; `n` opens a new one when that chat cannot be resumed.
  const canFresh = $derived(s?.state === 'changes' && !manual)
  const start = (fresh = false) => {
    busy = true
    error = ''
    startStep(project, id, fresh)
      .then((d) => put(project, d), (e: Error) => (error = `Start failed: ${e.message}`))
      .finally(() => (busy = false))
  }

  // A run whose end never arrived gets out of `doing` here: first press asks, second moves it.
  const canFinish = $derived(s?.state === 'doing' && !manual)
  const ticked = $derived(canFinish && !!s?.tasks.length && done === s.tasks.length)
  let confirming = $state(false)
  const finish = () => {
    busy = true
    error = ''
    finishStep(project, id)
      .then((d) => put(project, d), (e: Error) => (error = `Finish failed: ${e.message}`))
      .finally(() => ((busy = false), (confirming = false)))
  }
  const finishKey = () => canFinish && !busy && (confirming ? finish() : (confirming = true))
  const back = () => (location.hash = `#/projects/${encodeURIComponent(project)}`)

  // The cursor starts on the current task: the one doing, else the first todo.
  // `by: me`: j/k pick a task, x or a click ticks it; hubd moves the step.
  let pick = $state<number | null>(null)
  const current = $derived.by(() => {
    const t = s?.tasks ?? []
    const i = t.findIndex((x) => x.state === 'doing')
    return i >= 0 ? i : Math.max(0, t.findIndex((x) => x.state === 'todo'))
  })
  const sel = $derived(pick ?? current)
  const tick = (n: number) => {
    error = ''
    pick = n
    tickTask(project, id, n).then((d) => put(project, d), (e: Error) => (error = `Tick failed: ${e.message}`))
  }
  const walk = (d: number) => manual && s && (pick = Math.max(0, Math.min(s.tasks.length - 1, sel + d)))

  // Close the tab (the sidebar's OPEN entry) and fall back to Today.
  let focus = $state<'c' | 't'>('c')
  const chat = $derived(hub.demo && hub.demo.chat.step === key(project, id) ? hub.demo.chat : null)
  // Open questions first, answered ones after (stable sort keeps file order).
  const qs = $derived([...(s?.questions ?? [])].sort((a, b) => +a.answered - +b.answered))

  const close = () => {
    router.open = router.open.filter((k) => k !== key(project, id))
    location.hash = '#/today'
  }
  // The vault step wins over its command file; the screen says so when they differ.
  const model = $derived(s?.model ?? s?.command_model ?? '–')
  const overridden = $derived(!!s?.model && !!s?.command_model && s.model !== s.command_model)
  const lastRun = $derived(s?.runs.at(-1))
  const est = '–' // shortcut: the step file has no estimate field yet; show it when hubd serves one
  // First paragraph under `## Goal`, else the first paragraph of the spec.
  const lead = $derived((goal(s?.spec) || s?.spec || '').split(/\n\s*\n/)[0].replace(/^#+\s.*\n?/, '').trim())

  useKeys({ j: () => walk(1), k: () => walk(-1), x: () => manual && s?.tasks.length && tick(sel), c: () => (focus = 'c'), t: () => (focus = 't'), s: () => canStart && !busy && start(), n: () => canFresh && !busy && start(true), f: finishKey, y: () => confirming && finishKey(), Escape: () => (confirming ? (confirming = false) : back()) })

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

  const label = $derived.by(() => {
    if (s?.state !== 'doing') return s?.state ?? ''
    const t = ago(s.runs.at(-1)?.started, now)
    return t === '–' ? 'running' : `running · ${t}`
  })

  // Instant, no smooth scroll: the task is in view when the step opens.
  $effect(() => {
    void [sel, s?.tasks.length]
    document.querySelector('.task.sel')?.scrollIntoView({ block: 'nearest' })
  })

  // Loaded before the screen shows (nav.svelte.ts); `nav.failed` says why when that load did not work.
  const loadError = $derived(nav.failed == null ? '' : nav.failed === 404 ? `No step ${id} in ${project}.` : `Cannot load ${project}/${id}. Is hubd running?`)
  $effect(() => {
    void [project, id]
    error = ''
    confirming = false
  })
</script>

<div class="page">
<div class="hd">
  <div class="crumb"><a href="#/projects/{encodeURIComponent(project)}">{project}</a> › <span class="cur">{id}</span></div>
  {#if s}<span class="chip s-{s.state}">● {label}</span>{#if manual}<span class="chip">manual</span>{/if}{/if}
  <span class="acts">
    {#if canStart}
      <button class="btn pri" type="button" disabled={busy} onclick={() => start()}>{s?.state === 'changes' ? 'Continue chat' : 'Start'} <span class="kb">s</span></button>
      {#if canFresh}
        <button class="btn" type="button" disabled={busy} onclick={() => start(true)} title="Claude cannot resume the old chat: start a new one with your comment">New chat <span class="kb">n</span></button>
      {/if}
    {:else if s?.state === 'doing'}
      <!-- hubd has no stop API yet -->
      <button class="btn" type="button" disabled title="Stopping a run comes in a later sprint">Stop <span class="kb">s</span></button>
    {/if}
    {#if canFinish}
      <button class="btn" type="button" disabled={busy} onclick={finishKey}>Finish <span class="kb">f</span></button>
    {/if}
    <button class="btn dim" type="button" onclick={close}>Close tab <span class="kb">^W</span></button>
  </span>
</div>
{#if error || loadError}
  <p class="err">{error || loadError}</p>
{/if}
{#if confirming && canFinish}
  <p class="note ask">Finish this run? {id} goes to done, even if Claude is still working. <span class="kb">f</span> or <span class="kb">y</span> finish, <span class="kb">Esc</span> cancel.</p>
{:else if s?.run_gone && canFinish}
  <p class="note ask">The run is gone: no Claude session for it is running, and its end never arrived. Press <span class="kb">f</span> to finish it.</p>
{:else if ticked}
  <p class="note">All tasks ticked. Exit Claude (<code>/exit</code>) to send it to review.</p>
{/if}
{#if s}
  <div class="body">
    <section class="pn head">
      <div class="crumb">STEP {s.step}</div>
      <h1>{s.title}</h1>
      {#if lead}<p><Inline text={lead} /></p>{/if}
      <div class="meta">
        <div title={overridden ? `The vault step says ${s.model}, .claude/commands/sprint-${s.step}.md says ${s.command_model}. The vault step wins.` : ''}><span>MODEL</span>{model}{#if overridden} <i class="over">not {s.command_model}</i>{/if}</div>
        <div><span>EST.</span>{est}</div>
        <div title={s.branch ?? ''}><span>BRANCH</span>{s.branch ?? '–'}</div>
        <div><span>BY</span>{s.by}</div>
      </div>
      {#if lastRun}
        <div class="last">{s.runs.length} {s.runs.length === 1 ? 'run' : 'runs'} · last started {lastRun.started?.slice(0, 16).replace('T', ' ')} · {lastRun.model}</div>
      {/if}
      {#if s.review?.comment}<div class="last cm"><span>YOUR LAST COMMENT</span> {s.review.comment}</div>{/if}
    </section>

    <section class="pn ck" class:f={focus === 'c'} class:short={!s.tasks.length && !qs.length}>
      <div class="ph"><span class="hk">c</span>Checklist<span class="n">from sprint/progress/{s.step}.md</span><span class="r">live</span></div>
      {#if s.tasks.length}
        <div class="big">
          <b>{done}<span class="of"> / {s.tasks.length}</span></b>
          <div class="segs">
            {#each s.tasks as t}<i class={t.state}></i>{/each}
          </div>
        </div>
      {/if}
      <div class="rows">
        {#each s.tasks as t, i}
          <!-- svelte-ignore a11y_no_noninteractive_element_interactions, a11y_no_noninteractive_tabindex, a11y_click_events_have_key_events -->
          <div class="task {t.state}" class:man={manual} class:sel={i === sel} role={manual ? "button" : undefined} tabindex={manual ? 0 : undefined} onclick={manual ? () => tick(i) : undefined}>
            <span class="ix">{i + 1}</span>
            <span class="box" aria-label={t.state}>{#if t.state === 'done'}✓{:else if t.state === 'doing'}<span class="spin"></span>{/if}</span>
            <span class="tx"><Inline text={t.text} /></span>
            {#if t.state === 'doing'}<span class="chip" style="--x: var(--ac)">now</span>{:else}<span class="tm">{time(t)}</span>{/if}
          </div>
        {:else}
          <p class="dim pad">No checklist yet.</p>
        {/each}
      </div>
      {#if qs.length}
        <div class="qa">
          <div class="l">? QUESTIONS · {qs.filter((q) => !q.answered).length} open<span class="from">from sprint/questions/{s.step}.md</span></div>
          {#each qs as q}
            <div class="qt" class:ans={q.answered}>
              {q.text}{#if q.answered && q.answer}<span class="a"> → {q.answer}</span>{/if}
            </div>
          {/each}
        </div>
      {/if}
    </section>

    <section class="pn right" class:f={focus === 't'}>
      {#if chat}
        <div class="ph">
          <span class="hk">t</span>Chat<span class="n">session {chat.session} · {chat.count} messages</span>
          <span class="r"><span class="kb">^F</span> find <span class="kb">G</span> latest</span>
        </div>
        <div class="chat">
          {#each chat.messages as m}
            {#if m.kind === 'time'}
              <div class="ts">{m.text}</div>
            {:else if m.kind === 'me'}
              <div class="me">{m.text}</div>
            {:else}
              <div class="ai">
                <span class="av">C</span>
                <div>
                  <p><Inline text={m.text} /></p>
                  {#if m.tool}
                    <div class="tool">
                      {#if m.tool.ok === null}<span class="spin"></span>{:else}<span style="color: var(--{m.tool.ok ? 'g' : 'r'})">{m.tool.ok ? '✓' : '✗'}</span>{/if}
                      {m.tool.name} <span style="color: var(--fg)">{m.tool.arg}</span><span>{m.tool.info}</span>
                    </div>
                  {/if}
                </div>
              </div>
            {/if}
          {/each}
        </div>
        <!-- Replies come with the chat in a later sprint: the composer only shows where it will be. -->
        <div class="comp">
          <div class="in">Reply… type / for commands</div>
          <div class="bt"><span class="pill">{s.model ?? 'model'}</span><span>resumes {chat.session}</span><span class="go">^↵ send</span></div>
        </div>
      {:else}
        <div class="ph"><span class="hk">t</span>Spec<span class="n">from the repo</span></div>
        <div class="spec">
          {#if s.spec}
            <Spec text={s.spec} />
          {:else}
            <p class="dim">Spec missing: no spec file for this step in the repo.</p>
          {/if}
        </div>
      {/if}
    </section>
  </div>
{/if}
</div>

<style>
  /* Fills the window: no page scroll; the task list, spec and chat scroll inside their panes. */
  .page { height: 100%; display: flex; flex-direction: column; container-type: size; }
  .dim { color: var(--fgd); }
  .pad { padding: 12px 16px; }
  .err { margin: 14px 20px 0; padding: 8px 12px; border: 1px solid var(--r); border-radius: 6px; color: var(--r); }
  .note { flex: none; margin: 14px 20px 0; padding: 8px 12px; border: 1px solid var(--g); border-radius: 6px; color: var(--g); }
  .note.ask { border-color: var(--y); color: var(--y); }
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
  .body { flex: 1; padding: 16px 20px; display: grid; grid-template-columns: minmax(360px, 5fr) minmax(0, 7fr); grid-template-rows: auto minmax(0, 1fr); gap: 16px; min-height: 0; }
  .head { grid-column: 1; grid-row: 1; padding: 18px 20px; gap: 10px; }
  .head h1 { margin: 0; font-size: 23px; font-weight: 600; line-height: 1.25; }
  .head p { margin: 0; color: var(--fg2); font-size: 14px; line-height: 1.6; display: -webkit-box; -webkit-line-clamp: 3; line-clamp: 3; -webkit-box-orient: vertical; overflow: hidden; }
  .meta { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 8px; margin-top: 4px; }
  .meta div { border: 1px solid var(--sel); border-radius: 7px; padding: 6px 10px; background: var(--bg); font-size: 13px; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .meta span { display: block; font: 10.5px var(--mono); color: var(--fg2); letter-spacing: 0.05em; }
  .over { font-style: normal; color: var(--y); }
  .last { font: 12px var(--mono); color: var(--fg2); overflow-wrap: anywhere; }
  .cm span { color: var(--fgd); }
  .ck { grid-column: 1; grid-row: 2; }
  /* No checklist yet: the pane hugs its one line instead of filling the column. */
  .ck.short { align-self: start; }
  .right { grid-column: 2; grid-row: 1 / span 2; }
  .big { display: flex; align-items: center; gap: 14px; padding: 14px 16px; border-bottom: 1px solid var(--sel); }
  .big b { font-size: 26px; font-weight: 500; line-height: 1; }
  .of { color: var(--fg2); font-size: 16px; }
  .segs { flex: 1; display: flex; gap: 4px; }
  .segs i { flex: 1; height: 10px; border-radius: 3px; background: var(--sel); }
  .segs i.done { background: var(--g); }
  .segs i.doing { background: var(--ac); opacity: 0.6; }
  .rows { overflow: auto; min-height: 0; flex: 1; }
  .task {
    display: grid; grid-template-columns: 26px 24px minmax(0, 1fr) auto; align-items: center; gap: 10px; padding: 0 16px;
    min-height: 50px; border-bottom: 1px solid var(--sel); font-size: 14.5px; position: relative;
  }
  .ix { font: 12px var(--mono); color: var(--fgm); }
  .tm { font: 11.5px var(--mono); color: var(--fg2); }
  .task.man { cursor: pointer; }
  .task.sel { box-shadow: inset 3px 0 0 var(--ac); background: var(--sel); }
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
  .qa { flex: none; max-height: 30%; overflow: auto; margin: 14px 16px; border: 1px solid var(--y); border-radius: 8px; padding: 12px 14px; background: color-mix(in srgb, var(--y) 8%, transparent); }
  .qa .l { font: 11px var(--mono); color: var(--y); letter-spacing: 0.06em; }
  .qa .from { margin-left: 8px; color: var(--fgm); letter-spacing: 0; }
  .qt { margin-top: 6px; font-size: 14px; }
  .qt.ans { color: var(--fgm); }
  .qt .a { color: var(--fg2); }
  .spec { padding: 16px 20px; overflow: auto; min-height: 0; font-size: 14.5px; }
  .chat { flex: 1; padding: 20px 28px; display: flex; flex-direction: column; gap: 18px; overflow: auto; font-size: 15px; line-height: 1.65; }
  .ts { align-self: center; color: var(--fgm); font: 11.5px var(--mono); display: flex; align-items: center; gap: 10px; }
  .ts::before, .ts::after { content: ''; width: 50px; height: 1px; background: var(--sel); }
  .me { align-self: flex-end; max-width: 74%; background: var(--sel); border-radius: 14px 14px 4px 14px; padding: 9px 16px; }
  .ai { display: flex; gap: 14px; max-width: 92%; }
  .ai p { margin: 0 0 8px; }
  .av { flex: none; width: 28px; height: 28px; border-radius: 7px; background: var(--ac); color: var(--bg); font: 700 12px var(--mono); display: flex; align-items: center; justify-content: center; margin-top: 2px; }
  .tool { display: flex; align-items: center; gap: 10px; padding: 5px 12px; border: 1px solid var(--sel); border-radius: 6px; font: 12px var(--mono); color: var(--fg2); width: max-content; max-width: 100%; margin-bottom: 6px; background: var(--bg); }
  .tool .spin { width: 12px; height: 12px; }
  .comp { margin: 0 16px 16px; border: 1px solid var(--sel); border-radius: 10px; background: var(--bg); padding: 12px 14px 8px; opacity: 0.6; }
  .comp .in { color: var(--fgm); font-size: 14.5px; min-height: 26px; }
  .bt { display: flex; align-items: center; gap: 10px; font: 12px var(--mono); color: var(--fg2); }
  .pill { border: 1px solid var(--sel); border-radius: 10px; padding: 0 8px; }
  .go { margin-left: auto; font-weight: 700; color: var(--bg); background: var(--ac); padding: 2px 10px; border-radius: 4px; }
  /* Half screen (sidebar open: ~720 px of content): one slim column pair, smaller texts. */
  @container (max-width: 1060px) {
    .hd { padding: 0 16px; }
    .body { padding: 12px 16px; gap: 12px; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); }
    .head { padding: 14px 16px; }
    .head h1 { font-size: 20px; }
    .meta { grid-template-columns: repeat(2, minmax(0, 1fr)); }
    .meta div { white-space: normal; overflow-wrap: anywhere; }
    .ck .ph .n { display: none; }
    .task { padding: 0 12px; gap: 8px; }
    .spec, .chat { padding: 12px 16px; }
  }
  /* A half tile at 1.25 scale with the sidebar (~500 px): the head spans the width so the facts fit in one row,
     Checklist and Spec share the row below. A long branch wraps instead of being cut. */
  @container (max-width: 600px) {
    .btn { white-space: nowrap; }
    .btn:disabled { display: none; } /* the dead Stop gives its room to Finish and Close tab */
    .body { grid-template-columns: minmax(0, 5fr) minmax(0, 4fr); }
    .head { grid-column: 1 / -1; }
    .right { grid-row: 2; }
    .meta { grid-template-columns: repeat(4, minmax(0, 1fr)); }
    .ix { display: none; }
    .task { grid-template-columns: 24px minmax(0, 1fr) auto; }
  }
  /* Short windows: the header band and head pane give back room. */
  @container (max-height: 640px) {
    .hd { height: 48px; }
    .body { padding-top: 8px; padding-bottom: 8px; gap: 8px; }
    .head { padding: 10px 14px; gap: 6px; }
    .head h1 { font-size: 17px; }
    .head p { -webkit-line-clamp: 1; line-clamp: 1; }
    .meta { grid-template-columns: repeat(4, minmax(0, 1fr)); margin-top: 0; }
    .meta div { padding: 3px 8px; }
    .big { padding: 8px 14px; }
    .task { min-height: 40px; }
    .qa { margin: 8px 12px; padding: 8px 12px; }
  }
</style>
