<script lang="ts">
  import { answer, keys } from './keys.svelte'
</script>

{#if keys.confirm}
  <div class="back" role="presentation" onclick={() => answer(false)}>
    <!-- svelte-ignore a11y_click_events_have_key_events -->
    <div class="box" role="alertdialog" aria-modal="true" aria-label={keys.confirm.title} tabindex="-1" onclick={(e) => e.stopPropagation()}>
      <h2>{keys.confirm.title}</h2>
      <p>{keys.confirm.text}</p>
      <div class="bt">
        <button class="yes" type="button" onclick={() => answer(true)}>{keys.confirm.yes} <span class="kb">y</span></button>
        <button class="no" type="button" onclick={() => answer(false)}>Cancel <span class="kb">n</span></button>
      </div>
    </div>
  </div>
{/if}

<style>
  .back { position: fixed; inset: 0; background: color-mix(in srgb, var(--bg) 80%, transparent); display: grid; place-items: center; z-index: 20; padding: 16px; }
  .box { background: var(--dkr); border: 2px solid var(--y); border-radius: 12px; padding: 28px 32px; width: min(520px, 100%); box-shadow: 0 20px 60px rgb(0 0 0 / 0.5); }
  h2 { font-size: 22px; margin: 0 0 12px; }
  p { margin: 0 0 24px; font-size: 15px; line-height: 1.5; color: var(--fg2); overflow-wrap: anywhere; }
  .bt { display: flex; gap: 12px; justify-content: flex-end; flex-wrap: wrap; }
  button { height: 42px; padding: 0 18px; border-radius: 8px; font-size: 15px; display: inline-flex; align-items: center; gap: 10px; cursor: pointer; border: 1px solid var(--mu); background: var(--dk); color: var(--fg); }
  .yes { background: var(--y); color: var(--bg); border-color: var(--y); font-weight: 600; }
  .yes .kb { background: var(--bg); color: var(--y); }
</style>
