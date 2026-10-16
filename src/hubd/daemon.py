"""The Hub: owns the index and the runner. Every change goes through it, one at a time."""

import asyncio
import os
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from hubd.model import Run, Step
from hubd.notify import Notifier
from hubd.runners.base import AgentRunner, RunEnded
from hubd.states import Actor, Event, InvalidTransition, transition
from hubd.vault import StepEntry, _write_atomic, load_vault, save_step


class NotFound(Exception):
    pass


class Hub:
    def __init__(
        self, vault: Path, runner: Callable[[RunEnded], AgentRunner], notifier: Notifier
    ):
        self.vault = vault
        self.index = load_vault(vault)
        self.runner = runner(self.run_ended)
        self.notifier = notifier
        self.lock = asyncio.Lock()

    def entry(self, project: str, step_id: str) -> StepEntry:
        for entry in self.index.steps:
            if entry.project == project and entry.step.step == step_id:
                return entry
        raise NotFound(f"no step {project}/{step_id}")

    async def start(self, project: str, step_id: str) -> Step:
        async with self.lock:
            entry = self.entry(project, step_id)
            if entry.step.by == "me":
                raise InvalidTransition(f"step {step_id}: by: me, hubd does not run it")
            settings = self.index.projects[project]
            if settings.repo is None:
                raise InvalidTransition(f"project {project}: no repo to run in")
            new = transition(entry.step, Event.start, Actor.daemon)
            model = new.model or settings.model
            session = str(uuid4())
            started = datetime.now().replace(second=0, microsecond=0)  # the file keeps minutes
            new.runs = [*new.runs, Run(started=started, model=model, session=session)]
            before = entry.path.read_bytes()
            save_step(entry.path, new)
            old, entry.step = entry.step, new
            try:
                repo = self.vault / settings.repo
                await self.runner.start(new, session, model, repo, f"/sprint-{step_id}")
            except BaseException:
                _write_atomic(entry.path, before)  # no run started: the file says so too
                entry.step = old
                raise
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
            self.notifier.notify("Run ended", f"{entry.project} {step_id} {new.title}: review it")
            return new


def vault_path() -> Path:
    return Path(os.environ.get("HUB_VAULT", Path.home() / "Hub"))
