<script lang="ts">
  let { text, label = 'copy' }: { text: string; label?: string } = $props()
  let copied = $state(false)

  const copy = () =>
    navigator.clipboard.writeText(text).then(() => {
      copied = true
      setTimeout(() => (copied = false), 1200)
    })
</script>

<button class="cp" type="button" aria-label="Copy {label}" onclick={copy}>{copied ? 'copied' : 'copy'}</button>

<style>
  .cp {
    height: 20px; padding: 0 6px; border-radius: 4px; border: 1px solid var(--mu); background: var(--bg);
    font-size: 11px; color: var(--fgd); cursor: pointer; vertical-align: middle;
  }
  .cp:hover { background: var(--lt); color: var(--fg); }
</style>
