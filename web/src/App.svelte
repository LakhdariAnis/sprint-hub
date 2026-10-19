<script lang="ts">
  import './theme.css'
  import { router } from './route.svelte'
  import Empty from './screens/Empty.svelte'
  import Projects from './screens/Projects.svelte'
  import Sidebar from './Sidebar.svelte'
  import StatusLine from './StatusLine.svelte'
  import TopBar from './TopBar.svelte'

  const r = $derived(router.route)
</script>

<div class="app">
  <Sidebar />
  <div class="mn">
    <TopBar />
    <main>
      {#if r.name === 'today'}<Empty title="Today" />
      {:else if r.name === 'projects'}<Projects />
      {:else if r.name === 'project'}<Empty title={r.project} crumb="Projects" />
      {:else if r.name === 'step'}<Empty title="{r.project} · step {r.id}" crumb="Projects · {r.project}" />
      {:else}<Empty title="Review" />{/if}
    </main>
    <StatusLine />
  </div>
</div>

<style>
  .app { height: 100%; display: flex; overflow: hidden; }
  .mn { flex: 1; min-width: 0; display: flex; flex-direction: column; }
  main { flex: 1; min-height: 0; overflow: auto; background: var(--bg); }
</style>
