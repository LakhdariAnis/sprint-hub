<script lang="ts">
  import { onMount, tick } from 'svelte'
  import Copy from '../Copy.svelte'
  import Header from '../Header.svelte'
  import { useKeys } from '../keys.svelte'
  import type { Row } from '../projects'
  import { loadSettings, saveSettings, sx, type Check } from '../settings.svelte'
  import { lists } from '../store.svelte'

  type Name = 'terminal' | 'reminder_hour'
  type R =
    | { group: string; kind: 'check'; c: Check }
    | { group: string; kind: 'info'; label: string; value: string }
    | { group: string; kind: 'set'; name: Name }
    | { group: string; kind: 'project'; p: Row }

  // Loaded before the screen shows (nav.svelte.ts); the doctor is read again when the window gets focus back, e.g. after a fix was run in a terminal.
  const doctor = $derived(sx.doctor!)
  const settings = $derived(sx.settings!)
  const rows = $derived<R[]>([
    ...doctor.checks.map((c): R => ({ group: 'Health', kind: 'check', c })),
    { group: 'Health', kind: 'info', label: 'vault', value: doctor.vault },
    { group: 'Health', kind: 'info', label: 'version', value: doctor.version },
    { group: 'Health', kind: 'info', label: 'service', value: doctor.service },
    { group: 'Settings', kind: 'set', name: 'terminal' },
    { group: 'Settings', kind: 'set', name: 'reminder_hour' },
    ...(lists.projects ?? []).map((p): R => ({ group: 'Projects', kind: 'project', p })),
  ])
  const hint: Record<Name, string> = {
    terminal: 'argv split on spaces, must contain {cwd}',
    reminder_hour: '0–23, local time',
  }
  const shown = (n: Name) => (n === 'terminal' ? settings.terminal.join(' ') : String(settings.reminder_hour))

  let sel = $state(0)
  const at = $derived(Math.min(sel, rows.length - 1))
  const move = (d: number) => {
    sel = Math.max(0, Math.min(rows.length - 1, at + d))
    tick().then(() => document.querySelector('.row.f')?.scrollIntoView({ block: 'nearest' }))
  }

  let editing = $state<Name | null>(null)
  let text = $state('')
  let busy = $state(false)
  let note = $state<{ name: Name; ok: boolean; text: string } | null>(null)

  function edit(name: Name) {
    editing = name
    text = shown(name)
    note = null
  }
  const focus = (el: HTMLInputElement) => {
    el.focus()
    el.select()
  }
  async function save(name: Name) {
    if (busy) return
    busy = true
    try {
      const value = name === 'terminal' ? { terminal: text.split(/\s+/).filter(Boolean) } : { reminder_hour: text.trim() as unknown as number }
      const why = await saveSettings(value)
      if (why) note = { name, ok: false, text: why }
      else {
        editing = null
        note = { name, ok: true, text: 'saved to hub.toml, applies at once' }
      }
    } catch {
      note = { name, ok: false, text: 'cannot reach hubd' }
    }
    busy = false
  }
  function activate() {
    const r = rows[at]
    if (r?.kind === 'set') edit(r.name)
    else if (r?.kind === 'check') (document.querySelector('.row.f .cp') as HTMLElement | null)?.click()
  }
  useKeys({ j: () => move(1), k: () => move(-1), Enter: activate })

  onMount(() => {
    const again = () => loadSettings().catch(() => {})
    addEventListener('focus', again)
    return () => removeEventListener('focus', again)
  })
</script>

<div class="page">
  <Header>
    {#snippet crumb()}{settings.path}{/snippet}
    Settings
  </Header>

  <div class="body">
    <section class="pn f">
      <div class="ph">Health and settings<span class="n">{doctor.checks.filter((c) => !c.ok).length} to fix</span><span class="r"><span class="kb">↵</span> edit / copy</span></div>
      {#each rows as r, i}
        {#if i === 0 || rows[i - 1].group !== r.group}
          <div class="gr">{r.group.toUpperCase()}</div>
          {#if r.group === 'Settings'}
            {#if settings.error}<div class="warn" role="alert">hub.toml is not read, so these are the defaults: {settings.error}</div>{/if}
            {#if settings.comments}<div class="dim pad">Saving rewrites hub.toml from these two settings: comments and other lines in it are lost.</div>{/if}
          {/if}
        {/if}
        <!-- svelte-ignore a11y_click_events_have_key_events -->
        <div class="row {r.kind}" class:f={i === at} class:bad={r.kind === 'check' && !r.c.ok} role="button" tabindex="0" onclick={() => (sel = i)} onfocus={() => (sel = i)}>
          {#if r.kind === 'check'}
            <span class="mk" class:ok={r.c.ok}>{r.c.ok ? '✔' : '✘'}</span>
            <span class="tx">{r.c.text}{#if r.c.fix} <code>{r.c.fix}</code> <Copy text={r.c.fix} label="command" />{/if}</span>
          {:else if r.kind === 'info'}
            <span class="mk">ℹ</span>
            <span class="tx"><span class="dim">{r.label}</span> <span class="mono">{r.value}</span></span>
          {:else if r.kind === 'set'}
            <span class="nm mono">{r.name}</span>
            {#if editing === r.name}
              <input class="in mono" aria-label={r.name} bind:value={text} use:focus disabled={busy}
                onkeydown={(e) => { if (e.key === 'Enter') save(r.name); else if (e.key === 'Escape') { editing = null; note = null } }} />
            {:else}
              <span class="val mono">{shown(r.name)}</span>
            {/if}
            <span class="hint">{editing === r.name ? 'Enter saves · Esc leaves' : hint[r.name]}{settings.restart.includes(r.name) ? ' · needs a restart' : ' · applies at once'}</span>
            {#if note?.name === r.name}<span class="note" class:err={!note.ok} role={note.ok ? 'status' : 'alert'}>{note.text}</span>{/if}
          {:else}
            <b class="pname">{r.p.name}</b>
            <span class="mono repo">{r.p.path || 'vault only'}</span>
            <span class="mono base">base {r.p.base}</span>
            <span class="ex" class:no={r.p.repoMissing}>{r.p.path ? (r.p.repoMissing ? 'repo missing' : 'repo found') : ''}</span>
          {/if}
        </div>
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
  .gr { background: var(--dk); }
  .dim { color: var(--fgd); }
  .pad { padding: 8px 16px; }
  .warn { padding: 10px 16px; color: var(--y); background: color-mix(in srgb, var(--y) 10%, var(--dk)); border-bottom: 1px solid var(--sel); overflow-wrap: anywhere; }
  .mono, code { font: 12.5px var(--mono); }
  code { color: var(--fg); background: var(--bg); padding: 2px 8px; border-radius: 4px; }
  .row { display: grid; align-items: center; column-gap: 14px; row-gap: 2px; padding: 6px 16px; min-height: 40px; border-bottom: 1px solid var(--sel); cursor: pointer; overflow-wrap: anywhere; }
  .row:hover { background: var(--lt); }
  .row.f, .row.f:hover { background: var(--sel); box-shadow: inset 3px 0 0 var(--ac); }
  .check, .info { grid-template-columns: 20px minmax(0, 1fr); }
  .mk { color: var(--g); text-align: center; }
  .mk:not(.ok) { color: var(--fgm); }
  .bad .mk { color: var(--r); }
  .check .tx { display: flex; flex-wrap: wrap; align-items: center; gap: 4px 8px; }
  .set { grid-template-columns: 130px minmax(0, 1fr) minmax(0, 0.8fr); }
  .nm { color: var(--fg2); }
  .val { color: var(--fg); }
  .in { width: 100%; min-width: 0; height: 28px; padding: 0 8px; border: 1px solid var(--ac); border-radius: 4px; background: var(--bg); }
  .hint { color: var(--fgd); font-size: 12.5px; }
  .note { grid-column: 2 / -1; color: var(--g); }
  .note.err { color: var(--r); }
  .project { grid-template-columns: 150px minmax(0, 1fr) 90px 90px; }
  .pname { font-weight: 500; }
  .repo, .base { color: var(--fg2); }
  .ex { color: var(--g); font-size: 12.5px; }
  .ex.no { color: var(--r); }
  @container (max-width: 1060px) { .body { padding: 8px 16px 14px; } }
  /* One column: the label, then its value and hint under it. */
  @container (max-width: 700px) {
    .body { padding: 8px 12px 12px; }
    .row { padding: 6px 12px; column-gap: 10px; }
    .set { grid-template-columns: minmax(0, 1fr); }
    .note { grid-column: 1; }
    .project { grid-template-columns: minmax(0, 1fr) auto; }
    .project .repo { grid-column: 1 / -1; grid-row: 2; }
    .project .base { grid-row: 3; }
    .project .ex { grid-row: 3; text-align: right; }
  }
  @container (max-height: 640px) { .body { padding-bottom: 10px; } }
</style>
