<script lang="ts">
  import type { Snippet } from 'svelte'

  // The page header of every screen (canvas `.hd`): crumb line, h1, search box.
  let { crumb, children }: { crumb?: Snippet; children: Snippet } = $props()
</script>

<header class="hd">
  <div class="tt">
    {#if crumb}<div class="crumb">{@render crumb()}</div>{/if}
    <h1>{@render children()}</h1>
  </div>
  <!-- The palette comes in Sprint 4; until then the box only shows where it will be. -->
  <div class="search" title="Search comes in a later sprint">
    <svg viewBox="0 0 16 16" aria-hidden="true"><circle cx="7" cy="7" r="5" /><path d="M11 11l3 3" /></svg>
    Search, jump or run<span class="kb">^K</span>
  </div>
</header>

<style>
  .hd { height: 72px; flex: none; display: flex; align-items: center; gap: 14px; padding: 0 28px; border-bottom: 1px solid var(--sel); margin-bottom: 14px; }
  .tt { min-width: 0; }
  h1 { margin: 0; font-size: 21px; font-weight: 500; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .crumb { font: 12.5px var(--mono); color: var(--fg2); }
  .crumb :global(a) { color: var(--fg2); text-decoration: none; }
  .crumb :global(a:hover) { color: var(--fg); }
  .search {
    margin-left: auto; width: 300px; height: 34px; flex: none; border: 1px solid var(--sel); border-radius: 7px; background: var(--dk);
    display: flex; align-items: center; gap: 10px; padding: 0 10px; color: var(--fgm); font-size: 13.5px;
  }
  .search svg { width: 15px; height: 15px; stroke: currentColor; fill: none; stroke-width: 1.8; }
  .search .kb { margin-left: auto; }
</style>
