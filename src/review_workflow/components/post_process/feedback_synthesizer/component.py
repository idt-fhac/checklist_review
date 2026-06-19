"""Synthesize per-criterion evaluations into narrative feedback."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from strands import Agent

from src.core.criteria import criteria_set_stem
from src.core.pdf_processing import load_model_from_provider
from src.core.providers import resolve_provider_config
from src.review_workflow.components.evaluators.criterion_evaluator.file_utils import (
    get_evaluations_file_path,
    get_persona_manifest_path,
)
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

        persona_manifest = None
        manifest_path = get_persona_manifest_path(
            collection_name,
            pipeline_name,
            artifact_name,
            criteria_set_name,
            Path(collections_root),
        )
        if manifest_path.exists():
            persona_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

        provider_id = self.config.get("provider_id")
        if not provider_id:
            raise ValueError("feedback_synthesizer requires provider_id")
        provider_config = resolve_provider_config(provider_id)

        persona = self.config.get("persona") or "editor"
        system_prompt = self.config.get("system_prompt") or (
            "You are an expert review editor. Summarize evaluation results clearly, "
            "highlight compliance gaps, and give actionable advice."
        )
        user_prompt = self._build_prompt(evaluations, persona, persona_manifest)

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
            "multi_persona": bool(persona_manifest),
            "persona_manifest": persona_manifest,
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

    def _build_prompt(
        self,
        evaluations: List[Dict[str, Any]],
        persona: str,
        persona_manifest: Dict[str, Any] | None,
    ) -> str:
        lines = [f"Persona: {persona}", "Evaluation results:"]
        persona_labels: Dict[str, str] = {}
        if persona_manifest:
            persona_labels = {
                p["id"]: p.get("label", p["id"])
                for p in persona_manifest.get("personas", [])
                if isinstance(p, dict)
            }
            lines.append(
                f"Multi-persona review ({persona_manifest.get('merge_strategy', 'weighted')} merge)."
            )
        for item in evaluations:
            if not isinstance(item, dict):
                continue
            criterion = item.get("criterion_text") or item.get("description") or "Criterion"
            answer = item.get("answer")
            reasoning = item.get("reasoning") or item.get("explanation") or ""
            lines.append(f"- {criterion}")
            lines.append(f"  Merged answer: {answer}")
            if reasoning:
                lines.append(f"  Merged reasoning: {reasoning}")
            if item.get("disagreement"):
                lines.append("  Persona disagreement: yes")
            persona_scores = item.get("persona_scores") or {}
            for persona_id, score in persona_scores.items():
                if not isinstance(score, dict):
                    continue
                label = score.get("label") or persona_labels.get(persona_id, persona_id)
                lines.append(f"  [{label}] answer={score.get('answer')}")
                persona_reasoning = score.get("reasoning") or ""
                if persona_reasoning:
                    lines.append(f"    Reasoning: {persona_reasoning}")
        lines.append(
            "\nWrite an executive summary, prioritized recommendations, and explicit redlines. "
            "If personas disagreed, explain why and state your recommended action."
        )
        return "\n".join(lines)
