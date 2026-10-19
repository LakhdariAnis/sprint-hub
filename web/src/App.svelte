<script lang="ts">
  import './theme.css'
  import { router } from './route.svelte'
  import Empty from './screens/Empty.svelte'

  const r = $derived(router.route)
</script>

<main>
  {#if r.name === 'today'}<Empty title="Today" />
  {:else if r.name === 'projects'}<Empty title="Projects" />
  {:else if r.name === 'project'}<Empty title={r.project} crumb="Projects" />
  {:else if r.name === 'step'}<Empty title="{r.project} · step {r.id}" crumb="Projects · {r.project}" />
  {:else}<Empty title="Review" />{/if}
</main>
