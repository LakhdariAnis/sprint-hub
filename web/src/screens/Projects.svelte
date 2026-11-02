<script lang="ts">
  import Copy from '../Copy.svelte'
  import Header from '../Header.svelte'
  import { hub } from '../hub.svelte'
  import { useKeys } from '../keys.svelte'
  import { lists } from '../store.svelte'

  // Loaded before the screen shows (nav.svelte.ts): none here means that load failed.
  const rows = $derived(lists.projects ?? [])

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

{#if !lists.projects}
  <p class="dim pad">Cannot load projects. Is hubd running?</p>
{:else}
  <div class="body">
    <section class="pn f">
      <div class="ph">All projects<span class="n">{rows.length}</span><span class="r"><span class="kb">↵</span> open</span></div>
      <div class="lh grid"><span></span><span>project</span><span class="where">where</span><span>progress</span><span class="c">run</span><span class="c">review</span><span class="c">todo</span></div>
      {#each rows as r, i (r.id)}
        <!-- svelte-ignore a11y_click_events_have_key_events -->
        <div class="lr grid row" class:f={i === sel} role="link" tabindex="0" onclick={() => open(r.id)} onfocus={() => (sel = i)}>
          <span class="ic" style="background: var(--{tile[i % tile.length]})">{initials(r.name)}</span>
          <span class="nm"><b>{r.name}</b>{#if r.model}<span class="t2">{r.model}</span>{/if}{#if r.repoMissing}<span class="t2 hint">repo not found: {r.path}</span>{/if}{#if !r.total}<span class="t2 hint">no steps: uv run hubd import</span>{/if}</span>
          <span class="id where">{r.path || 'vault only'}</span>
          <span class="prog"><span class="pbar"><i style="width: {r.total ? (r.approved / r.total) * 100 : 0}%"></i></span><span class="id">{r.approved}/{r.total}</span></span>
          <!-- State colours as everywhere else; a zero steps back. -->
          <span class="num s-doing" class:z={!r.running}>{r.running}</span>
          <span class="num s-done" class:z={!r.review}>{r.review}</span>
          <span class="num" class:z={!r.todo}>{r.todo}</span>
        </div>
      {:else}
        <div class="first">
          <p><b>{hub.vaultFound ? 'The vault has no projects.' : `No vault at ${hub.vault}.`}</b></p>
          <p>Create it from the projects in <span class="mono">~/.config/sprint-hub/projects.toml</span>. Run in the sprint-hub folder:</p>
          <p class="cmd"><code>uv run hubd init</code> <Copy text="uv run hubd init" label="command" /></p>
        </div>
      {/each}
      {#if rows.some((r) => !r.total)}
        <div class="first">
          <p><b>{rows.every((r) => !r.total) ? 'No steps yet.' : 'Some projects have no steps yet.'}</b> Make them from the specs in each repo's <span class="mono">sprint/</span> folder:</p>
          <p class="cmd"><code>uv run hubd import</code> <Copy text="uv run hubd import" label="command" /></p>
        </div>
      {/if}
      {#each hub.errors as e}
        <div class="warn">⚠ <span class="mono">{e.path}{e.line ? `:${e.line}` : ''}</span> {e.message}</div>
      {/each}
    </section>
  </div>
{/if}

<style>
  .dim { color: var(--fgd); }
  .first { padding: 14px 16px; border-bottom: 1px solid var(--sel); overflow-wrap: anywhere; }
  .first p { margin: 0 0 8px; }
  .first .cmd { margin: 0; }
  .first code { font: 13px var(--mono); color: var(--fg); background: var(--bg); padding: 2px 8px; border-radius: 4px; }
  .mono { font: 12.5px var(--mono); }
  .hint { color: var(--y); }
  .pad { padding: 12px 16px; margin: 0; }
  .body { padding: 8px 28px 22px; container-type: inline-size; }
  .grid { display: grid; align-items: center; column-gap: 14px; padding: 0 16px; grid-template-columns: 28px minmax(0, 1.3fr) minmax(0, 1.3fr) 180px 60px 60px 60px; }
  .row { min-height: 56px; cursor: pointer; }
  .row:hover { background: var(--lt); }
  .row.f:hover { background: var(--sel); }
  .c { text-align: center; }
  .ic { width: 28px; height: 28px; border-radius: 7px; display: flex; align-items: center; justify-content: center; font: 700 11px var(--mono); color: var(--bg); }
  .nm { min-width: 0; display: flex; flex-direction: column; line-height: 1.35; }
  /* A name is never cut: it wraps when the column is narrow. */
  .nm b { font-weight: 500; overflow-wrap: anywhere; }
  .t2 { font-size: 12.5px; color: var(--fg2); }
  .id { font: 12.5px var(--mono); color: var(--fg2); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .prog { display: flex; align-items: center; gap: 8px; }
  .prog .pbar { flex: 1; }
  .num { font: 13px var(--mono); text-align: center; }
  .s-doing, .s-done { color: var(--x); }
  .z { color: var(--fgm); }
  .warn { padding: 10px 16px; color: var(--y); background: color-mix(in srgb, var(--y) 10%, var(--dk)); border-bottom: 1px solid var(--sel); }
  @container (max-width: 1060px) {
    .grid { grid-template-columns: 28px minmax(0, 1fr) 180px 60px 60px 60px; }
    .where { display: none; }
  }
  @container (max-width: 600px) {
    .grid { column-gap: 10px; grid-template-columns: 28px minmax(0, 1fr) 72px 48px 48px 48px; }
    .prog .pbar { display: none; }
  }
</style>
