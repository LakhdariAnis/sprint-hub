<script lang="ts">
  import { loadSteps, type Step } from '../steps'

  let { project }: { project: string } = $props()
  let steps = $state<Step[]>([])
  let status = $state<'loading' | 'ready' | 'failed'>('loading')

  $effect(() => {
    status = 'loading'
    loadSteps(project).then(
      (s) => ((steps = s), (status = 'ready')),
      () => (status = 'failed'),
    )
  })
</script>

<header class="hd">
  <div class="bc">Projects</div>
  <h1>{project}</h1>
</header>

{#if status === 'failed'}
  <p class="dim">Cannot load {project}. Is hubd running?</p>
{:else if status === 'ready'}
  <table>
    <thead><tr><th>Id</th><th>Title</th></tr></thead>
    <tbody>
      {#each steps as s (s.step)}
        <tr><td class="mono">{s.step}</td><td>{s.title}</td></tr>
      {/each}
    </tbody>
  </table>
  {#if steps.length === 0}<p class="dim">No steps in this project.</p>{/if}
{/if}

<style>
  .hd { padding: 16px 20px 14px; }
  .bc { font-size: 12px; color: var(--fgd); }
  h1 { font-size: 22px; font-weight: 600; margin: 3px 0 0; letter-spacing: -0.01em; line-height: 1.2; }
  .dim { color: var(--fgd); }
  p.dim { padding: 0 20px; }
  table { width: 100%; border-collapse: collapse; }
  th { text-align: left; font-size: 11px; letter-spacing: 0.07em; text-transform: uppercase; color: var(--fgd); font-weight: 400; padding: 6px 20px; border-bottom: 1px solid var(--lt); }
  td { padding: 0 20px; height: 34px; border-bottom: 1px solid var(--lt); }
</style>
