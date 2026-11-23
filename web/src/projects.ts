export type Row = { id: string; name: string; path: string; base: string; repoMissing: boolean; model: string; workspace: number | null; account: string; archived: boolean; approved: number; total: number; running: number; review: number; todo: number }
// `level: 'warning'`: the file still works, something in it was skipped (a sprint row).
export type FileError = { path: string; line: number | null; message: string; level?: 'warning' }

// Counts come from each project's steps: /projects has none. running = doing, review = done, todo = todo + changes.
export async function loadProjects(): Promise<Row[]> {
  const projects: { id: string; name: string; repo: string | null; base: string; model: string | null; workspace: number | null; account: string; archived: boolean; repo_missing: boolean }[] = await fetch('/projects').then((r) => r.json())
  const rows = await Promise.all(
    projects.map(async (p) => {
      const r = await fetch(`/projects/${encodeURIComponent(p.id)}/steps`)
      if (r.status === 404) return null // removed since the list was read
      const steps: { state: string }[] = await r.json()
      const n = (...s: string[]) => steps.filter((x) => s.includes(x.state)).length
      return { id: p.id, name: p.name, path: p.repo ?? '', base: p.base, repoMissing: p.repo_missing, model: p.model ?? '', workspace: p.workspace, account: p.account, archived: p.archived, approved: n('approved'), total: steps.length, running: n('doing'), review: n('done'), todo: n('todo', 'changes') }
    }),
  )
  return rows.filter((r) => r !== null).sort((a, b) => a.name.localeCompare(b.name))
}
