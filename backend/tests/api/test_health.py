"""Phase 0: /healthz + /readyz basics."""
from __future__ import annotations


def test_healthz_returns_ok(client) -> None:  # noqa: ANN001
    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_readyz_returns_ok_when_db_reachable(client) -> None:  # noqa: ANN001
    resp = client.get("/readyz")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["db"] is True


def test_docs_endpoint_renders(client) -> None:  # noqa: ANN001
    """OpenAPI JSON should be served for every phase's routers."""
    resp = client.get("/openapi.json")
    assert resp.status_code == 200
    paths = resp.json().get("paths", {})
    for expected in (
        "/users",
        "/interests",
        "/events",
        "/reels",
        "/notifications",
        "/ai/chat",
        "/missions",
    ):
        assert expected in paths, f"missing route: {expected}"
