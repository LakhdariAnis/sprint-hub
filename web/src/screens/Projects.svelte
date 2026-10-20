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
</script>

<Header>
  {#snippet crumb()}vault · {rows.length} projects{/snippet}
  Projects
</Header>

{#if status === 'failed'}
  <p class="dim">Cannot load projects. Is hubd running?</p>
{:else if status === 'ready'}
  <table>
    <thead>
      <tr><th>Project</th><th>Path</th><th class="n">Progress</th><th class="n">Running</th><th class="n">Review</th><th class="n">Todo</th></tr>
    </thead>
    <tbody>
      {#each rows as r, i (r.id)}
        <!-- svelte-ignore a11y_click_events_have_key_events -->
        <tr class="row" class:on={i === sel} tabindex="0" onclick={() => open(r.id)} onfocus={() => (sel = i)}>
          <td class="name">{r.name}</td>
          <td class="mono dim">{r.path}</td>
          <td class="n mono">{r.approved}/{r.total}</td>
          <td class="n mono" class:y={r.running > 0}>{r.running}</td>
          <td class="n mono" class:y={r.review > 0}>{r.review}</td>
          <td class="n mono">{r.todo}</td>
        </tr>
      {/each}
      {#each hub.errors as e}
        <tr class="warn"><td colspan="6">⚠ <span class="mono">{e.path}{e.line ? `:${e.line}` : ''}</span> {e.message}</td></tr>
      {/each}
    </tbody>
  </table>
  {#if rows.length === 0}<p class="dim">No projects in the vault.</p>{/if}
{/if}

<style>
  .dim { color: var(--fgd); }
  p.dim { padding: 0 20px; }
  table { width: 100%; border-collapse: collapse; }
  th { text-align: left; font-size: 11px; letter-spacing: 0.07em; text-transform: uppercase; color: var(--fgd); font-weight: 400; padding: 6px 20px; border-bottom: 1px solid var(--lt); }
  td { padding: 0 20px; height: 34px; border-bottom: 1px solid var(--lt); }
  .n { text-align: right; }
  .name { font-weight: 600; }
  .y { color: var(--y); }
  .row { cursor: pointer; }
  .row:hover, .row:focus { background: var(--lt); outline: none; }
  .row.on { background: var(--sel); box-shadow: inset 3px 0 0 var(--ac); }
  .warn td { color: var(--y); background: color-mix(in srgb, var(--y) 10%, var(--bg)); }
</style>
