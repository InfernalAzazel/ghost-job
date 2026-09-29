import asyncio

import httpx
import pytest

from job.utils import update


@pytest.fixture(autouse=True)
def fresh(monkeypatch):
    monkeypatch.setattr(update, "_checked", False)
    monkeypatch.setattr(update, "_newer", None)
    monkeypatch.setattr(update, "__version__", "0.6.2")


def serve(monkeypatch, handler):
    calls = []

    def recorded(request):
        calls.append(request)
        return handler(request)

    real = httpx.AsyncClient
    monkeypatch.setattr(
        update.httpx,
        "AsyncClient",
        lambda **kw: real(transport=httpx.MockTransport(recorded), **kw),
    )
    return calls


def redirect(tag):
    url = f"https://github.com/InfernalAzazel/ghost-job/releases/tag/{tag}"
    return lambda _: httpx.Response(302, headers={"location": url})


def test_newer_release(monkeypatch):
    calls = serve(monkeypatch, redirect("v0.7.0"))
    assert asyncio.run(update.check()) == update.Release(
        version="0.7.0",
        url="https://github.com/InfernalAzazel/ghost-job/releases/tag/v0.7.0",
    )
    asyncio.run(update.check())
    assert len(calls) == 1


def test_up_to_date(monkeypatch):
    serve(monkeypatch, redirect("v0.6.2"))
    assert asyncio.run(update.check()) is None


def test_request_failure_retries(monkeypatch):
    def down(request):
        raise httpx.ConnectTimeout("timeout", request=request)

    calls = serve(monkeypatch, down)
    assert asyncio.run(update.check()) is None
    assert asyncio.run(update.check()) is None
    assert len(calls) == 2


def test_no_redirect(monkeypatch):
    serve(monkeypatch, lambda _: httpx.Response(404))
    assert asyncio.run(update.check()) is None
