from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def app():
    from app import create_app

    application = create_app()
    application.config.update({"TESTING": True})
    return application


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def isolated_workspace(tmp_path, monkeypatch):
    """Route workspace I/O to a temp directory for isolated API tests."""
    workspaces_root = tmp_path / "workspaces"
    guest = workspaces_root / "guest"
    collections = guest / "collections"
    criteria_sets = guest / "criteria_sets"
    config_dir = guest / "config"
    collections.mkdir(parents=True)
    criteria_sets.mkdir(parents=True)
    config_dir.mkdir(parents=True)

    example_criteria = (
        Path(__file__).resolve().parent.parent
        / "config"
        / "criteria_sets"
        / "example.yaml"
    )
    if example_criteria.exists():
        (criteria_sets / "example.yaml").write_text(
            example_criteria.read_text(encoding="utf-8")
        )

    monkeypatch.setattr(
        "src.core.workspace.get_workspaces_root", lambda: workspaces_root
    )

    def _active_workspace():
        return "guest"

    monkeypatch.setattr("src.core.workspace.get_active_workspace", _active_workspace)
    return guest
