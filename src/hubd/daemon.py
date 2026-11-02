"""The Hub: owns the index and the runner. Every change goes through it, one at a time."""

import asyncio
import subprocess
from collections.abc import Callable, Iterator
from contextlib import aclosing, contextmanager
from datetime import date, datetime, timedelta
from pathlib import Path
from uuid import uuid4

from watchfiles import awatch

from hubd import importer, init
from hubd.importer import git
from hubd.model import Deadline, Review, Run, State, Step, TaskState
from hubd.notify import Notifier
from hubd.runners.base import AgentRunner, RunEnded
from hubd.states import Actor, Event, InvalidTransition, transition
from hubd.vault import (
    FileError,
    StepEntry,
    _guard,
    _join,
    _load_project,
    _load_step,
    _write_atomic,
    load_deadlines,
    load_vault,
    parse_questions,
    parse_tasks,
    save_step,
    step_tasks,
    tick_task,
)


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
    questions = [q.model_dump() for q in entry.questions]
    return {
        "project": entry.project,
        **entry.step.model_dump(mode="json"),
        "tasks": tasks,
        "questions": questions,
    }


def spec_text(entry: StepEntry) -> str | None:
    """The repo spec of a step; None when it has none, or it was removed from the repo."""
    return entry.spec.read_text() if entry.spec and entry.spec.is_file() else None


class Hub:
    def __init__(
        self,
        vault: Path,
        runner: Callable[[RunEnded], AgentRunner],
        notifier: Notifier,
        projects: Path | None = None,
    ):
        self.vault = vault = vault.resolve()  # watchfiles reports absolute paths
        self.projects_file = projects.resolve() if projects else None  # `projects.toml`
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

    def repo_missing(self, project: str) -> bool:
        repo = self.repo(project)
        return repo is not None and not repo.is_dir()

    def _sprint_dirs(self) -> set[Path]:
        return {
            s for p in self.index.projects if (r := self.repo(p)) and (s := r / "sprint").is_dir()
        }

    def _watchable(self, _: object, path: str) -> bool:
        return path.endswith(".md") or Path(path) == self.projects_file  # `.md` skips `.tmp` too

    async def watch(self, stop: asyncio.Event) -> None:
        """Reload each changed file of the vault, the repos' `sprint/` and `projects.toml`.

        Runs until `stop`. When a project's `sprint/` appears or goes, watching restarts.
        """
        known = self._sprint_dirs()
        loaded = self.vault.is_dir()
        while not stop.is_set():
            if not loaded and self.vault.is_dir():
                # `hubd init` made the vault: read it. Nothing is imported, `hubd import` does that.
                async with self.lock:
                    self._reload_all()
                known, loaded = self._sprint_dirs(), True
            roots = self._roots(known)
            if not roots:  # nothing to watch yet: the vault is not there
                await asyncio.sleep(1)
                continue
            # The timeout also yields: a `sprint/` that appears has no event, this check finds it.
            watching = awatch(
                *roots,
                watch_filter=self._watchable,
                debounce=50,
                stop_event=stop,
                rust_timeout=1000,
                yield_on_timeout=True,
            )
            try:
                async with aclosing(watching):
                    async for changes in watching:
                        for path in sorted({p for _, p in changes}):
                            await self.reload(Path(path))
                        if (now := self._sprint_dirs()) != known:
                            await self._import_projects(now - known)
                            known = now
                            break
                        if (
                            self._roots(known) != roots
                        ):  # the vault or projects.toml's folder appeared
                            break
            except OSError:  # a watched folder vanished between the check and the watch
                known = self._sprint_dirs()
                await asyncio.sleep(1)

    def _roots(self, sprints: set[Path]) -> list[Path]:
        """The folders to watch that exist now; a missing vault is watched once it appears."""
        config = self.projects_file.parent if self.projects_file else None
        return [p for p in (self.vault, *sprints, config) if p and p.is_dir()]

    async def _import_projects(self, sprints: set[Path]) -> None:
        """Import the projects whose `sprint/` just appeared: its specs may be there already."""
        async with self.lock:
            for project, settings in self.index.projects.items():
                repo = self.repo(project)
                if repo and repo / "sprint" in sprints:
                    folder = self.vault / "projects" / project
                    await asyncio.to_thread(importer.import_project, folder, settings, repo)
            self._reload_all()

    async def reload(self, path: Path) -> None:
        """Bring one changed file into the index and tell subscribers what changed."""
        async with self.lock:
            parts = path.relative_to(self.vault).parts if path.is_relative_to(self.vault) else ()
            if len(parts) == 4 and parts[0] == "projects" and parts[2] == "steps":
                self._reload_step(parts[1], path)
            elif len(parts) == 3 and parts[0] == "projects" and parts[2] == "project.md":
                self._reload_all()
            elif parts == ("deadlines.md",):
                deadlines, errors = load_deadlines(path)
                kept = [e for e in self.index.errors if e.path != path]
                self.index.deadlines, self.index.errors = deadlines, kept + errors
                self.emit({"type": "reload"})
            elif path == self.projects_file:
                await self._sync_projects()
            elif project := self._spec_project(path):
                await self._reload_spec(project, path)
            else:
                self._reload_tasks(path)

    def _reload_all(self) -> None:
        # shortcut: the whole vault is read again; fine for a few projects.
        self.index = load_vault(self.vault)
        self.emit({"type": "reload"})

    async def _sync_projects(self) -> None:
        """`projects.toml` changed: a project the vault lacks gets its folder and its steps."""
        path = self.projects_file
        self.index.errors = [e for e in self.index.errors if e.path != path]
        try:
            wanted = await asyncio.to_thread(init.load_projects, path)
        except ValueError as exc:
            self.index.errors.append(FileError(path, None, str(exc)))
            self.emit({"type": "error", "path": str(path), "line": None, "message": str(exc)})
            return
        created = False
        for name, repo in wanted:
            folder = self.vault / "projects" / init.slug(name)
            if (folder / "project.md").exists() or not repo.is_dir():
                continue
            try:
                await asyncio.to_thread(init.create, folder, name, repo)
                project = _load_project(folder / "project.md")
                await asyncio.to_thread(importer.import_project, folder, project, repo)
            except (OSError, ValueError) as exc:
                self.index.errors.append(FileError(folder, None, str(exc)))
                continue
            created = True
        if created:
            self._reload_all()

    def _spec_project(self, path: Path) -> str | None:
        """The project whose repo has `path` as a `sprint/<id>-*.md` spec."""
        if not importer.step_id(path):
            return None
        return next(
            (p for p in self.index.projects if (r := self.repo(p)) and path.parent == r / "sprint"),
            None,
        )

    async def _reload_spec(self, project: str, path: Path) -> None:
        """A new spec makes its vault step; an existing vault step is left alone."""
        step_id = importer.step_id(path) or ""
        folder = self.vault / "projects" / project
        target = folder / "steps" / f"{step_id}.md"
        repo = self.repo(project)
        if path.exists() and not target.exists() and repo:
            args = (folder, self.index.projects[project], repo, path)
            await asyncio.to_thread(importer.import_project, *args)
            self._reload_step(project, target)
            return
        entry = next((e for e in self.index.steps if e.path == target), None)
        if entry is None:
            return
        spec = _join(project, entry.path, entry.step, repo).spec
        if spec != entry.spec:
            entry.spec = spec
            self.emit({"type": "step", **step_json(entry), "spec": spec_text(entry)})

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
        if old is None or old.step != step or old.tasks != entry.tasks:
            self.emit({"type": "step", **step_json(entry)})

    def _reload_tasks(self, path: Path) -> None:
        for entry in self.index.steps:
            repo = self.repo(entry.project)
            if repo is None:
                continue
            if path == repo / "sprint" / "questions" / f"{entry.step.step}.md":
                questions = parse_questions(path.read_text()) if path.exists() else []
                if questions != entry.questions:
                    entry.questions = questions
                    self.emit({"type": "tasks", **step_json(entry)})
            if entry.step.by == "me":
                continue  # a `by: me` checklist is in the step file, reloaded with it
            if path == repo / "sprint" / "progress" / f"{entry.step.step}.md":
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

    def deadlines(self, days: int, today: date | None = None) -> list[Deadline]:
        """Open deadlines up to `today + days`, overdue ones included, by date.

        A step's `due:` counts too, linked to the step, until the step is approved.
        """
        today = today or date.today()
        steps = [
            Deadline(date=e.step.due, text=e.step.title, link=f"{e.project}/{e.step.step}")
            for e in self.index.steps
            if e.step.due and e.step.state != State.approved
        ]
        end = today + timedelta(days=days)
        due = [d for d in [*self.index.deadlines, *steps] if not d.done and d.date <= end]
        return sorted(due, key=lambda d: (d.date, d.text))

    def command_model(self, entry: StepEntry) -> str | None:
        """The `model:` of the step's `.claude/commands/sprint-<id>.md`."""
        repo = self.repo(entry.project)
        return importer.model_of(repo, entry.step.step) if repo else None

    async def start(self, project: str, step_id: str) -> Step:
        async with self.lock:
            entry = self.entry(project, step_id)
            if entry.step.by == "me":
                raise InvalidTransition(f"step {step_id}: manual step, tick its tasks")
            settings = self.index.projects[project]
            repo = self.repo(project)
            if repo is None:
                raise InvalidTransition(f"project {project}: no repo to run in")
            if not repo.is_dir():
                raise InvalidTransition(f"project {project}: the repo {repo} does not exist")
            new = transition(entry.step, Event.start, Actor.daemon)
            # Changes requested: continue the last run's chat, the review comment is the prompt.
            last = new.runs[-1] if entry.step.state == State.changes and new.runs else None
            comment = new.review.comment if new.review else ""
            resume = last if last and comment else None
            if resume:
                model, session = resume.model, resume.session
            else:
                model = new.model or self.command_model(entry) or settings.model
                session = str(uuid4())
            running = next(
                (
                    e.step.step
                    for e in self.index.steps
                    if e.step.state == State.doing
                    and e.step.by == "claude"
                    and self.repo(e.project) == repo
                ),
                None,
            )
            if reason := self.runner.refusal(step_id, repo, resume is None, running):
                raise InvalidTransition(f"step {step_id}: {reason}")
            if not new.branch and entry.spec:
                new.branch = f"step/{entry.spec.stem}"
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

    async def tick(self, project: str, step_id: str, n: int) -> StepEntry:
        """Toggle task `n` of a `by: me` step; first tick -> doing, all done -> done."""
        async with self.lock:
            entry = self.entry(project, step_id)
            if entry.step.by != "me":
                raise InvalidTransition(f"step {step_id}: by: claude, its run ticks the tasks")
            tasks = step_tasks(entry.path)  # the file, not the index: it may be newer
            if not 0 <= n < len(tasks):
                raise NotFound(f"step {project}/{step_id}: no task {n}")
            done = [t.state == TaskState.done for t in tasks]
            done[n] = not done[n]
            new = entry.step
            if new.state != State.doing:
                new = transition(new, Event.tick, Actor.me)
            if all(done):
                new = transition(new, Event.all_ticked, Actor.me)
            before = entry.path.read_bytes()
            try:
                tick_task(entry.path, n)
                save_step(entry.path, new)
            except BaseException:
                _write_atomic(entry.path, before)  # half a tick: put the file back
                raise
            entry.step, entry.tasks = new, step_tasks(entry.path)
            entry.seen[tasks[n].text] = datetime.now()
            self.emit({"type": "step", **step_json(entry)})
            return entry

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
        """Merge the step branch into the project's base (locally, never pushed), then approve."""
        async with self.lock:
            entry = self.entry(project, step_id)
            new = transition(entry.step, Event.approve, Actor.me)
            repo, branch = self.repo(project), entry.step.branch
            if entry.step.by == "claude" and not branch:
                raise InvalidTransition(f"step {step_id}: no branch to merge, nothing was approved")
            if repo and branch:  # no repo, or a `by: me` step with no branch: nothing to merge
                if not repo.is_dir():
                    raise InvalidTransition(f"project {project}: the repo {repo} does not exist")
                try:
                    base = self.index.projects[project].base
                    await asyncio.to_thread(_merge, repo, base, branch)
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
        """`git diff --stat base...branch`; empty when the step has no repo or branch."""
        entry = self.entry(project, step_id)
        repo, branch = self.repo(project), entry.step.branch
        if not repo or not branch:
            return ""
        base = self.index.projects[project].base
        return await asyncio.to_thread(_git, repo, "diff", "--stat", f"{base}...{branch}")


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True)
    if result.returncode:
        raise InvalidTransition(f"git {' '.join(args)}: {(result.stderr or result.stdout).strip()}")
    return result.stdout.strip()


def _merge(repo: Path, base: str, branch: str) -> None:
    """`git merge --no-ff branch` into `base`, starting on `base` or on `branch`.

    Any other branch, or tracked changes: refuse. Conflict: abort.
    """
    for name in (base, branch):
        if not git(repo, "rev-parse", "--verify", "--quiet", f"refs/heads/{name}"):
            raise InvalidTransition(f"{repo}: branch '{name}' does not exist")
    head = _git(repo, "branch", "--show-current")
    if head not in (base, branch):
        where = f"on branch '{head}'" if head else "not on a branch"
        raise InvalidTransition(f"{repo}: {where}, not '{base}' or '{branch}'; switch first")
    # Untracked files are not changes; git itself refuses if one would be overwritten.
    if changed := _git(repo, "diff", "--name-only", "HEAD").splitlines():
        raise InvalidTransition(f"{repo}: uncommitted changes in {', '.join(changed)}")
    if head != base:
        _git(repo, "switch", "-q", base)
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
