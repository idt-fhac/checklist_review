from __future__ import annotations

import json
from io import BytesIO
from unittest.mock import patch

import pytest

from src.core import storage, task_persistence


class TestHealthAndApiIndex:
    def test_health(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        assert response.get_json()["status"] == "ok"

    def test_api_index(self, client):
        response = client.get("/api")
        assert response.status_code == 200
        assert response.get_json()["base_path"] == "/api/v1"


class TestFrontend:
    def test_homepage_serves_html(self, client):
        response = client.get("/")
        assert response.status_code == 200
        assert b"Automated Review" in response.data
        assert b"/ui-static/js/review.js" in response.data

    def test_frontend_static_assets(self, client):
        response = client.get("/ui-static/css/review.css")
        assert response.status_code == 200
        assert b"--accent" in response.data


class TestPipelinesApi:
    def test_list_pipelines(self, client):
        response = client.get("/api/v1/pipelines")
        assert response.status_code == 200
        pipelines = response.get_json()
        assert isinstance(pipelines, list)
        ids = {p["id"] for p in pipelines}
        assert "tender_full" in ids
        assert "scientific_checklist" in ids

    def test_pipeline_detail_includes_personas(self, client):
        response = client.get("/api/v1/pipelines/tender_full")
        assert response.status_code == 200
        data = response.get_json()
        assert data["evaluation_mode"] == "multi_persona"
        assert len(data["personas"]) == 3

    def test_pipeline_detail_404(self, client):
        response = client.get("/api/v1/pipelines/does-not-exist")
        assert response.status_code == 404


class TestCollectionsApi:
    def test_create_collection(self, client, isolated_workspace):
        response = client.post("/api/v1/collections", json={"name": "api_test_proj"})
        assert response.status_code == 201
        assert response.get_json()["name"] == "api_test_proj"

    def test_create_duplicate_collection(self, client, isolated_workspace):
        client.post("/api/v1/collections", json={"name": "dup_api"})
        response = client.post("/api/v1/collections", json={"name": "dup_api"})
        assert response.status_code == 409

    def test_references_api(self, client, isolated_workspace):
        client.post("/api/v1/collections", json={"name": "ref_api"})
        response = client.put(
            "/api/v1/collections/ref_api/references",
            json={"urls": ["https://example.com/a"]},
        )
        assert response.status_code == 200
        get_response = client.get("/api/v1/collections/ref_api/references")
        assert get_response.get_json()["urls"] == ["https://example.com/a"]

    def test_upload_document(self, client, isolated_workspace, monkeypatch):
        client.post("/api/v1/collections", json={"name": "upload_api"})
        monkeypatch.setattr(
            "src.web.api.collection_service.process_pdf_to_markdown_and_metadata",
            lambda *args, **kwargs: {"title": "Test"},
        )
        monkeypatch.setattr(
            "src.web.api.collection_service.get_default_llm_provider",
            lambda: {"type": "ollama", "model_name": "test"},
        )

        data = {
            "file": (BytesIO(b"%PDF-1.4 test"), "draft.pdf"),
            "role": "artifact",
        }
        response = client.post(
            "/api/v1/collections/upload_api/documents",
            data=data,
            content_type="multipart/form-data",
        )
        assert response.status_code == 201
        assert response.get_json()["filename"] == "draft.pdf"

        artifacts = client.get("/api/v1/collections/upload_api/artifacts").get_json()
        assert len(artifacts) == 1


class TestReviewsApi:
    def test_review_not_found(self, client):
        response = client.get("/api/v1/reviews/nonexistent-id")
        assert response.status_code == 404

    def test_start_review_validation(self, client, isolated_workspace):
        response = client.post("/api/v1/reviews", json={"pipeline_id": "scientific_checklist"})
        assert response.status_code == 400

    @patch("src.web.api.review_service.multiprocessing.Process")
    def test_start_and_poll_review(self, mock_process, client, isolated_workspace):
        collections_root = isolated_workspace / "collections"
        storage.create_new_collection(collections_root, "review_api")
        storage.save_selected_list(
            collections_root,
            "review_api",
            [{"filename": "doc.pdf", "artifact_id": "doc", "title": "Doc"}],
        )
        mock_process.return_value.start = lambda: None
        mock_process.return_value.is_alive = lambda: False

        start = client.post(
            "/api/v1/reviews",
            json={
                "collection_name": "review_api",
                "pipeline_id": "scientific_checklist",
                "criteria_set_name": "example",
                "artifact_ids": ["doc"],
                "skip_existing": False,
            },
        )
        assert start.status_code == 201
        review_id = start.get_json()["review_id"]

        status = client.get(f"/api/v1/reviews/{review_id}")
        assert status.status_code == 200
        assert status.get_json()["review_id"] == review_id

    def test_report_for_completed_run(self, client, isolated_workspace):
        from src.review_workflow.engine.run_paths import artifact_run_dir

        collections_root = isolated_workspace / "collections"
        storage.create_new_collection(collections_root, "report_api")
        task_id = "report-task-1"
        task_persistence.write_task_payload(
            collections_root,
            task_id,
            collection_name="report_api",
            pipeline_id="scientific_checklist",
            criteria_set_name="example",
            artifacts=[{"filename": "doc.pdf", "artifact_id": "doc.pdf"}],
            progress={
                "status": "completed",
                "current": 1,
                "total": 1,
                "current_item": "",
                "results": [],
                "log_messages": [],
            },
        )

        run_dir = artifact_run_dir(
            collections_root,
            "report_api",
            "scientific_checklist",
            "doc.pdf",
            "example",
        )
        run_dir.mkdir(parents=True, exist_ok=True)
        evaluations = [
            {
                "criterion_id": "c1",
                "criterion_text": "Has abstract",
                "answer": True,
                "reasoning": "Found on page 1",
            }
        ]
        (run_dir / "evaluations.json").write_text(json.dumps(evaluations), encoding="utf-8")
        (run_dir / "synthesis.json").write_text(
            json.dumps({"summary": "Looks good overall."}),
            encoding="utf-8",
        )

        response = client.get(f"/api/v1/reviews/{task_id}/report")
        assert response.status_code == 200
        report = response.get_json()
        assert report["status"] == "completed"
        assert report["artifacts"][0]["evaluations"][0]["criterion_text"] == "Has abstract"
        assert report["artifacts"][0]["synthesis"]["summary"] == "Looks good overall."
