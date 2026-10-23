<script lang="ts">
  import Header from '../Header.svelte'
  import Inline from '../Inline.svelte'
  import { hub } from '../hub.svelte'
  import { useKeys } from '../keys.svelte'
  import { steps } from '../store.svelte'
  import { loadProjects, type Row } from '../projects'
  import { ago } from '../steps'

  const groups = [
    { id: 'running', title: 'RUNNING', mark: '●', state: 'doing', empty: 'Nothing is running.' },
    { id: 'review', title: 'WAITING FOR YOU', mark: '◐', state: 'done', empty: 'Nothing to review.' },
    { id: 'next', title: 'NEXT UP', mark: '○', state: 'todo', empty: 'Nothing ready to start.' },
  ] as const

  // Re-read every 30 s: minutes since a run started, and "today" in the week.
  let now = $state(Date.now())
  $effect(() => {
    const t = setInterval(() => (now = Date.now()), 30_000)
    return () => clearInterval(t)
  })
  const since = (started?: string) => ago(started, now)

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

  let projects = $state<Row[]>([])
  loadProjects().then((d) => (projects = d), () => {})

  // p / n / m / w / q / d focus a pane; j/k walk the rows of the Projects or Now pane.
  let focus = $state<'p' | 'n' | 'm' | 'w' | 'q' | 'd'>('p')
  const keysAll = $derived(groups.flatMap((g) => hub.today[g.id].filter((k) => steps[k])))
  let sel = $state('')
  const at = $derived(keysAll.includes(sel) ? sel : keysAll[0])
  let psel = $state(0)
  const move = (n: number) => {
    if (focus === 'n') sel = keysAll[Math.max(0, Math.min(keysAll.length - 1, keysAll.indexOf(at) + n))] ?? ''
    else if (focus === 'p') psel = Math.max(0, Math.min(projects.length - 1, psel + n))
  }
  const openProject = (id: string) => (location.hash = `#/projects/${encodeURIComponent(id)}`)
  useKeys({
    p: () => (focus = 'p'), n: () => (focus = 'n'), m: () => (focus = 'm'), q: () => (focus = 'q'), w: () => (focus = 'w'), d: () => (focus = 'd'), j: () => move(1), k: () => move(-1),
    Enter: () => (focus === 'q' ? (location.hash = '#/questions') : focus === 'n' ? at && open(at) : focus === 'p' && projects[psel] && openProject(projects[psel].id)),
  })

  // Whole days from today (local) to the deadline: negative = late. UTC math, so a DST change never skews it.
  const late = (iso: string) => {
    const [y, m, dd] = iso.split('-').map(Number)
    return Math.round((Date.UTC(y, m - 1, dd) - Date.UTC(d.getFullYear(), d.getMonth(), d.getDate())) / 86_400_000)
  }
  const when = (n: number) => (n < 0 ? `${-n} d late` : n === 0 ? 'today' : `in ${n} d`)

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
  <section class="pn" class:f={focus === 'p'} style="grid-column: span 8">
    <div class="ph">
      <span class="hk">p</span>Projects<span class="n">{projects.length} in the vault</span>
      <span class="r"><span class="kb">↵</span> open</span>
    </div>
    {#each projects as r, i (r.id)}
      <!-- svelte-ignore a11y_click_events_have_key_events -->
      <div class="pr" class:f={focus === 'p' && i === psel} role="link" tabindex="0" onclick={() => openProject(r.id)} onfocus={() => ((psel = i), (focus = 'p'))}>
        <span class="nm">{r.name}</span>
        <span class="pbar"><i style="width: {r.total ? (r.approved / r.total) * 100 : 0}%"></i></span>
        <span class="id">{r.approved}/{r.total}</span>
        <span class="chip" class:s-doing={r.running > 0} title="running">{r.running} running</span>
        <span class="chip" class:s-done={r.review > 0} title="to review">{r.review} review</span>
        <span class="id">{r.todo} todo</span>
      </div>
    {:else}
      <p class="dim pad">No projects in the vault.</p>
    {/each}
  </section>

  <div class="side" style="grid-column: span 4; grid-row: span 2">
  <section class="pn" class:f={focus === 'm'}>
    <div class="ph"><span class="hk">m</span>Reminders</div>
    {#if reminders}
      {#each reminders as [title, list, c]}
        <div class="gr" style={c && `color: var(--${c})`}>{title}</div>
        {#each list as r}
          {@const done = 'done' in r && r.done}
          {@const soon = 'soon' in r && r.soon}
          <div class="rm">
            <span class="ck" style={done ? 'background: var(--g); border-color: var(--g)' : c && `border-color: var(--${c})`}></span>
            <span style={done ? 'color: var(--fgm); text-decoration: line-through' : ''}>{r.text}</span>
            <span class="id" style={c ? `color: var(--${c})` : soon ? 'color: var(--y)' : ''}>{r.when}</span>
          </div>
        {/each}
      {/each}
    {:else}
      <p class="dim pad">No reminders yet.</p>
    {/if}
  </section>

  <section class="pn" class:f={focus === 'q'}>
    <div class="ph">
      <span class="hk">q</span><a class="qa" href="#/questions">Questions</a><span class="n">{hub.questions.length} open</span>
    </div>
    {#each hub.questions.slice(0, 3) as q (q.project + '/' + q.step + q.text)}
      <a class="rm qr" href="#/questions"><span class="id">{q.step}</span><span class="qx">{q.text}</span></a>
    {:else}
      <p class="dim pad">No open questions.</p>
    {/each}
    {#if hub.questions.length > 3}<a class="dim pad more" href="#/questions">+{hub.questions.length - 3} more</a>{/if}
  </section>

  <section class="pn" class:f={focus === 'd'}>
    <div class="ph"><span class="hk">d</span>Deadlines<span class="n">next 7 days</span></div>
    {#each hub.deadlines as dl (dl.date + dl.text)}
      {@const n = late(dl.date)}
      <div class="dl" style={dl.overdue ? 'color: var(--r)' : ''}>
        <span class="id" style={dl.overdue ? 'color: var(--r)' : ''} title={dl.date}>{when(n)}</span>
        <span>{dl.text}{#each dl.tags as t}<span class="chip">{t}</span>{/each}</span>
        {#if dl.link}<a class="id" href="#/steps/{dl.link}">{dl.link}</a>{/if}
      </div>
    {:else}
      <p class="dim pad">Nothing due in the next 7 days.</p>
    {/each}
  </section>

  <section class="pn" class:f={focus === 'n'}>
    <div class="ph">
      <span class="hk">n</span>Now<span class="n">{hub.running} running · {hub.review} to review</span>
    </div>
    {#each groups as g}
      {@const list = hub.today[g.id].map((k) => steps[k]).filter(Boolean)}
      <div class="gr"><span class="s-{g.state}" style="color: var(--x)">{g.mark}</span>{g.title}</div>
      {#each list as s (s.project + '/' + s.step)}
        {@const k = `${s.project}/${s.step}`}
        {@const done = s.tasks.filter((t) => t.state === 'done').length}
        {@const cur = s.tasks.find((t) => t.state === 'doing') ?? s.tasks.find((t) => t.state === 'todo')}
        {@const extra = hub.demo?.steps[k]}
        <!-- svelte-ignore a11y_click_events_have_key_events -->
        <div class="cols lr" class:f={focus === 'n' && k === at} role="link" tabindex="0" onclick={() => open(k)} onfocus={() => (sel = k)}>
          <span class="dot s-{g.state}"></span>
          <span class="id">{s.step}</span>
          <span>{s.title}{#if g.id === 'running' && cur}<span class="s">now: <Inline text={cur.text} /></span>{/if}</span>
          {#if g.id === 'running'}
            <span class="id">{done}/{s.tasks.length} · {since(s.runs.at(-1)?.started)}</span>
          {:else if g.id === 'review'}
            {#if extra}<span class="chip {extra.check.ok ? 'x-g' : 'x-r'}">{extra.check.ok ? '✓' : '✗'} {extra.check.name}</span>{:else}<span class="id">{since(s.runs.at(-1)?.started)}</span>{/if}
          {:else}
            <span class="id">{s.project} · {s.by === 'me' ? 'me' : (s.model ?? '–')}</span>
          {/if}
        </div>
      {:else}
        <p class="dim pad">{g.empty}</p>
      {/each}
    {/each}
  </section>

  </div>

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
  .cols { display: grid; align-items: center; column-gap: 14px; padding: 0 16px; grid-template-columns: 14px 36px minmax(0, 1fr) auto auto; cursor: pointer; font-size: 14px; }
  .cols:hover { background: var(--lt); }
  .cols.f { background: var(--sel); }
  .side { display: flex; flex-direction: column; gap: 20px; min-height: 0; }
  .pr { display: grid; grid-template-columns: minmax(0, 1fr) 120px 48px auto auto 60px; align-items: center; column-gap: 14px; padding: 0 16px; height: 44px; border-bottom: 1px solid var(--sel); cursor: pointer; font-size: 14px; }
  .pr:hover { background: var(--lt); }
  .pr.f { background: var(--sel); box-shadow: inset 3px 0 0 var(--ac); }
  .nm { font-weight: 600; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .id { font: 12.5px var(--mono); color: var(--fg2); }
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
  .qa { color: inherit; text-decoration: none; }
  .qr { grid-template-columns: 36px minmax(0, 1fr); color: inherit; text-decoration: none; }
  .qr:hover { background: var(--lt); }
  .qx { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .more { display: block; font-size: 13px; }
  .dl { display: grid; grid-template-columns: 64px minmax(0, 1fr) auto; align-items: center; gap: 12px; padding: 0 16px; min-height: 44px; border-bottom: 1px solid var(--sel); font-size: 14px; }
  .dl .chip { margin-left: 8px; }
  .ck { width: 16px; height: 16px; border: 1.5px solid var(--mu); border-radius: 4px; }
</style>
