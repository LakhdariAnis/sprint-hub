<script lang="ts">
  import { hub } from './hub.svelte'
  import { keys } from './keys.svelte'
  import { nav } from './nav.svelte'
  import { router } from './route.svelte'
  import { steps } from './store.svelte'

  // Icons from the canvas. Chats and Settings come in later sprints.
  const tabs = [
    { id: 'projects', label: 'Projects', icon: '<path d="M2 5.5h6l1.8 2H18v9H2z"/>' },
    { id: 'today', label: 'Today', icon: '<rect x="3" y="4" width="14" height="13" rx="2"/><path d="M3 8h14M7 2.5v3M13 2.5v3"/>' },
    { id: 'review', label: 'Review', icon: '<circle cx="10" cy="10" r="7.5"/><path d="M6.5 10l2.5 2.5 4.5-5"/>' },
    { id: 'questions', label: 'Questions', icon: '<circle cx="10" cy="10" r="7.5"/><path d="M7.8 8a2.3 2.3 0 114 1.5c-.8.7-1.8 1-1.8 2.2M10 14.2v.1"/>' },
    { id: 'chats', label: 'Chats', icon: '<path d="M3 4h14v10H8.5L5 17v-3H3z"/>', off: true },
    { id: 'settings', label: 'Settings', icon: '<path d="M3 6h8M15 6h2M3 14h2M9 14h8"/><circle cx="13" cy="6" r="2"/><circle cx="7" cy="14" r="2"/>', off: true },
  ]
  // The screen on show, not the URL: the frame swaps with the screen.
  const r = $derived(nav.route ?? router.route)
  // A project screen belongs to the Projects tab; a step screen to its OPEN entry.
  const active = $derived(r.name === 'project' ? 'projects' : r.name)
  const here = $derived(r.name === 'step' ? `${r.project}/${r.id}` : '')
</script>

<nav class="sb" class:rail={keys.rail} aria-label="Tabs">
  <div class="brand"><span class="wm">{#if !keys.rail}sprint{/if}<i>hub</i></span><span class="lbl ver">{hub.version}</span></div>
  <button class="newc" type="button" title="New chat comes in a later sprint"><b>+</b><span class="lbl">New chat</span><span class="k">^N</span></button>
  <div class="sg">TABS</div>
  {#each tabs as t, i}
    {#if t.off}
      <span class="tb off" aria-disabled="true" title="{t.label} comes in a later sprint">
        <svg viewBox="0 0 20 20" aria-hidden="true">{@html t.icon}</svg><span class="lbl">{t.label}</span>
      </span>
    {:else}
      <a class="tb" class:on={active === t.id} href="#/{t.id}" aria-label={t.label}>
        <svg viewBox="0 0 20 20" aria-hidden="true">{@html t.icon}</svg><span class="lbl">{t.label}</span>
        {#if t.id === 'review' && hub.review > 0}<span class="bd">{hub.review}</span>{/if}
        {#if t.id === 'questions' && hub.questions.length > 0}<span class="bd">{hub.questions.length}</span>{/if}
        <span class="k">{i + 1}</span>
      </a>
    {/if}
  {/each}
  {#if router.open.length}
    <div class="sg">OPEN</div>
    {#each router.open as k, i}
      {@const [project, id] = [k.slice(0, k.lastIndexOf('/')), k.slice(k.lastIndexOf('/') + 1)]}
      <a class="tb" class:on={here === k} href="#/steps/{encodeURIComponent(project)}/{encodeURIComponent(id)}" aria-label="{project} {id}">
        <span class="dot s-{steps[k]?.state}"></span><b class="mono">{id}</b><span class="lbl">{steps[k]?.title ?? project}</span>
        {#if i < 4}<span class="k">{i + 6}</span>{/if}
      </a>
    {/each}
  {/if}
  <div class="sbf">
    <span class="lbl"><span class="dot" class:x-g={hub.live} class:x-r={hub.live === false}></span> hubd {hub.live === false ? 'down' : 'live'}</span>
    <button class="hide" type="button" onclick={() => (keys.rail = !keys.rail)} title={keys.rail ? 'Expand sidebar' : 'Hide sidebar'}>
      <span class="kb">b</span><span class="lbl"> hide</span>
    </button>
  </div>
</nav>

<style>
  .sb {
    width: 236px; flex: none; background: var(--dk); border-right: 1px solid var(--sel);
    display: flex; flex-direction: column; padding: 14px 10px 10px; gap: 2px; overflow: hidden auto;
  }
  .brand { display: flex; align-items: center; gap: 10px; padding: 0 6px 14px; }
  .wm { font-weight: 700; font-size: 18px; letter-spacing: -0.02em; display: flex; align-items: center; gap: 3px; }
  .wm i { font-style: normal; background: var(--ac); color: var(--bg); border-radius: 5px; padding: 0 6px; line-height: 26px; }
  .ver { font: 11px var(--mono); color: var(--fgm); margin-left: auto; }
  .newc {
    height: 36px; display: flex; align-items: center; gap: 10px; padding: 0 10px; border-radius: 7px;
    border: 1px dashed var(--mu); background: none; margin: 0 0 4px; cursor: default; text-align: left;
  }
  .newc b { color: var(--ac); }
  .sg { font: 11px var(--mono); letter-spacing: 0.1em; color: var(--fgm); padding: 12px 8px 6px; }
  .tb {
    height: 36px; flex: none; display: flex; align-items: center; gap: 10px; padding: 0 8px; border-radius: 6px;
    color: var(--fg2); text-decoration: none; position: relative;
  }
  .tb:hover { background: var(--lt); }
  .tb.on { background: var(--sel); color: var(--fg); }
  .tb.on::before { content: ''; position: absolute; left: -10px; top: 8px; bottom: 8px; width: 3px; border-radius: 2px; background: var(--ac); }
  .tb.off { opacity: 0.45; }
  .tb.off:hover { background: none; }
  .tb svg { width: 17px; height: 17px; flex: none; stroke: currentColor; fill: none; stroke-width: 1.7; stroke-linecap: round; stroke-linejoin: round; }
  .tb b { font-size: 12px; font-weight: 400; }
  .tb .lbl { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .k { margin-left: auto; font: 11px var(--mono); color: var(--fgm); }
  .bd { background: var(--y); color: var(--bg); border-radius: 8px; padding: 0 6px; font: 700 10.5px/16px var(--mono); }
  .bd + .k { margin-left: 8px; }
  .sbf { margin-top: auto; display: flex; align-items: center; gap: 8px; padding: 10px 6px 0; font: 11.5px var(--mono); color: var(--fg2); }
  .sbf .lbl { display: flex; align-items: center; gap: 8px; }
  .hide { margin-left: auto; display: flex; align-items: center; gap: 4px; background: none; border: 0; padding: 0; cursor: pointer; color: inherit; }

  /* ^B: the 64 px icon rail of the canvas Step artboard. */
  .rail { width: 64px; padding: 14px 0 10px; align-items: center; gap: 4px; }
  .rail .lbl { display: none; }
  .rail .sg { font-size: 0; width: 28px; height: 1px; padding: 0; margin: 6px 0; background: var(--sel); }
  .rail .brand { padding: 0 0 10px; }
  .rail .wm { font-size: 14px; }
  .rail .wm i { padding: 0 5px; line-height: 24px; }
  .rail .newc, .rail .tb {
    width: 46px; height: 44px; padding: 0; margin: 0; gap: 0; flex-direction: column; justify-content: center;
    font: 10px var(--mono);
  }
  .rail .newc { color: var(--ac); border-color: var(--mu); }
  .rail .newc b { font-size: 12px; }
  .rail .newc .k, .rail .tb .k { margin: 0; font-size: 10px; color: inherit; }
  .rail .tb.on::before { left: -9px; top: 10px; bottom: 10px; }
  .rail .tb b { font-weight: 700; color: var(--fg); }
  .rail .tb .bd { position: absolute; top: 1px; right: 0; }
  .rail .tb .dot { position: absolute; top: 5px; right: 5px; width: 7px; height: 7px; }
  .rail .sbf { padding: 0; }
  .rail .hide { margin: 0; }
</style>
