import json
import logging
from pathlib import Path
from typing import Dict, Any, List

from src.core.criteria import criteria_for_evaluator, criteria_set_stem, find_criteria_set_path, load_criteria_set_file
from src.review_workflow.components.pre_process.document_loader.component import DocumentLoader
from src.review_workflow.components.evaluators.criterion_evaluator.component import CriterionEvaluator
from src.review_workflow.components.post_process.md_writer.component import MdWriter
from src.review_workflow.components.post_process.pdf_writer.component import PdfWriter
from src.review_workflow.components.post_process.json_writer.component import JsonWriter
from src.review_workflow.engine.base import BaseComponent
from src.review_workflow.engine.token_usage import create_accumulator, get_summary

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("ReviewProcess")


class ReviewProcess:
    def __init__(self, process_definition: Dict[str, Any], stop_event=None, log_callback=None, collections_root: Path = None):
        self.pipeline_name = process_definition["name"]
        self.pipeline_id = process_definition.get("pipeline_id")
        self.stop_event = stop_event
        self.log_callback = log_callback

        if collections_root is None:
            project_root = Path(__file__).resolve().parent.parent.parent.parent
            self.collections_root = project_root / "workspaces" / "guest" / "collections"
        else:
            self.collections_root = Path(collections_root)

        self.document_loader = self._init_component(process_definition.get("document_loader", {}), DocumentLoader)
        self.criterion_evaluator = self._init_component(process_definition.get("criterion_evaluator", {}), CriterionEvaluator)

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
        (artifact_dir / "token_usage.json").write_text(json.dumps(token_usage, indent=2), encoding="utf-8")

    def execute(
        self,
        collection_name: str,
        artifact_name: str,
        criteria_set_name: str,
        artifact_index: int | None = None,
        total_artifacts: int | None = None,
    ):
        if self.stop_event and self.stop_event.is_set():
            raise InterruptedError("Review process stopped by user")

        logger.info(
            "Starting pipeline %s: collection=%s artifact=%s criteria_set=%s",
            self.pipeline_name, collection_name, artifact_name, criteria_set_name,
        )

        col_dir = self.collections_root / self._slug(collection_name)
        from src.core import storage
        artifact_stem = Path(artifact_name).stem
        meta_dir = storage._source_metadata_dir(col_dir, create=False)
        meta_path = meta_dir / f"{artifact_stem}.json"
        artifact_title = artifact_name
        if meta_path.exists():
            artifact_title = json.loads(meta_path.read_text(encoding="utf-8")).get("title", artifact_name)

        if self.log_callback:
            if artifact_index and total_artifacts:
                self.log_callback(f"{'='*15}\n\n{artifact_title} ({artifact_index}/{total_artifacts})", "info")
            else:
                self.log_callback(f"{'='*15}\n\n{artifact_title}", "info")

        criteria_dir = self.collections_root.parent / "criteria_sets"
        criteria_path = find_criteria_set_path(criteria_dir, criteria_set_name)
        if criteria_path is None:
            raise FileNotFoundError(f"Criteria set '{criteria_set_name}' not found in {criteria_dir}")

        criteria_set = load_criteria_set_file(criteria_path)
        criteria = criteria_for_evaluator(criteria_set)
        if not criteria:
            raise ValueError(f"No criteria in criteria set '{criteria_set_name}'")

        if self.log_callback:
            self.log_callback("Criteria set loaded", "info")

        artifact_result = self.document_loader.execute({
            "collection_name": collection_name,
            "artifact_name": artifact_name,
            "pipeline_name": self.pipeline_name,
            "criteria_set_name": criteria_set_name,
            "collections_root": self.collections_root,
        })

        output_path = artifact_result.get("output_file")
        if not output_path or not Path(output_path).exists():
            raise FileNotFoundError("Document loader did not produce artifact content")

        if self.log_callback:
            self.log_callback("Artifact loaded", "info")

        token_usage_accumulator = create_accumulator()
        run_context = {
            "collection_name": collection_name,
            "pipeline_name": self.pipeline_name,
            "artifact_name": artifact_name,
            "criteria_set_name": criteria_set_name,
            "collections_root": self.collections_root,
            "log_callback": self.log_callback,
            "token_usage_accumulator": token_usage_accumulator,
        }

        if self.criterion_evaluator.config.get("answer_all_together", False):
            self.criterion_evaluator.execute({**run_context, "criteria": criteria})
        else:
            for idx, criterion in enumerate(criteria, 1):
                if self.stop_event and self.stop_event.is_set():
                    raise InterruptedError("Review process stopped by user")
                if self.log_callback:
                    self.log_callback(f"Evaluating criterion {idx}/{len(criteria)}", "info")
                self.criterion_evaluator.execute({**run_context, "criterion": criterion})

        token_usage = get_summary(token_usage_accumulator)
        self._write_token_usage_file(collection_name, artifact_name, criteria_set_name, token_usage)

        for pp in self.post_processors:
            pp.execute({
                "collection_name": collection_name,
                "pipeline_name": self.pipeline_name,
                "artifact_name": artifact_name,
                "criteria_set_name": criteria_set_name,
                "collections_root": self.collections_root,
                "log_callback": self.log_callback,
                "token_usage": token_usage,
            })

        if self.log_callback:
            self.log_callback("Review ended", "info")

        return {"token_usage": token_usage}
