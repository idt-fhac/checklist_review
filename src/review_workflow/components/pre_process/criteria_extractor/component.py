from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

from src.core.criteria import criteria_set_stem, save_criteria_set_file
from src.core.providers import resolve_provider_config
from src.review_workflow.components.pre_process.criteria_extractor.extraction import (
    extract_criteria_from_text,
    read_document_text,
)
from src.review_workflow.engine.base import BaseComponent
from src.review_workflow.engine.run_paths import artifact_run_dir


class CriteriaExtractor(BaseComponent):
    def execute(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        collection_name = inputs["collection_name"]
        pipeline_name = inputs["pipeline_name"]
        artifact_name = inputs["artifact_name"]
        criteria_set_name = inputs.get("criteria_set_name", "extracted")
        collections_root = inputs["collections_root"]
        log_callback = inputs.get("log_callback")

        source = (self.config.get("source") or "artifact").lower()
        if source == "criteria_set":
            if log_callback:
                log_callback("Criteria extractor skipped (source=criteria_set)", "info")
            return {"status": "skipped", "reason": "Using workspace criteria set"}

        source_path = self._resolve_source_path(
            Path(collections_root),
            collection_name,
            artifact_name,
            source,
            inputs.get("criteria_source_name"),
        )
        if log_callback:
            log_callback(f"Extracting criteria from {source_path.name}", "info")

        provider_id = self.config.get("provider_id")
        if not provider_id:
            raise ValueError("criteria_extractor requires provider_id (set provider in pipeline YAML)")
        provider_config = resolve_provider_config(provider_id)

        document_text = read_document_text(source_path)
        scoring_default = self.config.get("scoring") or "pass_fail"
        raw_criteria = extract_criteria_from_text(
            document_text,
            provider_config,
            system_prompt=self.config.get("system_prompt"),
            scoring_default=scoring_default,
        )
        if not raw_criteria:
            raise ValueError("No criteria extracted from source document")

        run_dir = artifact_run_dir(
            Path(collections_root),
            collection_name,
            pipeline_name,
            artifact_name,
            criteria_set_stem(criteria_set_name),
        )
        run_dir.mkdir(parents=True, exist_ok=True)
        output_name = self.config.get("output") or "criteria.yaml"
        criteria_file = run_dir / Path(output_name).name

        criteria_set = save_criteria_set_file(
            criteria_file,
            {
                "name": criteria_set_stem(criteria_set_name) or "extracted",
                "criteria": raw_criteria,
            },
            source=str(source_path.name),
        )
        if log_callback:
            log_callback(f"Extracted {len(criteria_set['criteria'])} criteria", "info")

        return {
            "status": "completed",
            "criteria_file": str(criteria_file),
            "criteria_count": len(criteria_set["criteria"]),
        }

    def _resolve_source_path(
        self,
        collections_root: Path,
        collection_name: str,
        artifact_name: str,
        source: str,
        criteria_source_name: Optional[str],
    ) -> Path:
        from src.core import storage

        col_dir = collections_root / collection_name.strip().replace(" ", "_").lower()
        if not col_dir.exists():
            alt = collections_root / collection_name
            col_dir = alt if alt.exists() else col_dir
        source_dir = storage._source_pdf_dir(col_dir, create=False)
        md_dir = storage._source_md_dir(col_dir, create=False)

        if self.config.get("source_filename"):
            explicit = source_dir / self.config["source_filename"]
            if explicit.exists():
                return explicit

        if criteria_source_name:
            for directory in (source_dir, md_dir):
                if not directory.exists():
                    continue
                candidate = directory / criteria_source_name
                if candidate.exists():
                    return candidate

        if source == "artifact":
            for directory in (source_dir, md_dir):
                if not directory.exists():
                    continue
                for name in (artifact_name, f"{Path(artifact_name).stem}.pdf", f"{Path(artifact_name).stem}.md"):
                    candidate = directory / name
                    if candidate.exists():
                        return candidate
            raise FileNotFoundError(f"Artifact source not found for criteria extraction: {artifact_name}")

        if source == "rfp":
            if source_dir.exists():
                for pattern in ("*rfp*", "*RFP*", "*requirements*", "*Requirements*"):
                    matches = sorted(source_dir.glob(pattern))
                    for match in matches:
                        if match.suffix.lower() in (".pdf", ".md", ".txt"):
                            return match
                for name in ("rfp.pdf", "RFP.pdf", "criteria_source.pdf"):
                    candidate = source_dir / name
                    if candidate.exists():
                        return candidate
            raise FileNotFoundError(
                "RFP source not found. Add an RFP PDF to the collection source folder "
                "or set criteria_extractor.source_filename in the pipeline config."
            )

        raise ValueError(f"Unknown criteria_extractor source: {source}")
