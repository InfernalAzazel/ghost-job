from backend.boss.session import DEFAULT_CDP_URL, resolve_cdp_url


def test_resolve_cdp_url_default(monkeypatch):
    monkeypatch.delenv("GHOSTJOB_CDP_URL", raising=False)
    assert resolve_cdp_url() == DEFAULT_CDP_URL


def test_resolve_cdp_url_from_env(monkeypatch):
    monkeypatch.setenv("GHOSTJOB_CDP_URL", "http://127.0.0.1:9333")
    assert resolve_cdp_url() == "http://127.0.0.1:9333"
