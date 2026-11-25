# ADR 0004 — graphify: a code graph for chats and the Project page

Date: 2026-11-25 · Status: proposed

## Problem
Claude and Anis need to see how a project's code is connected: what calls what, what breaks if X changes, which
parts are the main ones. Today the only way is to open files one by one (Anis) or let Claude read them (tokens, and it
still misses links across files). The hub shows a project's steps, not its code.

## Options
All numbers below come from one real run on `~/Projects/tinyml-bearing-fault` (graphify 0.9.120, commit `0ea533d`,
run on a copy in the scratchpad so the project stays clean). The project has 50 tracked files, 33 of them code.

1. **grep / ripgrep only.** No new tool: `rg` is already installed.
   - Gives: every line that holds a name. `rg chronological_split` returns 28 lines in 12 `.py` files.
   - Costs: nothing to install or keep fresh. Claude reads the hits and decides, which costs tokens each time.
   - Misses: it cannot tell a call from an import, a definition or a comment. No "what breaks if X changes" beyond one
     hop, no communities, no main parts. Nothing to draw in the Graph tab.
2. **graphify, code only** (`graphify update <path>`: tree-sitter AST, no LLM).
   - Gives: a graph of symbols and edges (calls, imports, defines, inherits). tinyml: 33 files → **131 nodes, 350 edges,
     10 communities** in **1.5 s**, **0 input and 0 output tokens**. 95% of edges are `EXTRACTED` (read from the code),
     5% `INFERRED` (19 edges, average confidence 0.85). It also finds the god nodes, an import cycle and a
     `GRAPH_REPORT.md`. A query is local: `graphify affected "chronological_split()"` answered in 0.36 s with 22 nodes,
     each marked `calls` or `imports` with file and line.
   - Costs: a Python tool (`~/.local/bin/graphify`) outside our control; the output is 548 KB for tinyml
     (`graph.json` 115 KB, `graph.html` 143 KB, `GRAPH_REPORT.md` 4 KB); it must be re-run after code changes (cheap, it
     is free). Its `graph.json` is graphify's own format, so a new release can change it.
   - Misses: **`.ino` files** (3 in tinyml, the ESP32 firmware) are not in the graph, the report lists them as
     unclassified. 5 more code files gave no symbols (two `model_data.h` arrays, and `model.py`, `test_subset.py`,
     `esp32_echo_test.py`). Dynamic calls are guessed (`INFERRED`) or absent. It only knows what the AST shows.
3. **graphify with docs** (`graphify extract`, an LLM reads Markdown, PDFs, images).
   - Gives: everything in option 2 plus concepts and links from the documents (README, papers).
   - Costs: tokens on every document, and an API key for a backend (Gemini, Claude, OpenAI, Ollama, …). **Not measured:**
     I did not run it, because it would spend tokens and needs a key. tinyml has one `.md` file; the whole code corpus is
     about 19,500 words, which gives a rough size for a doc corpus but no price.
   - Misses: the same code gaps as option 2. The semantic edges are `INFERRED` and can be wrong.
4. **A language server or ctags.**
   - Gives: exact definitions and references for one language at a time (pyright, tsserver, rust-analyzer). ctags gives a
     symbol index only.
   - Costs: one server per language, each one to install and keep running, and a protocol client in hubd. Neither
     `ctags` nor `pyright` is installed on this laptop (checked with `which`), so there is no number to compare.
   - Misses: no whole-project picture. A server answers "who references this symbol", not "what are the main parts"
     or "which files form a cycle". The Graph tab would need a graph built on top. ctags has no edges at all.
     `.ino` is C++ and works with clangd only if set up by hand.
5. **Our own AST walk.**
   - Gives: exactly the edges we want, in our own format, with no third-party format to follow.
   - Costs: code and tests that we write and keep: Python's `ast` is in the standard library, but every other language
     needs its own parser (tree-sitter bindings or one walker per language). **Not built, not measured;** my estimate is
     a few hundred lines per language plus community detection and the report. That is a project in itself.
   - Misses: everything we do not write. `.ino` would still need work.

### Where the output lives and how it is wrapped
- graphify writes `graphify-out/` inside the folder it scans, and `graphify --help` shows no output-folder option for
  `update`. The hub must not leave that folder in a repo. The graph files live in the hub's own folder
  (next to `hub.toml`), one folder per project, and are never added to a project repo or to a git commit. How the run
  gets there (a throwaway copy, or a move after the run) is step 655.
- The graph is **opt-in per project** and **code only**, which keeps it free. Docs go in only when Anis asks in a chat.
- Rule 4: hubd talks to a `GraphSource` interface (build or refresh a graph, read nodes and edges, query, path,
  affected, report). `GraphifyGraph` is the one real class: it shells out to `graphify` and reads its `graph.json`.
  `FakeGraph` serves a small fixed graph, so the tests and `hubd --demo` run without graphify installed. A real sample
  (`tinyml-graph.json` and its report) becomes a test fixture in step 654, the same way a real hook input is in
  `tests/fixtures/hook/`. A graphify release that changes `graph.json` is then one edit in one module, and `hubd doctor`
  can show it as ✘.

### Rule 2 exception
0.5.0 adds a 5th new tool (graphify), against rule 2's max two. The other four are the phone tools: Syncthing with
Obsidian, and ntfy over Tailscale (ADRs 0002 and 0003, step 704). Sprint 6.5 (this ADR's feature) runs inside 0.5.0 and Sprint 7 pauses after 701.
TODO(Anis): why the exception is worth it.
