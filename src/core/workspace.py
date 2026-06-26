from __future__ import annotations

import shutil
from pathlib import Path

from flask import has_request_context, session

from src.core.config_loader import seed_workspace_criteria_sets

DEFAULTS_WORKSPACE_NAME = "defaults"


def get_workspaces_root() -> Path:
    return Path(__file__).resolve().parent.parent.parent / "workspaces"


def get_defaults_workspace_dir() -> Path:
    return get_workspaces_root() / DEFAULTS_WORKSPACE_NAME


def is_reserved_workspace_name(name: str) -> bool:
    if not name or name.startswith("."):
        return True
    return name.strip().lower() == DEFAULTS_WORKSPACE_NAME


def list_workspaces() -> list[str]:
    root = get_workspaces_root()
    root.mkdir(parents=True, exist_ok=True)
    return sorted(
        d.name
        for d in root.iterdir()
        if d.is_dir()
        and not d.name.startswith(".")
        and d.name != DEFAULTS_WORKSPACE_NAME
    )


def get_active_workspace() -> str:
    if has_request_context():
        return session.get("workspace", "guest")
    return "guest"


def set_active_workspace(name: str) -> None:
    if has_request_context():
        session["workspace"] = name


def get_workspace_dir(workspace_name: str = None) -> Path:
    if not workspace_name:
        workspace_name = get_active_workspace()
    d = get_workspaces_root() / workspace_name
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_collections_dir(workspace_name: str = None) -> Path:
    d = get_workspace_dir(workspace_name) / "collections"
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_criteria_sets_dir(workspace_name: str = None) -> Path:
    d = get_workspace_dir(workspace_name) / "criteria_sets"
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_config_dir(workspace_name: str = None) -> Path:
    d = get_workspace_dir(workspace_name) / "config"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _copy_yaml_files_if_missing(src: Path, dest: Path) -> None:
    if not src.is_dir():
        return
    dest.mkdir(parents=True, exist_ok=True)
    for f in src.glob("*.yaml"):
        out = dest / f.name
        if not out.exists():
            shutil.copy2(f, out)


def _ensure_minimal_settings(cfg_dest: Path) -> None:
    settings_path = cfg_dest / "settings.yaml"
    if settings_path.is_file():
        return
    template = get_defaults_workspace_dir() / "config" / "settings.yaml"
    if template.is_file():
        shutil.copy2(template, settings_path)
        return
    from src.core.config_loader import save_yaml

    save_yaml(
        settings_path,
        {
            "schema_version": 1,
            "default_page": "checklist_review",
            "show_canvas_by_default": False,
        },
    )


def _seed_new_workspace(name: str, *, merge_missing_only: bool = False) -> None:
    defaults_root = get_defaults_workspace_dir()
    cfg_dest = get_config_dir(name)
    if defaults_root.is_dir():
        tmpl_cfg = defaults_root / "config"
        if tmpl_cfg.is_dir():
            _copy_yaml_files_if_missing(tmpl_cfg, cfg_dest)
    seed_workspace_criteria_sets(get_criteria_sets_dir(name))
    _copy_yaml_files_if_missing(
        defaults_root / "criteria_sets", get_criteria_sets_dir(name)
    )
    _ensure_minimal_settings(cfg_dest)


def ensure_guest_workspace_initialized() -> None:
    get_collections_dir("guest")
    get_criteria_sets_dir("guest")
    get_config_dir("guest")
    _seed_new_workspace("guest", merge_missing_only=True)


def create_workspace(name: str) -> bool:
    if is_reserved_workspace_name(name):
        return False
    if (get_workspaces_root() / name).exists():
        return False
    get_collections_dir(name)
    get_criteria_sets_dir(name)
    get_config_dir(name)
    _seed_new_workspace(name)
    return True


def duplicate_workspace(source_name: str, new_name: str) -> bool:
    if is_reserved_workspace_name(new_name) or source_name == new_name:
        return False
    source_root = get_workspaces_root() / source_name
    if not source_root.is_dir() or (get_workspaces_root() / new_name).exists():
        return False
    get_collections_dir(new_name)
    get_criteria_sets_dir(new_name)
    get_config_dir(new_name)
    cfg_src = get_config_dir(source_name)
    cfg_dest = get_config_dir(new_name)
    for f in cfg_src.glob("*.yaml"):
        shutil.copy2(f, cfg_dest / f.name)
    seed_workspace_criteria_sets(get_criteria_sets_dir(new_name))
    _copy_yaml_files_if_missing(
        get_criteria_sets_dir(source_name), get_criteria_sets_dir(new_name)
    )
    return True


def delete_workspace(name: str) -> bool:
    if not name or name == "guest" or is_reserved_workspace_name(name):
        return False
    target = get_workspaces_root() / name
    if not target.is_dir():
        return False
    shutil.rmtree(target)
    if has_request_context() and session.get("workspace") == name:
        session["workspace"] = "guest"
    return True
