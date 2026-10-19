import argparse
import sys

import uvicorn

from hubd import doctor, install
from hubd.api import HOST, PORT


def main() -> None:
    parser = argparse.ArgumentParser(prog="hubd")
    commands = ["serve", "install-hook", "uninstall-hook", "doctor"]
    parser.add_argument("command", nargs="?", default="serve", choices=commands)
    parser.add_argument("--demo", action="store_true", help="run on built-in data, FakeRunner")
    args = parser.parse_args()
    command = args.command
    if command == "install-hook":
        sys.exit(install.change(install.with_hook))
    if command == "doctor":
        sys.exit(doctor.main())
    if command == "uninstall-hook":
        sys.exit(install.change(install.uninstalled))
    if args.demo:
        print(f"hubd demo (built-in data, FakeRunner): http://{HOST}:{PORT}/docs", flush=True)
        uvicorn.run("hubd.demo:demo_app", factory=True, host=HOST, port=PORT)
        return
    uvicorn.run("hubd.api:serve_app", factory=True, host=HOST, port=PORT)


if __name__ == "__main__":
    main()
