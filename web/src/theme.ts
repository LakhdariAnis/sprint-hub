// Colours of the desktop theme (GET /theme) over the theme.css defaults. A var hubd leaves out keeps its default.
export async function applyTheme() {
  try {
    const r = await fetch('/theme')
    if (!r.ok) return
    const { vars, mode }: { vars: Record<string, string>; mode: 'dark' | 'light' } = await r.json()
    const root = document.documentElement
    for (const [name, value] of Object.entries(vars)) root.style.setProperty(name, value)
    root.style.colorScheme = mode
  } catch {
    // hubd down: the theme.css defaults stay
  }
}
