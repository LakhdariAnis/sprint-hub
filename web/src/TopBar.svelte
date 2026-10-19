<script lang="ts">
  import { hub } from './hub.svelte'
</script>

<header class="tb">
  <span class="dot" class:x-g={hub.live} class:x-r={hub.live === false}></span>
  <span class="v">{hub.live === null ? 'checking hubd…' : hub.live ? 'hubd live' : 'hubd down'}</span>
  · <span class="mono">:{location.port || 80}</span>
  · <span class="mono v">{hub.running}</span> running
  · <span class="mono v">{hub.review}</span> to review
</header>

<style>
  .tb {
    height: 30px; flex: none; display: flex; align-items: center; gap: 6px; padding: 0 14px;
    background: var(--dkr); border-bottom: 1px solid var(--lt); font-size: 11.5px;
    color: var(--fgd); white-space: nowrap;
  }
  .v { color: var(--fg); }
</style>
