<script lang="ts">
  import { untrack } from 'svelte'
  import { SvelteSet } from 'svelte/reactivity'
  import { graphStatusOf } from '../store.svelte'
  import { layout } from './layout'

  // A project's code graph: a canvas map (130+ nodes, so no SVG) and a Report tab.
  // `lit`: node ids to light and the banner that says why (a chat's graph query or a chip, 659); `onclear`: Show all was pressed;
  // `onask`: "Ask Claude about it" hands its text up.
  let { project, lit = null, onclear, onask }: { project: string; lit?: { ids: Set<string>; note: string } | null; onclear?: () => void; onask: (text: string) => void } = $props()

  type GNode = { id: string; label: string; file: string; line: number | null; group: number | null; degree: number; x: number; y: number; r: number }
  type Data = { nodes: GNode[]; links: { source: string; target: string; relation: string }[]; groups: { id: number; name: string }[]; commit: string | null; stale: boolean }

  // Group colours: theme tokens in this order, the rest share one.
  const TOKENS = ['--m', '--b', '--y', '--o', '--c', '--g', '--r', '--ac']
  const tokenOf = (g: number | null) => (g === null ? '--mu' : (TOKENS[g] ?? '--fgm'))

  // Code inside a file: not a library (no file) nor the file itself. Only these grow with their links,
  // as in graphify's god nodes: numpy's 66 imports would dwarf the code.
  const code = (n: { label: string; file: string }) => !!n.file && n.label !== n.file.split('/').pop()

  let data = $state.raw<Data | null>(null)
  let error = $state<{ off: boolean; text: string } | null>(null)
  const status = $derived(graphStatusOf(project))

  async function load() {
    const r = await fetch(`/projects/${encodeURIComponent(project)}/graph`).catch(() => null)
    if (!r?.ok) {
      const detail = await r?.json().then((b) => b.detail as string).catch(() => '')
      error = { off: r?.status === 404, text: detail || (r ? `HTTP ${r.status}` : 'hubd is not running') }
      data = null
      return
    }
    const d: Data = await r.json()
    const ix = new Map(d.nodes.map((n, i) => [n.id, i]))
    const r_ = d.nodes.map((n) => (code(n) ? 3.5 + Math.sqrt(n.degree) * 1.9 : 4))
    const { at } = layout(r_, d.links.flatMap((l) => (ix.has(l.source) && ix.has(l.target) ? [[ix.get(l.source)!, ix.get(l.target)!] as [number, number]] : [])))
    d.nodes.forEach((n, i) => Object.assign(n, at[i], { r: r_[i] }))
    error = null
    data = d
    fit()
  }
  // Again when a build ends (the graph_built event updates the project's status).
  $effect(() => {
    void project, status?.state, status?.at
    if (status?.state !== 'building') untrack(load)
  })

  // The Report tab: read when first opened, again after a rebuild.
  type Brief = { id: string; label: string; file: string; degree: number; group: number | null }
  type Report = { god_nodes: Brief[]; cycles: string[][]; groups: { id: number; name: string; size: number; top: Brief[] }[]; unread: { count: number; top: string[] } }
  let tab = $state<'map' | 'report'>('map')
  let report = $state.raw<Report | string | null>(null)
  $effect(() => {
    void data
    report = null
  })
  $effect(() => {
    if (tab === 'report' && data && report === null) untrack(loadReport)
  })
  async function loadReport() {
    const r = await fetch(`/projects/${encodeURIComponent(project)}/graph/report`).catch(() => null)
    report = r?.ok ? await r.json() : `Could not read the report${r ? ` (HTTP ${r.status})` : ''}`
  }
  const rel = (f: string) => f.replace(/^src\//, '')

  // The map: view transform, size, theme (a switch rewrites the root's style attribute).
  let tf = $state({ x: 0, y: 0, k: 1 })
  let W = $state(0), H = $state(0), themed = $state(0)
  let canvas = $state<HTMLCanvasElement>()
  let stage = $state<HTMLDivElement>()
  let hover = $state<GNode | null>(null)
  // The top nodes carry a label at any zoom.
  const big = $derived(new Set(data ? data.nodes.filter(code).sort((a, b) => b.degree - a.degree).slice(0, 8) : []))
  const byId = $derived(new Map(data?.nodes.map((n) => [n.id, n])))
  const counts = $derived(data ? data.groups.map((g) => ({ ...g, n: data!.nodes.filter((n) => n.group === g.id).length })).filter((g) => g.n) : [])

  // What stands out: 659's `lit` until a search or "What depends on it" replaces it, "Show all" clears it.
  let bright = $derived(lit?.ids ?? null)
  let note = $derived(lit?.note ?? '')
  let q = $state('')
  const hidden = new SvelteSet<number>()
  let sel = $state<GNode | null>(null)
  const shows = (n: GNode) => n.group === null || !hidden.has(n.group)

  function search() {
    const t = q.trim().toLowerCase()
    bright = t ? new Set(data!.nodes.filter((n) => n.label.toLowerCase().includes(t) || n.file.toLowerCase().includes(t)).map((n) => n.id)) : null
    note = t ? `${bright!.size} match “${q.trim()}”` : ''
  }
  function showAll() {
    ;[bright, note, q] = [null, '', '']
    onclear?.()
  }
  const toggle = (g: number) => (hidden.has(g) ? hidden.delete(g) : hidden.add(g))

  // The card's counts leave out `contains`: a file holding its functions is not a dependency.
  const deps = $derived(data?.links.filter((l) => l.relation !== 'contains') ?? [])
  const into = $derived(sel ? deps.filter((l) => l.target === sel!.id).length : 0)
  const outOf = $derived(sel ? deps.filter((l) => l.source === sel!.id).length : 0)
  async function dependents(n: GNode) {
    const r = await fetch(`/projects/${encodeURIComponent(project)}/graph/affected?node=${encodeURIComponent(n.id)}`).catch(() => null)
    if (!r?.ok) return void (note = `Could not ask the graph${r ? ` (HTTP ${r.status})` : ''}`)
    const ids: string[] = (await r.json()).affected.map((a: { id: string }) => a.id)
    bright = new Set([n.id, ...ids])
    note = `${ids.length} nodes depend on ${n.label}`
  }

  $effect(() => {
    if (!stage) return
    const ro = new ResizeObserver(() => ((W = stage!.clientWidth), (H = stage!.clientHeight)))
    ro.observe(stage)
    const mo = new MutationObserver(() => themed++)
    mo.observe(document.documentElement, { attributes: true, attributeFilter: ['style'] })
    return () => (ro.disconnect(), mo.disconnect())
  })

  function fit() {
    if (!data?.nodes.length || !W || !H) return
    const xs = data.nodes.map((n) => n.x), ys = data.nodes.map((n) => n.y)
    const [x0, x1, y0, y1] = [Math.min(...xs), Math.max(...xs), Math.min(...ys), Math.max(...ys)]
    const k = Math.min(6, Math.max(0.3, Math.min(W / (x1 - x0 + 80), H / (y1 - y0 + 80))))
    tf = { k, x: -((x0 + x1) / 2) * k, y: -((y0 + y1) / 2) * k }
  }
  $effect(() => {
    if (W && H && data) untrack(fit) // first size of the pane
  })

  function zoomAt(f: number, mx = W / 2, my = H / 2) {
    const k = Math.min(6, Math.max(0.3, tf.k * f))
    const wx = (mx - W / 2 - tf.x) / tf.k, wy = (my - H / 2 - tf.y) / tf.k
    tf = { k, x: mx - W / 2 - wx * k, y: my - H / 2 - wy * k }
  }

  const css = (v: string) => getComputedStyle(document.documentElement).getPropertyValue(v).trim()

  $effect(() => {
    const ctx = canvas?.getContext('2d')
    if (!ctx || !data || !W) return
    void themed
    const dpr = devicePixelRatio || 1
    canvas!.width = W * dpr
    canvas!.height = H * dpr
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
    ctx.clearRect(0, 0, W, H)
    ctx.translate(W / 2 + tf.x, H / 2 + tf.y)
    ctx.scale(tf.k, tf.k)
    const color = new Map([...TOKENS, '--mu', '--fgm'].map((t) => [t, css(t)]))
    const [fg, fgm, dim, mono] = [css('--fg'), css('--fgm'), css('--fg3'), css('--mono')]
    const ac = css('--ac'), on = (n: GNode) => !bright || bright.has(n.id)
    // Dim links in one path, then the lit ones over them.
    for (const hot of [false, true]) {
      if (hot && !bright) break
      ctx.strokeStyle = hot ? ac : dim
      ctx.globalAlpha = hot ? 0.9 : bright ? 0.12 : 0.45
      ctx.lineWidth = (hot ? 1.6 : 0.8) / Math.sqrt(tf.k)
      ctx.beginPath()
      for (const l of data.links) {
        const s = byId.get(l.source), t = byId.get(l.target)
        if (s && t && shows(s) && shows(t) && (!hot || (on(s) && on(t)))) (ctx.moveTo(s.x, s.y), ctx.lineTo(t.x, t.y))
      }
      ctx.stroke()
    }
    for (const n of data.nodes) {
      if (!shows(n)) continue
      ctx.globalAlpha = on(n) ? 1 : 0.18
      ctx.fillStyle = color.get(tokenOf(n.group))!
      ctx.beginPath()
      ctx.arc(n.x, n.y, n.r, 0, 7)
      ctx.fill()
      if (n === hover || n === sel) ((ctx.strokeStyle = fg), (ctx.lineWidth = 2 / tf.k), ctx.stroke())
    }
    ctx.globalAlpha = 1
    ctx.font = `${11 / Math.sqrt(tf.k)}px ${mono}`
    ctx.textAlign = 'center'
    const few = bright && bright.size <= 40 // a few lit nodes all get a label
    for (const n of data.nodes) {
      const mark = n === hover || n === sel || (few && bright!.has(n.id))
      if (!shows(n) || !(mark || (big.has(n) && on(n)) || tf.k > 1.8)) continue
      ctx.fillStyle = mark || big.has(n) ? fg : fgm
      ctx.fillText(n.label, n.x, n.y - n.r - 4)
    }
    const top = [...big][0] // for e2e: where the most connected node sits on screen
    if (top) canvas!.dataset.topAt = `${Math.round(W / 2 + tf.x + top.x * tf.k)},${Math.round(H / 2 + tf.y + top.y * tf.k)}`
  })

  // The node under the pointer, if any.
  function at(e: MouseEvent) {
    const x = (e.offsetX - W / 2 - tf.x) / tf.k, y = (e.offsetY - H / 2 - tf.y) / tf.k
    let best: GNode | null = null, bd = 6 / tf.k
    for (const n of data?.nodes ?? []) {
      if (!shows(n)) continue
      const d = Math.hypot(n.x - x, n.y - y) - n.r
      if (d < bd) ((bd = d), (best = n))
    }
    return best
  }

  // Drag pans; a press that does not move is a click.
  let drag: { x: number; y: number; tx: number; ty: number; moved: boolean } | null = null
  function down(e: PointerEvent) {
    drag = { x: e.clientX, y: e.clientY, tx: tf.x, ty: tf.y, moved: false }
    canvas!.setPointerCapture(e.pointerId)
  }
  function move(e: PointerEvent) {
    if (!drag) return void (hover = at(e))
    const dx = e.clientX - drag.x, dy = e.clientY - drag.y
    if (Math.abs(dx) + Math.abs(dy) > 3) drag.moved = true
    if (drag.moved) tf = { ...tf, x: drag.tx + dx, y: drag.ty + dy }
  }
  function up(e: PointerEvent) {
    if (drag && !drag.moved) sel = at(e)
    drag = null
  }
  function wheel(e: WheelEvent) {
    e.preventDefault()
    zoomAt(Math.exp(-e.deltaY * 0.002), e.offsetX, e.offsetY)
  }
</script>

<section class="graph" aria-label="Code graph">
  {#if status?.state === 'building'}
    <p class="msg">Building the code graph…</p>
  {:else if error?.off}
    <p class="msg">Code graph is off · <kbd>G</kbd> turns it on</p>
  {:else if error}
    <p class="msg bad" role="alert">The code graph failed: {error.text}</p>
  {:else if data}
    <div class="gbar">
      <b>Code graph</b>
      <span class="stat">{data.nodes.length} nodes · {data.links.length} links · {data.groups.length} groups{#if data.commit}{" · "}commit {data.commit.slice(0, 7)}{/if}</span>
      {#if data.stale && data.commit}<span class="chip x-y" title="The repo moved on since this build">built from {data.commit.slice(0, 7)}</span>{/if}
      <span class="sp"></span>
      {#if tab === 'map'}<input class="find" placeholder="Find a function or file" aria-label="Find in graph" bind:value={q} oninput={search} />{/if}
      <div class="tabs" role="group" aria-label="Graph view">
        <button aria-pressed={tab === 'map'} onclick={() => (tab = 'map')}>Map</button>
        <button aria-pressed={tab === 'report'} onclick={() => (tab = 'report')}>Report</button>
      </div>
    </div>
    {#if tab === 'report'}
      <div class="report">
        {#if typeof report === 'string'}
          <p class="msg bad" role="alert">{report}</p>
        {:else if report}
          <h4>Most connected</h4>
          {@const most = Math.max(1, ...report.god_nodes.map((n) => n.degree))}
          <div class="gods">
            {#each report.god_nodes as n (n.id)}
              <code>{n.label}</code><span class="f">{rel(n.file)}</span>
              <span class="bar" style:width="{(n.degree / most) * 100}%" title="{n.degree} links"></span><span class="f">{n.degree}</span>
            {/each}
          </div>
          <h4>Import cycles</h4>
          {#each report.cycles as c, i (i)}
            <div class="warnc">{c.map(rel).join(' → ')}</div>
          {:else}
            <p class="none">No import cycle.</p>
          {/each}
          <h4>Groups</h4>
          <div class="groups">
            {#each report.groups as g (g.id)}
              <div class="grp">
                <b><span class="dot" style:--x="var({tokenOf(g.id)})"></span>{g.name} <span>· {g.size}</span></b>
                <span>{g.top.map((n) => n.label).join(', ')}</span>
              </div>
            {/each}
          </div>
          <h4>Not in the graph</h4>
          {#if report.unread.count}
            <p class="none">{report.unread.count} files graphify could not read{report.unread.top.length ? `: ${report.unread.top.join(', ')}` : ''}.</p>
          {:else}
            <p class="none">Every file was read.</p>
          {/if}
        {:else}
          <p class="msg">Reading the report…</p>
        {/if}
      </div>
    {:else}
      <div class="stage" bind:this={stage}>
        <canvas
          bind:this={canvas}
          style:width="{W}px"
          style:height="{H}px"
          aria-label="Code graph of {project}. Drag to pan, scroll to zoom, click a node."
          title={hover ? `${hover.label} · ${hover.file || 'library'}` : ''}
          onpointerdown={down}
          onpointermove={move}
          onpointerup={up}
          onpointerleave={() => (hover = null)}
          onwheel={wheel}
        ></canvas>
        {#if note}
          <div class="banner" role="status"><span>{note}</span><button onclick={showAll}>Show all</button></div>
        {/if}
        <div class="zoom">
          <button aria-label="Zoom in" onclick={() => zoomAt(1.3)}>+</button>
          <button aria-label="Zoom out" onclick={() => zoomAt(1 / 1.3)}>−</button>
          <button aria-label="Fit" onclick={fit}>⤢</button>
        </div>
        <!-- One row: when the pane is narrow the card wraps above the legend instead of covering it. -->
        <div class="over">
          <div class="legend" role="group" aria-label="Groups">
            {#each counts as g (g.id)}
              <button class:off={hidden.has(g.id)} aria-pressed={!hidden.has(g.id)} title="Show or hide this group" onclick={() => toggle(g.id)}>
                <span class="dot" style:--x="var({tokenOf(g.id)})"></span>{g.name} · {g.n}
              </button>
            {/each}
          </div>
          {#if sel}
            <div class="card" role="dialog" aria-label={sel.label}>
              <div class="ct">{sel.label}<button class="x" aria-label="Close" onclick={() => (sel = null)}>×</button></div>
              <div class="cf">{sel.file ? `${sel.file}${sel.line ? `:${sel.line}` : ''}` : 'library (outside the repo)'}</div>
              <div class="row">
                <span class="dot" style:--x="var({tokenOf(sel.group)})"></span>
                {data.groups.find((g) => g.id === sel!.group)?.name ?? 'no group'} · {into} in · {outOf} out
              </div>
              <div class="acts">
                <button onclick={() => dependents(sel!)}>What depends on it</button>
                <button onclick={() => onask(`Explain ${sel!.label} in ${sel!.file || 'the project'}${sel!.line ? `:${sel!.line}` : ''}`)}>Ask Claude about it</button>
              </div>
            </div>
          {/if}
        </div>
      </div>
    {/if}
  {:else}
    <p class="msg">Loading the code graph…</p>
  {/if}
</section>

<style>
  .graph { height: 100%; min-width: 0; min-height: 0; background: var(--dkr); display: flex; flex-direction: column; position: relative; }
  .msg { margin: auto; padding: 16px; color: var(--fgd); text-align: center; overflow-wrap: anywhere; }
  .msg.bad { color: var(--r); }
  .gbar { flex: none; display: flex; align-items: center; gap: 8px 12px; padding: 12px 18px; flex-wrap: wrap; }
  .gbar b { font-size: 15px; font-weight: 600; }
  .stat { font: 12px var(--mono); color: var(--fgm); }
  .stage { flex: 1; min-height: 0; position: relative; overflow: hidden; }
  canvas { position: absolute; inset: 0; display: block; cursor: grab; touch-action: none; }
  canvas:active { cursor: grabbing; }
  .sp { flex: 1; }
  .find { height: 30px; width: 200px; max-width: 100%; border: 1px solid var(--sel); border-radius: 7px; background: var(--dk); padding: 0 10px; font-size: 13px; outline: none; }
  .find:focus { border-color: var(--ac); }
  .banner { position: absolute; top: 8px; left: 18px; right: 60px; display: flex; gap: 10px; align-items: center; font-size: 13px; color: var(--fg2); pointer-events: none; }
  .banner span { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .banner button { pointer-events: auto; flex: none; border: 1px solid var(--sel); background: var(--dk); border-radius: 7px; padding: 3px 10px; font-size: 12.5px; color: var(--fg2); cursor: pointer; }
  .over { position: absolute; left: 14px; right: 14px; bottom: 14px; display: flex; flex-wrap: wrap-reverse; justify-content: space-between; align-items: flex-end; gap: 10px; pointer-events: none; }
  .over > * { pointer-events: auto; }
  .legend { display: flex; flex-direction: column; gap: 2px; max-height: 40vh; overflow-y: auto; font-size: 12px; color: var(--fg2); background: color-mix(in srgb, var(--dkr) 85%, transparent); padding: 8px 10px; border-radius: 10px; }
  .legend button { border: 0; background: none; padding: 1px 4px; display: flex; gap: 8px; align-items: center; border-radius: 5px; color: inherit; font-size: 12px; text-align: left; cursor: pointer; }
  .legend button:hover { background: var(--lt); color: var(--fg); }
  .legend button.off { opacity: 0.35; }
  .card { margin-left: auto; width: 290px; max-width: 100%; background: var(--lt); border: 1px solid var(--mu); border-radius: 12px; padding: 12px 14px; display: flex; flex-direction: column; gap: 6px; box-shadow: 0 10px 30px rgb(0 0 0 / 0.35); }
  .ct { font: 600 14px var(--mono); overflow-wrap: anywhere; display: flex; gap: 8px; align-items: start; }
  .ct .x { margin-left: auto; border: 0; background: none; color: var(--fg2); font-size: 16px; line-height: 1; padding: 0 2px; cursor: pointer; }
  .cf { font: 12px var(--mono); color: var(--fgm); overflow-wrap: anywhere; }
  .row { font-size: 12.5px; color: var(--fg2); display: flex; gap: 6px; align-items: center; }
  .acts { display: flex; gap: 6px; flex-wrap: wrap; margin-top: 4px; }
  .acts button { border: 0; border-radius: 7px; background: var(--sel); padding: 4px 10px; font-size: 12.5px; cursor: pointer; }
  .acts button:first-child { background: var(--ac); color: var(--bg); }
  .tabs { display: flex; gap: 2px; background: var(--dk); border-radius: 8px; padding: 2px; }
  .tabs button { border: 0; background: none; color: var(--fg2); border-radius: 6px; padding: 4px 12px; font-size: 13px; cursor: pointer; }
  .tabs button[aria-pressed='true'] { background: var(--sel); color: var(--fg); }
  .report { flex: 1; min-height: 0; overflow-y: auto; padding: 0 24px 24px; }
  .report h4 { font: 11px var(--mono); letter-spacing: 0.1em; color: var(--fgm); margin: 18px 0 8px; text-transform: uppercase; }
  .gods { display: grid; grid-template-columns: auto minmax(0, auto) minmax(40px, 1fr) auto; gap: 4px 12px; font-size: 13px; align-items: center; }
  .gods code { font: 13px var(--mono); overflow-wrap: anywhere; }
  .gods .f { color: var(--fgm); font: 12px var(--mono); overflow-wrap: anywhere; }
  .bar { height: 6px; border-radius: 3px; background: var(--y); }
  .warnc { background: color-mix(in srgb, var(--r) 10%, var(--dk)); border-radius: 10px; padding: 10px 12px; margin-bottom: 6px; font: 13px/1.6 var(--mono); overflow-wrap: anywhere; }
  .none { margin: 0; color: var(--fg2); font-size: 13.5px; }
  .groups { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 8px; }
  .grp { background: var(--dk); border-radius: 10px; padding: 10px 12px; display: flex; flex-direction: column; gap: 4px; font-size: 13px; min-width: 0; }
  .grp b { display: flex; gap: 8px; align-items: center; font-weight: 600; overflow-wrap: anywhere; }
  .grp span { color: var(--fgm); font-size: 12px; font-weight: 400; overflow-wrap: anywhere; }
  .zoom { position: absolute; right: 14px; top: 8px; display: flex; flex-direction: column; gap: 4px; }
  .zoom button { width: 30px; height: 30px; border-radius: 7px; border: 1px solid var(--sel); background: var(--dk); color: var(--fg2); cursor: pointer; }
  .zoom button:hover { color: var(--fg); }
</style>
