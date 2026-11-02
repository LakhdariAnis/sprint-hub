import socket
import sys

import pytest

from hubd import __main__ as cli
from hubd import service


def test_busy_port_exits_with_the_code_the_unit_does_not_restart_on(
    monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    with socket.socket() as taken:
        taken.bind(("127.0.0.1", 0))
        taken.listen()
        monkeypatch.setattr(cli, "PORT", taken.getsockname()[1])
        monkeypatch.setattr(sys, "argv", ["hubd"])
        with pytest.raises(SystemExit) as exit_:
            cli.main()
    assert exit_.value.code == service.PORT_BUSY == 98
    err = capsys.readouterr().err.strip().splitlines()
    assert len(err) == 1 and "already in use" in err[0]


def test_free_port_is_not_busy(monkeypatch: pytest.MonkeyPatch) -> None:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        free = probe.getsockname()[1]
    monkeypatch.setattr(cli, "PORT", free)
    assert not cli.port_busy()
