<script lang="ts">
  import { hub } from './hub.svelte'
  import { router } from './route.svelte'

  const tabs = $derived([
    { id: 'today', label: 'Today', count: hub.next + hub.running + hub.review },
    { id: 'projects', label: 'Projects', count: hub.projects },
    { id: 'review', label: 'Review', count: hub.review },
  ])
  // A project or step screen belongs to the Projects tab.
  const active = $derived(router.route.name === 'step' || router.route.name === 'project' ? 'projects' : router.route.name)
</script>

<nav class="sb" aria-label="Main">
  <div class="wm"><span>sprint</span><b>hub</b></div>
  <div class="sl">Tabs</div>
  {#each tabs as t}
    <a class="ti" class:on={active === t.id} href="#/{t.id}">
      <span class="lbl">{t.label}</span>
      <span class="k" class:badge={t.id === 'review' && t.count > 0}>{t.count}</span>
    </a>
  {/each}
</nav>

<style>
  .sb {
    width: 236px; flex: none; background: var(--dkr); border-right: 1px solid var(--lt);
    display: flex; flex-direction: column; padding: 14px 10px 10px; gap: 2px;
  }
  .wm { display: flex; align-items: center; gap: 3px; font-size: 17px; font-weight: 600; padding: 2px 8px 14px; letter-spacing: -0.01em; }
  .wm b { background: var(--ac); color: var(--bg); border-radius: 6px; padding: 0 6px 1px; font-weight: 600; }
  .sl { font-size: 11px; letter-spacing: 0.07em; text-transform: uppercase; color: var(--fgd); padding: 16px 8px 6px; }
  .ti {
    display: flex; align-items: center; gap: 10px; height: 32px; padding: 0 8px;
    border-radius: 6px; text-decoration: none; color: var(--fg);
  }
  .ti:hover { background: var(--lt); }
  .ti.on { background: var(--sel); box-shadow: inset 3px 0 0 var(--ac); }
  .lbl { flex: 1; }
  .k { font: 11px var(--mono); color: var(--fgd); }
  .badge {
    min-width: 18px; height: 18px; border-radius: 9px; background: var(--y); color: var(--bg);
    font-weight: 700; line-height: 18px; text-align: center; padding: 0 5px;
  }
</style>
