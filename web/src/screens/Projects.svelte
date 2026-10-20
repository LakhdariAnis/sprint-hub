<script lang="ts">
  import Header from '../Header.svelte'
  import { hub } from '../hub.svelte'
  import { useKeys } from '../keys.svelte'
  import { loadProjects, type Row } from '../projects'

  let rows = $state<Row[]>([])
  let status = $state<'loading' | 'ready' | 'failed'>('loading')

  loadProjects().then(
    (d) => ((rows = d), (status = 'ready')),
    () => (status = 'failed'),
  )

  const open = (id: string) => (location.hash = `#/projects/${encodeURIComponent(id)}`)
  let sel = $state(0)
  const move = (d: number) => (sel = Math.max(0, Math.min(rows.length - 1, sel + d)))
  useKeys({ j: () => move(1), k: () => move(-1), Enter: () => rows[sel] && open(rows[sel].id) })

  // The canvas tile: two letters from the name, one colour per row so projects tell apart at a glance.
  const tile = ['g', 'ac', 'm', 'y']
  const initials = (n: string) => {
    const w = n.split(/[^a-zA-Z0-9]+/).filter(Boolean)
    return (w.length > 1 ? w[0][0] + w[1][0] : n.slice(0, 2)).toUpperCase()
  }
  const active = $derived(rows.filter((r) => r.running).length)
</script>

<Header>
  {#snippet crumb()}{rows.length} projects · {active} with runs active{/snippet}
  Projects
</Header>

{#if status === 'failed'}
  <p class="dim pad">Cannot load projects. Is hubd running?</p>
{:else if status === 'ready'}
  <div class="body">
    <section class="pn f">
      <div class="ph">All projects<span class="n">{rows.length}</span><span class="r"><span class="kb">↵</span> open</span></div>
      <div class="lh grid"><span></span><span>project</span><span>where</span><span>progress</span><span class="c">run</span><span class="c">review</span><span class="c">todo</span></div>
      {#each rows as r, i (r.id)}
        <!-- svelte-ignore a11y_click_events_have_key_events -->
        <div class="lr grid row" class:f={i === sel} role="link" tabindex="0" onclick={() => open(r.id)} onfocus={() => (sel = i)}>
          <span class="ic" style="background: var(--{tile[i % tile.length]})">{initials(r.name)}</span>
          <span class="nm"><b>{r.name}</b>{#if r.model}<span class="t2">{r.model}</span>{/if}</span>
          <span class="id">{r.path || 'vault only'}</span>
          <span class="prog"><span class="pbar"><i style="width: {r.total ? (r.approved / r.total) * 100 : 0}%"></i></span><span class="id">{r.approved}/{r.total}</span></span>
          <!-- State colours as everywhere else; a zero steps back. -->
          <span class="num s-doing" class:z={!r.running}>{r.running}</span>
          <span class="num s-done" class:z={!r.review}>{r.review}</span>
          <span class="num" class:z={!r.todo}>{r.todo}</span>
        </div>
      {:else}
        <p class="dim pad">No projects in the vault.</p>
      {/each}
      {#each hub.errors as e}
        <div class="warn">⚠ <span class="mono">{e.path}{e.line ? `:${e.line}` : ''}</span> {e.message}</div>
      {/each}
    </section>
  </div>
{/if}

<style>
  .dim { color: var(--fgd); }
  .pad { padding: 12px 16px; margin: 0; }
  .body { padding: 8px 28px 22px; }
  .grid { display: grid; align-items: center; column-gap: 14px; padding: 0 16px; grid-template-columns: 28px minmax(0, 1.3fr) minmax(0, 1.3fr) 180px 60px 60px 60px; }
  .row { min-height: 56px; cursor: pointer; }
  .row:hover { background: var(--lt); }
  .row.f:hover { background: var(--sel); }
  .c { text-align: center; }
  .ic { width: 28px; height: 28px; border-radius: 7px; display: flex; align-items: center; justify-content: center; font: 700 11px var(--mono); color: var(--bg); }
  .nm { min-width: 0; display: flex; flex-direction: column; line-height: 1.35; }
  .nm b { font-weight: 500; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .t2 { font-size: 12.5px; color: var(--fg2); }
  .id { font: 12.5px var(--mono); color: var(--fg2); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .prog { display: flex; align-items: center; gap: 8px; }
  .prog .pbar { flex: 1; }
  .num { font: 13px var(--mono); text-align: center; }
  .s-doing, .s-done { color: var(--x); }
  .z { color: var(--fgm); }
  .warn { padding: 10px 16px; color: var(--y); background: color-mix(in srgb, var(--y) 10%, var(--dk)); border-bottom: 1px solid var(--sel); }
</style>
