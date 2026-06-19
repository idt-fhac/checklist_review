import json
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List
from src.core.criteria import criteria_set_stem

from src.review_workflow.engine.base import BaseComponent


def _slug(name: str) -> str:
    return name.strip().replace(" ", "_").lower() or "process"


class PdfWriter(BaseComponent):
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

        output_dir = paper_output_dir / "outputs"
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / "Output.pdf"

        save_details = self.config.get("save_details", False)
        self._generate_pdf(
            artifact_name,
            evaluations,
            output_path,
            pipeline_name=pipeline_name or "",
            criteria_set_name=criteria_set_name or "",
            save_details=save_details,
        )

        return {
            "status": "success",
            "file_path": str(output_path),
            "output_filename": "Output.pdf",
        }

    def _generate_pdf(
        self,
        artifact_name: str,
        evaluations: List[Dict[str, Any]],
        output_path: Path,
        pipeline_name: str = "",
        criteria_set_name: str = "",
        save_details: bool = False,
    ) -> None:
        try:
            from reportlab.lib import colors
            from reportlab.lib.pagesizes import letter
            from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
            from reportlab.lib.units import inch
            from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
        except ImportError:
            raise ImportError(
                "pdf_writer requires reportlab. Install with: pip install reportlab"
            ) from None

        doc = SimpleDocTemplate(
            str(output_path),
            pagesize=letter,
            rightMargin=0.75 * inch,
            leftMargin=0.75 * inch,
            topMargin=0.75 * inch,
            bottomMargin=0.75 * inch,
        )
        styles = getSampleStyleSheet()
        story = []

        title_style = ParagraphStyle(
            name="CustomTitle",
            parent=styles["Heading1"],
            fontSize=16,
            spaceAfter=12,
        )
        heading_style = ParagraphStyle(
            name="CustomHeading",
            parent=styles["Heading2"],
            fontSize=12,
            spaceAfter=8,
        )
        question_style = ParagraphStyle(
            name="QuestionStyle",
            parent=styles["Heading3"],
            fontSize=11,
            spaceAfter=4,
            spaceBefore=12,
            leftIndent=0,
        )
        answer_yes_style = ParagraphStyle(
            name="AnswerYes",
            parent=styles["Normal"],
            fontSize=11,
            spaceAfter=18,
            leftIndent=12,
            textColor=colors.HexColor("#15803d"),
            backColor=colors.HexColor("#dcfce7"),
        )
        answer_no_style = ParagraphStyle(
            name="AnswerNo",
            parent=styles["Normal"],
            fontSize=11,
            spaceAfter=18,
            leftIndent=12,
            textColor=colors.HexColor("#b91c1c"),
            backColor=colors.HexColor("#fee2e2"),
        )
        ref_label_style = ParagraphStyle(
            name="RefLabel",
            parent=styles["Normal"],
            fontSize=9,
            spaceAfter=14,
            spaceBefore=6,
            leftIndent=12,
            textColor=colors.HexColor("#1e40af"),
            fontName="Helvetica-Bold",
        )
        quote_style = ParagraphStyle(
            name="QuoteStyle",
            parent=styles["Normal"],
            fontSize=9,
            spaceAfter=6,
            spaceBefore=8,
            leftIndent=24,
            rightIndent=24,
            textColor=colors.HexColor("#475569"),
            backColor=colors.HexColor("#f1f5f9"),
            borderPadding=8,
        )
        expl_style = ParagraphStyle(
            name="ExplStyle",
            parent=styles["Normal"],
            fontSize=9,
            spaceAfter=8,
            leftIndent=24,
            textColor=colors.HexColor("#64748b"),
            fontName="Helvetica-Oblique",
        )

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        story.append(Paragraph(f"Review Report: {artifact_name}", title_style))
        if pipeline_name:
            story.append(Paragraph(f"Review Process: {pipeline_name}", styles["Normal"]))
        if criteria_set_name:
            story.append(Paragraph(f"Checklist: {criteria_set_name}", styles["Normal"]))
        story.append(Paragraph(f"Generated on: {timestamp}", styles["Normal"]))
        story.append(Spacer(1, 0.25 * inch))
        story.append(Paragraph("Detailed Review", heading_style))

        def clean(s: str, max_len: int = 600) -> str:
            if s is None:
                return "N/A"
            s = str(s).replace("<br>", " ").strip()
            return (s[: max_len] + "…") if len(s) > max_len else s

        for i, item in enumerate(evaluations, 1):
            question = clean(item.get("criterion_text", "N/A"))
            is_yes = item.get("answer") in (True, "yes", "true", "Yes", "True")
            answer_text = "Yes" if is_yes else "No"
            answer_style = answer_yes_style if is_yes else answer_no_style

            story.append(Paragraph(f"{i}. {question}", question_style))
            story.append(Paragraph(f"Answer: {answer_text}", answer_style))

            if save_details and item.get("supporting_texts"):
                story.append(Spacer(1, 0.4 * inch))
                for idx, st in enumerate(item.get("supporting_texts", []), 1):
                    page = st.get("page_number", "?")
                    crop = clean(st.get("text_crop") or "")
                    expl = clean(st.get("short_explanation") or "", 300)
                    story.append(Paragraph(f"Reference {idx} (Page {page})", ref_label_style))
                    if crop:
                        story.append(Paragraph(crop, quote_style))
                    if expl:
                        story.append(Paragraph(f"Explanation: {expl}", expl_style))
            story.append(Spacer(1, 0.35 * inch))

        doc.build(story)