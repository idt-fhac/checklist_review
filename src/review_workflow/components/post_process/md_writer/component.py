import json
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List

from src.review_workflow.engine.base import BaseComponent

def _slug(name: str) -> str:
    return name.strip().replace(" ", "_").lower() or "process"

def _esc(s: str) -> str:
    return (s or "").replace("|", "\\|").replace("\n", " ").strip()

class MdWriter(BaseComponent):
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
        md_content = self._generate_markdown(
            paper_name, answers,
            review_process_name=review_process_name or "",
            checklist_name=checklist_name or "",
            save_details=save_details,
        )

        output_dir = paper_output_dir / "outputs"
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / "Output.md"

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(md_content)

        return {
            "status": "success",
            "file_path": str(output_path),
            "output_filename": "Output.md",
        }

    def _generate_markdown(
        self,
        paper_name: str,
        answers: List[Dict[str, Any]],
        review_process_name: str = "",
        checklist_name: str = "",
        save_details: bool = False,
    ) -> str:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        md = f"# Review Report: {paper_name}\n\n"
        if review_process_name:
            md += f"**Review Process:** {review_process_name}\n\n"
        if checklist_name:
            md += f"**Checklist:** {checklist_name}\n\n"
        md += f"**Generated on:** {timestamp}\n\n---\n\n"
        md += "## Detailed Review\n\n"

        if not save_details:
            md += "| Question | Answer |\n"
            md += "| :--- | :---: |\n"
            for item in answers:
                q = _esc(item.get("question_text", "N/A"))
                ans = "Yes" if item.get("answer") in (True, "yes", "true", "Yes", "True") else "No"
                md += f"| {q} | **{ans}** |\n"
            md += "\n"
            return md

        for item in answers:
            q = _esc(item.get("question_text", "N/A"))
            ans = "Yes" if item.get("answer") in (True, "yes", "true", "Yes", "True") else "No"
            md += f"### {q}\n\n"
            md += f"**Answer:** **{ans}**\n\n"
            supporting = item.get("supporting_texts") or []
            if supporting:
                md += "#### Supporting evidence\n\n"
                for idx, st in enumerate(supporting, 1):
                    page = st.get("page_number", "?")
                    crop = (st.get("text_crop") or "").strip()
                    expl = (st.get("short_explanation") or "").strip()
                    if crop:
                        md += f"**Reference {idx}** (Page {page}):\n\n"
                        md += f"> {_esc(crop)}\n\n"
                    if expl:
                        md += f"*Explanation:* {_esc(expl)}\n\n"
            md += "---\n\n"
        return md
