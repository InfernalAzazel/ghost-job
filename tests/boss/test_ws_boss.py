import asyncio

import pytest
from fastapi.testclient import TestClient

from backend import server
from backend.boss.jobs import Job


class FakeSession:
    def __init__(self) -> None:
        self.is_open = False
        self.closed = False

    async def open(self) -> None:
        self.is_open = True

    async def close(self) -> None:
        self.closed = True
        self.is_open = False

    async def search(self, url: str | None = None):
        return (
            url or "https://example.test/jobs",
            [Job("T", "C", "10K", "https://example.test/j/1", "1")],
            "done",
        )


@pytest.fixture()
def client(monkeypatch):
    fake = FakeSession()
    monkeypatch.setattr(server, "boss_session", fake, raising=False)
    monkeypatch.setattr(server, "_search_lock", asyncio.Lock(), raising=False)
    with TestClient(server.app) as c:
        yield c, fake


def test_boss_open_and_search(client):
    c, fake = client
    with c.websocket_connect("/ws") as ws:
        hello = ws.receive_json()
        assert hello["type"] == "hello"
        ws.send_json({"type": "boss.open"})
        # may receive launching then ready
        states: list[str] = []
        for _ in range(3):
            status = ws.receive_json()
            assert status["type"] == "boss.status"
            states.append(status["state"])
            if status["state"] == "ready":
                break
        assert "ready" in states
        assert fake.is_open is True
        ws.send_json({"type": "boss.search"})
        # may receive navigating then jobs/done
        msgs = [ws.receive_json(), ws.receive_json(), ws.receive_json()]
        types = {m["type"] for m in msgs}
        assert "boss.jobs" in types
        jobs_msg = next(m for m in msgs if m["type"] == "boss.jobs")
        assert jobs_msg["jobs"][0]["title"] == "T"
        assert any(
            m["type"] == "boss.status" and m.get("state") == "done" for m in msgs
        )
