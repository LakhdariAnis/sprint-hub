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

## End-to-end test

One Playwright test runs the loop on `hubd --demo`: Today, start a step, wait for `done`, approve, check `approved`.
It starts hubd itself on port 8765, so stop any running hubd first.

```sh
cd web
npm install
npx playwright install chromium   # once
npm run build                     # the test uses web/dist
npm run e2e                       # add -- --headed to watch it in a browser
```

A failed run keeps its video and trace in `web/test-results/`.
