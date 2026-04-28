import json
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional

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
        self.config = process_definition.get("config")
        self.stop_event = stop_event
        self.log_callback = log_callback
        
        # Determine collections_root
        if collections_root is None:
            project_root = Path(__file__).resolve().parent.parent.parent.parent
            self.collections_root = project_root / "workspaces" / "guest" / "collections"
        else:
            self.collections_root = Path(collections_root)
        
        self.paper_loader = self._init_component(
            process_definition.get("paper_loader", {}), PaperLoader
        )
        self.question_reviewer = self._init_component(
            process_definition.get("question_reviewer", {}), QuestionReviewer
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
        config = def_dict.get("config", {})
        return cls(config=config)
    
    def _slug(self, name: str) -> str:
        return name.strip().replace(" ", "_").lower() or "process"

    def _write_token_usage_file(self, collection_name: str, paper_name: str, checklist_name: str, token_usage: Dict[str, Any]) -> None:
        """Write token_usage.json to collections/.../process_name/checklist_name/paper_name/token_usage.json."""
        if token_usage is None:
            return
        paper_dir = (
            self.collections_root
            / self._slug(collection_name)
            / "review_processes"
            / self._slug(self.process_name)
        )
        if checklist_name:
            checklist_clean = checklist_name.rstrip(".json") if checklist_name.endswith(".json") else checklist_name
            paper_dir = paper_dir / self._slug(checklist_clean)
        paper_dir = paper_dir / paper_name
        paper_dir.mkdir(parents=True, exist_ok=True)
        token_usage_path = paper_dir / "token_usage.json"
        with open(token_usage_path, "w", encoding="utf-8") as f:
            json.dump(token_usage, f, indent=2)

    def execute(self, collection_name: str, paper_name: str, checklist_name: str, paper_index: int = None, total_papers: int = None):
        if self.stop_event and self.stop_event.is_set():
            logger.info(f"Stop event detected at start of execution for {paper_name}")
            raise InterruptedError("Review process stopped by user")
        
        logger.info(f"Starting Review Process: {self.process_name}")
        logger.info(f"Collection: {collection_name}, Paper: {paper_name}, Checklist: {checklist_name}")

        col_dir = self.collections_root / self._slug(collection_name)
        from src.core import storage
        paper_stem = Path(paper_name).stem
        meta_dir = storage._source_metadata_dir(col_dir, create=False)
        paper_json_path = (meta_dir / f"{paper_stem}.json") if meta_dir.exists() else (col_dir / "source_extracted" / f"{paper_stem}.json")
        paper_title = paper_name
        if paper_json_path.exists():
            with open(paper_json_path, "r", encoding="utf-8") as f:
                paper_metadata = json.load(f)
                paper_title = paper_metadata.get("title", paper_name)
        
        if paper_index and total_papers:
            title_line = f"{'='*15}\n\n{paper_title} ({paper_index}/{total_papers})"
        else:
            title_line = f"{'='*15}\n\n{paper_title}"
        
        if self.log_callback:
            self.log_callback(title_line, "info")

        if self.stop_event and self.stop_event.is_set():
            raise InterruptedError("Review process stopped by user")
        
        logger.info("Step 1: Loading Checklist")
        
        # Checklists are now in the active workspace's checklists directory
        from src.core.workspace import get_checklists_dir
        # If we have collections_root, we can derive the workspace root
        workspace_dir = self.collections_root.parent
        checklist_dir = workspace_dir / "checklists"
        
        checklist_name_clean = checklist_name
        if checklist_name_clean.endswith('.json'):
            checklist_name_clean = checklist_name_clean[:-5]
        
        checklist_json_path = checklist_dir / f"{checklist_name_clean}.json"
        if not checklist_json_path.exists():
            checklist_json_path = checklist_dir / checklist_name
            if not checklist_json_path.exists():
                available = [f.name for f in checklist_dir.glob("*.json")] if checklist_dir.exists() else []
                raise FileNotFoundError(
                    f"Checklist '{checklist_name}' not found in {checklist_dir}. "
                    f"Available checklists: {available}"
                )
        
        with open(checklist_json_path, "r", encoding="utf-8") as f:
            checklist_data = json.load(f)
        
        questions = []
        if isinstance(checklist_data, dict):
            if "questions" in checklist_data:
                questions = checklist_data["questions"]
            elif "content" in checklist_data:
                questions = checklist_data["content"]
            elif "items" in checklist_data:
                questions = checklist_data["items"]
        elif isinstance(checklist_data, list):
            questions = checklist_data
        
        checklist_content_list = []
        for i, q in enumerate(questions):
            if isinstance(q, dict):
                question_id = q.get("id", f"q{i+1}")
                question_text = q.get("text", q.get("question", str(q)))
            else:
                question_id = f"q{i+1}"
                question_text = str(q)
            
            if question_text:
                checklist_content_list.append({
                    "id": question_id,
                    "text": question_text
                })
        
        if not checklist_content_list:
            raise ValueError(f"No questions found in checklist '{checklist_name}'")
        
        checklist_content_data = {
            "type": "list",
            "content": checklist_content_list
        }

        if self.stop_event and self.stop_event.is_set():
            raise InterruptedError("Review process stopped by user")
        
        logger.info("Step 2: Loading Paper")
        paper_result = self.paper_loader.execute({
            "collection_name": collection_name,
            "paper_name": paper_name,
            "review_process_name": self.process_name,
            "checklist_name": checklist_name,
            "collections_root": self.collections_root,
            "log_callback": None
        })
        
        paper_output_path = paper_result.get("output_file")
        output_type = paper_result.get("output_type", "markdown")
        
        if not paper_output_path:
            raise ValueError("Paper loader did not return output_file path")
        
        if output_type == "direct_upload":
            raise ValueError(
                "Direct File Upload method is not yet implemented. "
                "Please use 'Extracted Content' method."
            )
        
        md_file_path = Path(paper_output_path)
        if not md_file_path.exists():
            raise FileNotFoundError(f"Paper markdown file not found: {md_file_path}")
        
        md_content = md_file_path.read_text(encoding="utf-8")
        
        if not md_content or not md_content.strip():
            raise ValueError(f"Paper content is empty in {md_file_path}")
        
        if self.log_callback:
            self.log_callback("Paper loaded", "info")
        
        logger.info("Step 3: Reviewing Questions")
        questions_list = checklist_content_data.get('content', [])
        
        answer_all_together = self.question_reviewer.config.get("answer_all_together", False)
        
        if self.log_callback:
            self.log_callback("Checklist loaded", "info")
        
        token_usage_accumulator = create_accumulator()
        if answer_all_together:
            # Answer all questions together in a single call
            logger.info(f"Reviewing {len(questions_list)} questions together in a single call.")
            if self.log_callback:
                self.log_callback(f"Answering all {len(questions_list)} questions together", "info")
            
            if self.stop_event and self.stop_event.is_set():
                logger.info(f"Stop event detected during question review for {paper_name}")
                raise InterruptedError("Review process stopped by user")
            
            self.question_reviewer.execute({
                "collection_name": collection_name,
                "review_process_name": self.process_name,
                "paper_name": paper_name,
                "checklist_name": checklist_name,
                "questions": questions_list,  # Pass all questions as a list
                "collections_root": self.collections_root,
                "log_callback": self.log_callback,
                "token_usage_accumulator": token_usage_accumulator,
            })
        else:
            # Answer questions one by one (original behavior)
            logger.info(f"Reviewing {len(questions_list)} questions separately.")
            for idx, question in enumerate(questions_list, 1):
                if self.stop_event and self.stop_event.is_set():
                    logger.info(f"Stop event detected during question review for {paper_name}")
                    raise InterruptedError("Review process stopped by user")
                
                if self.log_callback:
                    self.log_callback(f"Answering question {idx}/{len(questions_list)}", "info")
                
                self.question_reviewer.execute({
                    "collection_name": collection_name,
                    "review_process_name": self.process_name,
                    "paper_name": paper_name,
                    "checklist_name": checklist_name,
                    "question": question,
                    "collections_root": self.collections_root,
                    "log_callback": self.log_callback,
                    "token_usage_accumulator": token_usage_accumulator,
                })

        logger.info("Step 4: Post Processing")
        token_usage = get_summary(token_usage_accumulator)
        self._write_token_usage_file(collection_name, paper_name, checklist_name, token_usage)
        for pp in self.post_processors:
            pp.execute({
                "collection_name": collection_name,
                "review_process_name": self.process_name,
                "paper_name": paper_name,
                "checklist_name": checklist_name,
                "collections_root": self.collections_root,
                "log_callback": self.log_callback,
                "token_usage": token_usage,
            })
        
        if self.log_callback:
            self.log_callback("Review ended", "info")
        
        logger.info(f"Review Process Completed for {paper_name}")
        return {"token_usage": token_usage}
