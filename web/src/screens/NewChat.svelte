<script lang="ts">
  import { tick, untrack } from 'svelte'
  import Header from '../Header.svelte'
  import { change, chats, chip, contextOf, loadChat, pills, send, type Context } from '../chat.svelte'
  import { useKeys } from '../keys.svelte'
  import { loadProject } from '../nav.svelte'
  import { loadProjects } from '../projects'
  import { filter, options, slashQuery, split, type Opt } from '../slash'
  import { lists, steps } from '../store.svelte'

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
  useKeys({ c: focusBox, i: focusBox })

  // On load, and when the URL names another chat (n again, a link): the cursor goes to the box.
  $effect(() => {
    cid = id
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
    if (cmds.length && onmenu(e)) e.preventDefault()
    else if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) {
      e.preventDefault()
      submit()
    } else if (e.key === 'Escape') box?.blur()
  }

  // Follow the answer down, unless Anis scrolled up to read.
  let stick = true
  const onscroll = () => log && (stick = log.scrollHeight - log.scrollTop - log.clientHeight < 80)
  $effect(() => {
    turns.map((t) => t.ai.length + t.me.length) // re-run on every delta
    failed
    if (stick) tick().then(() => log && (log.scrollTop = log.scrollHeight))
  })

  // ``` fences make a code block, the rest is text (610 does the markdown). A fence still open while the answer streams is a block too.
  const parts = (s: string) => s.split('```').map((p, i) => ({ code: i % 2 === 1, text: i % 2 === 1 ? p.replace(/^[^\n]*\n/, '').replace(/\n$/, '') : p.trim() })).filter((p) => p.text)

  const starters = [
    ['/project', 'Talk about a project', 'loads its README and sprints'],
    ['/sprint', 'Plan or check a sprint', 'hours vs the 15 h budget'],
    ['/step', 'Work on one step', 'spec, report and diff in context'],
  ]
</script>

<div class="page">
  <Header>
    {#snippet crumb()}<a href="#/chat">Chats</a> › New{/snippet}
    {#snippet aside()}{#if !turns.length}Not saved until you send{/if}{/snippet}
    New chat
  </Header>
  <div class="body">
    <section class="pn f">
      <div class="ph"><span class="hk">c</span>Chat<span class="n">plain chat · no project</span></div>
      <div class="log" bind:this={log} {onscroll}>
        <div class="col">
          {#if !turns.length && !failed}
            <div class="hi">What are we working on?</div>
            <div class="dim">Just type. Or start from a project, a sprint or one step.</div>
            <div class="starters">
              {#each starters as [c, t, d]}
                <button type="button" class="starter" onmousedown={(e) => e.preventDefault()} onclick={() => ask(c.slice(1))}><span class="c">{c}</span><span>{t}</span><span class="dim xs">{d}</span></button>
              {/each}
            </div>
          {/if}
          {#each turns as t}
            <div class="me">{t.me}</div>
            {#each parts(t.ai) as p}
              {#if p.code}<pre>{p.text}</pre>{:else}<p class="ai">{p.text}</p>{/if}
            {/each}
            {#if !t.ai && !t.done}<div class="think">thinking…</div>{/if}
            {#if t.error}<div class="err" role="alert">{t.error}</div>{/if}
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
          {#if context}
            <div class="chip" role="status"><span class="dim">context</span> {typeof context === 'string' ? `not loaded: ${context}` : chip(context)}</div>
          {/if}
          <div class="box">
            <label class="sr" for="msg">Message</label>
            <textarea id="msg" rows="2" placeholder="Message Claude…" bind:this={box} bind:value={text} {onkeydown} oninput={typed}></textarea>
            <div class="hint"><span class="kb">/</span> commands · <span class="kb">⇧↵</span> new line · <span class="kb">↵</span> send</div>
          </div>
          <div class="pills">
            <button type="button" class="pill" disabled={!!cid} onclick={() => ask('project')}><span class="dim">project</span> {projectName(view.project)}</button>
            {#if pills.sprint}<button type="button" class="pill" disabled={!!cid} onclick={() => ask('sprint')}><span class="dim">sprint</span> {pills.sprint}</button>{/if}
            {#if pills.step}<button type="button" class="pill" disabled={!!cid} onclick={() => ask('step')}><span class="dim">step</span> {pills.step}</button>{/if}
            <button type="button" class="pill" onclick={() => ask('model')}><span class="dim">model</span> {view.model}</button>
            <button type="button" class="pill" onclick={() => ask('effort')}><span class="dim">effort</span> {view.effort}</button>
          </div>
        </div>
      </form>
    </section>
  </div>
</div>

<style>
  .dim { color: var(--fgd); }
  .xs { font-size: 11px; }
  .page { height: 100%; display: flex; flex-direction: column; container-type: size; }
  .body { flex: 1; min-height: 0; padding: 8px 28px 22px; display: flex; flex-direction: column; }
  .pn { flex: 1; }
  .log { flex: 1; min-height: 0; overflow-y: auto; padding: 28px 24px 12px; }
  /* Everything in the pane sits in one centred column. */
  .col { max-width: 760px; margin: 0 auto; display: flex; flex-direction: column; gap: 10px; }
  .hi { font-size: 20px; font-weight: 600; margin-bottom: -6px; }
  .starters { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 10px; margin-top: 6px; }
  .starter { display: flex; flex-direction: column; gap: 4px; padding: 12px 14px; border: 1px solid var(--sel); border-radius: 8px; min-width: 0; font: inherit; color: inherit; background: none; text-align: left; cursor: pointer; }
  .starter:hover, .starter:focus-visible { border-color: var(--ac); outline: none; }
  .starter .c { font: 700 13px var(--mono); color: var(--ac); }
  .me { align-self: flex-end; max-width: 85%; padding: 8px 12px; border-radius: 10px; background: var(--sel); white-space: pre-wrap; overflow-wrap: anywhere; }
  .ai { margin: 0; white-space: pre-wrap; overflow-wrap: anywhere; line-height: 1.55; }
  pre { margin: 0; padding: 10px 12px; border-radius: 8px; background: var(--dk); border: 1px solid var(--sel); font: 13px/1.5 var(--mono); overflow-x: auto; }
  .think { color: var(--fgd); font-size: 13px; }
  .err { padding: 8px 12px; border: 1px solid var(--r); border-radius: 6px; color: var(--r); overflow-wrap: anywhere; }
  .cmp { flex: none; padding: 0 24px 16px; }
  .box { border: 1px solid var(--ac); border-radius: 10px; background: var(--dk); padding: 12px 14px; display: flex; flex-direction: column; gap: 8px; }
  /* Chromium grows the box with its text (field-sizing); max-height is 8 lines, then it scrolls. */
  textarea { border: 0; background: none; resize: none; outline: none; width: 100%; padding: 0; font: inherit; font-size: 15px; line-height: 1.5; color: inherit; field-sizing: content; min-height: 3em; max-height: 12em; overflow-y: auto; }
  .hint { align-self: flex-end; font-size: 11px; color: var(--fgd); }
  .rel { position: relative; }
  .chip { align-self: flex-start; max-width: 100%; margin-bottom: 6px; font-size: 12px; padding: 3px 10px; border: 1px solid var(--sel); border-radius: 6px; overflow-wrap: anywhere; }
  .pills { display: flex; flex-wrap: wrap; gap: 8px; }
  .pill { font: inherit; font-size: 12px; padding: 3px 10px; border: 1px solid var(--sel); border-radius: 999px; background: none; color: inherit; cursor: pointer; }
  .pill:hover:not(:disabled), .pill:focus-visible { border-color: var(--ac); outline: none; }
  .pill:disabled { cursor: default; opacity: 0.7; }
  /* Above the box; two columns, commands and the options of the one picked. */
  .menu { position: absolute; left: 0; right: 0; bottom: calc(100% + 6px); display: grid; grid-template-columns: 1fr 1fr; max-height: min(280px, 45cqh); overflow-y: auto; background: var(--dk); border: 1px solid var(--sel); border-radius: 10px; z-index: 5; }
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
  @container (max-width: 700px) {
    .body { padding: 8px 12px 12px; }
    .log { padding: 16px 12px 8px; }
    .cmp { padding: 0 12px 12px; }
    .starters { grid-template-columns: 1fr; }
    .me { max-width: 95%; }
  }
</style>
