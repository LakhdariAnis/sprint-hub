<script lang="ts">
  import { tick, untrack } from 'svelte'
  import Header from '../Header.svelte'
  import { chats, loadChat, send } from '../chat.svelte'
  import { useKeys } from '../keys.svelte'

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

  function onkeydown(e: KeyboardEvent) {
    if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) {
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
                <div class="starter"><span class="c">{c}</span><span>{t}</span><span class="dim xs">{d}</span></div>
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
        <div class="col">
          <div class="box">
            <label class="sr" for="msg">Message</label>
            <textarea id="msg" rows="2" placeholder="Message Claude…" bind:this={box} bind:value={text} {onkeydown}></textarea>
            <div class="hint"><span class="kb">⇧↵</span> new line · <span class="kb">↵</span> send</div>
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
  .starter { display: flex; flex-direction: column; gap: 4px; padding: 12px 14px; border: 1px solid var(--sel); border-radius: 8px; min-width: 0; }
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
  .sr { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); }
  @container (max-width: 700px) {
    .body { padding: 8px 12px 12px; }
    .log { padding: 16px 12px 8px; }
    .cmp { padding: 0 12px 12px; }
    .starters { grid-template-columns: 1fr; }
    .me { max-width: 95%; }
  }
</style>
