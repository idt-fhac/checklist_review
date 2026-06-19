import json
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional

from src.core.criteria import criteria_for_reviewer, load_criteria_set
from src.review_workflow.components.pre_process.paper_loader.component import PaperLoader
from src.review_workflow.components.evaluators.question_reviewer.component import QuestionReviewer
from src.review_workflow.components.post_process.md_writer.component import MdWriter
from src.review_workflow.components.post_process.pdf_writer.component import PdfWriter
from src.review_workflow.components.post_process.json_writer.component import JsonWriter
from src.review_workflow.engine.base import BaseComponent
from src.review_workflow.engine.token_usage import create_accumulator, get_summary

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("ReviewProcess")

class ReviewProcess:
    def __init__(self, process_definition: Dict[str, Any], stop_event=None, log_callback=None, collections_root: Path = None):
        self.process_name = process_definition.get("name")
        self.pipeline_id = process_definition.get("pipeline_id")
        self.config = process_definition.get("config")
        self.stop_event = stop_event
        self.log_callback = log_callback
        
        if collections_root is None:
            project_root = Path(__file__).resolve().parent.parent.parent.parent
            self.collections_root = project_root / "workspaces" / "guest" / "collections"
        else:
            self.collections_root = Path(collections_root)
        
        loader_def = (
            process_definition.get("artifact_loader")
            or process_definition.get("paper_loader")
            or {}
        )
        evaluator_def = (
            process_definition.get("criterion_evaluator")
            or process_definition.get("question_reviewer")
            or {}
        )

        self.artifact_loader = self._init_component(loader_def, PaperLoader)
        self.paper_loader = self.artifact_loader
        self.criterion_evaluator = self._init_component(evaluator_def, QuestionReviewer)
        self.question_reviewer = self.criterion_evaluator
        
        self.post_processors: List[BaseComponent] = []
        for pp_def in process_definition.get("post_processors", []):
            if pp_def.get("id") == "md_writer":
                self.post_processors.append(self._init_component(pp_def, MdWriter))
            elif pp_def.get("id") == "pdf_writer":
                self.post_processors.append(self._init_component(pp_def, PdfWriter))
            elif pp_def.get("id") == "json_writer":
                self.post_processors.append(self._init_component(pp_def, JsonWriter))

    def _init_component(self, def_dict: Dict[str, Any], cls: Any) -> BaseComponent:
        config = def_dict.get("config", {})
        return cls(config=config)
    
    def _slug(self, name: str) -> str:
        return name.strip().replace(" ", "_").lower() or "process"

    def _write_token_usage_file(
        self,
        collection_name: str,
        artifact_name: str,
        criteria_set_name: str,
        token_usage: Dict[str, Any],
        *,
        paper_name: str = None,
        checklist_name: str = None,
    ) -> None:
        artifact_name = artifact_name or paper_name
        criteria_set_name = criteria_set_name or checklist_name
        if token_usage is None:
            return
        artifact_dir = (
            self.collections_root
            / self._slug(collection_name)
            / "review_processes"
            / self._slug(self.process_name)
        )
        if criteria_set_name:
            criteria_clean = criteria_set_name.rstrip(".json") if criteria_set_name.endswith(".json") else criteria_set_name
            artifact_dir = artifact_dir / self._slug(criteria_clean)
        artifact_dir = artifact_dir / artifact_name
        artifact_dir.mkdir(parents=True, exist_ok=True)
        token_usage_path = artifact_dir / "token_usage.json"
        with open(token_usage_path, "w", encoding="utf-8") as f:
            json.dump(token_usage, f, indent=2)

    def execute(
        self,
        collection_name: str,
        artifact_name: str = None,
        criteria_set_name: str = None,
        *,
        paper_name: str = None,
        checklist_name: str = None,
        artifact_index: int = None,
        paper_index: int = None,
        total_artifacts: int = None,
        total_papers: int = None,
    ):
        artifact_name = artifact_name or paper_name
        criteria_set_name = criteria_set_name or checklist_name
        artifact_index = artifact_index if artifact_index is not None else paper_index
        total_artifacts = total_artifacts if total_artifacts is not None else total_papers

        if not artifact_name:
            raise ValueError("artifact_name (or paper_name) is required")
        if not criteria_set_name:
            raise ValueError("criteria_set_name (or checklist_name) is required")

        if self.stop_event and self.stop_event.is_set():
            logger.info(f"Stop event detected at start of execution for {artifact_name}")
            raise InterruptedError("Review process stopped by user")
        
        logger.info(f"Starting Review Process: {self.process_name}")
        logger.info(
            f"Collection: {collection_name}, Artifact: {artifact_name}, Criteria set: {criteria_set_name}"
        )

        col_dir = self.collections_root / self._slug(collection_name)
        from src.core import storage
        artifact_stem = Path(artifact_name).stem
        meta_dir = storage._source_metadata_dir(col_dir, create=False)
        artifact_json_path = (meta_dir / f"{artifact_stem}.json") if meta_dir.exists() else (col_dir / "source_extracted" / f"{artifact_stem}.json")
        artifact_title = artifact_name
        if artifact_json_path.exists():
            with open(artifact_json_path, "r", encoding="utf-8") as f:
                artifact_metadata = json.load(f)
                artifact_title = artifact_metadata.get("title", artifact_name)
        
        if artifact_index and total_artifacts:
            title_line = f"{'='*15}\n\n{artifact_title} ({artifact_index}/{total_artifacts})"
        else:
            title_line = f"{'='*15}\n\n{artifact_title}"
        
        if self.log_callback:
            self.log_callback(title_line, "info")

        if self.stop_event and self.stop_event.is_set():
            raise InterruptedError("Review process stopped by user")
        
        logger.info("Step 1: Loading criteria set")
        
        workspace_dir = self.collections_root.parent
        criteria_dir = workspace_dir / "checklists"
        
        criteria_set_name_clean = criteria_set_name
        if criteria_set_name_clean.endswith('.json'):
            criteria_set_name_clean = criteria_set_name_clean[:-5]
        
        criteria_json_path = criteria_dir / f"{criteria_set_name_clean}.json"
        if not criteria_json_path.exists():
            criteria_json_path = criteria_dir / criteria_set_name
            if not criteria_json_path.exists():
                available = [f.name for f in criteria_dir.glob("*.json")] if criteria_dir.exists() else []
                raise FileNotFoundError(
                    f"Criteria set '{criteria_set_name}' not found in {criteria_dir}. "
                    f"Available criteria sets: {available}"
                )
        
        with open(criteria_json_path, "r", encoding="utf-8") as f:
            raw_criteria_data = json.load(f)
        
        criteria_set = load_criteria_set(raw_criteria_data, name=criteria_set_name_clean)
        criteria_list = criteria_for_reviewer(criteria_set)
        
        if not criteria_list:
            raise ValueError(f"No criteria found in criteria set '{criteria_set_name}'")
        
        criteria_content_data = {
            "type": "list",
            "content": criteria_list,
        }

        if self.stop_event and self.stop_event.is_set():
            raise InterruptedError("Review process stopped by user")
        
        logger.info("Step 2: Loading artifact")
        artifact_result = self.artifact_loader.execute({
            "collection_name": collection_name,
            "paper_name": artifact_name,
            "artifact_name": artifact_name,
            "review_process_name": self.process_name,
            "checklist_name": criteria_set_name,
            "criteria_set_name": criteria_set_name,
            "collections_root": self.collections_root,
            "log_callback": None
        })
        
        artifact_output_path = artifact_result.get("output_file")
        output_type = artifact_result.get("output_type", "markdown")
        
        if not artifact_output_path:
            raise ValueError("Artifact loader did not return output_file path")
        
        if output_type == "direct_upload":
            raise ValueError(
                "Direct File Upload method is not yet implemented. "
                "Please use 'Extracted Content' method."
            )
        
        md_file_path = Path(artifact_output_path)
        if not md_file_path.exists():
            raise FileNotFoundError(f"Artifact markdown file not found: {md_file_path}")
        
        md_content = md_file_path.read_text(encoding="utf-8")
        
        if not md_content or not md_content.strip():
            raise ValueError(f"Artifact content is empty in {md_file_path}")
        
        if self.log_callback:
            self.log_callback("Artifact loaded", "info")
        
        logger.info("Step 3: Evaluating criteria")
        criteria_items = criteria_content_data.get('content', [])
        
        answer_all_together = self.criterion_evaluator.config.get("answer_all_together", False)
        
        if self.log_callback:
            self.log_callback("Criteria set loaded", "info")
        
        token_usage_accumulator = create_accumulator()
        run_context = {
            "collection_name": collection_name,
            "review_process_name": self.process_name,
            "paper_name": artifact_name,
            "artifact_name": artifact_name,
            "checklist_name": criteria_set_name,
            "criteria_set_name": criteria_set_name,
            "collections_root": self.collections_root,
            "log_callback": self.log_callback,
            "token_usage_accumulator": token_usage_accumulator,
        }

        if answer_all_together:
            logger.info(f"Evaluating {len(criteria_items)} criteria together in a single call.")
            if self.log_callback:
                self.log_callback(f"Answering all {len(criteria_items)} criteria together", "info")
            
            if self.stop_event and self.stop_event.is_set():
                logger.info(f"Stop event detected during criterion evaluation for {artifact_name}")
                raise InterruptedError("Review process stopped by user")
            
            self.criterion_evaluator.execute({**run_context, "questions": criteria_items})
        else:
            logger.info(f"Evaluating {len(criteria_items)} criteria separately.")
            for idx, criterion in enumerate(criteria_items, 1):
                if self.stop_event and self.stop_event.is_set():
                    logger.info(f"Stop event detected during criterion evaluation for {artifact_name}")
                    raise InterruptedError("Review process stopped by user")
                
                if self.log_callback:
                    self.log_callback(f"Evaluating criterion {idx}/{len(criteria_items)}", "info")
                
                self.criterion_evaluator.execute({**run_context, "question": criterion})

        logger.info("Step 4: Post Processing")
        token_usage = get_summary(token_usage_accumulator)
        self._write_token_usage_file(collection_name, artifact_name, criteria_set_name, token_usage)
        for pp in self.post_processors:
            pp.execute({
                "collection_name": collection_name,
                "review_process_name": self.process_name,
                "paper_name": artifact_name,
                "artifact_name": artifact_name,
                "checklist_name": criteria_set_name,
                "criteria_set_name": criteria_set_name,
                "collections_root": self.collections_root,
                "log_callback": self.log_callback,
                "token_usage": token_usage,
            })
        
        if self.log_callback:
            self.log_callback("Review ended", "info")
        
        logger.info(f"Review Process Completed for {artifact_name}")
        return {"token_usage": token_usage}
