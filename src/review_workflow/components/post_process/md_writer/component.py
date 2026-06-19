import json
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List
from src.core.criteria import criteria_set_stem

from src.review_workflow.engine.base import BaseComponent

def _slug(name: str) -> str:
    return name.strip().replace(" ", "_").lower() or "process"

def _esc(s: str) -> str:
    return (s or "").replace("|", "\\|").replace("\n", " ").strip()

class MdWriter(BaseComponent):
    def execute(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        collection_name = inputs.get("collection_name")
        pipeline_name = inputs.get("pipeline_name")
        artifact_name = inputs.get("artifact_name")
        criteria_set_name = inputs.get("criteria_set_name")

        if not all([collection_name, pipeline_name, artifact_name]):
            raise ValueError("Missing required inputs: collection_name, pipeline_name, or artifact_name")

        collections_root = inputs.get("collections_root")
        if not collections_root:
            project_root = Path(__file__).resolve().parent.parent.parent.parent.parent.parent
            collections_root = project_root / "workspaces" / "guest" / "collections"
        collection_dir = Path(collections_root) / _slug(collection_name)
        paper_output_dir = collection_dir / "review_runs" / _slug(pipeline_name)

        if criteria_set_name:
            criteria_set_name_clean = criteria_set_stem(criteria_set_name)
            paper_output_dir = paper_output_dir / _slug(criteria_set_name_clean)

        paper_output_dir = paper_output_dir / artifact_name
        evaluations_file = paper_output_dir / "evaluations.json"

        if not evaluations_file.exists():
            return {"status": "skipped", "reason": "No evaluations.json found"}

        with open(evaluations_file, "r", encoding="utf-8") as f:
            evaluations = json.load(f)

        if isinstance(evaluations, dict):
            evaluations = list(evaluations.values())

        save_details = self.config.get("save_details", False)
        md_content = self._generate_markdown(
            artifact_name, evaluations,
            pipeline_name=pipeline_name or "",
            criteria_set_name=criteria_set_name or "",
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
        artifact_name: str,
        evaluations: List[Dict[str, Any]],
        pipeline_name: str = "",
        criteria_set_name: str = "",
        save_details: bool = False,
    ) -> str:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        md = f"# Review Report: {artifact_name}\n\n"
        if pipeline_name:
            md += f"**Review Process:** {pipeline_name}\n\n"
        if criteria_set_name:
            md += f"**Checklist:** {criteria_set_name}\n\n"
        md += f"**Generated on:** {timestamp}\n\n---\n\n"
        md += "## Detailed Review\n\n"

        if not save_details:
            md += "| Question | Answer |\n"
            md += "| :--- | :---: |\n"
            for item in evaluations:
                q = _esc(item.get("criterion_text", "N/A"))
                ans = "Yes" if item.get("answer") in (True, "yes", "true", "Yes", "True") else "No"
                md += f"| {q} | **{ans}** |\n"
            md += "\n"
            return md

        for item in evaluations:
            q = _esc(item.get("criterion_text", "N/A"))
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