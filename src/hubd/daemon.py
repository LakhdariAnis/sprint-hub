"""The Hub: owns the index and the runner. Every change goes through it, one at a time."""

import asyncio
import subprocess
import time
from collections.abc import Callable, Iterator
from contextlib import aclosing, contextmanager, suppress
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from uuid import uuid4

from watchfiles import awatch

from hubd import close, focus, importer, init, weeks
from hubd.close import Closed
from hubd.context import Context, build, graph_block
from hubd.graph import Built, FakeGraph, GraphSource
from hubd.importer import git
from hubd.model import Deadline, Review, Run, State, Step, TaskState, one_line
from hubd.notify import Click, Notifier
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
    live_file,
    load_deadlines,
    load_vault,
    parse_questions,
    parse_tasks,
    planned_hours,
    save_account,
    save_archived,
    save_graph,
    save_sprint,
    save_step,
    save_time,
    save_workspace,
    step_tasks,
    tick_task,
    worktrees,
)
from hubd.weeks import Sprint, parse_sprints

COMMANDS = Path(".claude/commands")
WAIT_GAP = 30.0  # seconds between two "waits for you" popups of one session and kind


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
        "run_gone": entry.run_gone,
        "planned": entry.planned,
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
        graph: GraphSource | None = None,
    ):
        self.vault = vault = vault.resolve()  # watchfiles reports absolute paths
        self.projects_file = projects.resolve() if projects else None  # `projects.toml`
        self.index = load_vault(vault)
        self.queues: set[asyncio.Queue[dict]] = set()
        self.runner = runner(self.run_ended)
        self.notifier = notifier
        self.clock = time.monotonic  # tests move it
        self.waited: dict[tuple[str, str], float] = {}  # (session, kind) -> last popup
        self.lock = asyncio.Lock()
        self.graph = graph or FakeGraph()  # `hubd serve` passes GraphifyGraph
        self.graphs: dict[str, dict] = {}  # project -> its graph's status, for its page
        self.builds: dict[str, asyncio.Task[None]] = {}  # the one build running per project
        self.again: set[str] = set()  # projects asked for while their build ran
        for project, settings in self.index.projects.items():
            if settings.graph and (g := self.graph.load(project)):
                self.graphs[project] = {"state": "built", "nodes": len(g.nodes), "at": g.built_at}
        for entry in self.index.steps:  # a hook sent while hubd was down never arrived
            if entry.step.state == State.doing and entry.step.by == "claude":
                runs = entry.step.runs
                entry.run_gone = not (runs and self.runner.running(runs[-1].session))

    async def focus(self, project: str) -> int:
        """Switch the desktop to the project's workspace; returns its number."""
        if project not in self.index.projects:
            raise NotFound(f"no project {project}")
        if (workspace := self.index.projects[project].workspace) is None:
            raise NotFound(f"{project} has no workspace: set `workspace:` in its project.md")
        await self.runner.focus(workspace)
        return workspace

    async def set_workspace(self, project: str, workspace: int | None) -> None:
        """Write the project's Hyprland workspace (None = anywhere) to its project.md."""
        if project not in self.index.projects:
            raise NotFound(f"no project {project}")
        path = self.vault / "projects" / project / "project.md"
        async with self.lock:
            await asyncio.to_thread(save_workspace, path, workspace)
            self._reload_all()

    async def set_account(self, project: str, account: str) -> None:
        """Write the Claude login of the project's runs and chats to its project.md."""
        if project not in self.index.projects:
            raise NotFound(f"no project {project}")
        path = self.vault / "projects" / project / "project.md"
        async with self.lock:
            await asyncio.to_thread(save_account, path, account)
            self._reload_all()

    async def set_archived(self, project: str, archived: bool) -> None:
        """Archive or unarchive the project in its project.md."""
        if project not in self.index.projects:
            raise NotFound(f"no project {project}")
        path = self.vault / "projects" / project / "project.md"
        async with self.lock:
            await asyncio.to_thread(save_archived, path, archived)
            self._reload_all()

    async def set_graph(self, project: str, on: bool) -> None:
        """Turn the project's code graph on (a first build starts now) or off."""
        if project not in self.index.projects:
            raise NotFound(f"no project {project}")
        path = self.vault / "projects" / project / "project.md"
        async with self.lock:
            await asyncio.to_thread(save_graph, path, on)
            self._reload_all()
        self.rebuild(project)

    def rebuild(self, project: str) -> None:
        """Build the project's graph in the background if it has `graph: on`.

        One build per project at a time; asks while it runs queue one more, never more.
        """
        settings = self.index.projects.get(project)
        if not (settings and settings.graph):
            return
        if project in self.builds:
            self.again.add(project)
        else:
            self.builds[project] = asyncio.create_task(self._build(project))

    async def _build(self, project: str) -> None:
        try:
            while True:
                self.again.discard(project)
                self._graph_status(project, {"state": "building"})
                repo = self.repo(project)
                built = (
                    await asyncio.to_thread(self.graph.build, repo, project)
                    if repo
                    else Built(reason="no repo: set repo: in its project.md")
                )
                if built.reason:
                    self._graph_status(project, {"state": "failed", "reason": built.reason})
                else:
                    at = datetime.now(UTC).isoformat(timespec="seconds")
                    self._graph_status(project, {"state": "built", "nodes": built.nodes, "at": at})
                settings = self.index.projects.get(project)
                if project not in self.again or not (settings and settings.graph):
                    return
        finally:
            del self.builds[project]

    def _graph_status(self, project: str, status: dict) -> None:
        self.graphs[project] = status
        self.emit({"type": f"graph_{status['state']}", "project": project, **status})

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

    def _repo_dirs(self) -> set[Path]:
        """Every repo folder to watch: `sprint/` of each repo and worktree, each repo's commands."""
        repos = [r for p in self.index.projects if (r := self.repo(p))]
        trees = [t for r in repos for t in (r, *worktrees(r))]
        sprints = {s for t in trees if (s := t / "sprint").is_dir()}
        return sprints | {c for r in repos if (c := r / COMMANDS).is_dir()}

    def _watchable(self, _: object, path: str) -> bool:
        return path.endswith(".md") or Path(path) == self.projects_file  # `.md` skips `.tmp` too

    async def watch(self, stop: asyncio.Event) -> None:
        """Reload each changed file of the vault, the repos' `sprint/` and `projects.toml`.

        Runs until `stop`. When a repo's or worktree's `sprint/` appears or goes, watching restarts.
        """
        known = self._repo_dirs()
        loaded = self.vault.is_dir()
        fresh = True  # read at start, before any watch: what came since has no event
        while not stop.is_set():
            if not loaded and self.vault.is_dir():
                # `hubd init` made the vault: read it. Nothing is imported, `hubd import` does that.
                async with self.lock:
                    self._reload_all()
                known, loaded = self._repo_dirs(), True
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
                        if fresh:  # a file written while watching (re)started had no event
                            fresh = False
                            async with self.lock:
                                self._reload_all()
                        for path in sorted({p for _, p in changes}):
                            await self.reload(Path(path))
                        if (now := self._repo_dirs()) != known:
                            await self._import_projects(now - known)
                            known = now
                            break
                        if (
                            self._roots(known) != roots
                        ):  # the vault or projects.toml's folder appeared
                            break
            except OSError:  # a watched folder vanished between the check and the watch
                known = self._repo_dirs()
                await asyncio.sleep(1)
            fresh = True

    def _roots(self, sprints: set[Path]) -> list[Path]:
        """The folders to watch that exist now; a missing vault is watched once it appears."""
        config = self.projects_file.parent if self.projects_file else None
        return [p for p in (self.vault, *sprints, config) if p and p.is_dir()]

    async def _import_projects(self, sprints: set[Path]) -> None:
        """Import the projects whose `sprint/` just appeared: its specs may be there already.

        Always reads the vault again: a worktree's `sprint/` has no specs but may hold a checklist.
        """
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
            elif path.parent.parts[-2:] == COMMANDS.parts:
                self._reload_command(path)
            elif self._readme_project(path):
                self.emit({"type": "sprints"})
            elif project := self._spec_project(path):
                await self._reload_spec(project, path)
            else:
                self._reload_tasks(path)

    def _reload_all(self) -> None:
        # shortcut: the whole vault is read again; fine for a few projects.
        old = {e.path: e for e in self.index.steps}
        self.index = load_vault(self.vault)
        for entry in self.index.steps:
            if was := old.get(entry.path):
                entry.seen, entry.run_gone = was.seen, was.run_gone
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

    def _readme_project(self, path: Path) -> str | None:
        """The project whose repo has `path` as its `sprint/README.md`."""
        return next(
            (
                p
                for p in self.index.projects
                if (r := self.repo(p)) and path == r / "sprint/README.md"
            ),
            None,
        )

    def sprint_tables(self) -> tuple[dict[str, list[Sprint]], list[FileError]]:
        """The sprint table of each project, read now; what a file got wrong comes back as errors.

        Read per request, not kept: a few small files, and the answer is never stale.
        """
        tables: dict[str, list[Sprint]] = {}
        problems: list[FileError] = []
        for project in self.index.projects:
            repo = self.repo(project)
            path = repo / "sprint/README.md" if repo else None
            if path is None or not path.is_file():
                continue  # a project without sprints has nothing to say
            try:
                tables[project], found = parse_sprints(project, path.read_text())
            except (OSError, ValueError) as exc:
                problems.append(FileError(path, None, f"cannot read the sprint table: {exc}"))
                continue
            problems += [FileError(path, line, message) for line, message in found]
        return tables, problems

    def week(self, today: date | None = None) -> dict:
        tables, _ = self.sprint_tables()
        names = {k: p.name for k, p in self.index.projects.items()}
        return weeks.week_view(tables, self.index.steps, names, today or date.today())

    def eta(self, project: str, today: date | None = None) -> dict:
        if project not in self.index.projects:
            raise NotFound(f"no project {project}")
        tables, _ = self.sprint_tables()
        return weeks.eta(project, tables, self.index.steps, today or date.today())

    async def close_sprint(
        self, project: str, number: int, own_hours: float | None = None, write: bool = False
    ) -> Closed:
        """Flow E of the `new-sprint` skill; `write=False` is the preview and changes nothing."""
        async with self.lock:
            repo = self.repo(project)
            if project not in self.index.projects or repo is None:
                raise NotFound(f"no project {project} with a repo")
            tables, _ = self.sprint_tables()
            steps = self.index.steps
            closed = await asyncio.to_thread(
                close.plan, repo, project, number, own_hours, steps, tables
            )
            if not write:
                return closed
            await asyncio.to_thread(close.write, repo, closed, date.today())
            for entry in steps:
                if entry.project == project and entry.step.step in closed.moved:
                    save_sprint(entry.path, closed.next)
                    entry.step.sprint = closed.next
                    self.emit({"type": "step", **step_json(entry)})
            return closed

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
        broken = any(e.path == path for e in self.index.errors)
        self.index.errors = [e for e in self.index.errors if e.path != path]
        if not path.exists():
            if old:
                self.emit({"type": "removed", "project": project, "step": old.step.step})
            elif broken:  # a broken file deleted: its error leaves the list
                self.emit({"type": "error", "path": str(path), "removed": True})
            return
        step = _guard(self.index, path, _load_step)
        if step is None:
            error = self.index.errors[-1]
            line, message = error.line, error.message
            self.emit({"type": "error", "path": str(path), "line": line, "message": message})
            return
        entry = _join(project, path, step, self.repo(project))
        if old:
            entry.seen, entry.run_gone = old.seen, old.run_gone
        self.index.steps.append(entry)
        self.index.steps.sort(key=lambda e: (e.project, e.path))
        if old is None or old.step != step or old.tasks != entry.tasks:
            self.emit({"type": "step", **step_json(entry)})

    def _reload_command(self, path: Path) -> None:
        """A command file changed: its step's planned hours may have."""
        for entry in self.index.steps:
            repo = self.repo(entry.project)
            if repo and path == repo / COMMANDS / f"sprint-{entry.step.step}.md":
                planned = planned_hours(repo, entry.step.step)
                if planned != entry.planned:
                    entry.planned = planned
                    self.emit({"type": "step", **step_json(entry)})

    def _reload_tasks(self, path: Path) -> None:
        for entry in self.index.steps:
            repo = self.repo(entry.project)
            if repo is None or path.name != f"{entry.step.step}.md":
                continue
            trees = (repo, *worktrees(repo))
            if path.parent in [t / "sprint" / "questions" for t in trees]:
                file = live_file(repo, "questions", entry.step.step)
                questions = parse_questions(file.read_text()) if file else []
                if questions != entry.questions:
                    entry.questions = questions
                    self.emit({"type": "tasks", **step_json(entry)})
            if entry.step.by == "me":
                continue  # a `by: me` checklist is in the step file, reloaded with it
            if path.parent in [t / "sprint" / "progress" for t in trees]:
                file = live_file(repo, "progress", entry.step.step)
                tasks = parse_tasks(file.read_text()) if file else []
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

    async def start(self, project: str, step_id: str, fresh: bool = False) -> Step:
        """Start a run. From `changes` it resumes the last chat; `fresh` opens a new one."""
        async with self.lock:
            entry = self.entry(project, step_id)
            if entry.step.by == "me":
                raise InvalidTransition(f"step {step_id}: manual step, tick its tasks")
            settings = self.index.projects[project]
            repo = self._run_repo(project)
            new = transition(entry.step, Event.start, Actor.daemon)
            # Changes requested: continue the last run's chat, the review comment is the prompt.
            changes = entry.step.state == State.changes
            if fresh and not changes:
                raise InvalidTransition(f"step {step_id}: a new chat is for a step in changes")
            last = new.runs[-1] if changes and new.runs else None
            comment = new.review.comment if changes and new.review else ""
            resume = last if last and comment and not fresh else None
            if resume:
                model, session = resume.model, resume.session
            else:
                model = new.model or self.command_model(entry) or settings.model
                session = str(uuid4())
            running = self._running_in(repo, step_id)
            if reason := self.runner.refusal(
                step_id, repo, resume is None, running, self.index.projects[project].account
            ):
                raise InvalidTransition(f"step {step_id}: {reason}")
            if not new.branch and entry.spec:
                new.branch = f"step/{entry.spec.stem}"
            started = datetime.now().replace(second=0, microsecond=0)  # the file keeps minutes
            new.runs = [*new.runs, Run(started=started, model=model, session=session)]
            before = entry.path.read_bytes()
            save_step(entry.path, new)
            old, entry.step = entry.step, new
            entry.run_gone = False
            workspace = self.index.projects[project].workspace
            account = self.index.projects[project].account
            try:
                if resume:
                    await self.runner.resume(new, session, repo, comment, workspace, account)
                else:
                    # The command file gets the comment as its arguments (`ARGUMENTS: ...`).
                    prompt = f"/sprint-{step_id} Changes requested on the earlier run: {comment}"
                    await self.runner.start(
                        new,
                        session,
                        model,
                        repo,
                        prompt if comment else f"/sprint-{step_id}",
                        workspace,
                        account,
                    )
            except BaseException:
                _write_atomic(entry.path, before)  # no run started: the file says so too
                entry.step = old
                raise
            self.emit({"type": "step", **step_json(entry)})
            return new

    def _run_repo(self, project: str) -> Path:
        repo = self.repo(project)
        if repo is None:
            raise InvalidTransition(f"project {project}: no repo to run in")
        if not repo.is_dir():
            raise InvalidTransition(f"project {project}: the repo {repo} does not exist")
        return repo

    def _running_in(self, repo: Path, step_id: str) -> str | None:
        """Another `by: claude` step `doing` in this repo, if any."""
        return next(
            (
                e.step.step
                for e in self.index.steps
                if e.step.state == State.doing
                and e.step.by == "claude"
                and e.step.step != step_id
                and self.repo(e.project) == repo
            ),
            None,
        )

    async def reopen(self, project: str, step_id: str) -> Step:
        """Open the last run's chat again after its terminal closed: `done` -> `doing`.

        A `doing` step whose run is gone reopens too and stays `doing`. Each open is its own run
        line with the same session, so `run_ended` and `finish` match it and its minutes count.
        """
        async with self.lock:
            entry = self.entry(project, step_id)
            if entry.step.by == "me":
                raise InvalidTransition(f"step {step_id}: manual step, tick its tasks")
            if not entry.step.runs:
                raise InvalidTransition(f"step {step_id}: no run yet, nothing to reopen")
            last = entry.step.runs[-1]
            if self.runner.running(last.session):
                raise InvalidTransition(f"step {step_id}: the chat is still open")
            gone = entry.step.state == State.doing and entry.run_gone
            new = (
                entry.step.model_copy()
                if gone
                else transition(entry.step, Event.reopen, Actor.daemon)
            )
            repo = self._run_repo(project)
            running = self._running_in(repo, step_id)
            if reason := self.runner.refusal(
                step_id, repo, False, running, self.index.projects[project].account
            ):
                raise InvalidTransition(f"step {step_id}: {reason}")
            started = datetime.now().replace(second=0, microsecond=0)
            new.runs = [*new.runs, Run(started=started, model=last.model, session=last.session)]
            before = entry.path.read_bytes()
            save_step(entry.path, new)
            old, entry.step = entry.step, new
            entry.run_gone = False
            try:
                await self.runner.resume(
                    new,
                    last.session,
                    repo,
                    "",
                    self.index.projects[project].workspace,
                    self.index.projects[project].account,
                )
            except BaseException:
                _write_atomic(entry.path, before)  # no terminal: the file says so too
                entry.step, entry.run_gone = old, gone
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

    def _run_entry(self, session_id: str, step_id: str) -> StepEntry:
        entry = next(
            (e for e in self.index.steps if any(r.session == session_id for r in e.step.runs)),
            None,
        )
        if entry is None or entry.step.step != step_id:
            raise NotFound(f"no run {session_id} for step {step_id}")
        return entry

    def run_waiting(self, session_id: str, step_id: str, kind: str, notify: bool = True) -> bool:
        """Claude ended its turn or wants Anis (`hubd.hook`): a popup, no state change.

        At most one per session and kind every `WAIT_GAP` s. True = a popup was sent.
        """
        entry = self._run_entry(session_id, step_id)
        if not notify or entry.step.state != State.doing:
            return False  # off in Settings, or a late hook after the run ended
        where = f"{entry.project} {step_id}"
        title, body = {
            "turn": ("Claude answered", f"{where} {entry.step.title}"),
            "permission": ("Claude needs permission", where),
            "idle": ("Claude waits for you", where),
        }[kind]
        project = entry.project
        workspace = self.index.projects[project].workspace
        return self.popup(
            (session_id, kind),
            title,
            body,
            lambda: focus.open_run(session_id, project, step_id, workspace),
        )

    def popup(self, key: tuple[str, str], title: str, body: str, on_click: Click) -> bool:
        """A "waits for you" popup, at most one per `key` (session or chat, kind) per `WAIT_GAP`."""
        now = self.clock()
        if now - self.waited.get(key, -WAIT_GAP) < WAIT_GAP:
            return False
        self.waited[key] = now
        self.notifier.notify(title, body, on_click)
        return True

    async def run_ended(self, session_id: str, step_id: str) -> Step:
        async with self.lock:
            entry = self._run_entry(session_id, step_id)
            if entry.step.runs[-1].session != session_id:
                raise InvalidTransition(f"step {step_id}: {session_id} is not the latest run")
            if entry.step.state != State.doing:
                return entry.step  # a late hook: `f` already ended this run
            new = self._end_run(entry)
            self.notifier.notify(
                "Run ended",
                f"{entry.project} {step_id} {new.title}: review it, or o reopens the chat",
            )
            return new

    async def finish(self, project: str, step_id: str) -> Step:
        """End a run from the app, for a run whose hook never arrived. Same move as the hook."""
        async with self.lock:
            entry = self.entry(project, step_id)
            if entry.step.by == "me":
                raise InvalidTransition(f"step {step_id}: manual step, tick its tasks")
            runs = entry.step.runs
            # A session already gone ended at some unknown time: no end, the run counts 0.
            return self._end_run(entry, bool(runs) and self.runner.running(runs[-1].session))

    def _end_run(self, entry: StepEntry, ended_now: bool = True) -> Step:
        new = transition(entry.step, Event.run_ended, Actor.daemon)
        if ended_now and new.runs and new.runs[-1].minutes is None:
            last = new.runs[-1]
            minutes = max((datetime.now() - last.started) // timedelta(minutes=1), 0)
            new.runs = [*new.runs[:-1], last.model_copy(update={"minutes": minutes})]
        save_step(entry.path, new)
        entry.step = new
        self.emit({"type": "step", **step_json(entry)})
        self.rebuild(entry.project)
        return new

    async def approve(
        self, project: str, step_id: str, own_hours: float | None = None
    ) -> tuple[Step, str | None]:
        """Merge the step branch into the project's base (locally, never pushed), then approve.

        Returns the step and the commit `base` is on now; None when nothing was merged.
        """
        async with self.lock:
            entry = self.entry(project, step_id)
            new = transition(entry.step, Event.approve, Actor.me)
            new.own_hours = own_hours
            repo, branch, commit = self.repo(project), entry.step.branch, None
            if entry.step.by == "claude" and not branch:
                raise InvalidTransition(f"step {step_id}: no branch to merge, nothing was approved")
            if repo and branch:  # no repo, or a `by: me` step with no branch: nothing to merge
                if not repo.is_dir():
                    raise InvalidTransition(f"project {project}: the repo {repo} does not exist")
                try:
                    base = self.index.projects[project].base
                    commit = await asyncio.to_thread(_merge, repo, base, branch)
                except MergeConflict as exc:
                    self.notifier.notify(
                        "Merge conflict", f"{project} {step_id}: {', '.join(exc.files)}"
                    )
                    raise
            save_step(entry.path, new)
            entry.step = new
            self.emit({"type": "step", **step_json(entry)})
            if commit:
                self.rebuild(project)
            if repo:
                await asyncio.to_thread(self._write_time, project, repo, new, commit)
            return new, commit

    def _write_time(self, project: str, repo: Path, step: Step, commit: str | None) -> None:
        """The one repo file hubd writes. The merge is done: a failure only warns."""
        if not (repo / "sprint").is_dir():
            return
        reason = None
        # A tracked PROGRESS.md left changed would make the next approve refuse to merge.
        if git(repo, "ls-files", "sprint/PROGRESS.md"):
            reason = "sprint/PROGRESS.md is tracked by git, add the line by hand"
        else:
            base = self.index.projects[project].base
            merged = f"Merged into `{base}` in `{commit}`." if commit else None
            try:
                save_time(repo / "sprint/PROGRESS.md", step, merged, date.today())
            except (OSError, ValueError) as exc:
                reason = str(exc)
        if reason:
            self.notifier.notify("Time not written", f"{project} {step.step}: {reason}")

    async def request_changes(self, project: str, step_id: str, comment: str) -> Step:
        """Save the comment in `## Review`, state `changes`; the next start resumes the chat."""
        async with self.lock:
            entry = self.entry(project, step_id)
            new = transition(entry.step, Event.request_changes, Actor.me)
            if not (comment := one_line(comment)):
                raise InvalidTransition(f"step {step_id}: write what should change first")
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

    async def context(self, project: str, sprint: int | None, step_id: str | None) -> Context:
        """What a chat about the project (and its sprint or step) is told; the repo must exist."""
        repo = self.repo(project)
        if project not in self.index.projects or repo is None:
            raise NotFound(f"no project {project} with a repo")
        spec = diff = None
        if step_id:
            spec = spec_text(self.entry(project, step_id))
            with suppress(InvalidTransition):  # a branch gone or never made: a note says so
                diff = await self.diffstat(project, step_id)
        settings = self.index.projects[project]
        return await asyncio.to_thread(
            lambda: build(repo, settings.name, sprint, step_id, spec, diff, self._graph(project))
        )

    def _graph(self, project: str) -> str | None:
        """The context's code graph part: only with `graph: on` and a graph built."""
        settings = self.index.projects[project]
        if not settings.graph or (path := self.graph.where(project)) is None:
            return None
        if (graph := self.graph.load(project)) is None:
            return None
        project_md = self.vault / "projects" / project / "project.md"
        return graph_block(path, graph, settings.graph_docs, project_md)


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True)
    if result.returncode:
        raise InvalidTransition(f"git {' '.join(args)}: {(result.stderr or result.stdout).strip()}")
    return result.stdout.strip()


def _merge(repo: Path, base: str, branch: str) -> str:
    """`git merge --no-ff branch` into `base`, locally.

    On `base`: a normal merge, refused with tracked changes; a failed one puts the repo back.
    Anywhere else: the merge commit is made without touching the working tree or HEAD.
    """
    for name in (base, branch):
        if not git(repo, "rev-parse", "--verify", "--quiet", f"refs/heads/{name}"):
            raise InvalidTransition(f"{repo}: branch '{name}' does not exist")
    if _git(repo, "branch", "--show-current") != base:
        return _merge_in_memory(repo, base, branch)
    # Untracked files are not changes; git itself refuses if one would be overwritten.
    if changed := _git(repo, "diff", "--name-only", "HEAD").splitlines():
        raise InvalidTransition(f"{repo}: uncommitted changes in {', '.join(changed)}")
    try:
        _git(repo, "merge", "--no-ff", "--no-edit", branch)
    except InvalidTransition as exc:
        files = _git(repo, "diff", "--name-only", "--diff-filter=U").splitlines()
        # A hook or a missing git identity also stops a merge halfway, with no conflict.
        if git(repo, "rev-parse", "--verify", "--quiet", "MERGE_HEAD"):
            _git(repo, "merge", "--abort")
        if not files:
            raise  # not a conflict: git's own message says why
        raise MergeConflict(
            f"merge {branch}: conflict in {', '.join(files)}; merge aborted", files
        ) from exc
    return _git(repo, "rev-parse", "--short", "HEAD")


def _merge_in_memory(repo: Path, base: str, branch: str) -> str:
    """`base` is not checked out here: merge-tree + commit-tree, then move `base` only.

    No hooks run, as with any commit made without a working tree.
    """
    worktrees = _git(repo, "worktree", "list", "--porcelain").splitlines()
    if f"branch refs/heads/{base}" in worktrees:
        raise InvalidTransition(f"{repo}: '{base}' is checked out in another worktree; merge there")
    old = _git(repo, "rev-parse", f"refs/heads/{base}")
    result = subprocess.run(
        ["git", "merge-tree", "--write-tree", "--name-only", "--no-messages", base, branch],
        cwd=repo,
        capture_output=True,
        text=True,
    )
    lines = result.stdout.splitlines()
    if result.returncode == 1:
        files = list(dict.fromkeys(f for f in lines[1:] if f))
        raise MergeConflict(
            f"merge {branch}: conflict in {', '.join(files)}; nothing merged", files
        )
    if result.returncode:
        raise InvalidTransition(f"git merge-tree: {(result.stderr or result.stdout).strip()}")
    into = "" if base in ("main", "master") else f" into {base}"
    message = f"Merge branch '{branch}'{into}"
    commit = _git(repo, "commit-tree", lines[0], "-p", old, "-p", branch, "-m", message)
    _git(repo, "update-ref", "-m", f"merge {branch}", f"refs/heads/{base}", commit, old)
    return commit[:7]
