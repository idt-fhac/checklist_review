from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from src.core import storage, task_persistence
from src.web.api.review_service import (
    ReviewServiceError,
    get_pipeline_manifest,
    start_review,
)


class TestReviewService:
    def test_get_pipeline_manifest_tender(self):
        manifest = get_pipeline_manifest("tender_full")
        assert manifest["id"] == "tender_full"
        assert manifest["evaluation_mode"] == "multi_persona"
        assert len(manifest["personas"]) == 3

    def test_get_pipeline_manifest_missing_raises(self):
        with pytest.raises(ReviewServiceError) as exc:
            get_pipeline_manifest("nonexistent_pipeline_xyz")
        assert exc.value.status_code == 404

    def test_start_review_requires_collection(self):
        with pytest.raises(ReviewServiceError, match="collection_name"):
            start_review(
                collection_name="",
                pipeline_id="scientific_checklist",
                criteria_set_name="example",
            )

    def test_start_review_requires_artifacts(self, isolated_workspace):
        storage.create_new_collection(
            isolated_workspace / "collections", "empty_project"
        )
        with pytest.raises(ReviewServiceError, match="Upload a draft"):
            start_review(
                collection_name="empty_project",
                pipeline_id="scientific_checklist",
                criteria_set_name="example",
            )

    @patch("src.web.api.review_service.multiprocessing.Process")
    def test_start_review_launches_background_process(
        self, mock_process, isolated_workspace
    ):
        collections_root = isolated_workspace / "collections"
        storage.create_new_collection(collections_root, "run_project")
        storage.save_selected_list(
            collections_root,
            "run_project",
            [{"filename": "draft.pdf", "artifact_id": "draft", "title": "Draft"}],
        )

        mock_process.return_value = MagicMock()

        review_id = start_review(
            collection_name="run_project",
            pipeline_id="scientific_checklist",
            criteria_set_name="example",
            artifact_ids=["draft"],
            skip_existing=False,
        )

        assert review_id
        mock_process.assert_called_once()
        payload = task_persistence.read_task_payload(collections_root, review_id)
        assert payload["pipeline_id"] == "scientific_checklist"
        assert payload["criteria_set_name"] == "example"

    def test_tender_defaults_criteria_set_to_extracted(self, isolated_workspace):
        collections_root = isolated_workspace / "collections"
        storage.create_new_collection(collections_root, "tender_project")
        storage.save_selected_list(
            collections_root,
            "tender_project",
            [
                {
                    "filename": "proposal.pdf",
                    "artifact_id": "proposal",
                    "title": "Proposal",
                }
            ],
        )

        with patch(
            "src.web.api.review_service.multiprocessing.Process"
        ) as mock_process:
            mock_process.return_value = MagicMock()
            review_id = start_review(
                collection_name="tender_project",
                pipeline_id="tender_full",
                criteria_source_name="rfp.pdf",
                artifact_ids=["proposal"],
                skip_existing=False,
            )

        payload = task_persistence.read_task_payload(collections_root, review_id)
        assert payload["criteria_set_name"] == "extracted"
        assert payload["criteria_source_name"] == "rfp.pdf"
