import shutil
from pathlib import Path

import pytest

from hubd.daemon import Hub
from hubd.runners.fake import FakeRunner

FIXTURE = Path(__file__).parent / "fixtures" / "vault"


class Recorder:
    """A Notifier that keeps what it was asked to show."""

    def __init__(self) -> None:
        self.sent: list[tuple[str, str]] = []

    def notify(self, title: str, body: str) -> None:
        self.sent.append((title, body))


@pytest.fixture
def vault(tmp_path: Path) -> Path:
    """A copy of the fixture vault, plus a spec for step 104 so it can run."""
    shutil.copytree(FIXTURE, tmp_path, dirs_exist_ok=True)
    (tmp_path / "demo-repo" / "sprint" / "104-retry.md").write_text(
        "# Step 104 — Retry\n\n## Tasks\n- Find the bug\n- Fix it\n"
    )
    return tmp_path


@pytest.fixture
def notifier() -> Recorder:
    return Recorder()


@pytest.fixture
def hub(vault: Path, notifier: Recorder) -> Hub:
    return Hub(vault, lambda ended: FakeRunner(ended, delay=0), notifier)
