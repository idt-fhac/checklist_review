"""Load pipelines from config/pipelines/*.yaml and build ReviewProcess definitions."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

from src.core.config_loader import load_pipeline, load_profile
from src.review_workflow.engine.tool_loader import discover_review_tools

logger = logging.getLogger(__name__)

STAGE_TO_COMPONENT: Dict[str, str] = {
    "document_loader": "document_loader",
    "criterion_evaluator": "criterion_evaluator",
    "criteria_extractor": "criteria_extractor",
    "section_mapper": "section_mapper",
    "feedback_synthesizer": "feedback_synthesizer",
    "report_writer": "report_writer",
    "md_writer": "md_writer",
    "pdf_writer": "pdf_writer",
    "json_writer": "json_writer",
}

COMPONENT_PHASE: Dict[str, str] = {
    "document_loader": "pre_process",
    "criterion_evaluator": "review",
    "criteria_extractor": "pre_process",
    "section_mapper": "pre_process",
    "feedback_synthesizer": "post_process",
    "md_writer": "post_process",
    "pdf_writer": "post_process",
    "json_writer": "post_process",
    "github_checker": "tool",
    "figure_reviewer": "tool",
}

IMPLEMENTED_STAGES = {
    "document_loader",
    "criteria_extractor",
    "section_mapper",
    "criterion_evaluator",
    "feedback_synthesizer",
    "report_writer",
    "md_writer",
    "pdf_writer",
    "json_writer",
}


def _parse_stages(pipeline: Dict[str, Any]) -> List[Tuple[str, Dict[str, Any]]]:
    stages: List[Tuple[str, Dict[str, Any]]] = []
    for entry in pipeline.get("stages") or []:
        if not isinstance(entry, dict) or len(entry) != 1:
            continue
        stage_name, stage_config = next(iter(entry.items()))
        stages.append(
            (stage_name, stage_config if isinstance(stage_config, dict) else {})
        )
    return stages


def _merge_profile(pipeline: Dict[str, Any]) -> Dict[str, Any]:
    profile_id = pipeline.get("profile")
    if not profile_id:
        return pipeline
    try:
        profile = load_profile(str(profile_id))
    except FileNotFoundError:
        logger.warning(
            "Profile '%s' not found for pipeline '%s'", profile_id, pipeline.get("name")
        )
        return pipeline
    merged = dict(pipeline)
    merged["_profile"] = profile
    return merged


def _resolve_provider_fields(config: Dict[str, Any]) -> Dict[str, Any]:
    resolved = dict(config)
    provider_ref = resolved.pop("provider", None)
    if provider_ref:
        resolved["provider_id"] = provider_ref
    embedding_ref = resolved.pop("embedding_provider", None)
    if embedding_ref:
        resolved["rag_embedding_provider_id"] = embedding_ref
    profile = resolved.pop("_profile_prompts", None)
    stage = resolved.pop("_stage", None)
    persona_id = resolved.get("persona")
    if profile and not resolved.get("system_prompt"):
        prompts = profile.get("prompts") or {}
        prompt_key = resolved.get("prompt_key")
        if prompt_key and prompts.get(prompt_key):
            resolved["system_prompt"] = prompts[prompt_key]
        elif stage == "criteria_extractor" and prompts.get("extractor_system"):
            resolved["system_prompt"] = prompts["extractor_system"]
        elif stage == "feedback_synthesizer" and prompts.get("synthesizer_system"):
            resolved["system_prompt"] = prompts["synthesizer_system"]
        elif persona_id and prompts.get(f"{persona_id}_system"):
            resolved["system_prompt"] = prompts[f"{persona_id}_system"]
        elif prompts.get("evaluator_system"):
            resolved["system_prompt"] = prompts["evaluator_system"]
    return resolved


def _resolve_persona_definition(
    persona_cfg: Dict[str, Any],
    profile: Dict[str, Any],
) -> Dict[str, Any]:
    persona_id = persona_cfg.get("id") or persona_cfg.get("persona")
    if not persona_id:
        raise ValueError("Each persona requires an id")

    prompts = profile.get("prompts") or {}
    system_prompt = persona_cfg.get("system_prompt")
    prompt_key = persona_cfg.get("prompt_key")
    if not system_prompt and prompt_key:
        system_prompt = prompts.get(prompt_key)
    if not system_prompt:
        system_prompt = prompts.get(f"{persona_id}_system")
    if not system_prompt:
        system_prompt = prompts.get("evaluator_system")

    return {
        "id": str(persona_id),
        "label": persona_cfg.get("label") or str(persona_id).replace("_", " ").title(),
        "weight": float(persona_cfg.get("weight", 1.0)),
        "system_prompt": system_prompt or "",
    }


def _build_evaluation_plan(
    steps: List[Dict[str, Any]], profile: Dict[str, Any]
) -> Dict[str, Any]:
    evaluator_steps = [
        step for step in steps if step.get("component_id") == "criterion_evaluator"
    ]
    if not evaluator_steps:
        return {
            "mode": "single",
            "personas": [],
            "merge_strategy": "weighted",
            "keep_persona_scores": False,
            "base_config": {},
        }

    first_config = dict(evaluator_steps[0].get("config") or {})
    merge_strategy = first_config.get("merge_strategy", "weighted")
    keep_persona_scores = bool(first_config.get("keep_persona_scores", True))

    if len(evaluator_steps) == 1 and first_config.get("personas"):
        personas = [
            _resolve_persona_definition(persona, profile)
            for persona in first_config.get("personas") or []
            if isinstance(persona, dict)
        ]
        mode = first_config.get("evaluation_mode") or (
            "multi_persona" if personas else "single"
        )
        base_config = dict(first_config)
        base_config.pop("personas", None)
        return {
            "mode": mode if personas else "single",
            "personas": personas,
            "merge_strategy": merge_strategy,
            "keep_persona_scores": keep_persona_scores,
            "base_config": base_config,
        }

    if len(evaluator_steps) > 1:
        personas = []
        for step in evaluator_steps:
            personas.append(
                _resolve_persona_definition(step.get("config") or {}, profile)
            )
        base_config = dict(first_config)
        return {
            "mode": "multi_persona",
            "personas": personas,
            "merge_strategy": merge_strategy,
            "keep_persona_scores": keep_persona_scores,
            "base_config": base_config,
        }

    return {
        "mode": "single",
        "personas": [],
        "merge_strategy": merge_strategy,
        "keep_persona_scores": False,
        "base_config": first_config,
    }


def pipeline_to_steps(pipeline: Dict[str, Any]) -> List[Dict[str, Any]]:
    pipeline = _merge_profile(pipeline)
    profile = pipeline.get("_profile") or {}
    steps: List[Dict[str, Any]] = []
    for index, (stage_name, stage_config) in enumerate(_parse_stages(pipeline)):
        if stage_name not in IMPLEMENTED_STAGES:
            logger.info("Skipping unimplemented pipeline stage: %s", stage_name)
            continue
        component_id = STAGE_TO_COMPONENT.get(stage_name, stage_name)
        if stage_name == "report_writer":
            component_id = stage_config.get("component") or "pdf_writer"
        config = _resolve_provider_fields(
            {**stage_config, "_profile_prompts": profile, "_stage": stage_name}
        )
        steps.append(
            {
                "id": f"step_{index + 1}",
                "component_id": component_id,
                "config": config,
                "phase": COMPONENT_PHASE.get(component_id, "unknown"),
                "stage": stage_name,
            }
        )
    return steps


def pipeline_to_flow(pipeline: Dict[str, Any]) -> Dict[str, Any]:
    pipeline = _merge_profile(pipeline)
    steps = pipeline_to_steps(pipeline)
    nodes: List[Dict[str, Any]] = []
    edges: List[Dict[str, Any]] = []
    for index, step in enumerate(steps):
        node_id = str(index + 1)
        nodes.append(
            {
                "id": node_id,
                "type": "custom",
                "position": {"x": 50 + index * 280, "y": 80},
                "data": {
                    "label": step["component_id"].replace("_", " ").title(),
                    "component_id": step["component_id"],
                    "category": step.get("phase", "unknown"),
                    "config": step.get("config", {}),
                    "readonly": True,
                },
            }
        )
        if index > 0:
            prev_id = str(index)
            edges.append(
                {
                    "id": f"e{prev_id}-{node_id}",
                    "source": prev_id,
                    "sourceHandle": "out",
                    "target": node_id,
                    "targetHandle": "in",
                }
            )
    return {
        "name": pipeline.get("name") or pipeline.get("id"),
        "profile": pipeline.get("profile"),
        "nodes": nodes,
        "edges": edges,
        "readonly": True,
        "source": "config",
    }


def build_review_process_definition(
    pipeline_id: str,
    *,
    pipeline: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    pipeline = pipeline or load_pipeline(pipeline_id)
    pipeline = _merge_profile(pipeline)
    steps = pipeline_to_steps(pipeline)

    review_process_def: Dict[str, Any] = {
        "name": pipeline.get("name") or pipeline_id,
        "pipeline_id": pipeline.get("id") or pipeline_id,
        "profile": pipeline.get("profile"),
        "document_loader": {},
        "criteria_extractor": {},
        "section_mapper": {},
        "criterion_evaluator": {},
        "feedback_synthesizer": {},
        "post_processors": [],
        "evaluation": {},
    }

    available_tools = discover_review_tools()
    tool_ids = set(available_tools.keys())
    tools_map: Dict[str, Dict[str, Any]] = {}

    for step in steps:
        comp_id = step.get("component_id")
        if comp_id in tool_ids:
            tools_map[step["id"]] = {comp_id: step.get("config", {})}

    for step in steps:
        comp_id = step.get("component_id")
        config = dict(step.get("config") or {})

        if comp_id == "document_loader":
            review_process_def["document_loader"] = {"config": config}
        elif comp_id == "criteria_extractor":
            review_process_def["criteria_extractor"] = {"config": config}
        elif comp_id == "section_mapper":
            review_process_def["section_mapper"] = {"config": config}
        elif comp_id == "criterion_evaluator":
            continue
        elif comp_id == "feedback_synthesizer":
            review_process_def["feedback_synthesizer"] = {"config": config}
        elif comp_id in ("md_writer", "pdf_writer", "json_writer"):
            review_process_def["post_processors"].append(
                {"id": comp_id, "config": config}
            )

    evaluation_plan = _build_evaluation_plan(steps, pipeline.get("_profile") or {})
    base_config = dict(evaluation_plan.get("base_config") or {})
    base_config.setdefault("tools", [])
    for tool_cfg in tools_map.values():
        base_config["tools"].append(tool_cfg)
    review_process_def["evaluation"] = evaluation_plan
    review_process_def["criterion_evaluator"] = {"config": base_config}

    return review_process_def


def load_pipeline_flow(pipeline_id: str) -> Dict[str, Any]:
    return pipeline_to_flow(load_pipeline(pipeline_id))
