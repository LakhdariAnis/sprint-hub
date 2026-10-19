<script lang="ts">
  import './theme.css'
  import './keys.svelte'
  import { router } from './route.svelte'
  import Project from './screens/Project.svelte'
  import Review from './screens/Review.svelte'
  import Projects from './screens/Projects.svelte'
  import Step from './screens/Step.svelte'
  import Today from './screens/Today.svelte'
  import Help from './Help.svelte'
  import Sidebar from './Sidebar.svelte'
  import StatusLine from './StatusLine.svelte'
  import TopBar from './TopBar.svelte'

  const r = $derived(router.route)
</script>

<div class="app">
  <Help />
  <Sidebar />
  <div class="mn">
    <TopBar />
    <main>
      {#if r.name === 'today'}<Today />
      {:else if r.name === 'projects'}<Projects />
      {:else if r.name === 'project'}<Project project={r.project} />
      {:else if r.name === 'step'}<Step project={r.project} id={r.id} />
      {:else}<Review project={r.project} id={r.id} />{/if}
    </main>
    <StatusLine />
  </div>
</div>

<style>
  .app { height: 100%; display: flex; overflow: hidden; }
  .mn { flex: 1; min-width: 0; display: flex; flex-direction: column; }
  main { flex: 1; min-height: 0; overflow: auto; background: var(--bg); }
</style>
