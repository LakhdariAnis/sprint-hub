<script lang="ts">
  import { hub } from '../hub.svelte'
  import { useKeys } from '../keys.svelte'
  import { steps } from '../store.svelte'

  const panes = [
    { id: 'running', title: 'Running', empty: 'Nothing is running.' },
    { id: 'review', title: 'Waiting for you', empty: 'Nothing to review.' },
    { id: 'next', title: 'Next up', empty: 'Nothing ready to start.' },
  ] as const

  // Minutes since the latest run started, re-read every 30 s.
  let now = $state(Date.now())
  $effect(() => {
    const t = setInterval(() => (now = Date.now()), 30_000)
    return () => clearInterval(t)
  })
  const since = (started?: string) => (started ? `${Math.max(0, Math.floor((now - Date.parse(started)) / 60_000))}m` : '–')

  const open = (k: string) => (location.hash = `#/steps/${k}`)

  // j/k walk the three panes as one list.
  const keysAll = $derived(panes.flatMap((p) => hub.today[p.id].filter((k) => steps[k])))
  let sel = $state('')
  const at = $derived(keysAll.includes(sel) ? sel : keysAll[0])
  const move = (d: number) => (sel = keysAll[Math.max(0, Math.min(keysAll.length - 1, keysAll.indexOf(at) + d))] ?? '')
  useKeys({ j: () => move(1), k: () => move(-1), Enter: () => at && open(at) })
</script>

<header class="hd"><h1>Today</h1></header>

{#if hub.live === false}
  <p class="dim pad">Cannot reach hubd.</p>
{/if}
<div class="panes">
  {#each panes as p}
    {@const list = hub.today[p.id].map((k) => steps[k]).filter(Boolean)}
    <section class="pane">
      <div class="ph">{p.title} <span class="mono dim">{list.length}</span></div>
      {#each list as s (s.project + '/' + s.step)}
        {@const k = `${s.project}/${s.step}`}
        {@const done = s.tasks.filter((t) => t.state === 'done').length}
        {@const cur = s.tasks.find((t) => t.state === 'doing') ?? s.tasks.find((t) => t.state === 'todo')}
        <!-- svelte-ignore a11y_click_events_have_key_events -->
        <div class="row" class:on={k === at} role="link" tabindex="0" onclick={() => open(k)} onfocus={() => (sel = k)}>
          <span class="mono dim">{s.project}</span>
          <span class="mono">{s.step}</span>
          <span class="t">
            {s.title}
            {#if p.id === 'running' && cur}<span class="dim cur">{cur.text}</span>{/if}
          </span>
          {#if p.id === 'running'}
            <span class="mono dim">{done}/{s.tasks.length}</span>
            <span class="mono">{since(s.runs.at(-1)?.started)}</span>
          {/if}
        </div>
      {:else}
        <p class="dim pad">{p.empty}</p>
      {/each}
    </section>
  {/each}
</div>

<style>
  .hd { padding: 16px 20px 14px; }
  h1 { font-size: 22px; font-weight: 600; margin: 3px 0 0; letter-spacing: -0.01em; line-height: 1.2; }
  .dim { color: var(--fgd); }
  .pad { padding: 12px 16px; margin: 0; }
  .panes { display: grid; gap: 12px; padding: 0 20px 14px; }
  .pane { background: var(--bg); border: 1px solid var(--sel); border-radius: 8px; min-width: 0; }
  .ph { height: 38px; display: flex; align-items: center; gap: 8px; padding: 0 12px; border-bottom: 1px solid var(--lt); font-weight: 600; }
  .row { display: grid; grid-template-columns: auto auto minmax(0, 1fr) auto auto; gap: 12px; align-items: center; padding: 10px 16px; border-bottom: 1px solid var(--lt); font-size: 14px; cursor: pointer; }
  .row:last-child { border-bottom: 0; }
  .row:hover, .row:focus { background: var(--lt); outline: none; }
  .row.on { background: var(--sel); box-shadow: inset 3px 0 0 var(--ac); }
  .cur { display: block; font-size: 12px; }
</style>
