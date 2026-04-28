from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional
from typing_extensions import TypedDict

import requests

from src.core.types import LLMProvider
from src.core.workspace import get_config_dir
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
    "embedding_model_type": "ollama",
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
    def _get_secrets_file() -> Path:
        return get_config_dir() / "secrets.json"

    @staticmethod
    def ensure_dirs():
        get_config_dir().mkdir(parents=True, exist_ok=True)

    @staticmethod
    def load_settings() -> Settings:
        SettingsManager.ensure_dirs()
        settings_file = SettingsManager._get_settings_file()
        if not settings_file.exists():
            return DEFAULT_SETTINGS.copy()
        try:
            with open(settings_file, "r") as f:
                data = json.load(f)
                return {**DEFAULT_SETTINGS, **data}
        except Exception:
            return DEFAULT_SETTINGS.copy()

    @staticmethod
    def save_settings(settings: Settings) -> None:
        SettingsManager.ensure_dirs()
        with open(SettingsManager._get_settings_file(), "w") as f:
            json.dump(settings, f, indent=2)

    @staticmethod
    def load_secrets() -> List[LLMProvider]:
        SettingsManager.ensure_dirs()
        secrets_file = SettingsManager._get_secrets_file()
        if not secrets_file.exists():
            return []
        try:
            with open(secrets_file, "r") as f:
                return json.load(f)
        except Exception:
            return []

    @staticmethod
    def save_secrets(secrets: List[LLMProvider]) -> None:
        SettingsManager.ensure_dirs()
        with open(SettingsManager._get_secrets_file(), "w") as f:
            json.dump(secrets, f, indent=2)

    @staticmethod
    def get_ollama_models(base_url: str) -> List[str]:
        try:
            base_url = base_url.rstrip("/")
            response = requests.get(f"{base_url}/api/tags", timeout=5)
            if response.status_code == 200:
                data = response.json()
                models = [model["name"] for model in data.get("models", [])]
                return sorted(models)
        except Exception:
            pass
        return []

    @staticmethod
    def get_openai_models(base_url: str, api_key: Optional[str] = None, port: Optional[int] = None) -> List[str]:
        try:
            from urllib.parse import urlparse, urlunparse
            
            url = base_url.rstrip("/")
            parsed = urlparse(url)
            
            if port and not parsed.port:
                netloc = parsed.netloc
                if netloc:
                    netloc = f"{netloc}:{port}"
                    url = urlunparse((
                        parsed.scheme or 'https',
                        netloc,
                        parsed.path,
                        parsed.params,
                        parsed.query,
                        parsed.fragment
                    ))
                    parsed = urlparse(url)
            
            if parsed.path.endswith("/v1"):
                models_url = f"{url}/models"
            elif parsed.path.endswith("/v1/"):
                models_url = f"{url.rstrip('/')}/models"
            elif "/v1" in parsed.path:
                models_url = f"{url.rstrip('/')}/models"
            else:
                models_url = f"{url.rstrip('/')}/v1/models"
            
            headers = {"Content-Type": "application/json"}
            if api_key:
                headers["Authorization"] = f"Bearer {api_key}"
            
            response = requests.get(models_url, headers=headers, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                if isinstance(data, dict) and "data" in data:
                    models = [model["id"] for model in data.get("data", []) if isinstance(model, dict) and "id" in model]
                    return sorted(models)
                elif isinstance(data, list):
                    models = [model.get("id") if isinstance(model, dict) else str(model) for model in data]
                    return sorted([m for m in models if m])
        except Exception:
            pass
        return []

    @staticmethod
    def get_all_available_llms() -> List[Dict[str, str]]:
        secrets = SettingsManager.load_secrets()
        available = []

        for provider in secrets:
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
            elif provider["type"] == "openai":
                available.append({
                    "name": f"{provider['model_name']} ({provider['name']})",
                    "provider_id": provider["id"],
                    "model_id": provider["model_name"] or "gpt-3.5-turbo",
                    "type": "openai",
                    "base_url": provider["base_url"],
                    "api_key": provider["api_key"]
                })
        
        return available
