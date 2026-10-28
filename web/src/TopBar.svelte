<script lang="ts">
  import { hub } from './hub.svelte'
</script>

<header class="ub">
  <span class="dot" class:x-g={hub.live} class:x-r={hub.live === false}></span>
  <span>{hub.live === null ? 'checking hubd…' : hub.live ? 'hubd live' : 'hubd down'}{hub.demo ? ' · demo' : ''}</span>
  <!-- Usage, agents and system numbers: fake in demo only, until hubd reads them. -->
  {#if hub.demo}
    {@const u = hub.demo.usage}
    <!-- One group per span: a group that does not fit wraps to the hidden second line, so the last groups drop whole. -->
    <span class="slot">
      <span class="g"><span class="cap">CLAUDE USAGE</span><span>5h</span><span class="um"><i style="width:{u.fiveHour}%;background:var(--y)"></i></span><b>{u.fiveHour}%</b><span>resets {u.resets}</span></span>
      <span class="g"><span class="sep">|</span><span>week</span><span class="um"><i style="width:{u.week}%;background:var(--g)"></i></span><b>{u.week}%</b></span>
      <span class="g"><span class="sep">|</span><span>today <b>{u.today}</b></span></span>
      <span class="g"><span class="sep">|</span><span class="cap">AGENTS</span><span>cpu <b>{u.agents.cpu}%</b></span><span>ram <b>{u.agents.ram}</b></span></span>
      <span class="g"><span class="sep">|</span><span class="cap">SYSTEM</span><span class="um sys"><i style="width:{u.system.cpu}%;background:var(--ac)"></i></span><b>{u.system.cpu}%</b><span>{u.system.ram}</span><span>{u.system.temp}</span></span>
    </span>
  {/if}
</header>

<style>
  .ub {
    height: 30px; flex: none; display: flex; align-items: center; gap: 8px; padding: 0 20px;
    background: var(--dk); border-bottom: 1px solid var(--sel); font: 11.5px var(--mono);
    color: var(--fg2); white-space: nowrap;
  }
  /* Narrow windows drop the last groups whole instead of cutting a number at the edge. */
  .slot { margin-left: auto; display: flex; flex-wrap: wrap; justify-content: flex-end; gap: 0 8px; min-width: 0; height: 29px; overflow: hidden; }
  .g { height: 29px; display: flex; align-items: center; gap: 8px; }
  .cap { letter-spacing: .08em; }
  .sep { color: var(--mu); }
  b { color: var(--fg); font-weight: 700; }
  .um { width: 64px; height: 6px; border-radius: 3px; background: var(--sel); overflow: hidden; }
  .um.sys { width: 40px; }
  .um i { display: block; height: 100%; border-radius: 3px; }
</style>
