import json
import shutil
from pathlib import Path

from src.core.criteria import criteria_set_stem
from typing import Dict, Any, Optional

from src.review_workflow.engine.base import BaseComponent


def _slug(name: str) -> str:
    return name.strip().replace(" ", "_").lower() or "process"


class DocumentLoader(BaseComponent):
    def execute(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        col_name = inputs["collection_name"]
        artifact_name = inputs["artifact_name"]
        pipeline_name = inputs["pipeline_name"]
        criteria_set_name = inputs.get("criteria_set_name")
        collections_root = inputs["collections_root"]

        col_dir = Path(collections_root) / _slug(col_name)
        if not col_dir.exists():
            raise FileNotFoundError(f"Collection '{col_name}' not found.")

        source_path = self._find_artifact(col_dir, artifact_name)
        if not source_path:
            raise FileNotFoundError(f"Artifact '{artifact_name}' not found in collection source")

        run_dir = col_dir / "review_runs" / _slug(pipeline_name)
        if criteria_set_name:
            criteria_clean = criteria_set_stem(criteria_set_name)
            run_dir = run_dir / _slug(criteria_clean)

        artifact_out_dir = run_dir / artifact_name
        artifact_out_dir.mkdir(parents=True, exist_ok=True)

        output_json = artifact_out_dir / "artifact_content.json"
        output_md = artifact_out_dir / "artifact_content.md"

        method = self.config.get("extraction_method", "Extracted Content")
        normalized_method = self._normalize_method(method)
        force_reextract = normalized_method == "force_reextract"

        if (
            normalized_method != "direct_upload"
            and not force_reextract
            and output_md.exists()
            and not self.config.get("force_execution", False)
        ):
            md_content = output_md.read_text(encoding="utf-8")
            if md_content.strip():
                if not output_json.exists():
                    metadata = {"method": method, "source_pdf": str(source_path)}
                    output_json.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
                if self.config.get("extract_pages_as_image", False) and source_path.suffix.lower() == ".pdf":
                    from src.core.pdf_processing import pdf_to_png
                    pdf_to_png(source_path, artifact_out_dir / "artifact_pages")
                return {"output_file": str(output_md), "output_type": "markdown", "status": "cached"}

        metadata = self._extract_content(col_dir, source_path, output_md, output_json, method)
        output_json.write_text(json.dumps(metadata, indent=2), encoding="utf-8")

        if self.config.get("extract_pages_as_image", False) and source_path.suffix.lower() == ".pdf":
            from src.core.pdf_processing import pdf_to_png
            pdf_to_png(source_path, artifact_out_dir / "artifact_pages")

        if normalized_method == "direct_upload":
            return {"output_file": str(output_json), "output_type": "direct_upload", "status": "generated"}

        return {"output_file": str(output_md), "output_type": "markdown", "status": "generated"}

    def _find_artifact(self, col_dir: Path, name: str) -> Optional[Path]:
        from src.core import storage

        source_dir = storage._source_pdf_dir(col_dir, create=False)
        candidate = source_dir / name
        if candidate.exists():
            return candidate
        if not name.lower().endswith(".pdf"):
            candidate = source_dir / f"{name}.pdf"
            if candidate.exists():
                return candidate
        return None

    def _normalize_method(self, method: str) -> str:
        method_map = {
            "Extracted Content": "extracted_content",
            "Force Re-Extract": "force_reextract",
            "Direct File Upload": "direct_upload",
        }
        return method_map.get(method, method)

    def _extract_content(
        self,
        col_dir: Path,
        pdf_path: Path,
        output_md: Path,
        output_json: Path,
        method: str,
    ) -> Dict[str, Any]:
        normalized_method = self._normalize_method(method)
        artifact_stem = pdf_path.stem

        if normalized_method == "extracted_content":
            from src.core import storage

            md_dir = storage._source_md_dir(col_dir, create=False)
            existing_md = md_dir / f"{artifact_stem}.md"
            if not existing_md.exists():
                raise FileNotFoundError(
                    f"Extracted markdown not found: {existing_md}. Process the artifact in Collections first."
                )
            shutil.copy2(existing_md, output_md)
            return {"method": method, "source_pdf": str(pdf_path)}

        if normalized_method == "force_reextract":
            from src.core.pdf_processing import pdf_to_markdown, PDFProcessingError

            try:
                pdf_to_markdown(pdf_path, output_md)
            except PDFProcessingError as e:
                raise RuntimeError(f"Force re-extract failed: {e}") from e
            return {"method": method, "source_pdf": str(pdf_path)}

        if normalized_method == "direct_upload":
            return {"method": method, "source_pdf": str(pdf_path)}

        raise ValueError(f"Unknown extraction method: {method}")
