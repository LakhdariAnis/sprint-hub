<script lang="ts">
  import type { Snippet } from 'svelte'
  import { openPalette } from './keys.svelte'

  // The page header of every screen (canvas `.hd`): crumb line, h1, search box.
  let { crumb, children }: { crumb?: Snippet; children: Snippet } = $props()
</script>

<header class="hd">
  <div class="tt">
    {#if crumb}<div class="crumb">{@render crumb()}</div>{/if}
    <h1>{@render children()}</h1>
  </div>
  <button class="search" type="button" onclick={openPalette} title="Search, jump or run (Ctrl+K or /)">
    <svg viewBox="0 0 16 16" aria-hidden="true"><circle cx="7" cy="7" r="5" /><path d="M11 11l3 3" /></svg>
    <span class="lbl">Search, jump or run</span><span class="kb">^K</span>
  </button>
</header>

<style>
  .hd { height: 72px; flex: none; display: flex; align-items: center; gap: 14px; padding: 0 28px; border-bottom: 1px solid var(--sel); margin-bottom: 14px; }
  .tt { min-width: 0; }
  h1 { margin: 0; font-size: 21px; font-weight: 500; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .crumb { font: 12.5px var(--mono); color: var(--fg2); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .crumb :global(a) { color: var(--fg2); text-decoration: none; }
  .crumb :global(a:hover) { color: var(--fg); }
  .search {
    margin-left: auto; width: 300px; min-width: 0; flex: 0 1 300px; height: 34px; border: 1px solid var(--sel); border-radius: 7px; background: var(--dk);
    display: flex; align-items: center; gap: 10px; padding: 0 10px; color: var(--fgm); font: inherit; font-size: 13.5px; text-align: left; cursor: pointer;
  }
  @media (max-height: 700px) { .hd { height: 52px; margin-bottom: 8px; } }
  .search svg { width: 15px; height: 15px; stroke: currentColor; fill: none; stroke-width: 1.8; }
  .search .kb { margin-left: auto; }
  /* A half tile with the sidebar: the crumb and title get the room, the box keeps its icon and key. */
  @container (max-width: 600px) { .hd { padding: 0 16px; } .search { flex: none; width: auto; } .search .lbl { display: none; } }
</style>
