<script lang="ts">
  import { hub } from './hub.svelte'
</script>

<header class="ub">
  <span class="dot" class:x-g={hub.live} class:x-r={hub.live === false}></span>
  <span>{hub.live === null ? 'checking hubd…' : hub.live ? 'hubd live' : 'hubd down'}{hub.demo ? ' · demo' : ''}</span>
  <!-- Usage, agents and system numbers come in step 213b. -->
  <span class="slot"></span>
</header>

<style>
  .ub {
    height: 30px; flex: none; display: flex; align-items: center; gap: 8px; padding: 0 20px;
    background: var(--dk); border-bottom: 1px solid var(--sel); font: 11.5px var(--mono);
    color: var(--fg2); white-space: nowrap;
  }
  .slot { margin-left: auto; display: flex; align-items: center; gap: 8px; }
</style>
