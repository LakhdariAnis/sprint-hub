import subprocess
from pathlib import Path

import pytest

from hubd import service

EXE = Path("/repo/.venv/bin/hubd")


class Systemctl:
    """Records the calls; no real systemctl."""

    def __init__(self, code: int = 0, out: str = "") -> None:
        self.calls: list[tuple[str, ...]] = []
        self.code, self.out = code, out

    def __call__(self, *args: str) -> subprocess.CompletedProcess[str]:
        self.calls.append(args)
        return subprocess.CompletedProcess(args, self.code, self.out, "boom")


@pytest.fixture
def exe(tmp_path: Path) -> Path:
    path = tmp_path / "hubd"
    path.write_text("")
    return path


def test_unit_text() -> None:
    text = service.unit_text(EXE, "/a/b:/c%d")
    assert "ExecStart=/repo/.venv/bin/hubd\n" in text
    assert 'Environment="PATH=/a/b:/c%%d"\n' in text
    assert "Restart=on-failure\n" in text
    assert "RestartPreventExitStatus=98\n" in text
    assert "WantedBy=default.target\n" in text


def test_install_no_writes_nothing(tmp_path: Path, exe: Path, capsys) -> None:
    unit, run = tmp_path / "u" / "hubd.service", Systemctl()
    assert service.install_service(unit, exe, "/bin", lambda _: "n", run) == 1
    assert not unit.exists() and run.calls == []
    assert "+ExecStart=" in capsys.readouterr().out  # the unit text was shown as a diff


def test_install_yes_writes_and_enables(tmp_path: Path, exe: Path) -> None:
    unit, run = tmp_path / "u" / "hubd.service", Systemctl()
    assert service.install_service(unit, exe, "/bin", lambda _: "y", run) == 0
    assert unit.read_text() == service.unit_text(exe, "/bin")
    assert run.calls == [("daemon-reload",), ("enable", "--now", "hubd.service")]


def test_install_again_asks_nothing(tmp_path: Path, exe: Path) -> None:
    unit = tmp_path / "hubd.service"
    service.install_service(unit, exe, "/bin", lambda _: "y", Systemctl())

    def never(_: str) -> str:
        raise AssertionError("asked")

    assert service.install_service(unit, exe, "/bin", never, Systemctl()) == 0


def test_install_without_venv(tmp_path: Path) -> None:
    run = Systemctl()
    missing = tmp_path / "none"
    assert service.install_service(tmp_path / "u", missing, "/bin", lambda _: "y", run) == 1
    assert run.calls == []


def test_install_reports_systemctl_failure(tmp_path: Path, exe: Path, capsys) -> None:
    assert service.install_service(tmp_path / "u", exe, "/bin", lambda _: "y", Systemctl(1)) == 1
    assert "daemon-reload: boom" in capsys.readouterr().err


def test_uninstall(tmp_path: Path, exe: Path) -> None:
    unit = tmp_path / "hubd.service"
    service.install_service(unit, exe, "/bin", lambda _: "y", Systemctl())
    run = Systemctl()
    assert service.uninstall_service(unit, lambda _: "n", run) == 1
    assert unit.exists() and run.calls == []
    assert service.uninstall_service(unit, lambda _: "y", run) == 0
    assert not unit.exists()
    assert run.calls == [("disable", "--now", "hubd.service"), ("daemon-reload",)]
    assert service.uninstall_service(unit, lambda _: "y", run) == 0  # nothing left: nothing asked


def test_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(service, "UNIT", tmp_path / "hubd.service")
    assert service.state(Systemctl()) == "not installed"
    (tmp_path / "hubd.service").write_text("")
    assert service.state(Systemctl(3, "inactive\n")) == "inactive"
