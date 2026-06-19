"""Load version-controlled configuration from the repo ``config/`` directory."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_CONFIG_DIR = _REPO_ROOT / "config"


def get_repo_config_dir() -> Path:
    return _CONFIG_DIR


def get_repo_root() -> Path:
    return _REPO_ROOT


def _load_yaml(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    return data if isinstance(data, dict) else {}


@lru_cache(maxsize=1)
def load_providers_config() -> Dict[str, Any]:
    return _load_yaml(_CONFIG_DIR / "providers.yaml")


@lru_cache(maxsize=1)
def load_search_config() -> Dict[str, Any]:
    return _load_yaml(_CONFIG_DIR / "search.yaml")


def load_profile(profile_id: str) -> Dict[str, Any]:
    path = _CONFIG_DIR / "profiles" / f"{profile_id}.yaml"
    if not path.exists():
        slug = profile_id.strip().replace(" ", "_").lower()
        path = _CONFIG_DIR / "profiles" / f"{slug}.yaml"
    data = _load_yaml(path)
    if not data:
        raise FileNotFoundError(f"Profile '{profile_id}' not found in config/profiles/")
    return data


def list_profiles() -> List[str]:
    profiles_dir = _CONFIG_DIR / "profiles"
    if not profiles_dir.exists():
        return []
    return sorted(p.stem for p in profiles_dir.glob("*.yaml"))


def load_pipeline(pipeline_id: str) -> Dict[str, Any]:
    path = _CONFIG_DIR / "pipelines" / f"{pipeline_id}.yaml"
    if not path.exists():
        slug = pipeline_id.strip().replace(" ", "_").lower()
        path = _CONFIG_DIR / "pipelines" / f"{slug}.yaml"
    data = _load_yaml(path)
    if not data:
        raise FileNotFoundError(f"Pipeline '{pipeline_id}' not found in config/pipelines/")
    data.setdefault("id", path.stem)
    return data


def list_pipelines() -> List[Dict[str, Any]]:
    pipelines_dir = _CONFIG_DIR / "pipelines"
    if not pipelines_dir.exists():
        return []
    results: List[Dict[str, Any]] = []
    for path in sorted(pipelines_dir.glob("*.yaml")):
        try:
            data = _load_yaml(path)
        except Exception:
            continue
        if not data:
            continue
        pipeline_id = path.stem
        results.append(
            {
                "id": pipeline_id,
                "name": data.get("name", pipeline_id),
                "profile": data.get("profile"),
                "path": str(path),
            }
        )
    return results


def resolve_env_value(value: Any) -> Any:
    """Resolve ``api_key_env`` fields and ``${VAR}`` placeholders."""
    if isinstance(value, str):
        if value.startswith("${") and value.endswith("}"):
            inner = value[2:-1]
            if ":-" in inner:
                var_name, default = inner.split(":-", 1)
                return os.environ.get(var_name, default)
            return os.environ.get(inner, "")
    return value


def get_default_provider_ref(purpose: str) -> Optional[str]:
    cfg = load_providers_config()
    defaults = cfg.get("defaults") or {}
    ref = defaults.get(purpose)
    return str(ref) if ref else None


def get_pdf_metadata_method() -> str:
    cfg = load_providers_config()
    pdf_cfg = cfg.get("pdf_metadata") or {}
    method = pdf_cfg.get("method", "llm")
    return "rule_based" if method == "rule_based" else "llm"
