<script lang="ts">
  let { title, crumb = '' }: { title: string; crumb?: string } = $props()
</script>

<header class="hd">
  {#if crumb}<div class="bc">{crumb}</div>{/if}
  <h1>{title}</h1>
</header>
<p class="dim">Empty for now.</p>

<style>
  .hd { padding: 16px 20px 14px; }
  .bc { font-size: 12px; color: var(--fgd); }
  h1 { font-size: 22px; font-weight: 600; margin: 3px 0 0; letter-spacing: -0.01em; line-height: 1.2; }
  .dim { color: var(--fgd); padding: 0 20px; }
</style>
