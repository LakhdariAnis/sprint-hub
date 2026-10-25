<script lang="ts">
  import './theme.css'
  import './keys.svelte'
  import { nav } from './nav.svelte'
  import Project from './screens/Project.svelte'
  import Review from './screens/Review.svelte'
  import Questions from './screens/Questions.svelte'
  import Projects from './screens/Projects.svelte'
  import Step from './screens/Step.svelte'
  import Today from './screens/Today.svelte'
  import Help from './Help.svelte'
  import Sidebar from './Sidebar.svelte'
  import StatusLine from './StatusLine.svelte'
  import TopBar from './TopBar.svelte'

  const r = $derived(nav.route)
</script>

<div class="app">
  <Help />
  <Sidebar />
  <div class="mn">
    <TopBar />
    <main>
      <!-- A plain line, no motion: the next screen is still loading. -->
      {#if nav.slow}<div class="slow"></div>{/if}
      {#if !r}<!-- first load: nothing to keep on show -->
      {:else if r.name === 'today'}<Today />
      {:else if r.name === 'questions'}<Questions />
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
  main { position: relative; flex: 1; min-height: 0; overflow: auto; background: var(--bg); }
  .slow { position: sticky; top: 0; height: 0; border-top: 2px solid var(--b); z-index: 1; }
</style>
