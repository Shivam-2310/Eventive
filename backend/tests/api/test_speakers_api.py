"""Speakers REST endpoints (Phase 3)."""
from __future__ import annotations


def test_list_speakers_after_seed(seeded, client) -> None:  # noqa: ANN001, ARG001
    r = client.get("/speakers")
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 20


def test_create_get_patch_delete_speaker(client) -> None:  # noqa: ANN001
    r = client.post("/speakers", json={"name": "Dr. Test", "company": "Acme"})
    assert r.status_code == 201, r.text
    sid = r.json()["id"]

    r = client.get(f"/speakers/{sid}")
    assert r.status_code == 200
    assert r.json()["name"] == "Dr. Test"

    r = client.patch(f"/speakers/{sid}", json={"bio": "new bio"})
    assert r.status_code == 200
    assert r.json()["bio"] == "new bio"

    r = client.delete(f"/speakers/{sid}")
    assert r.status_code == 204
    assert client.get(f"/speakers/{sid}").status_code == 404


def test_get_missing_speaker(client) -> None:  # noqa: ANN001
    assert client.get("/speakers/999999").status_code == 404
    assert client.patch("/speakers/999999", json={"bio": "x"}).status_code == 404
    assert client.delete("/speakers/999999").status_code == 404
