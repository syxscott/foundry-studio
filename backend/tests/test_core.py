"""Unit tests for the database state machine and simulation engine."""

from __future__ import annotations

import json


def test_job_lifecycle(db):
    job = db.create_job(
        model="rfd3",
        name="lifecycle",
        params={"contigs": "A1-20"},
        input_files=[],
        engine_mode="simulation",
    )
    assert job["status"] == "draft"

    # Submit -> queued.
    db.submit_job(job["id"])
    assert db.get_job(job["id"])["status"] == "queued"

    # Claim -> running.
    claimed = db.claim_next_job("rfd3")
    assert claimed is not None
    assert claimed["id"] == job["id"]
    assert db.get_job(job["id"])["status"] == "running"

    # Nothing else to claim.
    assert db.claim_next_job("rfd3") is None

    # Update to terminal.
    db.update_job(job["id"], status="succeeded", progress=100)
    final = db.get_job(job["id"])
    assert final["status"] == "succeeded"
    assert final["progress"] == 100
    assert final["finished_at"] is not None


def test_cancel_queued(db):
    job = db.create_job(
        model="mpnn", name="c", params={}, input_files=[], engine_mode="simulation"
    )
    db.submit_job(job["id"])
    db.update_job(job["id"], status="canceled")
    assert db.get_job(job["id"])["status"] == "canceled"


def test_requeue_stale(db):
    import time

    job = db.create_job(
        model="rf3", name="s", params={}, input_files=[], engine_mode="simulation"
    )
    db.update_job(
        job["id"],
        status="running",
        started_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - 3600)),
    )
    n = db.requeue_stale_running(stale_seconds=300)
    assert n == 1
    assert db.get_job(job["id"])["status"] == "queued"


def test_simulation_engine_produces_outputs(db, tmp_path):
    from foundry_studio.engines.simulation import SimulationEngine

    workdir = tmp_path / "jobs"
    workdir.mkdir(parents=True)
    log = tmp_path / "w.log"
    engine = SimulationEngine(db=db, workdir=workdir, log_path=log)
    engine.initialize()

    job = db.create_job(
        model="rfd3",
        name="sim",
        params={"contigs": "A1-40", "n_batches": 1},
        input_files=[],
        engine_mode="simulation",
    )
    result = engine.run(job)
    assert len(result.outputs) >= 2  # CIF + JSON
    kinds = {o.kind for o in result.outputs}
    assert "cif" in kinds and "json" in kinds
    # CIF must be a real parseable file with content.
    cif = next(o for o in result.outputs if o.kind == "cif")
    assert cif.path.is_file()
    assert cif.path.stat().st_size > 200

    # MPNN simulation yields a FASTA.
    job2 = db.create_job(
        model="mpnn",
        name="sim2",
        params={"model_type": "protein_mpnn", "number_of_batches": 4, "temperature": 0.1},
        input_files=[],
        engine_mode="simulation",
    )
    result2 = engine.run(job2)
    kinds2 = {o.kind for o in result2.outputs}
    assert "fasta" in kinds2
    fasta = next(o for o in result2.outputs if o.kind == "fasta")
    text = fasta.path.read_text()
    assert text.startswith(">")
    assert "\n" in text


def test_checkpoint_registry():
    from foundry_studio.engines import checkpoints as ckpt

    entries = ckpt.list_checkpoints()
    names = {e["name"] for e in entries}
    assert {"rfd3", "rfd3na", "rf3", "proteinmpnn", "ligandmpnn"} <= names
    for e in entries:
        assert e["filename"]
        assert e["description"]


def test_i18n_localize():
    from foundry_studio.i18n import localize

    zh = localize("error.model_not_found", "zh", {"model": "X"})
    en = localize("error.model_not_found", "en", {"model": "X"})
    ja = localize("error.model_not_found", "ja", {"model": "X"})
    ru = localize("error.model_not_found", "ru", {"model": "X"})
    assert "X" in zh and "X" in en and "X" in ja and "X" in ru
    assert zh != en != ja != ru
    # Unknown key falls back to the key itself.
    assert localize("no.such.key", "en") == "no.such.key"
