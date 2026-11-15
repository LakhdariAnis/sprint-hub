<script lang="ts">
  import Markdown from './Markdown.svelte'

  let { text }: { text: string } = $props()
</script>

<Markdown {text} skipTitle />
