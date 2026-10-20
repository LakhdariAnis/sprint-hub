<script lang="ts">
  import Header from '../Header.svelte'
  import { hub } from '../hub.svelte'
  import { useKeys } from '../keys.svelte'
  import { steps } from '../store.svelte'

  const groups = [
    { id: 'running', title: 'RUNNING', mark: '●', color: 'ac', empty: 'Nothing is running.' },
    { id: 'review', title: 'WAITING FOR YOU', mark: '◐', color: 'y', empty: 'Nothing to review.' },
    { id: 'next', title: 'NEXT UP', mark: '○', color: 'mu', empty: 'Nothing ready to start.' },
  ] as const

  // Re-read every 30 s: minutes since a run started, and "today" in the week.
  let now = $state(Date.now())
  $effect(() => {
    const t = setInterval(() => (now = Date.now()), 30_000)
    return () => clearInterval(t)
  })
  const since = (started?: string) => {
    if (!started) return '–'
    const m = Math.max(0, Math.floor((now - Date.parse(started)) / 60_000))
    return m < 60 ? `${m}m` : m < 1440 ? `${Math.floor(m / 60)}h` : `${Math.floor(m / 1440)}d`
  }

  const d = $derived(new Date(now))
  // ISO week number: the week of the Thursday.
  const week = $derived.by(() => {
    const t = new Date(Date.UTC(d.getFullYear(), d.getMonth(), d.getDate()))
    t.setUTCDate(t.getUTCDate() + 4 - (t.getUTCDay() || 7))
    return Math.ceil(((+t - Date.UTC(t.getUTCFullYear(), 0, 1)) / 86_400_000 + 1) / 7)
  })
  const hello = $derived(d.getHours() < 12 ? 'morning' : d.getHours() < 18 ? 'afternoon' : 'evening')
  const monday = $derived(new Date(d.getFullYear(), d.getMonth(), d.getDate() - ((d.getDay() + 6) % 7)))
  const days = $derived(Array.from({ length: 7 }, (_, i) => new Date(monday.getFullYear(), monday.getMonth(), monday.getDate() + i)))
  const sunday = $derived(days[6])
  const range = $derived(
    `${monday.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })} – ${monday.getMonth() === sunday.getMonth() ? '' : sunday.toLocaleDateString('en-US', { month: 'short' }) + ' '}${sunday.getDate()}`,
  )
  const todayIdx = $derived((d.getDay() + 6) % 7)

  const open = (k: string) => (location.hash = `#/steps/${k}`)

  // n / m / w focus a pane; j/k walk the Now pane's rows as one list.
  let focus = $state<'n' | 'm' | 'w'>('n')
  const keysAll = $derived(groups.flatMap((g) => hub.today[g.id].filter((k) => steps[k])))
  let sel = $state('')
  const at = $derived(keysAll.includes(sel) ? sel : keysAll[0])
  const move = (n: number) => focus === 'n' && (sel = keysAll[Math.max(0, Math.min(keysAll.length - 1, keysAll.indexOf(at) + n))] ?? '')
  useKeys({ n: () => (focus = 'n'), m: () => (focus = 'm'), w: () => (focus = 'w'), j: () => move(1), k: () => move(-1), Enter: () => focus === 'n' && at && open(at) })

  const reminders = $derived(
    hub.demo && ([['OVERDUE', hub.demo.reminders.overdue, 'r'], ['TODAY', hub.demo.reminders.today, ''], ['LATER', hub.demo.reminders.later, '']] as const),
  )
</script>

<Header>
  {#snippet crumb()}{d.toLocaleDateString('en-GB', { weekday: 'long', day: 'numeric', month: 'long' })} · week {week}{/snippet}
  Good {hello}, Anis
</Header>

{#if hub.live === false}
  <p class="dim pad">Cannot reach hubd.</p>
{/if}
<div class="body">
  <section class="pn" class:f={focus === 'n'} style="grid-column: span 8">
    <div class="ph">
      <span class="hk">n</span>Now<span class="n">{hub.running} running · {hub.review} to review</span>
      <span class="r"><span class="kb">↵</span> open</span>
    </div>
    {#each groups as g}
      {@const list = hub.today[g.id].map((k) => steps[k]).filter(Boolean)}
      <div class="gr"><span style="color: var(--{g.color})">{g.mark}</span>{g.title}</div>
      {#each list as s (s.project + '/' + s.step)}
        {@const k = `${s.project}/${s.step}`}
        {@const done = s.tasks.filter((t) => t.state === 'done').length}
        {@const cur = s.tasks.find((t) => t.state === 'doing') ?? s.tasks.find((t) => t.state === 'todo')}
        {@const extra = hub.demo?.steps[k]}
        <!-- svelte-ignore a11y_click_events_have_key_events -->
        <div class="cols lr" class:f={focus === 'n' && k === at} role="link" tabindex="0" onclick={() => open(k)} onfocus={() => (sel = k)}>
          <span class="dot" style="--x: var(--{g.color})"></span>
          <span class="id">{s.step}</span>
          <span>{s.title}{#if g.id === 'running' && cur}<span class="s">now: {cur.text}</span>{/if}</span>
          {#if g.id === 'running'}
            <span class="prog"><span class="pbar" style="flex: 1"><i style="width: {s.tasks.length ? (done / s.tasks.length) * 100 : 0}%"></i></span><span class="id">{done}/{s.tasks.length}</span></span>
            <span class="id">{s.model ?? '–'}</span>
            <span class="id">{since(s.runs.at(-1)?.started)}</span>
          {:else if g.id === 'review'}
            <span class="id">{#if extra}<span style="color: var(--g)">+{extra.add}</span>{#if extra.del} <span style="color: var(--r)">−{extra.del}</span>{/if}{/if}</span>
            {#if extra}<span class="chip {extra.check.ok ? 'x-g' : 'x-r'}">{extra.check.ok ? '✓' : '✗'} {extra.check.name}</span>{:else}<span></span>{/if}
            <span class="id">{since(s.runs.at(-1)?.started)}</span>
          {:else}
            <span class="id">{s.project}</span>
          {/if}
        </div>
      {:else}
        <p class="dim pad">{g.empty}</p>
      {/each}
    {/each}
  </section>

  <section class="pn" class:f={focus === 'm'} style="grid-column: span 4; grid-row: span 2">
    <div class="ph"><span class="hk">m</span>Reminders</div>
    {#if reminders}
      {#each reminders as [title, list, c]}
        <div class="gr" style={c && `color: var(--${c})`}>{title}</div>
        {#each list as r}
          {@const done = 'done' in r && r.done}
          {@const soon = 'soon' in r && r.soon}
          <div class="rm">
            <span class="ck" style={done ? 'background: var(--g); border-color: var(--g)' : c && `border-color: var(--${c})`}></span>
            <span style={done ? 'color: var(--fg3); text-decoration: line-through' : ''}>{r.text}</span>
            <span class="id" style={c ? `color: var(--${c})` : soon ? 'color: var(--y)' : ''}>{r.when}</span>
          </div>
        {/each}
      {/each}
    {:else}
      <p class="dim pad">No reminders yet.</p>
    {/if}
  </section>

  <section class="pn" class:f={focus === 'w'} style="grid-column: span 8">
    <div class="ph"><span class="hk">w</span>This week<span class="n">{range}</span></div>
    {#if hub.demo}
      <div class="wk">
        {#each days as day, i}
          <div class="dh" class:today={i === todayIdx}>{day.toLocaleDateString('en-GB', { weekday: 'short' }).toUpperCase()}<b>{day.getDate()}</b></div>
        {/each}
        {#each days as _, i}
          <div class="dc" class:f={i === todayIdx}>
            {#each hub.demo.week.filter((e) => e.day === i) as e}
              <div class="ev" style="border-left-color: var(--{e.color})"><span class="t">{e.time}</span>{e.text}</div>
            {/each}
          </div>
        {/each}
      </div>
    {:else}
      <p class="dim pad">Nothing planned this week.</p>
    {/if}
  </section>
</div>

<style>
  .dim { color: var(--fgd); }
  .pad { padding: 12px 16px; margin: 0; }
  .body { padding: 8px 28px 22px; display: grid; grid-template-columns: repeat(12, minmax(0, 1fr)); grid-template-rows: auto minmax(220px, 1fr); gap: 20px; }
  .cols { display: grid; align-items: center; column-gap: 14px; padding: 0 16px; grid-template-columns: 14px 36px minmax(0, 1fr) 150px 90px 48px; cursor: pointer; font-size: 14px; }
  .cols:hover { background: var(--lt); }
  .cols.f { background: var(--sel); }
  .id { font: 12.5px var(--mono); color: var(--fg2); }
  .prog { display: flex; align-items: center; gap: 8px; }
  .wk { flex: 1; display: grid; grid-template-columns: repeat(7, minmax(0, 1fr)); grid-template-rows: 36px 1fr; min-height: 0; }
  .dh { display: flex; flex-direction: column; align-items: center; justify-content: center; font: 10.5px var(--mono); color: var(--fg2); border-bottom: 1px solid var(--sel); line-height: 1.2; }
  .dh b { font-size: 13px; color: var(--fg); }
  .dh.today { box-shadow: inset 0 -2px 0 var(--ac); }
  .dh.today b { color: var(--ac); }
  .dc { border-right: 1px solid var(--sel); padding: 8px 6px; display: flex; flex-direction: column; gap: 6px; min-height: 0; }
  .dc:last-child { border-right: 0; }
  .dc.f { background: color-mix(in srgb, var(--ac) 7%, transparent); }
  .ev { border-radius: 5px; padding: 4px 7px; font-size: 12px; line-height: 1.35; background: var(--bg); border-left: 3px solid var(--fg3); }
  .ev .t { display: block; font: 10.5px var(--mono); color: var(--fg2); }
  .rm { display: grid; grid-template-columns: 20px minmax(0, 1fr) auto; align-items: center; gap: 12px; padding: 0 16px; min-height: 44px; border-bottom: 1px solid var(--sel); }
  .ck { width: 16px; height: 16px; border: 1.5px solid var(--mu); border-radius: 4px; }
</style>
