"""Interests REST: list + filter + free-text create."""
from __future__ import annotations


def test_list_interests_returns_44_after_seed(seeded, client) -> None:  # noqa: ANN001, ARG001
    r = client.get("/interests")
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 44


def test_list_interests_filter_by_category(seeded, client) -> None:  # noqa: ANN001, ARG001
    r = client.get("/interests?category=topic")
    assert r.status_code == 200
    body = r.json()
    assert body
    assert all(i["category"] == "topic" for i in body)


def test_create_free_text_interest(client) -> None:  # noqa: ANN001
    r = client.post("/interests", json={"label": "Weird Custom", "category": "topic"})
    assert r.status_code == 201
    body = r.json()
    assert body["is_predefined"] is False
    assert body["slug"] == "weird-custom"


def test_get_interest_missing_returns_404(client) -> None:  # noqa: ANN001
    r = client.get("/interests/999999")
    assert r.status_code == 404


def test_get_interest_by_id(seeded, client) -> None:  # noqa: ANN001, ARG001
    first = client.get("/interests").json()[0]
    r = client.get(f"/interests/{first['id']}")
    assert r.status_code == 200
    assert r.json()["id"] == first["id"]
