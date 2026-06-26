import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.core.criteria import (
    criteria_for_evaluator,
    criteria_set_stem,
    load_criteria_set_file,
)
from src.review_workflow.components.evaluators.criterion_evaluator.component import (
    CriterionEvaluator,
)
from src.review_workflow.components.evaluators.criterion_evaluator.file_utils import (
    get_evaluations_file_path,
    get_persona_manifest_path,
    load_existing_evaluations,
    save_evaluations,
)
from src.review_workflow.components.post_process.feedback_synthesizer.component import (
    FeedbackSynthesizer,
)
from src.review_workflow.components.post_process.json_writer.component import JsonWriter
from src.review_workflow.components.post_process.md_writer.component import MdWriter
from src.review_workflow.components.post_process.pdf_writer.component import PdfWriter
from src.review_workflow.components.pre_process.criteria_extractor.component import (
    CriteriaExtractor,
)
from src.review_workflow.components.pre_process.document_loader.component import (
    DocumentLoader,
)
from src.review_workflow.components.pre_process.section_mapper.component import (
    SectionMapper,
)
from src.review_workflow.engine.base import BaseComponent
from src.review_workflow.engine.evaluation_merger import (
    merge_criterion_results,
    normalize_persona_weights,
)
from src.review_workflow.engine.token_usage import create_accumulator, get_summary

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("ReviewProcess")


class ReviewProcess:
    def __init__(
        self,
        process_definition: Dict[str, Any],
        stop_event=None,
        log_callback=None,
        collections_root: Path = None,
    ):
        self.pipeline_name = process_definition["name"]
        self.pipeline_id = process_definition.get("pipeline_id")
        self.stop_event = stop_event
        self.log_callback = log_callback

        if collections_root is None:
            project_root = Path(__file__).resolve().parent.parent.parent.parent
            self.collections_root = (
                project_root / "workspaces" / "guest" / "collections"
            )
        else:
            self.collections_root = Path(collections_root)

        self.document_loader = self._init_component(
            process_definition.get("document_loader", {}), DocumentLoader
        )
        self.criteria_extractor = self._init_optional(
            process_definition.get("criteria_extractor", {}), CriteriaExtractor
        )
        self.section_mapper = self._init_optional(
            process_definition.get("section_mapper", {}), SectionMapper
        )
        self.criterion_evaluator = self._init_component(
            process_definition.get("criterion_evaluator", {}), CriterionEvaluator
        )
        self.feedback_synthesizer = self._init_optional(
            process_definition.get("feedback_synthesizer", {}), FeedbackSynthesizer
        )
        self.evaluation_plan = process_definition.get("evaluation") or {}
        self.evaluation_mode = self.evaluation_plan.get("mode", "single")
        self.evaluation_personas = normalize_persona_weights(
            self.evaluation_plan.get("personas") or []
        )
        self.merge_strategy = self.evaluation_plan.get("merge_strategy", "weighted")
        self.keep_persona_scores = bool(
            self.evaluation_plan.get("keep_persona_scores", True)
        )

        self.post_processors: List[BaseComponent] = []
        for pp_def in process_definition.get("post_processors", []):
            if pp_def.get("id") == "md_writer":
                self.post_processors.append(self._init_component(pp_def, MdWriter))
            elif pp_def.get("id") == "pdf_writer":
                self.post_processors.append(self._init_component(pp_def, PdfWriter))
            elif pp_def.get("id") == "json_writer":
                self.post_processors.append(self._init_component(pp_def, JsonWriter))

    def _init_component(self, def_dict: Dict[str, Any], cls: Any) -> BaseComponent:
        return cls(config=def_dict.get("config", {}))

    def _init_optional(
        self, def_dict: Dict[str, Any], cls: Any
    ) -> Optional[BaseComponent]:
        if not def_dict or not def_dict.get("config"):
            return None
        return cls(config=def_dict.get("config", {}))

    def _slug(self, name: str) -> str:
        return name.strip().replace(" ", "_").lower() or "process"

    def _write_token_usage_file(
        self,
        collection_name: str,
        artifact_name: str,
        criteria_set_name: str,
        token_usage: Dict[str, Any],
    ) -> None:
        if token_usage is None:
            return
        artifact_dir = (
            self.collections_root
            / self._slug(collection_name)
            / "review_runs"
            / self._slug(self.pipeline_name)
        )
        criteria_clean = criteria_set_stem(criteria_set_name)
        artifact_dir = artifact_dir / self._slug(criteria_clean) / artifact_name
        artifact_dir.mkdir(parents=True, exist_ok=True)
        (artifact_dir / "token_usage.json").write_text(
            json.dumps(token_usage, indent=2), encoding="utf-8"
        )

    def _load_criteria_set(
        self,
        collection_name: str,
        criteria_set_name: str,
    ):
        from src.core.criteria_resolver import load_criteria_for_review

        criteria_dir = self.collections_root.parent / "criteria_sets"
        return load_criteria_for_review(
            self.collections_root,
            collection_name,
            criteria_set_name,
            criteria_dir,
        )

    def execute(
        self,
        collection_name: str,
        artifact_name: str,
        criteria_set_name: str,
        artifact_index: int | None = None,
        total_artifacts: int | None = None,
        criteria_source_name: str | None = None,
        reference_urls: List[str] | None = None,
    ):
        if self.stop_event and self.stop_event.is_set():
            raise InterruptedError("Review process stopped by user")

        logger.info(
            "Starting pipeline %s: collection=%s artifact=%s criteria_set=%s",
            self.pipeline_name,
            collection_name,
            artifact_name,
            criteria_set_name,
        )

        col_dir = self.collections_root / self._slug(collection_name)
        from src.core import storage

        artifact_stem = Path(artifact_name).stem
        meta_dir = storage._source_metadata_dir(col_dir, create=False)
        meta_path = meta_dir / f"{artifact_stem}.json"
        artifact_title = artifact_name
        if meta_path.exists():
            artifact_title = json.loads(meta_path.read_text(encoding="utf-8")).get(
                "title", artifact_name
            )

        if self.log_callback:
            if artifact_index and total_artifacts:
                self.log_callback(
                    f"{'=' * 15}\n\n{artifact_title} ({artifact_index}/{total_artifacts})",
                    "info",
                )
            else:
                self.log_callback(f"{'=' * 15}\n\n{artifact_title}", "info")

        extractor_source = (
            (self.criteria_extractor.config.get("source") or "artifact").lower()
            if self.criteria_extractor
            else None
        )
        use_extractor = (
            self.criteria_extractor
            and extractor_source != "criteria_set"
            and criteria_set_name == "extracted"
            and bool(criteria_source_name)
        )

        criteria_set = None
        if not use_extractor:
            criteria_set = self._load_criteria_set(collection_name, criteria_set_name)
            if criteria_set is None:
                raise FileNotFoundError(
                    f"Criteria set '{criteria_set_name}' not found for collection '{collection_name}'"
                )
            if self.log_callback:
                self.log_callback("Criteria set loaded", "info")

        artifact_result = self.document_loader.execute(
            {
                "collection_name": collection_name,
                "artifact_name": artifact_name,
                "pipeline_name": self.pipeline_name,
                "criteria_set_name": criteria_set_name,
                "collections_root": self.collections_root,
            }
        )

        output_path = artifact_result.get("output_file")
        if not output_path or not Path(output_path).exists():
            raise FileNotFoundError("Document loader did not produce artifact content")

        if self.log_callback:
            self.log_callback("Artifact loaded", "info")

        if use_extractor:
            extract_result = self.criteria_extractor.execute(
                {
                    "collection_name": collection_name,
                    "artifact_name": artifact_name,
                    "pipeline_name": self.pipeline_name,
                    "criteria_set_name": criteria_set_name,
                    "collections_root": self.collections_root,
                    "criteria_source_name": criteria_source_name,
                    "log_callback": self.log_callback,
                }
            )
            if extract_result.get("status") == "completed":
                criteria_set = load_criteria_set_file(
                    Path(extract_result["criteria_file"])
                )
                if self.log_callback:
                    self.log_callback(
                        f"Using {extract_result.get('criteria_count', 0)} extracted criteria",
                        "info",
                    )
            elif criteria_set is None:
                criteria_set = self._load_criteria_set(
                    collection_name, criteria_set_name
                )
            if criteria_set is None:
                raise FileNotFoundError("No criteria available after extraction")

        criteria = criteria_for_evaluator(criteria_set)
        if not criteria:
            raise ValueError(f"No criteria available for '{criteria_set_name}'")

        token_usage_accumulator = create_accumulator()
        run_context = {
            "collection_name": collection_name,
            "pipeline_name": self.pipeline_name,
            "artifact_name": artifact_name,
            "criteria_set_name": criteria_set_name,
            "collections_root": self.collections_root,
            "log_callback": self.log_callback,
            "token_usage_accumulator": token_usage_accumulator,
            "section_mapping": None,
            "reference_urls": reference_urls or [],
        }

        if self.section_mapper:
            mapping_result = self.section_mapper.execute(
                {
                    **run_context,
                    "criteria": criteria,
                }
            )
            run_context["section_mapping"] = mapping_result.get("mapping")

        self._run_criterion_evaluations(run_context, criteria)

        if self.feedback_synthesizer:
            self.feedback_synthesizer.execute(
                {
                    **run_context,
                    "token_usage_accumulator": token_usage_accumulator,
                }
            )

        token_usage = get_summary(token_usage_accumulator)
        self._write_token_usage_file(
            collection_name, artifact_name, criteria_set_name, token_usage
        )

        for pp in self.post_processors:
            pp.execute(
                {
                    "collection_name": collection_name,
                    "pipeline_name": self.pipeline_name,
                    "artifact_name": artifact_name,
                    "criteria_set_name": criteria_set_name,
                    "collections_root": self.collections_root,
                    "log_callback": self.log_callback,
                    "token_usage": token_usage,
                }
            )

        if self.log_callback:
            self.log_callback("Review ended", "info")

        return {"token_usage": token_usage}

    def _write_persona_manifest(
        self,
        collection_name: str,
        artifact_name: str,
        criteria_set_name: str,
    ) -> None:
        if self.evaluation_mode != "multi_persona" or not self.evaluation_personas:
            return
        manifest_path = get_persona_manifest_path(
            collection_name,
            self.pipeline_name,
            artifact_name,
            criteria_set_name,
            self.collections_root,
        )
        manifest_path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "evaluation_mode": self.evaluation_mode,
                    "merge_strategy": self.merge_strategy,
                    "keep_persona_scores": self.keep_persona_scores,
                    "personas": self.evaluation_personas,
                },
                indent=2,
            ),
            encoding="utf-8",
        )

    def _criterion_already_evaluated(
        self,
        collection_name: str,
        artifact_name: str,
        criteria_set_name: str,
        criterion_id: Any,
    ) -> bool:
        merged_file = get_evaluations_file_path(
            collection_name,
            self.pipeline_name,
            artifact_name,
            criteria_set_name,
            self.collections_root,
        )
        merged = load_existing_evaluations(merged_file)
        if criterion_id not in merged:
            return False
        if self.evaluation_mode != "multi_persona":
            return True
        if self.criterion_evaluator.config.get("force_review", False):
            return False
        from src.review_workflow.components.evaluators.criterion_evaluator.file_utils import (
            get_persona_evaluations_file_path,
        )

        for persona in self.evaluation_personas:
            persona_file = get_persona_evaluations_file_path(
                collection_name,
                self.pipeline_name,
                artifact_name,
                persona["id"],
                criteria_set_name,
                self.collections_root,
            )
            persona_evaluations = load_existing_evaluations(persona_file)
            if criterion_id not in persona_evaluations:
                return False
        return True

    def _run_criterion_evaluations(
        self, run_context: Dict[str, Any], criteria: List[Dict[str, Any]]
    ) -> None:
        if self.criterion_evaluator.config.get("answer_all_together", False):
            if self.evaluation_mode == "multi_persona":
                raise ValueError(
                    "answer_all_together is not supported with multi_persona evaluation"
                )
            self.criterion_evaluator.execute({**run_context, "criteria": criteria})
            return

        collection_name = run_context["collection_name"]
        artifact_name = run_context["artifact_name"]
        criteria_set_name = run_context["criteria_set_name"]
        merged_file = get_evaluations_file_path(
            collection_name,
            self.pipeline_name,
            artifact_name,
            criteria_set_name,
            self.collections_root,
        )
        merged_evaluations = load_existing_evaluations(merged_file)

        for idx, criterion in enumerate(criteria, 1):
            if self.stop_event and self.stop_event.is_set():
                raise InterruptedError("Review process stopped by user")

            criterion_id = criterion.get("id")
            if self._criterion_already_evaluated(
                collection_name, artifact_name, criteria_set_name, criterion_id
            ):
                continue

            if self.evaluation_mode == "multi_persona" and self.evaluation_personas:
                persona_results: Dict[str, Dict[str, Any]] = {}
                for persona in self.evaluation_personas:
                    if self.log_callback:
                        self.log_callback(
                            f"Persona {persona['label']} — criterion {idx}/{len(criteria)}",
                            "info",
                        )
                    result = self.criterion_evaluator.execute(
                        {
                            **run_context,
                            "criterion": criterion,
                            "persona_id": persona["id"],
                            "config_override": {
                                "system_prompt": persona.get("system_prompt")
                            },
                        }
                    )
                    persona_results[persona["id"]] = result

                merged_entry = merge_criterion_results(
                    persona_results,
                    self.evaluation_personas,
                    merge_strategy=self.merge_strategy,
                )
                if not self.keep_persona_scores:
                    merged_entry.pop("persona_scores", None)
                merged_evaluations[criterion_id] = merged_entry
                save_evaluations(merged_file, merged_evaluations)
                continue

            if self.log_callback:
                self.log_callback(f"Evaluating criterion {idx}/{len(criteria)}", "info")
            result = self.criterion_evaluator.execute(
                {**run_context, "criterion": criterion}
            )
            merged_evaluations[criterion_id] = result
            save_evaluations(merged_file, merged_evaluations)

        self._write_persona_manifest(collection_name, artifact_name, criteria_set_name)
