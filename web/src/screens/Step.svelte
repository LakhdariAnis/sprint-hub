<script lang="ts">
  import Copy from '../Copy.svelte'
  import Spec from '../Spec.svelte'
  import { loadStep, startStep } from '../steps'
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

  $effect(() => {
    error = ''
    loadStep(project, id).then(
      (d) => put(project, d),
      (status) => (error = status === 404 ? `No step ${id} in ${project}.` : `Cannot load ${project}/${id}. Is hubd running?`),
    )
  })
</script>

<header class="hd">
  <div class="bc"><a href="#/projects">Projects</a> › <a href="#/projects/{encodeURIComponent(project)}">{project}</a> › <span class="mono">{id}</span></div>
  <h1><span class="mono dim">{id}</span> {s?.title ?? ''}</h1>
  {#if s}
    <div class="meta">
      <span class="chip s-{s.state}">{s.state}</span>
      <span class="mi"><span class="dim">model</span> <span class="mono">{s.model ?? '–'}</span></span>
      <span class="mi"><span class="dim">branch</span> <span class="mono">{s.branch ?? '–'}</span> {#if s.branch}<Copy text={s.branch} label="branch" />{/if}</span>
      {#if s.path}<span class="mi"><span class="dim">file</span> <span class="mono">{s.path}</span> <Copy text={s.path} label="step file path" /></span>{/if}
      {#if canStart}<button class="btn" type="button" disabled={busy} onclick={start}>Start <kbd>s</kbd></button>{/if}
    </div>
  {/if}
</header>

{#if error}
  <p class="err">{error}</p>
{/if}
{#if s}
  <div class="grid">
    <section class="pane">
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
    <section class="pane">
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

<style>
  .hd { padding: 16px 20px 14px; }
  .bc { font-size: 12px; color: var(--fgd); }
  .bc a { color: var(--fgd); text-decoration: none; }
  .bc a:hover { color: var(--fg); }
  h1 { font-size: 22px; font-weight: 600; margin: 3px 0 10px; letter-spacing: -0.01em; line-height: 1.2; }
  .dim { color: var(--fgd); }
  .err { margin: 0 20px 14px; padding: 8px 12px; border: 1px solid var(--r); border-radius: 6px; color: var(--r); }
  .meta { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }
  .mi { display: inline-flex; align-items: center; gap: 6px; height: 26px; padding: 0 10px; border: 1px solid var(--lt); border-radius: 6px; font-size: 12px; background: var(--bg); }
  .chip {
    display: inline-flex; align-items: center; gap: 6px; height: 20px; padding: 0 8px; border-radius: 10px;
    font-size: 11.5px; background: color-mix(in srgb, var(--x) 16%, transparent);
  }
  .chip::before { content: ''; width: 6px; height: 6px; border-radius: 50%; background: var(--x); }
  .btn {
    margin-left: auto; height: 30px; padding: 0 12px; border-radius: 6px; border: 1px solid var(--ac);
    background: var(--ac); color: var(--bg); font-weight: 500; display: inline-flex; align-items: center; gap: 8px; cursor: pointer;
  }
  .btn:disabled { opacity: 0.6; cursor: default; }
  .btn kbd { background: transparent; border-color: color-mix(in srgb, var(--bg) 45%, transparent); color: var(--bg); }
  .grid { display: grid; grid-template-columns: minmax(0, 5fr) minmax(0, 7fr); gap: 12px; padding: 0 20px 14px; align-items: start; }
  .pane { background: var(--bg); border: 1px solid var(--sel); border-radius: 8px; min-width: 0; }
  .ph { height: 38px; display: flex; align-items: center; gap: 8px; padding: 0 12px; border-bottom: 1px solid var(--lt); font-weight: 600; }
  .pad { padding: 12px 16px; }
  .task { display: grid; grid-template-columns: 20px 22px minmax(0, 1fr) auto; gap: 12px; align-items: center; padding: 10px 16px; border-bottom: 1px solid var(--lt); font-size: 14px; }
  .task.done { color: var(--fgd); }
  .tm { font-size: 12px; font-weight: 400; }
  .task.doing { background: var(--sel); box-shadow: inset 3px 0 0 var(--ac); font-weight: 600; }
  .box { width: 22px; height: 22px; border-radius: 6px; border: 2px solid var(--mu); display: grid; place-items: center; }
  .done .box { background: var(--g); border-color: var(--g); }
  .done .box::after { content: ''; width: 10px; height: 5px; border: 2.5px solid var(--bg); border-top: 0; border-right: 0; transform: translateY(-2px) rotate(-45deg); }
  .doing .box { border-color: var(--ac); border-right-color: transparent; border-radius: 50%; }
</style>
