"""Ingest REST: multipart CSV / JSON upload + job polling."""
from __future__ import annotations

import io
import json


def _poll_job(client, job_id: int, tries: int = 20) -> dict:  # noqa: ANN001
    for _ in range(tries):
        job = client.get(f"/ingest/jobs/{job_id}").json()
        if job["status"] in {"success", "failed"}:
            return job
    return job


def test_events_csv_ingest_flow(client) -> None:  # noqa: ANN001
    csv = (
        b"external_id,title,track,start_time,end_time,timezone,status\n"
        b"probe-1,Probe,AI,2026-07-11T09:00:00,2026-07-11T10:00:00,UTC,scheduled\n"
    )
    r = client.post(
        "/ingest/events",
        files={"file": ("probe.csv", io.BytesIO(csv), "text/csv")},
    )
    assert r.status_code == 202, r.text
    job_id = r.json()["job_id"]
    job = _poll_job(client, job_id)
    assert job["status"] == "success"
    stats = job["stats"] or {}
    assert stats.get("added") == 1


def test_events_csv_rejects_non_csv(client) -> None:  # noqa: ANN001
    r = client.post(
        "/ingest/events",
        files={"file": ("no.txt", io.BytesIO(b"junk"), "text/plain")},
    )
    assert r.status_code == 400


def test_speakers_csv_ingest(client) -> None:  # noqa: ANN001
    csv = b"name,bio\nAda Lovelace,Original\n"
    r = client.post(
        "/ingest/speakers",
        files={"file": ("s.csv", io.BytesIO(csv), "text/csv")},
    )
    assert r.status_code == 202
    job_id = r.json()["job_id"]
    job = _poll_job(client, job_id)
    assert job["status"] == "success"


def test_json_bundle_ingest(client) -> None:  # noqa: ANN001
    payload = {
        "speakers": [{"name": "Grace Hopper", "title": "RA"}],
        "events": [
            {
                "external_id": "j1",
                "title": "History",
                "speakers": [{"name": "Grace Hopper"}],
            }
        ],
    }
    body = json.dumps(payload).encode()
    r = client.post(
        "/ingest/json",
        files={"file": ("bundle.json", io.BytesIO(body), "application/json")},
    )
    assert r.status_code == 202
    job_id = r.json()["job_id"]
    job = _poll_job(client, job_id)
    assert job["status"] == "success"


def test_list_ingest_jobs(client) -> None:  # noqa: ANN001
    csv = b"external_id,title\nx,Y\n"
    r = client.post(
        "/ingest/events",
        files={"file": ("y.csv", io.BytesIO(csv), "text/csv")},
    )
    assert r.status_code == 202
    r = client.get("/ingest/jobs")
    assert r.status_code == 200
    assert isinstance(r.json(), list)
    assert r.json()


def test_get_missing_job_404(client) -> None:  # noqa: ANN001
    assert client.get("/ingest/jobs/999999").status_code == 404
