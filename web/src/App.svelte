<script lang="ts">
  let live = $state<boolean | null>(null)

  fetch('/health')
    .then((r) => r.ok && r.json())
    .then((body) => (live = body?.ok === true))
    .catch(() => (live = false))
</script>

<main>
  <h1>sprint-hub</h1>
  <p>{live === null ? 'checking hubd…' : live ? 'hubd live' : 'hubd down'}</p>
</main>
