"""Synthesize per-criterion evaluations into narrative feedback."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from strands import Agent

from src.core.criteria import criteria_set_stem
from src.core.pdf_processing import load_model_from_provider
from src.core.providers import resolve_provider_config
from src.review_workflow.components.evaluators.criterion_evaluator.file_utils import get_evaluations_file_path
from src.review_workflow.engine.base import BaseComponent
from src.review_workflow.engine.run_paths import artifact_run_dir


class FeedbackSynthesizer(BaseComponent):
    def execute(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        collection_name = inputs["collection_name"]
        pipeline_name = inputs["pipeline_name"]
        artifact_name = inputs["artifact_name"]
        criteria_set_name = inputs["criteria_set_name"]
        collections_root = inputs["collections_root"]
        log_callback = inputs.get("log_callback")
        token_usage_accumulator = inputs.get("token_usage_accumulator")

        evaluations_path = get_evaluations_file_path(
            collection_name,
            pipeline_name,
            artifact_name,
            criteria_set_name,
            Path(collections_root),
        )
        if not evaluations_path.exists():
            raise FileNotFoundError(f"No evaluations found at {evaluations_path}")

        evaluations = json.loads(evaluations_path.read_text(encoding="utf-8"))
        if isinstance(evaluations, dict):
            evaluations = list(evaluations.values())

        provider_id = self.config.get("provider_id")
        if not provider_id:
            raise ValueError("feedback_synthesizer requires provider_id")
        provider_config = resolve_provider_config(provider_id)

        persona = self.config.get("persona") or "editor"
        system_prompt = self.config.get("system_prompt") or (
            "You are an expert review editor. Summarize evaluation results clearly, "
            "highlight compliance gaps, and give actionable advice."
        )
        user_prompt = self._build_prompt(evaluations, persona)

        model = load_model_from_provider(provider_config)
        agent = Agent(model=model, system_prompt=system_prompt)
        response = agent(user_prompt)
        narrative = getattr(response, "text", None) or getattr(response, "content", None) or str(response)

        run_dir = artifact_run_dir(
            Path(collections_root),
            collection_name,
            pipeline_name,
            artifact_name,
            criteria_set_stem(criteria_set_name),
        )
        synthesis_doc = {
            "schema_version": 1,
            "persona": persona,
            "summary": narrative.strip(),
            "evaluation_count": len(evaluations),
        }
        synthesis_path = run_dir / "synthesis.json"
        synthesis_path.write_text(json.dumps(synthesis_doc, indent=2), encoding="utf-8")

        if log_callback:
            log_callback("Feedback synthesis complete", "info")

        return {
            "status": "completed",
            "synthesis_file": str(synthesis_path),
            "summary": synthesis_doc["summary"],
        }

    def _build_prompt(self, evaluations: List[Dict[str, Any]], persona: str) -> str:
        lines = [f"Persona: {persona}", "Evaluation results:"]
        for item in evaluations:
            if not isinstance(item, dict):
                continue
            criterion = item.get("criterion_text") or item.get("description") or "Criterion"
            answer = item.get("answer")
            reasoning = item.get("reasoning") or item.get("explanation") or ""
            lines.append(f"- {criterion}")
            lines.append(f"  Answer: {answer}")
            if reasoning:
                lines.append(f"  Reasoning: {reasoning}")
        lines.append("\nWrite a concise executive summary plus prioritized recommendations.")
        return "\n".join(lines)
