<script lang="ts">
  import { loadProjects, type Row } from '../projects'

  let rows = $state<Row[]>([])
  let status = $state<'loading' | 'ready' | 'failed'>('loading')

  loadProjects().then(
    (d) => ((rows = d.rows), (status = 'ready')),
    () => (status = 'failed'),
  )

  const open = (id: string) => (location.hash = `#/projects/${encodeURIComponent(id)}`)
  const key = (e: KeyboardEvent, id: string) => e.key === 'Enter' && open(id)
</script>

<header class="hd"><h1>Projects</h1></header>

{#if status === 'failed'}
  <p class="dim">Cannot load projects. Is hubd running?</p>
{:else if status === 'ready'}
  <table>
    <thead>
      <tr><th>Project</th><th>Path</th><th class="n">Progress</th><th class="n">Running</th><th class="n">Review</th><th class="n">Todo</th></tr>
    </thead>
    <tbody>
      {#each rows as r (r.id)}
        <tr class="row" tabindex="0" onclick={() => open(r.id)} onkeydown={(e) => key(e, r.id)}>
          <td class="name">{r.name}</td>
          <td class="mono dim">{r.path}</td>
          <td class="n mono">{r.approved}/{r.total}</td>
          <td class="n mono" class:y={r.running > 0}>{r.running}</td>
          <td class="n mono" class:y={r.review > 0}>{r.review}</td>
          <td class="n mono">{r.todo}</td>
        </tr>
      {/each}
    </tbody>
  </table>
  {#if rows.length === 0}<p class="dim">No projects in the vault.</p>{/if}
{/if}

<style>
  .hd { padding: 16px 20px 14px; }
  h1 { font-size: 22px; font-weight: 600; margin: 3px 0 0; letter-spacing: -0.01em; line-height: 1.2; }
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
  .row:focus { box-shadow: inset 3px 0 0 var(--ac); }
  .warn td { color: var(--y); background: color-mix(in srgb, var(--y) 10%, var(--bg)); }
</style>
