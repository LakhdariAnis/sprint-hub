<script lang="ts">
  import { workspaceTitle } from './steps'

  // The Hyprland workspace of a project, as a chip; nothing when it has none.
  let { n }: { n: number | null | undefined } = $props()
</script>

{#if workspaceTitle(n)}<span class="chip ws" title={workspaceTitle(n)} aria-label={workspaceTitle(n)}>{n}</span>{/if}

<style>
  .ws { flex: none; }
</style>
