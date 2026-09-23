"""Minimal local gateway: health + WebSocket echo + boss session protocol."""

from __future__ import annotations

import asyncio
import json
import os
from contextlib import asynccontextmanager
from datetime import UTC, datetime

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from backend.boss.jobs import DEFAULT_SEARCH_URL, job_to_dict
from backend.boss.session import BossSession

boss_session = BossSession()
_search_lock = asyncio.Lock()


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    await boss_session.close()


app = FastAPI(title="ghostjob-backend", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict[str, str]:
    return {
        "status": "ok",
        "service": "ghostjob",
        "time": datetime.now(UTC).isoformat(),
    }


async def _handle_boss(websocket: WebSocket, payload: dict) -> None:
    typ = payload.get("type")
    if typ == "boss.open":
        await websocket.send_json({"type": "boss.status", "state": "launching"})
        try:
            await boss_session.open()
            await websocket.send_json({"type": "boss.status", "state": "ready"})
        except Exception as exc:  # noqa: BLE001
            await websocket.send_json(
                {"type": "boss.error", "message": str(exc), "code": "launch_failed"}
            )
            await websocket.send_json(
                {"type": "boss.status", "state": "error", "message": str(exc)}
            )
        return

    if typ == "boss.close":
        await boss_session.close()
        await websocket.send_json({"type": "boss.status", "state": "done", "message": "closed"})
        return

    if typ == "boss.search":
        if _search_lock.locked():
            await websocket.send_json(
                {"type": "boss.error", "message": "search already running", "code": "busy"}
            )
            return
        async with _search_lock:
            await websocket.send_json({"type": "boss.status", "state": "navigating"})
            try:
                url = payload.get("url") or DEFAULT_SEARCH_URL
                final_url, jobs, state = await boss_session.search(url)
                await websocket.send_json(
                    {
                        "type": "boss.jobs",
                        "url": final_url,
                        "jobs": [job_to_dict(j) for j in jobs],
                    }
                )
                await websocket.send_json({"type": "boss.status", "state": state})
            except Exception as exc:  # noqa: BLE001
                await websocket.send_json(
                    {"type": "boss.error", "message": str(exc), "code": "search_failed"}
                )
                await websocket.send_json(
                    {"type": "boss.status", "state": "error", "message": str(exc)}
                )
        return


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    await websocket.accept()
    await websocket.send_json({"type": "hello", "message": "ghostjob backend ready"})
    try:
        while True:
            raw = await websocket.receive_text()
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                payload = {"type": "text", "data": raw}

            if payload.get("type") == "ping":
                await websocket.send_json(
                    {
                        "type": "pong",
                        "echo": payload.get("data"),
                        "time": datetime.now(UTC).isoformat(),
                    }
                )
            elif str(payload.get("type", "")).startswith("boss."):
                await _handle_boss(websocket, payload)
            else:
                await websocket.send_json({"type": "echo", "data": payload})
    except WebSocketDisconnect:
        return


def main() -> None:
    import uvicorn

    host = os.environ.get("GHOSTJOB_HOST", "127.0.0.1")
    port = int(os.environ.get("GHOSTJOB_PORT", "8765"))
    # Ready marker for Electron to parse from stdout (Hermes-style).
    print(f"GHOSTJOB_BACKEND_READY port={port}", flush=True)
    uvicorn.run(app, host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
