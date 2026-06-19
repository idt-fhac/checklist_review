from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional
from typing_extensions import TypedDict

from src.core.providers import (
    get_ollama_models,
    get_openai_models,
    list_providers_for_api,
    load_all_providers,
)
from src.core.workspace import get_config_dir

class Settings(TypedDict, total=False):
    embedding_model_type: Literal["ollama", "tfidf", "provider"]
    embedding_ollama_model: str
    embedding_provider_id: Optional[str]
    default_page: str
    pdf_metadata_extraction_method: Literal["llm", "rule_based"]
    pdf_processing_llm_provider_id: Optional[str]
    checklist_extraction_llm_provider_id: Optional[str]

DEFAULT_SETTINGS: Settings = {
    "embedding_model_type": "provider",
    "embedding_ollama_model": "mbxai-embed-large:latest",
    "default_page": "checklist_review",
    "pdf_metadata_extraction_method": "llm",
    "pdf_processing_llm_provider_id": None,
    "checklist_extraction_llm_provider_id": None,
}

class SettingsManager:
    @staticmethod
    def _get_settings_file() -> Path:
        return get_config_dir() / "settings.json"

    @staticmethod
    def ensure_dirs():
        get_config_dir().mkdir(parents=True, exist_ok=True)

    @staticmethod
    def load_settings() -> Settings:
        from src.core.config_loader import get_pdf_metadata_method

        SettingsManager.ensure_dirs()
        settings_file = SettingsManager._get_settings_file()
        settings = DEFAULT_SETTINGS.copy()
        settings["pdf_metadata_extraction_method"] = (
            "rule_based" if get_pdf_metadata_method() == "rule_based" else "llm"
        )
        if not settings_file.exists():
            return settings
        try:
            with open(settings_file, "r") as f:
                data = json.load(f)
                return {**settings, **data}
        except Exception:
            return settings

    @staticmethod
    def save_settings(settings: Settings) -> None:
        SettingsManager.ensure_dirs()
        with open(SettingsManager._get_settings_file(), "w") as f:
            json.dump(settings, f, indent=2)

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
    def get_openai_models(base_url: str, api_key: Optional[str] = None, port: Optional[int] = None) -> List[str]:
        return get_openai_models(base_url, api_key, port)

    @staticmethod
    def get_all_available_llms() -> List[Dict[str, str]]:
        available = []
        for provider in load_all_providers():
            if provider.get("is_embedding_model"):
                continue
            if provider["type"] == "ollama":
                models = SettingsManager.get_ollama_models(provider["base_url"])
                for m in models:
                    available.append({
                        "name": f"{m} (Ollama: {provider['name']})",
                        "provider_id": provider["id"],
                        "model_id": m,
                        "type": "ollama",
                        "base_url": provider["base_url"]
                    })
            elif provider["type"] in ("openai", "litellm", "gemini"):
                available.append({
                    "name": f"{provider.get('model_name')} ({provider['name']})",
                    "provider_id": provider["id"],
                    "model_id": provider.get("model_name") or "gpt-3.5-turbo",
                    "type": provider["type"],
                    "base_url": provider.get("base_url"),
                    "api_key": provider.get("api_key")
                })
        return available

    @staticmethod
    def list_providers_for_api(*, embedding_only: bool = False) -> List[Dict[str, str]]:
        return list_providers_for_api(embedding_only=embedding_only)
