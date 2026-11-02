import os
import subprocess
from pathlib import Path

import pytest

APP = Path(__file__).parent.parent / "bin" / "sprint-hub-app"


def run_app(tmp_path: Path, service: bool) -> list[str]:
    """Run the script with fake commands; return the log of what it called."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    log = tmp_path / "log"
    fakes = {
        "curl": f"[ -e {tmp_path}/up ]",  # hubd answers once something started it
        "systemctl": f'echo "systemctl $*" >> {log}\n'
        f'[ "$2" = cat ] && exit {0 if service else 1}\n'
        f"touch {tmp_path}/up",
        "setsid": f'echo "fallback $*" >> {log}\ntouch {tmp_path}/up',
        "omarchy-launch-or-focus-webapp": f'echo "window" >> {log}',
        "notify-send": f'echo "notify $*" >> {log}',
    }
    for name, body in fakes.items():
        script = bin_dir / name
        script.write_text(f"#!/bin/bash\n{body}\n")
        script.chmod(0o755)
    env = {**os.environ, "PATH": f"{bin_dir}:/usr/bin:/bin"}
    subprocess.run([str(APP)], env=env, check=True, timeout=20)
    return log.read_text().splitlines()


@pytest.mark.parametrize("service", [True, False])
def test_start_through_service_or_fallback(tmp_path: Path, service: bool) -> None:
    lines = run_app(tmp_path, service)
    assert lines[-1] == "window"
    if service:
        assert "systemctl --user start hubd.service" in lines
        assert not any(line.startswith("fallback") for line in lines)
    else:
        assert any(line.startswith("fallback") for line in lines)
        assert not any("start" in line for line in lines if line.startswith("systemctl"))
