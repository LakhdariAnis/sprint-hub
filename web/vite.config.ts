import { svelte } from '@sveltejs/vite-plugin-svelte'
import { defineConfig } from 'vite'

// `npm run dev` serves the app on :5173 and sends API calls to hubd.
const hubd = 'http://127.0.0.1:8765'

export default defineConfig({
  plugins: [svelte()],
  server: {
    proxy: { '^/(health|projects|steps|today|errors|events|runs|theme)': hubd },
  },
})
