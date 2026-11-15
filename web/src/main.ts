import { mount } from 'svelte'
import App from './App.svelte'
import { askBeforeLeave } from './leave'
import { loadTheme } from './theme'

loadTheme()
askBeforeLeave()

const app = mount(App, {
  target: document.getElementById('app')!,
})

export default app
