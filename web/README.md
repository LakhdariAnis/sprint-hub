# web

The sprint-hub UI: Svelte + Vite + TypeScript. hubd serves the built app at `/`.

## Build and run

```sh
cd web
npm install
npm run build        # writes web/dist
uv run hubd --demo   # then open http://127.0.0.1:8765/
```

## Develop

Start hubd (`uv run hubd --demo`), then `npm run dev` in `web/` and open http://localhost:5173/.
Vite reloads on save and sends API calls to hubd on port 8765.
