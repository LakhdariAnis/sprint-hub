<script lang="ts">
  import './theme.css'
  import './keys.svelte'
  import { hub } from './hub.svelte'
  import { nav } from './nav.svelte'
  import Project from './screens/Project.svelte'
  import Review from './screens/Review.svelte'
  import Questions from './screens/Questions.svelte'
  import Projects from './screens/Projects.svelte'
  import Step from './screens/Step.svelte'
  import Settings from './screens/Settings.svelte'
  import Today from './screens/Today.svelte'
  import Errors from './Errors.svelte'
  import Help from './Help.svelte'
  import Sidebar from './Sidebar.svelte'
  import StatusLine from './StatusLine.svelte'
  import TopBar from './TopBar.svelte'

  const r = $derived(nav.route)
</script>

<div class="app">
  <Help />
  <Errors />
  <Sidebar />
  <div class="mn">
    <TopBar />
    <!-- The event stream reconnects by itself: the first reply from hubd clears this. -->
    {#if hub.live === false}
      <div class="down" role="alert">hubd is not running, so this screen may be out of date. Start it with <code>uv run hubd</code>; this goes away by itself when it is back.</div>
    {/if}
    <main>
      <!-- A plain line, no motion: the next screen is still loading. -->
      {#if nav.slow}<div class="slow"></div>{/if}
      {#if !r}<!-- first load: nothing to keep on show -->
      {:else if r.name === 'today'}<Today />
      {:else if r.name === 'questions'}<Questions />
      {:else if r.name === 'settings'}<Settings />
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
  .down { flex: none; padding: 8px 28px; background: color-mix(in srgb, var(--r) 14%, var(--dk)); border-bottom: 1px solid var(--r); color: var(--r); overflow-wrap: anywhere; }
  .down code { font: 12.5px var(--mono); color: var(--fg); }
  .slow { position: sticky; top: 0; height: 0; border-top: 2px solid var(--b); z-index: 1; }
</style>
