"""Web search via Serper (config/search.yaml)."""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

import requests

from src.core.config_loader import load_search_config, resolve_env_value


class SearchError(Exception):
    pass


def get_serper_api_key() -> str:
    cfg = load_search_config()
    env_name = cfg.get("api_key_env") or "SERPER_API_KEY"
    key = os.environ.get(env_name) or resolve_env_value(f"${{{env_name}}}")
    if not key:
        raise SearchError(
            f"Serper API key not configured. Set the {env_name} environment variable."
        )
    return str(key)


def serper_search(
    query: str,
    *,
    max_results: Optional[int] = None,
    allowed_domains: Optional[List[str]] = None,
) -> List[Dict[str, str]]:
    if not query or not query.strip():
        raise SearchError("Search query is empty")

    cfg = load_search_config()
    if (cfg.get("provider") or "serper").lower() != "serper":
        raise SearchError(f"Unsupported search provider: {cfg.get('provider')}")

    limit = max_results if max_results is not None else int(cfg.get("max_results") or 5)
    domains = (
        allowed_domains
        if allowed_domains is not None
        else (cfg.get("allowed_domains") or [])
    )

    payload: Dict[str, Any] = {
        "q": query.strip(),
        "num": max(1, min(limit, 10)),
    }
    safe = cfg.get("safe_search")
    if safe:
        payload["safe"] = safe

    response = requests.post(
        "https://google.serper.dev/search",
        headers={
            "X-API-KEY": get_serper_api_key(),
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=30,
    )
    if response.status_code != 200:
        raise SearchError(
            f"Serper request failed ({response.status_code}): {response.text[:300]}"
        )

    data = response.json()
    organic = data.get("organic") or []
    results: List[Dict[str, str]] = []
    for item in organic[:limit]:
        link = item.get("link") or ""
        if domains and link:
            if not any(domain.lower() in link.lower() for domain in domains):
                continue
        results.append(
            {
                "title": str(item.get("title") or ""),
                "link": link,
                "snippet": str(item.get("snippet") or ""),
            }
        )
    return results


def format_search_results(results: List[Dict[str, str]]) -> str:
    if not results:
        return "No web search results found."
    lines = ["Web search results:"]
    for index, item in enumerate(results, 1):
        lines.append(f"{index}. {item.get('title') or 'Untitled'}")
        if item.get("link"):
            lines.append(f"   URL: {item['link']}")
        if item.get("snippet"):
            lines.append(f"   Snippet: {item['snippet']}")
    return "\n".join(lines)
