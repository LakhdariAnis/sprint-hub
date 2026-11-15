// Ctrl+W, Alt+F4 and the close button never reach the page in the `--app` window (bin/sprint-hub-app); `beforeunload` is the only hook.
// Chromium shows "Leave site?" only after a user gesture on the page, so the handler is set on the first key press or click.
const ask = (e: BeforeUnloadEvent) => e.preventDefault()

export function askBeforeLeave() {
  const arm = () => {
    addEventListener('beforeunload', ask)
    removeEventListener('keydown', arm, true)
    removeEventListener('pointerdown', arm, true)
  }
  addEventListener('keydown', arm, true)
  addEventListener('pointerdown', arm, true)
}
