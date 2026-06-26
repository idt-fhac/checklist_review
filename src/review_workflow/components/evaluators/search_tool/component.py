"""Serper web search tool for criterion evaluation."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from strands import tool

from src.core.criteria import criteria_set_stem
from src.core.search import SearchError, format_search_results, serper_search
from src.review_workflow.engine.base import BaseComponent
from src.review_workflow.engine.run_paths import artifact_run_dir


class SearchTool(BaseComponent):
    def as_tool(
        self,
        collection_name: str,
        pipeline_name: str,
        criteria_set_name: str,
        artifact_name: str,
        log_callback=None,
        token_usage_accumulator=None,
        collections_root=None,
    ):
        max_results = self.config.get("max_results")
        allowed_domains = self.config.get("allowed_domains")

        @tool(name="web_search")
        def web_search(query: str) -> str:
            """
            Search the public web for facts that cannot be verified from the artifact alone.

            Use this when a criterion involves external verification (company credentials, standards,
            regulations, market facts, prior publications, or claims requiring third-party evidence).

            Args:
                query: A concise search query.

            Returns:
                Top web results with titles, URLs, and snippets.
            """
            try:
                results = serper_search(
                    query,
                    max_results=max_results,
                    allowed_domains=allowed_domains,
                )
                self._append_search_log(
                    collections_root,
                    collection_name,
                    pipeline_name,
                    criteria_set_name,
                    artifact_name,
                    query,
                    results,
                )
                if log_callback:
                    log_callback(
                        f"Web search returned {len(results)} result(s)", "info"
                    )
                return format_search_results(results)
            except SearchError as exc:
                message = f"Web search failed: {exc}"
                if log_callback:
                    log_callback(message, "warning")
                return message

        return web_search

    def _append_search_log(
        self,
        collections_root,
        collection_name: str,
        pipeline_name: str,
        criteria_set_name: str,
        artifact_name: str,
        query: str,
        results: List[Dict[str, str]],
    ) -> None:
        if not collections_root:
            return
        run_dir = artifact_run_dir(
            Path(collections_root),
            collection_name,
            pipeline_name,
            artifact_name,
            criteria_set_stem(criteria_set_name),
        )
        run_dir.mkdir(parents=True, exist_ok=True)
        log_path = run_dir / "search_log.json"

        payload: Dict[str, Any] = {"schema_version": 1, "queries": []}
        if log_path.exists():
            try:
                payload = json.loads(log_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                payload = {"schema_version": 1, "queries": []}

        payload.setdefault("queries", []).append(
            {
                "timestamp": datetime.utcnow().isoformat(),
                "query": query,
                "results": results,
            }
        )
        log_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
