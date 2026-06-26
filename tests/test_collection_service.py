from __future__ import annotations

from io import BytesIO

import pytest
from werkzeug.datastructures import FileStorage

from src.core import task_persistence
from src.web.api.collection_service import (
    CollectionServiceError,
    create_collection,
    get_document_content,
    get_references,
    list_artifacts,
    list_collections,
    save_collection_criteria,
    set_references,
    upload_document,
)


class TestCollectionService:
    def test_create_and_list_collection(self, isolated_workspace):
        result = create_collection("demo_project")
        assert result["name"] == "demo_project"
        names = [c["name"] for c in list_collections()]
        assert "demo_project" in names

    def test_create_duplicate_collection_raises(self, isolated_workspace):
        create_collection("dup_test")
        with pytest.raises(CollectionServiceError) as exc:
            create_collection("dup_test")
        assert exc.value.status_code == 409

    def test_references_round_trip(self, isolated_workspace):
        create_collection("refs_test")
        saved = set_references(
            "refs_test",
            ["https://example.com/spec", "  https://example.com/other  "],
        )
        assert saved["urls"] == [
            "https://example.com/spec",
            "https://example.com/other",
        ]
        assert get_references("refs_test") == saved["urls"]

    def test_upload_artifact_with_mocked_ingest(self, isolated_workspace, monkeypatch):
        create_collection("upload_test")
        monkeypatch.setattr(
            "src.web.api.collection_service.process_pdf_to_markdown_and_metadata",
            lambda pdf_path, collection_dir, provider_config=None: {
                "title": "Draft Title"
            },
        )
        monkeypatch.setattr(
            "src.web.api.collection_service.get_default_llm_provider",
            lambda: {"type": "ollama", "model_name": "test"},
        )

        file = FileStorage(
            stream=BytesIO(b"%PDF-1.4 minimal"),
            filename="draft.pdf",
            content_type="application/pdf",
        )
        result = upload_document("upload_test", file, role="artifact")
        assert result["filename"] == "draft.pdf"
        assert result["selected_for_review"] is True

        artifacts = list_artifacts("upload_test")
        assert len(artifacts) == 1
        assert artifacts[0]["filename"] == "draft.pdf"

    def test_upload_rfp_not_selected_for_review(self, isolated_workspace, monkeypatch):
        create_collection("rfp_test")
        monkeypatch.setattr(
            "src.web.api.collection_service.process_pdf_to_markdown_and_metadata",
            lambda *args, **kwargs: {"title": "RFP"},
        )
        monkeypatch.setattr(
            "src.web.api.collection_service.get_default_llm_provider",
            lambda: {"type": "ollama", "model_name": "test"},
        )

        file = FileStorage(
            stream=BytesIO(b"%PDF-1.4"),
            filename="tender_rfp.pdf",
            content_type="application/pdf",
        )
        result = upload_document("rfp_test", file, role="rfp")
        assert result["selected_for_review"] is False
        assert list_artifacts("rfp_test") == []

    def test_upload_text_markdown_draft(self, isolated_workspace):
        create_collection("text_test")
        file = FileStorage(
            stream=BytesIO(b"# Draft heading\n\nBody text."),
            filename="draft.md",
            content_type="text/markdown",
        )
        result = upload_document("text_test", file, role="artifact")
        assert result["filename"] == "draft.md"
        assert result["artifact_id"] == "draft"
        assert result["selected_for_review"] is True

        content = get_document_content("text_test", "draft.md")
        assert "Draft heading" in content["content"]
        assert content["content_type"] == "text/markdown"

    def test_save_collection_criteria_from_text(self, isolated_workspace):
        create_collection("criteria_test")
        saved = save_collection_criteria(
            "criteria_test",
            "custom",
            text="Innovation level (Gewichtung 15%)\nTeam experience",
        )
        assert saved["criteria_count"] == 2
        assert saved["criteria_set_name"] == "custom"


class TestTaskPersistence:
    def test_task_payload_stores_reference_urls(self, isolated_workspace):
        collections_root = isolated_workspace / "collections"
        collections_root.mkdir(exist_ok=True)
        task_persistence.write_task_payload(
            collections_root,
            "task-123",
            collection_name="demo",
            pipeline_id="scientific_checklist",
            criteria_set_name="example",
            artifacts=[{"filename": "paper.pdf", "artifact_id": "paper"}],
            reference_urls=["https://example.com/ref"],
            progress={"status": "pending", "current": 0, "total": 1},
        )
        payload = task_persistence.read_task_payload(collections_root, "task-123")
        assert payload["reference_urls"] == ["https://example.com/ref"]
