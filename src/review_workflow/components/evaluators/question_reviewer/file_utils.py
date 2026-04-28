import json
from pathlib import Path
from typing import Dict, Any

from src.review_workflow.components.evaluators.question_reviewer.helpers import get_project_root, slug


def get_paper_file_paths(collection_name: str, review_process_name: str, paper_name: str, checklist_name: str = None, collections_root: Path = None):
    if collections_root is None:
        project_root = get_project_root()
        collections_root = project_root / "workspaces" / "guest" / "collections"
    paper_dir = Path(collections_root) / slug(collection_name) / "review_processes" / slug(review_process_name)
    
    # If checklist_name is provided, add it to the path
    if checklist_name:
        checklist_name_clean = checklist_name
        if checklist_name_clean.endswith('.json'):
            checklist_name_clean = checklist_name_clean[:-5]
        paper_dir = paper_dir / slug(checklist_name_clean)
    
    paper_dir = paper_dir / paper_name
    return paper_dir / "paper_content.json", paper_dir / "paper_content.md"


def get_answer_file_path(collection_name: str, review_process_name: str, paper_name: str, checklist_name: str = None, collections_root: Path = None) -> Path:
    if collections_root is None:
        project_root = get_project_root()
        collections_root = project_root / "workspaces" / "guest" / "collections"
    paper_output_dir = Path(collections_root) / slug(collection_name) / "review_processes" / slug(review_process_name)
    
    # If checklist_name is provided, add it to the path
    if checklist_name:
        checklist_name_clean = checklist_name
        if checklist_name_clean.endswith('.json'):
            checklist_name_clean = checklist_name_clean[:-5]
        paper_output_dir = paper_output_dir / slug(checklist_name_clean)
    
    paper_output_dir = paper_output_dir / paper_name
    paper_output_dir.mkdir(parents=True, exist_ok=True)
    return paper_output_dir / "answers.json"


def load_existing_answers(answers_file: Path) -> Dict[str, Any]:
    if not answers_file.exists():
        return {}
    try:
        with open(answers_file, "r", encoding="utf-8") as f:
            content = json.load(f)
            if isinstance(content, list):
                return {item.get("question_id"): item for item in content}
            return content if isinstance(content, dict) else {}
    except (json.JSONDecodeError, IOError):
        return {}


def save_answers(answers_file: Path, answers: Dict[str, Any]):
    with open(answers_file, "w", encoding="utf-8") as f:
        json.dump(list(answers.values()), f, indent=2)
