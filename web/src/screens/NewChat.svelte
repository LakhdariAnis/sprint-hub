<script lang="ts">
  import { tick, untrack } from 'svelte'
  import Header from '../Header.svelte'
  import Markdown from '../Markdown.svelte'
  import { answer, answerOf, asksOf, toolsOf, change, chats, edit, saved, chip, contextOf, loadChat, pills, send, stop, type Ask, type Context } from '../chat.svelte'
  import { costLine } from '../cost'
  import { keys, useKeys } from '../keys.svelte'
  import { loadProject } from '../nav.svelte'
  import { loadProjects } from '../projects'
  import { filter, options, slashQuery, split, type Opt } from '../slash'
  import { graphOf, lists, steps } from '../store.svelte'
  import GraphPane from '../graph/GraphPane.svelte'
  import { MAX, MIN, clamp, read, write } from '../split'

  let { id }: { id?: string } = $props()

  // The chat on show. It follows the URL, but a first send sets it before the URL catches up: no flash of the start page.
  let cid = $state<string | undefined>()
  let text = $state('')
  let failed = $state('')
  let sending = $state(false)
  let box = $state<HTMLTextAreaElement>()
  let log = $state<HTMLElement>()

  const turns = $derived(cid ? (chats[cid]?.turns ?? []) : [])
  const focusBox = () => box?.focus()

  // The card waiting for Anis, oldest first: a / d / A answer it.
  const waiting = $derived(turns.flatMap((t) => (t.done ? [] : asksOf(t))).find((a) => a.request && !a.answer))
  async function decide(choice: 'allow' | 'deny' | 'chat') {
    const a = waiting
    if (!a?.request || !cid || (choice === 'chat' && !a.wide)) return
    failed = ''
    await answer(cid, a.request, choice).then(focusBox, (e: Error) => (failed = e.message))
  }
  // A turn is running: Stop, or Esc Esc.
  const busy = $derived(turns.some((t) => !t.done))
  async function halt(refocus = false) {
    if (!cid || !busy) return
    failed = ''
    await stop(cid).then(() => refocus && focusBox(), (e: Error) => (failed = e.message))
  }
  // NORMAL mode (the box has no focus): j k pick a turn, ↵ opens or closes its tool lines.
  let sel = $state<number | null>(null)
  function pick(step: number) {
    if (!turns.length) return
    sel = Math.max(0, Math.min(turns.length - 1, (sel ?? (step > 0 ? -1 : turns.length)) + step))
    tick().then(() => log?.querySelectorAll('.turn')[sel!]?.scrollIntoView({ block: 'nearest' }))
  }
  function fold() {
    const turn = sel === null ? undefined : turns[sel]
    const tools = turn ? toolsOf(turn) : []
    const open = tools.some((t) => !t.open)
    for (const t of tools) t.open = open
  }
  // `x`: out of the sidebar's OPEN (the chat stays in the vault; a new message brings it back). Only a chat that was sent.
  async function close() {
    if (!cid || !saved.list?.some((c) => c.id === cid)) return
    failed = ''
    await edit(cid, { open: false }).then(() => (location.hash = '#/chat'), (e: Error) => (failed = e.message))
  }
  // The saved chat's name (the vault's, `R` changes it); a chat that was not sent has none.
  const title = $derived(saved.list?.find((c) => c.id === cid)?.title ?? '')
  // No turns and no saved name: the greeting and the box sit in the middle, until the first send.
  const home = $derived(!turns.length && !title)
  let renaming = $state(false)
  let draft = $state('')
  let nameBox = $state<HTMLInputElement>()
  function rename() {
    if (!title) return
    draft = title
    renaming = true
    tick().then(() => (nameBox?.focus(), nameBox?.select()))
  }
  async function saveName() {
    const t = draft.trim()
    renaming = false
    focusBox()
    if (!t || t === title || !cid) return
    failed = ''
    await edit(cid, { title: t }).catch((e: Error) => (failed = e.message))
  }
  let lastEsc = 0
  function esc() {
    const now = Date.now()
    if (now - lastEsc < 1000) {
      lastEsc = 0
      halt()
    } else lastEsc = now
  }
  const choices: Record<string, 'allow' | 'deny' | 'chat'> = { a: 'allow', d: 'deny', A: 'chat' }
  useKeys({ get g() { return graphOn ? () => (open = !open) : undefined }, x: close, R: rename, c: focusBox, i: focusBox, Escape: esc, j: () => pick(1), k: () => pick(-1), Enter: fold, a: () => decide('allow'), d: () => decide('deny'), A: () => decide('chat') })
  const verb = (a: Ask) => (a.tool === 'Bash' || a.tool === 'PowerShell' ? 'run' : a.diff !== null || /Edit|Write/.test(a.tool) ? 'change' : 'use')
  const outcome: Record<string, string> = {
    allow: 'Allowed',
    chat: 'Allowed for this chat',
    deny: 'Denied: Claude was told “Anis denied”',
    timeout: 'No answer in 10 min, so it was denied',
    stopped: 'The chat was stopped',
  }

  // On load, and when the URL names another chat (n again, a link): the cursor goes to the box.
  $effect(() => {
    cid = id
    sel = null
    failed = ''
    untrack(() => id && !chats[id] && loadChat(id).catch((e) => (failed = e.message)))
    tick().then(focusBox)
  })

  async function submit() {
    const t = text.trim()
    if (!t || sending) return
    sending = true
    failed = ''
    try {
      const sent = await send(cid, t)
      text = ''
      if (!cid) {
        cid = sent
        location.hash = `#/chat/${sent}`
      }
    } catch (e) {
      failed = (e as Error).message // the text stays in the box
    } finally {
      sending = false
    }
  }

  // What the chat on show runs with: its own once it has started, else the pills.
  const view = $derived((cid && chats[cid]?.model ? chats[cid] : pills) as { model: string; effort: string; project: string | null })
  // The chip above the box: what hubd will tell Claude (the pills, before the first send), or what it told this chat.
  let preview = $state<Context | string | null>(null)
  $effect(() => {
    const { project, sprint, step } = pills
    if (cid || !project) return void (preview = null)
    let live = true
    contextOf(project, sprint, step).then(
      (c) => live && (preview = c),
      (e: Error) => live && (preview = e instanceof TypeError ? 'hubd is not running' : e.message),
    )
    return () => (live = false)
  })
  const context = $derived(cid && chats[cid]?.model ? (chats[cid].context ?? null) : preview)
  // The split (658b): chat | handle | graph, only for a project whose graph is on. `open` and `left` (the chat's % of the width) are kept per window.
  const saved0 = read()
  let open = $state(saved0.open)
  let left = $state(saved0.left)
  let grid = $state<HTMLElement>()
  const graphOn = $derived(!!view.project && graphOf(view.project))
  const shared = $derived(graphOn && open)
  // Whether a project has the graph on comes with the project list: fetch it when a chat has a project and none is loaded (a reload).
  $effect(() => {
    if (view.project && !lists.projects) loadProjects().then((p) => (lists.projects ??= p), () => {})
  })
  $effect(() => write({ open, left }))
  // The split takes the room: the sidebar folds to its ^B rail (not saved) and comes back as it was.
  $effect(() => {
    if (!shared) return
    const was = untrack(() => keys.rail)
    keys.rail = true
    return () => void (!was && (keys.rail = false))
  })
  function drag(e: PointerEvent) {
    const h = e.currentTarget as HTMLElement
    h.setPointerCapture(e.pointerId)
    const move = (ev: PointerEvent) => {
      const b = grid!.getBoundingClientRect()
      left = clamp(((ev.clientX - b.left) / b.width) * 100)
    }
    const up = () => (h.removeEventListener('pointermove', move), h.removeEventListener('pointerup', up))
    h.addEventListener('pointermove', move)
    h.addEventListener('pointerup', up)
  }
  function nudge(e: KeyboardEvent) {
    if (e.key !== 'ArrowLeft' && e.key !== 'ArrowRight') return
    e.preventDefault()
    left = clamp(left + (e.key === 'ArrowLeft' ? -3 : 3))
  }
  const projectName = (id: string | null) => (id ? (lists.projects?.find((p) => p.id === id)?.name ?? id) : 'none')

  // The / menu: `at` = command row, `opt` = option row, `col` = the column that has the keys. Esc sets `shut` until the next key typed.
  let at = $state(0)
  let opt = $state(0)
  let col = $state(0)
  let shut = $state(false)
  const q = $derived(slashQuery(text))
  const cmds = $derived(q === null || shut ? [] : filter(q))
  const cmd = $derived(cmds[Math.min(at, cmds.length - 1)])
  const ctx = $derived({ projects: lists.projects ?? [], steps: (view.project ? (lists.steps[view.project] ?? []) : []).map((k) => steps[k]) })
  const opts = $derived(cmd ? options(cmd.name, ctx) : [])
  const nothing = $derived(cmd && !opts.length && cmd.name !== 'clear')

  // The project list and the project's steps come when a menu needs them.
  $effect(() => {
    if (!cmds.length) return
    if (!lists.projects) loadProjects().then((p) => (lists.projects = p), () => {})
    const p = view.project
    if (p && !lists.steps[p]) loadProject(p).catch(() => {})
  })

  const current = (name: string) => (name === 'model' ? view.model : name === 'effort' ? view.effort : name === 'project' ? (view.project ?? '') : name === 'sprint' ? (pills.sprint ?? '') : (pills.step ?? ''))
  function toOptions() {
    if (!opts.length) return
    col = 1
    opt = Math.max(0, opts.findIndex((o) => o.value === current(cmd.name)))
  }
  const typed = () => ((at = 0), (col = 0), (opt = 0), (shut = false))

  async function choose(o: Opt) {
    const name = cmd.name as 'model' | 'effort' | 'project' | 'sprint' | 'step'
    failed = ''
    try {
      if ((name === 'model' || name === 'effort') && cid && chats[cid]?.model) await change(cid, { [name]: o.value })
      if (name === 'model' || name === 'effort') pills[name] = o.value
      else if (cid) throw new Error(`A chat keeps its ${name}: hubd told Claude when it started. Type /clear for a new chat.`)
      else if (name === 'project') Object.assign(pills, { project: o.value || null, sprint: null, step: null })
      else pills[name] = o.value || null
      text = ''
      typed()
    } catch (e) {
      failed = (e as Error).message // the menu stays open
    }
  }

  function clear() {
    text = ''
    typed()
    failed = ''
    if (cid) location.hash = '#/chat' // the effect above drops the old chat
  }

  // A pill opens the menu on its command, with the options column ready.
  async function ask(name: string) {
    text = `/${name}`
    typed()
    box?.focus()
    await tick()
    toOptions()
  }

  function onmenu(e: KeyboardEvent): boolean {
    const n = col ? opts.length : cmds.length
    const move = (d: number) => (col ? (opt = Math.max(0, Math.min(n - 1, opt + d))) : (at = Math.max(0, Math.min(n - 1, at + d))))
    if (e.key === 'ArrowDown') move(1)
    else if (e.key === 'ArrowUp') move(-1)
    else if (e.key === 'Tab') col ? (col = 0) : toOptions()
    else if (e.key === 'Escape') shut = true
    else if (e.key === 'Enter' && !e.isComposing) {
      if (col) choose(opts[opt])
      else if (cmd.name === 'clear') clear()
      else toOptions()
    } else if (col && /^[1-9]$/.test(e.key) && opts[+e.key - 1]) choose(opts[+e.key - 1])
    else return false
    return true
  }

  function onkeydown(e: KeyboardEvent) {
    if (e.key === 'Escape') esc()
    if (cmds.length && onmenu(e)) e.preventDefault()
    // A card waits and the box is empty: a / d / A answer it from the box too.
    else if (waiting && !text && choices[e.key] && !e.ctrlKey && !e.metaKey && !e.altKey) {
      e.preventDefault()
      decide(choices[e.key])
    }
    else if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) {
      e.preventDefault()
      submit()
    } else if (e.key === 'Escape') box?.blur()
  }

  // Follow the answer down, unless Anis scrolled up to read.
  let stick = true
  const onscroll = () => log && (stick = log.scrollHeight - log.scrollTop - log.clientHeight < 80)
  $effect(() => {
    turns.map((t) => t.me.length + t.blocks.length + answerOf(t).length + (t.end ? 1 : 0)) // re-run on every delta, tool line and card
    failed
    if (stick) tick().then(() => log && (log.scrollTop = log.scrollHeight))
  })

  const starters = [
    ['/project', 'Talk about a project: loads its README and sprints'],
    ['/sprint', 'Plan or check a sprint: hours vs the 15 h budget'],
    ['/step', 'Work on one step: spec, report and diff in context'],
  ]
</script>

<div class="page">
  <Header>
    {#snippet crumb()}<a href="#/chat">Chats</a> › {title ? 'Chat' : 'New'}{/snippet}
    {#snippet aside()}
      {#if graphOn}
        <div class="seg" role="group" aria-label="Layout">
          <button type="button" aria-pressed={!open} onclick={() => (open = false)}>Chat</button>
          <button type="button" aria-pressed={open} onclick={() => (open = true)}>Chat + Graph <span class="kb">g</span></button>
        </div>
      {:else if !turns.length && !title}Not saved until you send{/if}
    {/snippet}
    {#if renaming}
      <input class="name" aria-label="Chat name" maxlength="100" bind:this={nameBox} bind:value={draft} onblur={() => (renaming = false)}
        onkeydown={(e) => (e.key === 'Enter' && !e.isComposing ? saveName() : e.key === 'Escape' && ((renaming = false), focusBox()))} />
    {:else}{title || 'New chat'}{/if}
  </Header>
  <div class="split" class:on={shared} style:--left="{left}%" bind:this={grid}>
  <div class="body" class:home>
    <div class="log" bind:this={log} {onscroll}>
      <div class="col">
        {#if home && !failed}<div class="hi">What are we working on?</div>{/if}
        {#if cid && chats[cid]?.earlier_hidden}<div class="dim xs" role="status">earlier turns not shown</div>{/if}
        {#each turns as t, i}
          <div class="turn" class:foc={i === sel} aria-current={i === sel ? 'true' : undefined}>
            <div class="me">{t.me}</div>
            {#each t.blocks as b}
              {#if b.kind === 'text'}
                <div class="ai"><Markdown text={b.text} /></div>
              {:else if b.kind === 'tool'}
                <div class="tool" class:open={b.open}>
                  <button type="button" class="tl" aria-expanded={b.open} title={b.line} onclick={() => (b.open = !b.open)}>
                    <span class="tw" aria-hidden="true">{b.open ? '▾' : '▸'}</span><span class="tn">{b.line}</span>{#if b.result !== undefined}<span class="ts" class:bad={b.error} aria-label={b.error ? 'failed' : 'done'}>{b.error ? '✗' : '✓'}</span>{/if}
                  </button>
                  {#if b.open}
                    <pre class="tin" aria-label="Input">{b.input}</pre>
                    {#if b.result === undefined}<div class="dim xs">{t.done ? 'No result' : 'Running…'}</div>{:else}<pre class="tres" class:bad={b.error} aria-label="Result">{b.result || '(empty)'}</pre>{/if}
                  {/if}
                </div>
              {:else}
                {@const a = b}
                <div class="ask" class:open={a === waiting} role="group" aria-label="Permission: {a.tool}">
                  <div class="at"><span class="tname">{a.tool}</span> <span class="dim">wants to {verb(a)}</span></div>
                  <code class="tgt">{a.target}</code>
                  {#if a.diff}<pre class="diff">{#each a.diff.split('\n') as line}<span class:add={line.startsWith('+')} class:del={line.startsWith('-')}>{line}</span>{'\n'}{/each}</pre>{/if}
                  {#if a === waiting}
                    <div class="btns">
                      <button type="button" class="b ok" onclick={() => decide('allow')}><span class="k" aria-hidden="true">a</span> Allow</button>
                      <button type="button" class="b" onclick={() => decide('deny')}><span class="k" aria-hidden="true">d</span> Deny</button>
                      {#if a.wide}<button type="button" class="b" onclick={() => decide('chat')}><span class="k" aria-hidden="true">A</span> Allow for this chat</button>{/if}
                      <span class="note dim xs">Claude waits. No answer in 10 min denies it. a d A work in the box while it is empty.</span>
                    </div>
                  {:else}
                    <div class="dim xs" role="status">{a.refused ? `Refused: ${a.refused}` : a.answer ? outcome[a.answer] ?? a.answer : t.done ? 'Not answered' : 'Waiting for the card above'}</div>
                  {/if}
                </div>
              {/if}
            {/each}
            {#if !t.blocks.length && !t.done}<div class="think">thinking…</div>{/if}
            {#if t.error}<div class="err" role="alert">{t.error}</div>{/if}
            {#if t.stopped}<div class="stopped" role="status">stopped</div>{/if}
            {#if t.end && costLine(t.end)}<div class="cost">{costLine(t.end)}</div>{/if}
          </div>
        {/each}
        {#if failed}<div class="err" role="alert">{failed}</div>{/if}
      </div>
    </div>
    <form class="cmp" onsubmit={(e) => (e.preventDefault(), submit())}>
      <div class="col rel">
        {#if cmds.length}
          <div class="menu" aria-label="Commands">
            <div class="cmds" role="listbox" aria-label="Commands">
              {#each cmds as c, i}
                {@const [a, b] = split(c.name, q ?? '')}
                <button type="button" tabindex="-1" role="option" aria-selected={i === at} class:on={i === at} class:foc={i === at && !col} onmousedown={(e) => e.preventDefault()} onclick={() => ((at = i), c.name === 'clear' ? clear() : toOptions())}>
                  <span class="cn">/<u>{a}</u>{b}</span><span class="dim xs">{c.desc}</span>
                </button>
              {/each}
            </div>
            <div class="cmds" role="listbox" aria-label="Options of /{cmd?.name}">
              {#each opts as o, i}
                <button type="button" tabindex="-1" role="option" aria-selected={col === 1 && i === opt} class:on={col === 1 && i === opt} class:foc={col === 1 && i === opt} onmousedown={(e) => e.preventDefault()} onclick={() => choose(o)}>
                  <span class="cn">{#if i < 9}<span class="dim num">{i + 1}</span>{/if}{o.label}</span><span class="dim xs">{o.value === current(cmd.name) ? 'current' : (o.desc ?? '')}</span>
                </button>
              {:else}
                <div class="dim xs pad">{nothing ? (!view.project ? 'Pick a project first' : lists.steps[view.project] ? 'This project has no steps' : 'Loading steps…') : 'Enter clears the chat'}</div>
              {/each}
            </div>
          </div>
        {/if}
        <div class="box">
          {#if context}
            <div class="chip" role="status"><span class="dim">context</span> {typeof context === 'string' ? `not loaded: ${context}` : chip(context)}</div>
          {/if}
          <div class="in">
          <label class="sr" for="msg">Message</label>
          <textarea id="msg" rows="1" placeholder="Message Claude…" bind:this={box} bind:value={text} {onkeydown} oninput={typed}></textarea>
          {#if cid}<span class="meta" title="This chat's model and project">{view.model} · {projectName(view.project)}</span>{/if}
          {#if busy}
            <button type="button" class="go" aria-label="Stop (Esc Esc)" title="Stop (Esc Esc)" onclick={() => halt(true)}><svg viewBox="0 0 16 16" aria-hidden="true"><rect x="3.5" y="3.5" width="9" height="9" rx="1.5" fill="currentColor" /></svg></button>
          {:else}
            <button type="submit" class="go" aria-label="Send" title="Send (↵)" disabled={!text.trim() || sending}><svg viewBox="0 0 16 16" aria-hidden="true"><path d="M8 13V3M3.5 7.5 8 3l4.5 4.5" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" /></svg></button>
          {/if}
          </div>
        </div>
        <div class="pills">
          <div class="pg">
            <button type="button" class="pill" disabled={!!cid} onclick={() => ask('project')}><span class="dim">project</span> {projectName(view.project)}</button>
            {#if pills.sprint}<button type="button" class="pill" disabled={!!cid} onclick={() => ask('sprint')}><span class="dim">sprint</span> {pills.sprint}</button>{/if}
            {#if pills.step}<button type="button" class="pill" disabled={!!cid} onclick={() => ask('step')}><span class="dim">step</span> {pills.step}</button>{/if}
          </div>
          <div class="pg">
            <button type="button" class="pill" onclick={() => ask('model')}><span class="dim">model</span> {view.model}</button>
            <button type="button" class="pill" onclick={() => ask('effort')}><span class="dim">effort</span> {view.effort}</button>
          </div>
        </div>
        {#if home}
          <div class="starters">
            {#each starters as [c, d]}
              <button type="button" class="starter" title={d} onmousedown={(e) => e.preventDefault()} onclick={() => ask(c.slice(1))}>{c}</button>
            {/each}
          </div>
        {/if}
        <div class="hint"><span class="kb">/</span> commands · <span class="kb">⇧↵</span> new line · <span class="kb">↵</span> send</div>
      </div>
    </form>
  </div>
  {#if shared && view.project}
    <!-- svelte-ignore a11y_no_noninteractive_tabindex, a11y_no_noninteractive_element_interactions -->
    <div class="drag" role="separator" aria-orientation="vertical" aria-label="Chat and graph width" aria-valuemin={MIN} aria-valuemax={MAX} aria-valuenow={Math.round(left)} tabindex="0" onpointerdown={drag} onkeydown={nudge}></div>
    <GraphPane project={view.project} onask={(t) => ((text = t), focusBox())} />
  {/if}
  </div>
</div>

<style>
  .dim { color: var(--fgd); }
  .xs { font-size: 11px; }
  .page { height: 100%; display: flex; flex-direction: column; container-type: size; }
  /* One flat canvas under the header: the log scrolls, the box stays at the bottom. */
  .split { flex: 1; min-height: 0; display: grid; grid-template: minmax(0, 1fr) / minmax(0, 1fr); }
  .split.on { grid-template-columns: var(--left) 6px minmax(0, 1fr); }
  .seg { display: flex; gap: 2px; padding: 2px; border: 1px solid var(--sel); border-radius: 8px; }
  .seg button { border: 0; background: none; color: var(--fg2); border-radius: 6px; padding: 4px 10px; font: inherit; font-size: 13px; cursor: pointer; }
  .seg button[aria-pressed='true'] { background: var(--sel); color: var(--fg); }
  .seg button:focus-visible { outline: 2px solid var(--ac); }
  .drag { cursor: col-resize; background: var(--sel); touch-action: none; }
  .drag:hover, .drag:focus-visible, .drag:active { background: var(--ac); outline: none; }
  .body { min-width: 0; min-height: 0; display: flex; flex-direction: column; }
  .log { flex: 1; min-height: 0; overflow-y: auto; padding: 28px 28px 12px; }
  /* Home: the log shrinks to the greeting and the whole body centres, so the box sits mid-page. */
  .home { justify-content: center; }
  .home .log { flex: none; overflow: visible; padding-bottom: 20px; }
  /* Everything sits in one centred column. */
  .col { max-width: 760px; margin: 0 auto; display: flex; flex-direction: column; gap: 10px; }
  .hi { font: 400 36px/1.2 var(--read); text-align: center; padding: 0 0 8px; }
  .starters { display: flex; flex-wrap: wrap; justify-content: center; gap: 8px; }
  .starter { padding: 3px 12px; border: 1px solid var(--sel); border-radius: 999px; font: 12px var(--mono); color: var(--ac); background: none; cursor: pointer; }
  .starter:hover, .starter:focus-visible { border-color: var(--ac); outline: none; }
  .me { align-self: flex-end; max-width: 85%; padding: 10px 16px; border-radius: 16px; background: var(--sel); font: 16px/1.55 var(--sans); white-space: pre-wrap; overflow-wrap: anywhere; }
  /* Claude's text: the reading font. The rules reach into Markdown (scoped here: the Spec view keeps its look); code stays mono. */
  .ai { min-width: 0; font: 400 17.5px/1.72 var(--read); max-width: 68ch; }
  .ai :global(.md) { line-height: inherit; }
  .ai :global(p) { margin: 0 0 0.85em; }
  .ai :global(.md > :last-child) { margin-bottom: 0; }
  .ai :global(.h) { font-family: var(--read); line-height: 1.4; margin: 1.1em 0 0.35em; }
  .ai :global(.h1) { font-size: 1.25em; }
  .ai :global(.h2) { font-size: 1.12em; }
  .ai :global(.h3) { font-size: 1.02em; }
  .ai :global(ul), .ai :global(ol) { margin: 0 0 0.85em; padding-left: 1.4em; }
  .ai :global(li) { margin: 0.2em 0; }
  .ai :global(b) { font-weight: 600; }
  .ai :global(p code), .ai :global(li code), .ai :global(td code), .ai :global(th code) { font-size: 0.82em; }
  .ai :global(table) { font-size: 0.85em; }
  pre { margin: 0; padding: 10px 12px; border-radius: 8px; background: var(--dk); border: 1px solid var(--sel); font: 13px/1.5 var(--mono); overflow-x: auto; }
  .think { color: var(--fgd); font-size: 13px; }
  .turn { display: flex; flex-direction: column; gap: 10px; min-width: 0; padding-left: 10px; margin-left: -10px; }
  .turn.foc { box-shadow: inset 3px 0 0 var(--ac); }
  .cost { overflow-wrap: anywhere; font-size: 12px; color: var(--fgm); }
  .name { font: inherit; color: inherit; background: var(--dk); border: 1px solid var(--ac); border-radius: 5px; padding: 0 6px; height: 30px; width: min(420px, 100%); outline: none; }
  .stopped { align-self: flex-start; padding: 0 8px; border: 1px solid var(--sel); border-radius: 999px; font-size: 11px; color: var(--fgd); }
  .tool { display: flex; flex-direction: column; gap: 4px; min-width: 0; font: 13px/1.5 var(--mono); }
  .tl { display: flex; gap: 8px; min-width: 0; padding: 0; border: 0; background: none; color: var(--fgd); font: inherit; text-align: left; cursor: pointer; }
  .tl:hover, .tl:focus-visible { color: inherit; outline: none; }
  .ts { flex: none; }
  .ts.bad { color: var(--r); }
  .tn { min-width: 0; overflow-wrap: anywhere; }
  .tin, .tres { max-height: 20em; overflow: auto; font-size: 12px; white-space: pre-wrap; overflow-wrap: anywhere; }
  .tres.bad { border-color: var(--r); }
  .ask { display: flex; flex-direction: column; gap: 8px; padding: 12px 14px; background: var(--lt); border-radius: 12px; min-width: 0; }
  .tname { font: 700 13px var(--mono); }
  .tgt { font: 13px/1.5 var(--mono); white-space: pre-wrap; overflow-wrap: anywhere; }
  .diff { max-height: 16em; overflow: auto; }
  .diff .add { color: var(--g); }
  .diff .del { color: var(--r); }
  .btns { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; }
  .note { margin-left: auto; text-align: right; min-width: 0; }
  .b { font: inherit; font-size: 13px; padding: 4px 12px; border: 1px solid transparent; border-radius: 8px; background: none; color: inherit; cursor: pointer; }
  .b:hover, .b:focus-visible { background: var(--sel); outline: none; }
  .b.ok { background: var(--ac); color: var(--bg); }
  .b.ok:hover, .b.ok:focus-visible { background: var(--ac); outline: 2px solid var(--fg); outline-offset: 1px; }
  .k { font-family: var(--mono); color: var(--fgd); margin-right: 4px; }
  .b.ok .k { color: inherit; opacity: 0.7; }
  .err { padding: 8px 12px; border: 1px solid var(--r); border-radius: 6px; color: var(--r); overflow-wrap: anywhere; }
  .cmp { flex: none; padding: 0 28px 16px; }
  /* A raised box, as in the Claude app; the round button sits bottom right and turns into Stop while a turn runs. */
  .box { display: flex; flex-direction: column; gap: 6px; background: var(--lt); border: 1px solid var(--mu); border-radius: 16px; padding: 12px 12px 12px 18px; box-shadow: 0 6px 24px rgb(0 0 0 / 0.18); }
  .in { display: flex; align-items: flex-end; gap: 10px; }
  .meta { flex: none; align-self: center; max-width: 40%; font-size: 12px; color: var(--fgm); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .box:focus-within { border-color: color-mix(in srgb, var(--ac) 55%, var(--mu)); }
  /* Chromium grows the box with its text (field-sizing); max-height is 8 lines, then it scrolls. */
  textarea { flex: 1; min-width: 0; border: 0; background: none; resize: none; outline: none; padding: 4px 0; font: inherit; font-size: 16px; line-height: 1.5; color: inherit; field-sizing: content; min-height: 1.5em; max-height: 12em; overflow-y: auto; }
  textarea::placeholder { color: var(--fgm); }
  .go { flex: none; width: 36px; height: 36px; padding: 0; display: grid; place-items: center; border: 0; border-radius: 50%; background: var(--ac); color: var(--bg); cursor: pointer; }
  .go svg { width: 18px; height: 18px; }
  .go:disabled { background: var(--sel); color: var(--fgm); cursor: default; }
  .go:focus-visible { outline: 2px solid var(--fg); outline-offset: 2px; }
  .hint { text-align: center; font-size: 11px; color: var(--fgd); }
  .rel { position: relative; }
  .chip { max-width: 100%; font-size: 12.5px; color: var(--fgm); overflow-wrap: anywhere; }
  .pills { display: flex; flex-wrap: wrap; justify-content: space-between; gap: 8px 16px; }
  .pg { display: flex; flex-wrap: wrap; gap: 8px; }
  .pill { font: inherit; font-size: 12px; padding: 3px 10px; border: 1px solid var(--sel); border-radius: 999px; background: none; color: inherit; cursor: pointer; }
  .pill:hover:not(:disabled), .pill:focus-visible { border-color: var(--ac); outline: none; }
  .pill:disabled { cursor: default; opacity: 0.7; }
  /* Above the box; two columns, commands and the options of the one picked. */
  .menu { position: absolute; left: 0; right: 0; bottom: calc(100% + 8px); display: grid; grid-template-columns: 1fr 1fr; max-height: min(280px, 45cqh); overflow-y: auto; background: var(--dk); border: 1px solid var(--sel); border-radius: 14px; box-shadow: 0 10px 32px rgb(0 0 0 / 0.35); z-index: 5; }
  .cmds { display: flex; flex-direction: column; padding: 6px; min-width: 0; }
  .cmds + .cmds { border-left: 1px solid var(--sel); }
  .cmds button { display: flex; justify-content: space-between; gap: 10px; align-items: baseline; font: inherit; color: inherit; background: none; border: 0; border-radius: 6px; padding: 5px 8px; text-align: left; cursor: pointer; min-width: 0; }
  .cmds button .xs { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; min-width: 0; }
  .cmds button.on { background: var(--sel); }
  .cmds button.foc { outline: 1px solid var(--ac); }
  .cn { font-family: var(--mono); font-size: 13px; white-space: nowrap; }
  .cn u { text-decoration-color: var(--ac); text-underline-offset: 3px; }
  .num { margin-right: 8px; }
  .pad { padding: 5px 8px; }
  .sr { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); }
  /* Narrow: chat on top, graph under; the handle goes (the halves are equal). */
  @container (max-width: 900px) {
    .split.on { grid-template: minmax(0, 1fr) minmax(0, 1fr) / minmax(0, 1fr); }
    .drag { display: none; }
    .split > :global(.graph) { border-top: 1px solid var(--sel); }
  }
  @container (max-width: 700px) {
    .log { padding: 16px 12px 8px; }
    .cmp { padding: 0 12px 12px; }
    .hi { font-size: 28px; }
    .me { max-width: 95%; }
  }
</style>
