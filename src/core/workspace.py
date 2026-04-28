from __future__ import annotations

import json
import shutil
from pathlib import Path

from flask import session, has_request_context

DEFAULTS_WORKSPACE_NAME = "defaults"


def get_workspaces_root() -> Path:
    return Path(__file__).resolve().parent.parent.parent / "workspaces"


def get_defaults_workspace_dir() -> Path:
    return get_workspaces_root() / DEFAULTS_WORKSPACE_NAME


def get_shared_process_definitions_dir() -> Path:
    """Templates shipped at repo level: workspaces/process_definitions/."""
    return get_workspaces_root() / "process_definitions"


def _defaults_settings_source(defaults_root: Path) -> Path | None:
    """Prefer defaults/config/settings.json, then workspaces/defaults/settings.json."""
    for candidate in (
        defaults_root / "config" / "settings.json",
        defaults_root / "settings.json",
    ):
        if candidate.is_file():
            return candidate
    return None


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


def set_active_workspace(name: str):
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


def get_checklists_dir(workspace_name: str = None) -> Path:
    d = get_workspace_dir(workspace_name) / "checklists"
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_process_definitions_dir(workspace_name: str = None) -> Path:
    d = get_workspace_dir(workspace_name) / "process_definitions"
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_config_dir(workspace_name: str = None) -> Path:
    d = get_workspace_dir(workspace_name) / "config"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _copy_json_files(src: Path, dest: Path) -> None:
    if not src.is_dir():
        return
    dest.mkdir(parents=True, exist_ok=True)
    for f in src.glob("*.json"):
        shutil.copy2(f, dest / f.name)


def _copy_json_files_if_missing(src: Path, dest: Path) -> None:
    """Copy *.json from src to dest only when the destination file does not exist."""
    if not src.is_dir():
        return
    dest.mkdir(parents=True, exist_ok=True)
    for f in src.glob("*.json"):
        out = dest / f.name
        if not out.exists():
            shutil.copy2(f, out)


def _strip_question_reviewer_llm_provider(process_data: dict) -> None:
    """Remove LLM provider fields from question_reviewer nodes (template / new workspaces)."""
    for node in process_data.get("nodes") or []:
        data = node.get("data") or {}
        if data.get("component_id") != "question_reviewer":
            continue
        cfg = data.get("config")
        if not isinstance(cfg, dict):
            continue
        cfg.pop("provider_id", None)
        cfg.pop("rag_embedding_provider_id", None)


def _load_stripped_guest_demo_process_dict() -> dict | None:
    """
    Load workspaces/guest/process_definitions/demo_process.json for seeding demo_process.json.
    Strips LLM provider fields from question_reviewer. Returns None if missing or invalid.
    """
    guest_demo = (
        get_workspaces_root() / "guest" / "process_definitions" / "demo_process.json"
    )
    if not guest_demo.is_file():
        return None
    try:
        data = json.loads(guest_demo.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    if not isinstance(data, dict):
        return None
    _strip_question_reviewer_llm_provider(data)
    return data


def _ensure_minimal_settings(cfg_dest: Path) -> None:
    settings_path = cfg_dest / "settings.json"
    if settings_path.is_file():
        return
    minimal = {
        "embedding_model_type": "tfidf",
        "default_page": "checklist_review",
        "pdf_metadata_extraction_method": "rule_based",
        "show_canvas_by_default": False,
        "pdf_processing_llm_provider_id": None,
        "checklist_extraction_llm_provider_id": None,
    }
    settings_path.write_text(json.dumps(minimal, indent=2) + "\n", encoding="utf-8")


def _seed_new_workspace(
    name: str,
    *,
    config_source: Path | None,
    merge_missing_only: bool = False,
) -> None:
    """
    Populate a new workspace from workspaces/defaults (processes, checklists, base config).
    If config_source is set (duplicate), copy settings.json and secrets.json from it first,
    then fill any remaining config/*.json from defaults.

    Fresh workspaces (no duplicate): apply settings from defaults/config/settings.json or
    workspaces/defaults/settings.json; seed process_definitions from defaults and from
    workspaces/process_definitions (shared JSON overlay after defaults).

    When merge_missing_only is True, never overwrite existing JSON files (used to bootstrap
    workspaces/guest on first app run without clobbering user edits later).
    """
    defaults_root = get_defaults_workspace_dir()
    cfg_dest = get_config_dir(name)
    copy_fn = _copy_json_files_if_missing if merge_missing_only else _copy_json_files

    if defaults_root.is_dir():
        tmpl_cfg = defaults_root / "config"
        if config_source and config_source.is_dir():
            for fname in ("settings.json", "secrets.json"):
                src = config_source / fname
                if src.is_file():
                    shutil.copy2(src, cfg_dest / fname)
            if tmpl_cfg.is_dir():
                for f in tmpl_cfg.glob("*.json"):
                    if not (cfg_dest / f.name).exists():
                        shutil.copy2(f, cfg_dest / f.name)
        elif tmpl_cfg.is_dir():
            copy_fn(tmpl_cfg, cfg_dest)

        # Non-duplicate: apply canonical defaults settings (covers defaults/settings.json only).
        if config_source is None:
            settings_src = _defaults_settings_source(defaults_root)
            if settings_src is not None:
                dest_settings = cfg_dest / "settings.json"
                if merge_missing_only:
                    if not dest_settings.exists():
                        shutil.copy2(settings_src, dest_settings)
                else:
                    shutil.copy2(settings_src, dest_settings)

        copy_fn(
            defaults_root / "process_definitions",
            get_process_definitions_dir(name),
        )
        if config_source is None:
            copy_fn(
                get_shared_process_definitions_dir(),
                get_process_definitions_dir(name),
            )
        copy_fn(defaults_root / "checklists", get_checklists_dir(name))

        # Fresh workspace: prefer stripped guest demo as demo_process.json when guest supplies one.
        if config_source is None:
            demo = _load_stripped_guest_demo_process_dict()
            if demo is not None:
                out = get_process_definitions_dir(name) / "demo_process.json"
                if not merge_missing_only or not out.exists():
                    out.write_text(json.dumps(demo, indent=2) + "\n", encoding="utf-8")

    _ensure_minimal_settings(cfg_dest)


def ensure_guest_workspace_initialized() -> None:
    """
    Populate workspaces/guest from defaults when missing (e.g. fresh clone with no guest tree).

    Safe to call on every app startup: only fills missing JSON/config files, never overwrites.
    """
    get_collections_dir("guest")
    get_checklists_dir("guest")
    get_process_definitions_dir("guest")
    get_config_dir("guest")
    _seed_new_workspace("guest", config_source=None, merge_missing_only=True)


def create_workspace(name: str) -> bool:
    if is_reserved_workspace_name(name):
        return False
    ws_dir = get_workspaces_root() / name
    if ws_dir.exists():
        return False

    get_collections_dir(name)
    get_checklists_dir(name)
    get_process_definitions_dir(name)
    get_config_dir(name)

    _seed_new_workspace(name, config_source=None)
    return True


def duplicate_workspace(source_name: str, new_name: str) -> bool:
    if is_reserved_workspace_name(new_name):
        return False
    if source_name == new_name:
        return False
    if source_name == DEFAULTS_WORKSPACE_NAME:
        return False

    source_root = get_workspaces_root() / source_name
    if not source_root.is_dir():
        return False

    new_root = get_workspaces_root() / new_name
    if new_root.exists():
        return False

    get_collections_dir(new_name)
    get_checklists_dir(new_name)
    get_process_definitions_dir(new_name)
    get_config_dir(new_name)

    _seed_new_workspace(new_name, config_source=get_config_dir(source_name))
    return True


def delete_workspace(name: str) -> bool:
    if not name or name.startswith(".") or name == "guest" or name == DEFAULTS_WORKSPACE_NAME:
        return False
    ws_dir = get_workspaces_root() / name
    if not ws_dir.exists():
        return False

    try:
        shutil.rmtree(ws_dir)
        if get_active_workspace() == name:
            set_active_workspace("guest")
        return True
    except Exception:
        return False
