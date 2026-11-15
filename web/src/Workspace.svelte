<script lang="ts">
  import { workspaceTitle } from './steps'

  // The Hyprland workspace of a project, as a chip; nothing when it has none.
  let { n }: { n: number | null | undefined } = $props()
</script>

{#if workspaceTitle(n)}<span class="chip ws" title={workspaceTitle(n)} aria-label={workspaceTitle(n)}>{n}</span>{/if}

<style>
  /* --fg, not the default --fg2: its 16% tint under it gives only 3.8:1 on the dark theme. */
  .ws { flex: none; --x: var(--fg); }
</style>
