from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

import yaml
from typing_extensions import TypedDict

from src.core.providers import (
    get_ollama_models,
    get_openai_models,
    list_providers_for_api,
    load_all_providers,
)
from src.core.workspace import get_config_dir

SETTINGS_SCHEMA_VERSION = 1


class Settings(TypedDict, total=False):
    embedding_model_type: Literal["ollama", "tfidf", "provider"]
    embedding_ollama_model: str
    embedding_provider_id: Optional[str]
    default_page: str
    pdf_metadata_extraction_method: Literal["llm", "rule_based"]
    pdf_processing_llm_provider_id: Optional[str]
    checklist_extraction_llm_provider_id: Optional[str]
    show_canvas_by_default: bool


DEFAULT_SETTINGS: Settings = {
    "embedding_model_type": "provider",
    "embedding_ollama_model": "mbxai-embed-large:latest",
    "default_page": "checklist_review",
    "pdf_metadata_extraction_method": "llm",
    "pdf_processing_llm_provider_id": None,
    "checklist_extraction_llm_provider_id": None,
    "show_canvas_by_default": False,
}


class SettingsManager:
    @staticmethod
    def _get_settings_file() -> Path:
        return get_config_dir() / "settings.yaml"

    @staticmethod
    def ensure_dirs():
        get_config_dir().mkdir(parents=True, exist_ok=True)

    @staticmethod
    def load_settings() -> Settings:
        from src.core.config_loader import get_pdf_metadata_method

        SettingsManager.ensure_dirs()
        settings_file = SettingsManager._get_settings_file()
        settings: Settings = DEFAULT_SETTINGS.copy()
        settings["pdf_metadata_extraction_method"] = (
            "rule_based" if get_pdf_metadata_method() == "rule_based" else "llm"
        )
        if not settings_file.exists():
            return settings
        try:
            with open(settings_file, encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            if not isinstance(data, dict):
                return settings
            data.pop("schema_version", None)
            return {**settings, **data}
        except Exception:
            return settings

    @staticmethod
    def save_settings(settings: Settings) -> None:
        SettingsManager.ensure_dirs()
        payload: Dict[str, Any] = {
            "schema_version": SETTINGS_SCHEMA_VERSION,
            **settings,
        }
        with open(SettingsManager._get_settings_file(), "w", encoding="utf-8") as f:
            yaml.safe_dump(
                payload,
                f,
                sort_keys=False,
                allow_unicode=True,
                default_flow_style=False,
            )

    @staticmethod
    def load_secrets() -> List[Dict[str, Any]]:
        """Return providers from config/providers.yaml (read-only)."""
        return load_all_providers()

    @staticmethod
    def save_secrets(secrets: List[Dict[str, Any]]) -> None:
        raise PermissionError(
            "Providers are defined in config/providers.yaml with API keys from environment variables."
        )

    @staticmethod
    def get_ollama_models(base_url: str) -> List[str]:
        return get_ollama_models(base_url)

    @staticmethod
    def get_openai_models(base_url: str, api_key: str) -> List[str]:
        return get_openai_models(base_url, api_key)

    @staticmethod
    def list_providers_for_api() -> List[Dict[str, Any]]:
        return list_providers_for_api()
