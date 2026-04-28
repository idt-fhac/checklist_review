import json
import shutil
from pathlib import Path
from typing import Dict, Any, Optional

from src.review_workflow.engine.base import BaseComponent

def _slug(name: str) -> str:
    return name.strip().replace(" ", "_").lower() or "process"

class PaperLoader(BaseComponent):
    def execute(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        col_name = inputs.get("collection_name")
        pap_name = inputs.get("paper_name")
        proc_name = inputs.get("review_process_name")
        checklist_name = inputs.get("checklist_name")
        collections_root = inputs.get("collections_root")

        if not all([col_name, pap_name, proc_name, collections_root]):
            raise ValueError("Missing required inputs: collection_name, paper_name, review_process_name, collections_root")

        col_dir = Path(collections_root) / _slug(col_name)
        
        if not col_dir.exists():
            raise FileNotFoundError(f"Collection '{col_name}' not found.")

        source_path = self._find_paper(col_dir, pap_name)
        if not source_path:
            raise FileNotFoundError(f"Paper '{pap_name}' not found in {col_dir / 'source'}")

        proc_dir = col_dir / "review_processes" / _slug(proc_name)
        
        # If checklist_name is provided, add it to the path
        if checklist_name:
            checklist_name_clean = checklist_name
            if checklist_name_clean.endswith('.json'):
                checklist_name_clean = checklist_name_clean[:-5]
            proc_dir = proc_dir / _slug(checklist_name_clean)
        
        paper_out_dir = proc_dir / pap_name
        paper_out_dir.mkdir(parents=True, exist_ok=True)
        
        output_json = paper_out_dir / "paper_content.json"
        output_md = paper_out_dir / "paper_content.md"
        
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
                if output_json.exists():
                    with open(output_json, "r", encoding="utf-8") as f:
                        metadata = json.load(f)
                else:
                    metadata = {
                        "method": method,
                        "source_pdf": str(source_path),
                    }
                    with open(output_json, "w", encoding="utf-8") as f:
                        json.dump(metadata, f, indent=2)
                
                if self.config.get("extract_pages_as_image", False) and source_path.suffix.lower() == ".pdf":
                    from src.core.pdf_processing import pdf_to_png
                    pdf_to_png(source_path, paper_out_dir / "paper_pages")
                return {
                    "output_file": str(output_md),
                    "output_type": "markdown",
                    "status": "cached"
                }

        method = self.config.get("extraction_method", "Extracted Content")
        metadata = self._extract_content(col_dir, source_path, pap_name, output_md, output_json, method, None)

        with open(output_json, "w", encoding="utf-8") as f:
            json.dump(metadata, f, indent=2)

        if self.config.get("extract_pages_as_image", False) and source_path.suffix.lower() == ".pdf":
            from src.core.pdf_processing import pdf_to_png
            paper_pages_dir = paper_out_dir / "paper_pages"
            pdf_to_png(source_path, paper_pages_dir)

        method_normalized = self._normalize_method(method)
        if method_normalized == "direct_upload":
            return {
                "output_file": str(output_json),
                "output_type": "direct_upload",
                "status": "generated"
            }
        
        return {
            "output_file": str(output_md),
            "output_type": "markdown",
            "status": "generated"
        }

    def _find_paper(self, col_dir: Path, name: str) -> Optional[Path]:
        from src.core import storage
        source_dir = storage._source_pdf_dir(col_dir, create=False)
        if not source_dir.exists():
            source_dir = col_dir / "source"  # legacy
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

    def _extract_content(self, col_dir: Path, pdf_path: Path, paper_name: str, output_md: Path, output_json: Path, method: str, log_callback=None) -> Dict[str, Any]:
        normalized_method = self._normalize_method(method)
        paper_stem = pdf_path.stem
        
        if normalized_method == "extracted_content":
            from src.core import storage
            md_dir = storage._source_md_dir(col_dir, create=False)
            if not md_dir.exists():
                md_dir = col_dir / "source_extracted"  # legacy
            existing_md = md_dir / f"{paper_stem}.md"
            if not existing_md.exists():
                raise FileNotFoundError(
                    f"Extracted markdown file not found: {existing_md}. "
                    f"Please process the paper first in the collection module."
                )
            
            shutil.copy2(existing_md, output_md)
            
            return {
                "method": method,
                "source_pdf": str(pdf_path),
            }

        if normalized_method == "force_reextract":
            from src.core.pdf_processing import pdf_to_markdown, PDFProcessingError
            try:
                pdf_to_markdown(pdf_path, output_md)
            except PDFProcessingError as e:
                raise RuntimeError(f"Force re-extract failed: {e}") from e
            return {
                "method": method,
                "source_pdf": str(pdf_path),
            }
            
        elif normalized_method == "direct_upload":
            return {
                "method": method,
                "source_pdf": str(pdf_path),
            }
            
        else:
            raise ValueError(f"Unknown extraction method: {method}")