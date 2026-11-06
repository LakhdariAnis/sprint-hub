<script lang="ts">
  import { tick, untrack } from 'svelte'
  import { keys, press } from './keys.svelte'
  import { loadProject, nav } from './nav.svelte'
  import { items, search, type Item } from './palette'
  import { loadProjects } from './projects'
  import { key, lists, steps } from './store.svelte'

  // Rows drawn: the match is done on everything, so a short query on 500 steps stays one cheap paint.
  const MAX = 50
  let q = $state('')
  let at = $state(0)
  let list = $state<HTMLElement>()
  let from: Element | null = null

  // The step on show, for the actions.
  const current = $derived.by(() => {
    const r = nav.route
    return r && (r.name === 'step' || (r.name === 'review' && r.id)) ? steps[key(r.project!, r.id!)] : undefined
  })
  const all = $derived(items(Object.values(steps), lists.projects ?? [], current))
  const found = $derived(search(all, q))
  const rows = $derived(found.slice(0, MAX))

  // Steps and projects not on any screen yet come from the API once, when the box opens: later keys search the store.
  async function loadAll() {
    try {
      const ps = lists.projects ?? (lists.projects = await loadProjects())
      await Promise.all(ps.filter((p) => !lists.steps[p.id]).map((p) => loadProject(p.id)))
    } catch {}
  }

  // Before the box mounts and takes focus.
  $effect.pre(() => {
    if (keys.palette) from = document.activeElement
  })
  $effect(() => {
    if (!keys.palette) return
    q = ''
    at = 0
    untrack(loadAll) // it reads the store: only opening may rerun this
  })
  $effect(() => {
    void q
    at = 0
  })
  $effect(() => {
    void at
    list?.querySelector('.on')?.scrollIntoView({ block: 'nearest' })
  })

  const focus = (n: HTMLElement) => n.focus()
  const close = (back: boolean) => {
    keys.palette = false
    if (back && from instanceof HTMLElement) from.focus()
  }
  const pick = (it: Item | undefined) => {
    if (!it) return
    close(false)
    // The box is gone first, so a key that focuses something (c on Review) keeps it.
    tick().then(() => (it.key ? press(it.go, it.key) : (location.hash = it.go)))
  }
  const move = (d: number) => (at = Math.max(0, Math.min(rows.length - 1, at + d)))

  function onkey(e: KeyboardEvent) {
    const k = e.key.toLowerCase()
    if (e.key === 'Escape' || (e.ctrlKey && k === 'k')) close(true)
    else if (e.key === 'ArrowDown' || (e.ctrlKey && k === 'n')) move(1)
    else if (e.key === 'ArrowUp' || (e.ctrlKey && k === 'p')) move(-1)
    else if (e.key === 'Enter') pick(rows[at])
    else return
    e.preventDefault()
  }
</script>

{#if keys.palette}
  <div class="back" role="presentation" onmousedown={() => close(true)}>
    <div class="box" role="dialog" aria-label="Command palette" tabindex="-1" onmousedown={(e) => e.stopPropagation()}>
      <input use:focus bind:value={q} onkeydown={onkey} placeholder="Search, jump or run" spellcheck="false" autocomplete="off" role="combobox" aria-expanded="true" aria-controls="palette-list" aria-label="Search, jump or run" />
      <div class="list" id="palette-list" role="listbox" bind:this={list}>
        {#each rows as it, i (it.kind + it.go + it.label)}
          <!-- svelte-ignore a11y_click_events_have_key_events -->
          <div class="row" class:on={i === at} role="option" tabindex="-1" aria-selected={i === at} onmousemove={() => (at = i)} onclick={() => pick(it)}>
            <span class="k">{it.kind === 'action' ? 'do' : it.kind}</span>
            {#if it.kind === 'step'}<span class="sub">{it.sub}</span>{/if}
            <span class="t">{it.label}</span>
            {#if it.kind !== 'step' && it.sub}<span class="sub r">{it.sub}</span>{/if}
            {#if it.state}<span class="chip s-{it.state}">{it.state}</span>{/if}
          </div>
        {:else}
          <p class="dim">{q.trim() ? 'No match.' : 'Nothing needs you. Type to search.'}</p>
        {/each}
        {#if found.length > MAX}<p class="dim">{found.length - MAX} more: type to narrow.</p>{/if}
      </div>
      <div class="foot"><span class="kb">↑↓</span> move <span class="kb">Enter</span> go <span class="kb">Esc</span> close</div>
    </div>
  </div>
{/if}

<style>
  .back { position: fixed; inset: 0; background: color-mix(in srgb, var(--bg) 70%, transparent); display: flex; justify-content: center; align-items: flex-start; padding: 12vh 16px 0; z-index: 20; }
  .box { background: var(--dkr); border: 1px solid var(--mu); border-radius: 8px; width: min(640px, 100%); max-height: calc(100vh - 12vh - 16px); display: flex; flex-direction: column; overflow: hidden; }
  input { flex: none; height: 44px; padding: 0 14px; border: 0; border-bottom: 1px solid var(--sel); background: transparent; color: var(--fg); font: inherit; font-size: 15px; outline: none; }
  .list { flex: 1; min-height: 0; overflow-y: auto; padding: 4px; }
  .row { display: flex; align-items: center; gap: 10px; height: 34px; padding: 0 10px; border-radius: 5px; cursor: default; min-width: 0; }
  .row.on { background: var(--sel); }
  .row > * { flex: none; }
  .k { width: 52px; font: 11px var(--mono); color: var(--fgd); text-transform: uppercase; }
  .sub { font: 12.5px var(--mono); color: var(--fg2); }
  .t { flex: 1 1 auto; min-width: 0; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .sub.r { margin-left: auto; }
  .dim { color: var(--fgd); margin: 8px 10px; }
  .foot { flex: none; padding: 7px 14px; border-top: 1px solid var(--sel); color: var(--fgd); font-size: 12px; }
  @media (max-width: 800px) { .k { display: none; } .sub { font-size: 12px; } }
</style>
