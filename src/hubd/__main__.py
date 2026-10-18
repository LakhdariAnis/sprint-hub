import argparse
import sys

import uvicorn

from hubd import doctor, install
from hubd.api import HOST, PORT


def main() -> None:
    parser = argparse.ArgumentParser(prog="hubd")
    commands = ["serve", "install-hook", "uninstall-hook", "doctor"]
    parser.add_argument("command", nargs="?", default="serve", choices=commands)
    command = parser.parse_args().command
    if command == "install-hook":
        sys.exit(install.change(install.with_hook))
    if command == "doctor":
        sys.exit(doctor.main())
    if command == "uninstall-hook":
        sys.exit(install.change(install.uninstalled))
    uvicorn.run("hubd.api:serve_app", factory=True, host=HOST, port=PORT)


if __name__ == "__main__":
    main()
