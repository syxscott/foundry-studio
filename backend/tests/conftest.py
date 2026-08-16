"""Shared test fixtures: isolated data dir + API test client."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

# Make the backend importable regardless of CWD.
BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

os.environ.setdefault("FOUNDRY_STUDIO_ENGINE_MODE", "simulation")


@pytest.fixture()
def settings(tmp_path: Path):
    """Settings pointed at an isolated temp data dir, simulation engine."""
    from foundry_studio.config import Settings

    return Settings(
        data_dir=tmp_path / "data",
        engine_mode="simulation",
        allow_simulation_fallback=True,
    )


@pytest.fixture()
def db(settings):
    from foundry_studio.db import StudioDB

    database = StudioDB(settings.resolved_data_dir() / "studio.db")
    yield database
    database.close()


@pytest.fixture()
def client(settings):
    """FastAPI TestClient with an isolated app (no worker autostart)."""
    from foundry_studio.app import create_app

    app = create_app(settings=settings)
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def sample_cif(tmp_path: Path) -> Path:
    """A minimal valid CIF file for upload tests."""
    path = tmp_path / "mini.cif"
    path.write_text(
        "data_mini\n#\nloop_\n_atom_site.group_PDB\n_atom_site.id\n"
        "_atom_site.type_symbol\n_atom_site.label_atom_id\n"
        "_atom_site.label_comp_id\n_atom_site.label_asym_id\n"
        "_atom_site.label_seq_id\n_atom_site.Cartn_x\n_atom_site.Cartn_y\n"
        "_atom_site.Cartn_z\n_atom_site.occupancy\n_atom_site.B_iso_or_equiv\n"
        "ATOM 1 C CA ALA A 1 1.0 1.0 1.0 1.00 20.00\n",
        encoding="utf-8",
    )
    return path
