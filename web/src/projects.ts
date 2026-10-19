export type Row = { id: string; name: string; path: string; approved: number; total: number; running: number; review: number; todo: number }
export type FileError = { path: string; line: number | null; message: string }

// Counts come from each project's steps: /projects has none. running = doing, review = done, todo = todo + changes.
export async function loadProjects(): Promise<{ rows: Row[]; errors: FileError[] }> {
  const [projects, errors]: [{ id: string; name: string; repo: string | null }[], FileError[]] = await Promise.all([
    fetch('/projects').then((r) => r.json()),
    fetch('/errors').then((r) => r.json()),
  ])
  const rows = await Promise.all(
    projects.map(async (p) => {
      const steps: { state: string }[] = await fetch(`/projects/${encodeURIComponent(p.id)}/steps`).then((r) => r.json())
      const n = (...s: string[]) => steps.filter((x) => s.includes(x.state)).length
      return { id: p.id, name: p.name, path: p.repo ?? '', approved: n('approved'), total: steps.length, running: n('doing'), review: n('done'), todo: n('todo', 'changes') }
    }),
  )
  return { rows: rows.sort((a, b) => a.name.localeCompare(b.name)), errors }
}
