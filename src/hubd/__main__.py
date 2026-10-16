import argparse

import uvicorn

HOST = "127.0.0.1"  # localhost only: the API has no auth
PORT = 8765


def main() -> None:
    parser = argparse.ArgumentParser(prog="hubd")
    parser.add_argument("command", nargs="?", default="serve", choices=["serve"])
    parser.parse_args()
    uvicorn.run("hubd.api:app", host=HOST, port=PORT)


if __name__ == "__main__":
    main()
