"""Provider registry backed by config/providers.yaml and environment variables."""

from __future__ import annotations

import os
import uuid
from typing import Any, Dict, List, Optional

from src.core.config_loader import (
    get_default_provider_ref,
    load_providers_config,
    resolve_env_value,
)
from src.core.types import LLMProvider


def _normalize_provider(raw: Dict[str, Any]) -> LLMProvider:
    provider: LLMProvider = {
        "id": str(raw.get("id") or uuid.uuid4()),
        "type": raw.get("type", "ollama"),
        "name": raw.get("name", raw.get("id", "provider")),
        "base_url": raw.get("base_url", ""),
        "model_name": raw.get("model_name"),
        "port": raw.get("port"),
        "params": raw.get("params"),
        "is_embedding_model": bool(raw.get("is_embedding_model", False)),
        "accepts_image_input": bool(raw.get("accepts_image_input", False)),
    }
    api_key_env = raw.get("api_key_env")
    if api_key_env:
        provider["api_key"] = os.environ.get(str(api_key_env))
    elif raw.get("api_key"):
        provider["api_key"] = resolve_env_value(raw["api_key"])
    return provider


def load_all_providers() -> List[LLMProvider]:
    cfg = load_providers_config()
    providers = [
        _normalize_provider(p)
        for p in cfg.get("providers") or []
        if isinstance(p, dict)
    ]
    return providers


def get_provider(provider_id: str) -> Optional[LLMProvider]:
    if not provider_id:
        return None
    for provider in load_all_providers():
        if provider.get("id") == provider_id:
            return provider
    return None


def resolve_provider_config(provider_id: str) -> Dict[str, Any]:
    provider = get_provider(provider_id)
    if not provider:
        raise ValueError(f"Provider '{provider_id}' not found in config/providers.yaml")
    return dict(provider)


def get_provider_for_purpose(purpose: str) -> Optional[LLMProvider]:
    ref = get_default_provider_ref(purpose)
    if not ref:
        providers = load_all_providers()
        return providers[0] if providers else None
    return get_provider(ref)


def list_providers_for_api(*, embedding_only: bool = False) -> List[Dict[str, str]]:
    providers = load_all_providers()
    result: List[Dict[str, str]] = []
    for provider in providers:
        is_embedding = bool(provider.get("is_embedding_model"))
        if embedding_only and not is_embedding:
            continue
        if not embedding_only and is_embedding:
            continue
        result.append(
            {
                "id": provider["id"],
                "name": provider.get("name", provider["id"]),
                "type": provider.get("type", "ollama"),
            }
        )
    return result


def get_ollama_models(base_url: str) -> List[str]:
    import requests

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


def get_openai_models(
    base_url: str, api_key: Optional[str] = None, port: Optional[int] = None
) -> List[str]:
    from urllib.parse import urlparse, urlunparse

    import requests

    try:
        url = base_url.rstrip("/")
        parsed = urlparse(url)

        if port and not parsed.port:
            netloc = parsed.netloc
            if netloc:
                netloc = f"{netloc}:{port}"
                url = urlunparse(
                    (
                        parsed.scheme or "https",
                        netloc,
                        parsed.path,
                        parsed.params,
                        parsed.query,
                        parsed.fragment,
                    )
                )
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
                models = [
                    model["id"]
                    for model in data.get("data", [])
                    if isinstance(model, dict) and "id" in model
                ]
                return sorted(models)
            if isinstance(data, list):
                models = [
                    model.get("id") if isinstance(model, dict) else str(model)
                    for model in data
                ]
                return sorted([m for m in models if m])
    except Exception:
        pass
    return []
