import { mount } from 'svelte'
import App from './App.svelte'
import { askBeforeLeave } from './leave'
import { reportPresence } from './presence'
import { loadTheme } from './theme'

loadTheme()
askBeforeLeave()
reportPresence()

const app = mount(App, {
  target: document.getElementById('app')!,
})

export default app
