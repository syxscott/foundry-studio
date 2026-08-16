"""Regression tests for bug fixes found during code review."""

from __future__ import annotations

import json


def test_claim_is_atomic_no_double_claim(db):
    """Two concurrent claims must never return the same job."""
    jobs = [
        db.create_job(
            model="rfd3",
            name=f"j{i}",
            params={},
            input_files=[],
            engine_mode="simulation",
        )
        for i in range(5)
    ]
    # Submit all.
    for j in jobs:
        db.submit_job(j["id"])

    claimed = [db.claim_next_job("rfd3") for _ in range(10)]
    ids = [c["id"] for c in claimed if c is not None]
    assert len(ids) == 5, f"expected 5 unique claims, got {len(ids)}"
    assert len(set(ids)) == 5, "duplicate job claimed!"


def test_download_nested_output_path(client, settings, db):
    """Outputs under subdirectories must be downloadable."""
    import os
    import zipfile

    job = db.create_job(
        model="rfd3",
        name="nested",
        params={"contigs": "A1-30"},
        input_files=[],
        engine_mode="simulation",
    )
    job_id = job["id"]
    db.submit_job(job_id)

    # Simulate a worker that produced a nested output.
    out_dir = settings.resolved_data_dir() / "jobs" / job_id / "traj"
    out_dir.mkdir(parents=True)
    (out_dir / "model_0.cif").write_text("data_x\n#\nATOM\n", encoding="utf-8")
    db.update_job(job_id, status="succeeded", progress=100,
                  outputs_dir=str(settings.resolved_data_dir() / "jobs" / job_id))

    # Nested path download.
    res = client.get(f"/api/jobs/{job_id}/files/traj/model_0.cif")
    assert res.status_code == 200, res.text
    assert res.headers["content-type"].startswith("chemical/x-cif")

    # Path traversal attempts must be rejected (404).
    for evil in ("../studio.db", "..%2Fstudio.db", "..\\studio.db", "a/../../studio.db"):
        r = client.get(f"/api/jobs/{job_id}/files/{evil}")
        assert r.status_code == 404, f"traversal not blocked: {evil}"

    # ZIP download contains all outputs.
    zr = client.get(f"/api/jobs/{job_id}/download-zip")
    assert zr.status_code == 200, zr.text
    assert zr.headers["content-type"] == "application/zip"
    data = zr.content
    assert data[:2] == b"PK", "not a zip file"
    with zipfile.ZipFile(__import__("io").BytesIO(data)) as zf:
        names = zf.namelist()
    assert any("model_0.cif" in n for n in names), f"zip missing output: {names}"


def test_job_input_files_helper(db):
    """Engines read uploaded files from input_files_json, not params."""
    from foundry_studio.engines.simulation import SimulationEngine

    workdir = __import__("pathlib").Path(db.db_path).parent / "jobs"
    workdir.mkdir(parents=True, exist_ok=True)
    engine = SimulationEngine(db=db, workdir=workdir, log_path=workdir / "w.log")

    job = db.create_job(
        model="mpnn",
        name="files",
        params={"temperature": 0.1},
        input_files=[
            {"role": "structure", "filename": "x.cif", "name": "x"},
            {"role": "motif", "filename": "m.cif", "name": "m"},
        ],
        engine_mode="simulation",
    )
    all_files = engine.job_input_files(job)
    assert len(all_files) == 2
    structures = engine.job_input_files(job, roles={"structure", "input"})
    assert len(structures) == 1
    assert structures[0]["filename"] == "x.cif"
    # Params must not carry the input files.
    params = json.loads(job["params_json"])
    assert "_input_files" not in params
