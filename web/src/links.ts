// Answer chips (659): inline code that is exactly a node's label or a file's path names that node on the map.
export type Node = { id: string; label: string; file: string }
export type Link = { source: string; target: string }

const base = (f: string) => f.split('/').pop()

// A label names every node that has it; a path names its file node (the one labelled with the file's name), not each function in it.
export function matcher(nodes: Node[], links: Link[]) {
  const by = new Map<string, Set<string>>()
  const add = (k: string, id: string) => by.set(k, (by.get(k) ?? new Set()).add(id))
  for (const n of nodes) {
    add(n.label, n.id)
    if (n.file && n.label === base(n.file)) add(n.file, n.id)
  }
  return {
    // Node ids for a code span, case-sensitive, no trimming; none when it is not in the graph.
    ids: (code: string): string[] => [...(by.get(code) ?? [])],
    // The nodes and everything one link away, either direction.
    around(ids: string[]): Set<string> {
      const out = new Set(ids)
      for (const l of links) {
        if (ids.includes(l.source)) out.add(l.target)
        if (ids.includes(l.target)) out.add(l.source)
      }
      return out
    },
  }
}
