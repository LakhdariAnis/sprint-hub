<script lang="ts">
  import { untrack } from 'svelte'
  import { graphStatusOf } from '../store.svelte'
  import { layout } from './layout'

  // A project's code graph: a canvas map (130+ nodes, so no SVG) and a Report tab.
  // `lit`: node ids to light (a chat's graph query, 659); `onask`: "Ask Claude about it" hands its text up.
  let { project, lit = null, onask }: { project: string; lit?: Set<string> | null; onask: (text: string) => void } = $props()

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

  // The map: view transform, size, theme (a switch rewrites the root's style attribute).
  let tf = $state({ x: 0, y: 0, k: 1 })
  let W = $state(0), H = $state(0), themed = $state(0)
  let canvas = $state<HTMLCanvasElement>()
  let stage = $state<HTMLDivElement>()
  let hover = $state<GNode | null>(null)
  // The top nodes carry a label at any zoom.
  const big = $derived(new Set(data ? data.nodes.filter(code).sort((a, b) => b.degree - a.degree).slice(0, 8) : []))
  const byId = $derived(new Map(data?.nodes.map((n) => [n.id, n])))

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
    ctx.strokeStyle = dim
    ctx.globalAlpha = 0.45
    ctx.lineWidth = 0.8 / Math.sqrt(tf.k)
    ctx.beginPath()
    for (const l of data.links) {
      const s = byId.get(l.source), t = byId.get(l.target)
      if (s && t) (ctx.moveTo(s.x, s.y), ctx.lineTo(t.x, t.y))
    }
    ctx.stroke()
    ctx.globalAlpha = 1
    for (const n of data.nodes) {
      ctx.fillStyle = color.get(tokenOf(n.group))!
      ctx.beginPath()
      ctx.arc(n.x, n.y, n.r, 0, 7)
      ctx.fill()
      if (n === hover) ((ctx.strokeStyle = fg), (ctx.lineWidth = 2 / tf.k), ctx.stroke())
    }
    ctx.font = `${11 / Math.sqrt(tf.k)}px ${mono}`
    ctx.textAlign = 'center'
    for (const n of data.nodes) {
      if (!(big.has(n) || n === hover || tf.k > 1.8)) continue
      ctx.fillStyle = big.has(n) || n === hover ? fg : fgm
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
  function up() {
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
    </div>
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
      <div class="zoom">
        <button aria-label="Zoom in" onclick={() => zoomAt(1.3)}>+</button>
        <button aria-label="Zoom out" onclick={() => zoomAt(1 / 1.3)}>−</button>
        <button aria-label="Fit" onclick={fit}>⤢</button>
      </div>
    </div>
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
  .zoom { position: absolute; right: 14px; top: 8px; display: flex; flex-direction: column; gap: 4px; }
  .zoom button { width: 30px; height: 30px; border-radius: 7px; border: 1px solid var(--sel); background: var(--dk); color: var(--fg2); cursor: pointer; }
  .zoom button:hover { color: var(--fg); }
</style>
