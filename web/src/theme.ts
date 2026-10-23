type Theme = { vars: Record<string, string>; mode: 'dark' | 'light' }

let applied: string[] = []

// Colours of the desktop theme over the theme.css defaults. A var the theme leaves out keeps its default,
// also when the previous theme set it.
export function applyTheme({ vars, mode }: Theme) {
  const root = document.documentElement
  for (const name of applied) root.style.removeProperty(name)
  for (const [name, value] of Object.entries(vars)) root.style.setProperty(name, value)
  applied = Object.keys(vars)
  root.style.colorScheme = mode
}

// At start: GET /theme. Later switches arrive as `theme` events on /events.
export async function loadTheme() {
  try {
    const r = await fetch('/theme')
    if (r.ok) applyTheme(await r.json())
  } catch {
    // hubd down: the theme.css defaults stay
  }
}
