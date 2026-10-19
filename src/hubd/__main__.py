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
        print(f"hubd demo (built-in data, FakeRunner): http://{HOST}:{PORT}/", flush=True)
        app = "hubd.demo:demo_app"
    else:
        app = "hubd.api:serve_app"
    # Open `/events` streams never close on their own: without a timeout, Ctrl+C waits forever.
    uvicorn.run(app, factory=True, host=HOST, port=PORT, timeout_graceful_shutdown=1)


if __name__ == "__main__":
    main()
