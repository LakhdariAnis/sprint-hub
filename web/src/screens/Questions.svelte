<script lang="ts">
  import Header from '../Header.svelte'
  import { hub } from '../hub.svelte'
  import { useKeys } from '../keys.svelte'

  const id = (q: { project: string; step: string }) => `${q.project}/${q.step}`
  let sel = $state(0)
  const at = $derived(Math.min(sel, hub.questions.length - 1))
  const open = (q: { project: string; step: string }) => (location.hash = `#/steps/${encodeURIComponent(q.project)}/${encodeURIComponent(q.step)}`)
  const move = (n: number) => (sel = Math.max(0, Math.min(hub.questions.length - 1, at + n)))
  useKeys({ j: () => move(1), k: () => move(-1), Enter: () => hub.questions[at] && open(hub.questions[at]) })
</script>

<div class="page">
<Header>
  {#snippet crumb()}Read-only: answer in the step's sprint/questions file{/snippet}
  Questions
</Header>

<div class="body">
  <section class="pn">
    <div class="ph">Open<span class="n">{hub.questions.length} across projects</span><span class="r"><span class="kb">↵</span> open step</span></div>
    {#each hub.questions as q, i (id(q) + q.text)}
      <!-- svelte-ignore a11y_click_events_have_key_events -->
      <div class="row" class:f={i === at} role="link" tabindex="0" onclick={() => open(q)} onfocus={() => (sel = i)}>
        <span class="id">{q.project}</span>
        <span class="id">{q.step}</span>
        <span class="st">{q.title}</span>
        <span class="qt">{q.text}</span>
      </div>
    {:else}
      <p class="dim pad">No open questions.</p>
    {/each}
  </section>
</div>
</div>

<style>
  /* Fills the window: no page scroll, the list scrolls inside its pane. */
  .page { height: 100%; display: flex; flex-direction: column; container-type: size; }
  .body { flex: 1; min-height: 0; display: flex; flex-direction: column; padding: 8px 28px 22px; }
  .pn { overflow-y: auto; }
  .pn > :global(*) { flex-shrink: 0; }
  .ph { position: sticky; top: 0; background: var(--dk); z-index: 1; }
  .dim { color: var(--fgd); }
  .pad { padding: 12px 16px; margin: 0; }
  .id { font: 12.5px var(--mono); color: var(--fg2); }
  .row {
    display: grid; grid-template-columns: 110px 44px minmax(0, 0.6fr) minmax(0, 1fr); align-items: center; column-gap: 14px;
    padding: 0 16px; min-height: 48px; border-bottom: 1px solid var(--sel); cursor: pointer; font-size: 14px;
  }
  .row:hover { background: var(--lt); }
  .row.f { background: var(--sel); box-shadow: inset 3px 0 0 var(--ac); }
  .st { color: var(--fg2); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .qt { color: var(--y); }
  @container (max-width: 1060px) {
    .body { padding: 8px 16px 14px; }
    .row { grid-template-columns: 80px 40px minmax(0, 1fr); padding: 0 12px; column-gap: 10px; }
    .row .st { display: none; }
  }
  /* One column: project and step on a line, the question under it. */
  @container (max-width: 700px) {
    .body { padding: 8px 12px 12px; }
    .row { grid-template-columns: auto minmax(0, 1fr); row-gap: 2px; padding: 8px 12px; }
    .row .qt { grid-column: 1 / -1; }
  }
  @container (max-height: 640px) { .body { padding-bottom: 10px; } }
</style>
