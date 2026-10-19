"""The Hub: owns the index and the runner. Every change goes through it, one at a time."""

import asyncio
import os
import subprocess
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from watchfiles import awatch

from hubd.model import Review, Run, State, Step
from hubd.notify import Notifier
from hubd.runners.base import AgentRunner, RunEnded
from hubd.states import Actor, Event, InvalidTransition, transition
from hubd.vault import (
    StepEntry,
    _guard,
    _join,
    _load_step,
    _write_atomic,
    load_vault,
    parse_tasks,
    save_step,
)

# shortcut: every repo merges into `main`; add a per-project setting when a repo needs another.
MAIN = "main"


class NotFound(Exception):
    pass


class MergeConflict(InvalidTransition):
    def __init__(self, reason: str, files: list[str]):
        super().__init__(reason)
        self.files = files


def step_json(entry: StepEntry) -> dict:
    """A step as clients see it: frontmatter, runs, review and checklist."""
    tasks = [
        {"text": t.text, "state": t.state.name}
        | ({"at": at.isoformat(timespec="seconds")} if (at := entry.seen.get(t.text)) else {})
        for t in entry.tasks
    ]
    return {"project": entry.project, **entry.step.model_dump(mode="json"), "tasks": tasks}


class Hub:
    def __init__(self, vault: Path, runner: Callable[[RunEnded], AgentRunner], notifier: Notifier):
        self.vault = vault = vault.resolve()  # watchfiles reports absolute paths
        self.index = load_vault(vault)
        self.queues: set[asyncio.Queue[dict]] = set()
        self.runner = runner(self.run_ended)
        self.notifier = notifier
        self.lock = asyncio.Lock()

    def emit(self, event: dict) -> None:
        for queue in self.queues:
            queue.put_nowait(event)

    @contextmanager
    def subscribe(self) -> Iterator[asyncio.Queue[dict]]:
        queue: asyncio.Queue[dict] = asyncio.Queue()
        self.queues.add(queue)
        try:
            yield queue
        finally:
            self.queues.discard(queue)

    def repo(self, project: str) -> Path | None:
        settings = self.index.projects.get(project)
        return self.vault / settings.repo if settings and settings.repo else None

    async def watch(self, stop: asyncio.Event) -> None:
        """Reload each changed `.md` file in the vault and in each repo's `sprint/` until `stop`."""
        # shortcut: repos are picked once at start; a project added later needs a hubd restart.
        repos = [r / "sprint" for p in self.index.projects if (r := self.repo(p))]
        paths = [self.vault, *(r for r in repos if r.is_dir())]
        async for changes in awatch(*paths, watch_filter=_is_md, debounce=50, stop_event=stop):
            for path in sorted({p for _, p in changes}):
                await self.reload(Path(path))

    async def reload(self, path: Path) -> None:
        """Bring one changed file into the index and tell subscribers what changed."""
        async with self.lock:
            parts = path.relative_to(self.vault).parts if path.is_relative_to(self.vault) else ()
            if len(parts) == 4 and parts[0] == "projects" and parts[2] == "steps":
                self._reload_step(parts[1], path)
            elif len(parts) == 3 and parts[0] == "projects" and parts[2] == "project.md":
                # shortcut: a project.md edit reloads the whole vault; fine for a few projects.
                self.index = load_vault(self.vault)
                self.emit({"type": "reload"})
            else:
                self._reload_tasks(path)

    def _reload_step(self, project: str, path: Path) -> None:
        old = next((e for e in self.index.steps if e.path == path), None)
        if old:
            self.index.steps.remove(old)
        self.index.errors = [e for e in self.index.errors if e.path != path]
        if not path.exists():
            if old:
                self.emit({"type": "removed", "project": project, "step": old.step.step})
            return
        step = _guard(self.index, path, _load_step)
        if step is None:
            error = self.index.errors[-1]
            line, message = error.line, error.message
            self.emit({"type": "error", "path": str(path), "line": line, "message": message})
            return
        entry = _join(project, path, step, self.repo(project))
        if old:
            entry.seen = old.seen
        self.index.steps.append(entry)
        self.index.steps.sort(key=lambda e: (e.project, e.path))
        if old is None or old.step != step:
            self.emit({"type": "step", **step_json(entry)})

    def _reload_tasks(self, path: Path) -> None:
        for entry in self.index.steps:
            repo = self.repo(entry.project)
            if repo and path == repo / "sprint" / "progress" / f"{entry.step.step}.md":
                tasks = parse_tasks(path.read_text()) if path.exists() else []
                if tasks != entry.tasks:
                    before, now = {t.text: t.state for t in entry.tasks}, datetime.now()
                    entry.seen = {
                        t.text: now if before.get(t.text) != t.state else entry.seen.get(t.text)
                        for t in tasks
                    }
                    entry.tasks = tasks
                    self.emit({"type": "tasks", **step_json(entry)})

    def entry(self, project: str, step_id: str) -> StepEntry:
        for entry in self.index.steps:
            if entry.project == project and entry.step.step == step_id:
                return entry
        raise NotFound(f"no step {project}/{step_id}")

    def blocked(self, entry: StepEntry) -> bool:
        """A step is blocked while a step it `needs` (same project) is not approved."""
        approved = {
            e.step.step
            for e in self.index.steps
            if e.project == entry.project and e.step.state == State.approved
        }
        return any(need not in approved for need in entry.step.needs)

    def today(self) -> dict[str, list[StepEntry]]:
        steps = self.index.steps
        ready = [
            e for e in steps if e.step.state in (State.todo, State.changes) and not self.blocked(e)
        ]
        ready.sort(key=lambda e: (e.step.due is None, e.step.due or "", e.project, e.step.step))
        return {
            "running": [e for e in steps if e.step.state == State.doing],
            "review": [e for e in steps if e.step.state == State.done],
            "next": ready,
        }

    async def start(self, project: str, step_id: str) -> Step:
        async with self.lock:
            entry = self.entry(project, step_id)
            if entry.step.by == "me":
                raise InvalidTransition(f"step {step_id}: by: me, hubd does not run it")
            settings = self.index.projects[project]
            repo = self.repo(project)
            if repo is None:
                raise InvalidTransition(f"project {project}: no repo to run in")
            new = transition(entry.step, Event.start, Actor.daemon)
            # Changes requested: continue the last run's chat, the review comment is the prompt.
            last = new.runs[-1] if entry.step.state == State.changes and new.runs else None
            comment = new.review.comment if new.review else ""
            resume = last if last and comment else None
            if resume:
                model, session = resume.model, resume.session
            else:
                model, session = new.model or settings.model, str(uuid4())
            started = datetime.now().replace(second=0, microsecond=0)  # the file keeps minutes
            new.runs = [*new.runs, Run(started=started, model=model, session=session)]
            before = entry.path.read_bytes()
            save_step(entry.path, new)
            old, entry.step = entry.step, new
            try:
                if resume:
                    await self.runner.resume(new, session, repo, comment)
                else:
                    await self.runner.start(new, session, model, repo, f"/sprint-{step_id}")
            except BaseException:
                _write_atomic(entry.path, before)  # no run started: the file says so too
                entry.step = old
                raise
            self.emit({"type": "step", **step_json(entry)})
            return new

    async def run_ended(self, session_id: str, step_id: str) -> Step:
        async with self.lock:
            entry = next(
                (e for e in self.index.steps if any(r.session == session_id for r in e.step.runs)),
                None,
            )
            if entry is None or entry.step.step != step_id:
                raise NotFound(f"no run {session_id} for step {step_id}")
            if entry.step.runs[-1].session != session_id:
                raise InvalidTransition(f"step {step_id}: {session_id} is not the latest run")
            new = transition(entry.step, Event.run_ended, Actor.daemon)
            save_step(entry.path, new)
            entry.step = new
            self.emit({"type": "step", **step_json(entry)})
            self.notifier.notify("Run ended", f"{entry.project} {step_id} {new.title}: review it")
            return new

    async def approve(self, project: str, step_id: str) -> Step:
        """Merge the step branch into main (locally, never pushed), then mark it approved."""
        async with self.lock:
            entry = self.entry(project, step_id)
            new = transition(entry.step, Event.approve, Actor.me)
            repo, branch = self.repo(project), entry.step.branch
            if repo and branch:  # no repo or no branch (a `by: me` step): nothing to merge
                try:
                    await asyncio.to_thread(_merge, repo, branch)
                except MergeConflict as exc:
                    self.notifier.notify(
                        "Merge conflict", f"{project} {step_id}: {', '.join(exc.files)}"
                    )
                    raise
            save_step(entry.path, new)
            entry.step = new
            self.emit({"type": "step", **step_json(entry)})
            return new

    async def request_changes(self, project: str, step_id: str, comment: str) -> Step:
        """Save the comment in `## Review`, state `changes`; the next start resumes the chat."""
        async with self.lock:
            entry = self.entry(project, step_id)
            new = transition(entry.step, Event.request_changes, Actor.me)
            new.review = Review(verdict="changes", comment=comment)
            save_step(entry.path, new)
            entry.step = new
            self.emit({"type": "step", **step_json(entry)})
            return new

    async def diffstat(self, project: str, step_id: str) -> str:
        """`git diff --stat main...branch`; empty when the step has no repo or branch."""
        entry = self.entry(project, step_id)
        repo, branch = self.repo(project), entry.step.branch
        if not repo or not branch:
            return ""
        return await asyncio.to_thread(_git, repo, "diff", "--stat", f"{MAIN}...{branch}")


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True)
    if result.returncode:
        raise InvalidTransition(f"git {' '.join(args)}: {(result.stderr or result.stdout).strip()}")
    return result.stdout.strip()


def _merge(repo: Path, branch: str) -> None:
    """`git merge --no-ff branch`; refuse a dirty repo or wrong branch, abort a conflict."""
    head = _git(repo, "branch", "--show-current")
    if head != MAIN:
        raise InvalidTransition(f"{repo}: on branch '{head}', not '{MAIN}'; switch to {MAIN} first")
    # Untracked files are not changes; git itself refuses if one would be overwritten.
    if _git(repo, "status", "--porcelain", "--untracked-files=no"):
        raise InvalidTransition(f"{repo}: uncommitted changes; commit or stash them first")
    try:
        _git(repo, "merge", "--no-ff", "--no-edit", branch)
    except InvalidTransition as exc:
        files = _git(repo, "diff", "--name-only", "--diff-filter=U").splitlines()
        if not files:
            raise  # not a conflict (e.g. no such branch): git's own message says why
        _git(repo, "merge", "--abort")
        raise MergeConflict(
            f"merge {branch}: conflict in {', '.join(files)}; merge aborted", files
        ) from exc


def _is_md(_: object, path: str) -> bool:
    return path.endswith(".md")  # also skips save_step's `.tmp` files


def vault_path() -> Path:
    return Path(os.environ.get("HUB_VAULT", Path.home() / "Hub"))
