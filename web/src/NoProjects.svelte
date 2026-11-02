<script lang="ts">
  import { hub } from './hub.svelte'
</script>

<!-- Today, Review and Questions have nothing to show without projects: say why, once. -->
{#if hub.ready && hub.projects === 0}
  <p class="np">No projects yet. Run <code>uv run hubd init</code>, <a href="#/projects">Projects</a> shows how.</p>
{/if}

<style>
  .np { margin: 0; padding: 12px 28px; color: var(--y); overflow-wrap: anywhere; }
  code { font: 12.5px var(--mono); color: var(--fg); }
  a { color: var(--ac); }
</style>
