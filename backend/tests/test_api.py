"""API integration tests (simulation engine mode)."""

from __future__ import annotations

import json


def test_health(client):
    res = client.get("/api/health")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "ok"
    assert body["engine_mode"] == "simulation"
    assert "version" in body


def test_models_catalog(client):
    res = client.get("/api/models")
    assert res.status_code == 200
    models = res.json()
    ids = {m["id"] for m in models}
    assert {"rfd3", "rfd3na", "rf3", "mpnn"} <= ids
    rfd3 = next(m for m in models if m["id"] == "rfd3")
    assert "contigs" in rfd3["param_schema"]["properties"]
    assert rfd3["effective_engine"] == "simulation"


def test_checkpoints_list(client):
    res = client.get("/api/checkpoints")
    assert res.status_code == 200
    entries = res.json()
    names = {e["name"] for e in entries}
    assert {"rfd3", "rf3", "proteinmpnn"} <= names


def test_create_draft_then_submit_and_run(client, settings, sample_cif):
    # Create a draft job.
    res = client.post(
        "/api/jobs",
        json={
            "model": "rfd3",
            "name": "test-design",
            "params": {"contigs": "A1-30", "n_batches": 1},
            "engine_mode": "simulation",
        },
    )
    assert res.status_code == 201
    job = res.json()
    assert job["status"] == "draft"
    job_id = job["id"]

    # Upload an input file.
    with open(sample_cif, "rb") as fh:
        up = client.post(
            f"/api/jobs/{job_id}/files",
            files=[("files", (sample_cif.name, fh, "application/octet-stream"))],
            data={"role": "scaffold"},
        )
    assert up.status_code == 200, up.text
    upload = up.json()
    assert len(upload["uploaded"]) == 1
    assert upload["uploaded"][0]["filename"] == sample_cif.name

    # Submit -> queued, then run synchronously via the simulation engine.
    sub = client.post(f"/api/jobs/{job_id}/submit")
    assert sub.status_code == 200, sub.text
    assert sub.json()["status"] == "queued"

    # Execute the job inline using the shared engine runner (same code path
    # the production subprocess uses — see :mod:`foundry_studio.hpc._local_runner`).
    from foundry_studio.db import StudioDB
    from foundry_studio.engines.runner import run_one as runner_run_one
    from foundry_studio.engines.registry import resolve_engine

    db = StudioDB(settings.resolved_data_dir() / "studio.db")
    workdir = settings.resolved_data_dir() / "jobs"
    engine, mode, is_sim = resolve_engine(
        "rfd3",
        engine_mode="simulation",
        allow_simulation=True,
        db=db,
        workdir=workdir,
        log_path=workdir / "w.log",
    )
    engine.initialize()
    # Re-claim the queued job.
    job_row = db.claim_next_job("rfd3")
    assert job_row is not None
    runner_run_one(
        db=db,
        settings=settings,
        model="rfd3",
        engine=engine,
        job=job_row,
        data_dir=settings.resolved_data_dir(),
    )
    db.close()

    # Job should now be succeeded with outputs.
    detail = client.get(f"/api/jobs/{job_id}")
    assert detail.status_code == 200
    body = detail.json()
    assert body["status"] == "succeeded"
    assert body["progress"] == 100
    assert len(body["outputs"]) >= 1
    cif_outputs = [o for o in body["outputs"] if o["kind"] == "cif"]
    assert cif_outputs, "expected at least one CIF output"

    # Download the CIF.
    dl = client.get(cif_outputs[0]["url"])
    assert dl.status_code == 200
    assert dl.headers["content-type"].startswith("chemical/x-cif")


def test_cancel_queued_job(client):
    res = client.post(
        "/api/jobs",
        json={"model": "mpnn", "params": {}, "engine_mode": "simulation"},
    )
    job_id = res.json()["id"]
    assert client.post(f"/api/jobs/{job_id}/submit").json()["status"] == "queued"

    cancel = client.post(f"/api/jobs/{job_id}/cancel")
    assert cancel.status_code == 200
    assert cancel.json()["canceled"] is True
    assert client.get(f"/api/jobs/{job_id}").json()["status"] == "canceled"


def test_delete_finished_job(client, settings):
    res = client.post(
        "/api/jobs",
        json={"model": "rf3", "params": {}, "engine_mode": "simulation"},
    )
    job_id = res.json()["id"]
    client.post(f"/api/jobs/{job_id}/submit")
    # Force terminal state (simulate a completed job).
    from foundry_studio.db import StudioDB

    db = StudioDB(settings.resolved_data_dir() / "studio.db")
    db.update_job(job_id, status="succeeded", progress=100)
    db.close()

    delete = client.delete(f"/api/jobs/{job_id}")
    assert delete.status_code == 200
    assert delete.json()["ok"] is True
    assert client.get(f"/api/jobs/{job_id}").status_code == 404


def test_errors_are_localized(client):
    # Unknown model -> localized error payload.
    res = client.post("/api/jobs", json={"model": "nope", "params": {}})
    assert res.status_code == 404
    body = res.json()
    assert body["message_key"] == "error.model_not_found"
    assert "model" in body["params"]
    # English default message.
    assert "Unknown model" in body["message"]
    # Chinese via lang param.
    res_zh = client.post("/api/jobs?lang=zh", json={"model": "nope", "params": {}})
    assert "未知的模型" in res_zh.json()["message"]

    # Missing job.
    res = client.get("/api/jobs/does-not-exist")
    assert res.status_code == 404
    assert res.json()["message_key"] == "error.job_not_found"


def test_i18n_catalog(client):
    res = client.get("/api/i18n")
    assert res.status_code == 200
    msgs = res.json()
    assert "error.unknown" in msgs
    assert "zh" in msgs["error.unknown"]
    assert "ru" in msgs["error.unknown"]
