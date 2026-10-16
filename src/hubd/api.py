from importlib.metadata import version

from fastapi import FastAPI

app = FastAPI(title="hubd")


@app.get("/health")
def health() -> dict:
    return {"ok": True, "version": version("hubd")}
