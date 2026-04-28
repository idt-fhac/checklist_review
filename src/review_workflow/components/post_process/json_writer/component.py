import json
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List, Optional

from src.review_workflow.engine.base import BaseComponent


def _slug(name: str) -> str:
    return name.strip().replace(" ", "_").lower() or "process"


def _answer_entry(item: Dict[str, Any], save_details: bool) -> Dict[str, Any]:
    """One answer for JSON: when save_details is False only question_text and answer (True/False)."""
    out = {
        "question_id": item.get("question_id"),
        "question_text": item.get("question_text", "N/A"),
        "answer": item.get("answer") in (True, "yes", "true", "Yes", "True"),
    }
    if save_details and item.get("supporting_texts"):
        out["supporting_texts"] = item.get("supporting_texts")
    return out


class JsonWriter(BaseComponent):
    def execute(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        collection_name = inputs.get("collection_name")
        review_process_name = inputs.get("review_process_name")
        paper_name = inputs.get("paper_name")
        checklist_name = inputs.get("checklist_name")

        if not all([collection_name, review_process_name, paper_name]):
            raise ValueError("Missing required inputs: collection_name, review_process_name, or paper_name")

        collections_root = inputs.get("collections_root")
        if not collections_root:
            project_root = Path(__file__).resolve().parent.parent.parent.parent.parent.parent
            collections_root = project_root / "workspaces" / "guest" / "collections"
        collection_dir = Path(collections_root) / _slug(collection_name)
        paper_output_dir = collection_dir / "review_processes" / _slug(review_process_name)

        if checklist_name:
            checklist_name_clean = checklist_name.rstrip(".json") if checklist_name.endswith(".json") else checklist_name
            paper_output_dir = paper_output_dir / _slug(checklist_name_clean)

        paper_output_dir = paper_output_dir / paper_name
        answers_file = paper_output_dir / "answers.json"

        if not answers_file.exists():
            return {"status": "skipped", "reason": "No answers.json found"}

        with open(answers_file, "r", encoding="utf-8") as f:
            answers = json.load(f)

        if isinstance(answers, dict):
            answers = list(answers.values())

        save_details = self.config.get("save_details", False)
        token_usage = inputs.get("token_usage")
        payload = self._build_payload(
            paper_name,
            answers,
            review_process_name=review_process_name or "",
            checklist_name=checklist_name or "",
            save_details=save_details,
            token_usage=token_usage,
        )

        output_dir = paper_output_dir / "outputs"
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / "Output.json"

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)

        if token_usage is not None:
            token_usage_path = paper_output_dir / "token_usage.json"
            with open(token_usage_path, "w", encoding="utf-8") as f:
                json.dump(self._format_token_usage(token_usage), f, indent=2)

        return {
            "status": "success",
            "file_path": str(output_path),
            "output_filename": "Output.json",
        }

    def _build_payload(
        self,
        paper_name: str,
        answers: List[Dict[str, Any]],
        review_process_name: str = "",
        checklist_name: str = "",
        save_details: bool = False,
        token_usage: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        payload = {
            "paper_name": paper_name,
            "review_process": review_process_name,
            "checklist": checklist_name,
            "generated_at": timestamp,
            "answers": [_answer_entry(a, save_details) for a in answers],
        }
        if token_usage and (token_usage.get("total_tokens") or token_usage.get("by_model")):
            payload["metadata"] = {
                "token_usage": self._format_token_usage(token_usage),
            }
        return payload

    def _format_token_usage(self, token_usage: Dict[str, Any]) -> Dict[str, Any]:
        """User-friendly token usage: totals + per-model breakdown."""
        total_in = token_usage.get("total_input_tokens", 0)
        total_out = token_usage.get("total_output_tokens", 0)
        total = token_usage.get("total_tokens", 0)
        by_model = token_usage.get("by_model") or {}
        summary = {
            "total_input_tokens": total_in,
            "total_output_tokens": total_out,
            "total_tokens": total,
            "by_model": {
                model_id: {
                    "input_tokens": m.get("input_tokens", 0),
                    "output_tokens": m.get("output_tokens", 0),
                    "total_tokens": m.get("total_tokens", 0),
                }
                for model_id, m in by_model.items()
            },
        }
        return summary
