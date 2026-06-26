"""Versioned REST API for review runs."""

from __future__ import annotations

from flask import Blueprint, jsonify, request, send_file

from src.web.api.collection_service import (
    CollectionServiceError,
    create_collection,
    get_collection_criteria,
    get_document_content,
    get_references,
    list_artifacts,
    list_collections,
    list_source_documents,
    save_collection_criteria,
    set_references,
    upload_document,
)
from src.web.api.review_service import (
    ReviewServiceError,
    build_review_report,
    cancel_review,
    get_output_file_path,
    get_pipeline_manifest,
    get_review_status,
    list_criteria_sets_manifest,
    list_pipelines_manifest,
    start_review,
)

api_v1_bp = Blueprint("api_v1", __name__, url_prefix="/api/v1")


@api_v1_bp.get("/pipelines")
def pipelines():
    return jsonify(list_pipelines_manifest())


@api_v1_bp.get("/pipelines/<pipeline_id>")
def pipeline_detail(pipeline_id: str):
    try:
        return jsonify(get_pipeline_manifest(pipeline_id))
    except ReviewServiceError as exc:
        return jsonify({"error": str(exc)}), exc.status_code


@api_v1_bp.get("/criteria-sets")
def criteria_sets():
    return jsonify(list_criteria_sets_manifest())


@api_v1_bp.get("/collections")
def collections():
    return jsonify(list_collections())


@api_v1_bp.post("/collections")
def create_collection_route():
    data = request.get_json(silent=True) or {}
    try:
        return jsonify(create_collection(data.get("name"))), 201
    except CollectionServiceError as exc:
        return jsonify({"error": str(exc)}), exc.status_code


@api_v1_bp.get("/collections/<collection_name>/artifacts")
def collection_artifacts(collection_name: str):
    try:
        return jsonify(list_artifacts(collection_name))
    except CollectionServiceError as exc:
        return jsonify({"error": str(exc)}), exc.status_code


@api_v1_bp.get("/collections/<collection_name>/documents")
def collection_documents(collection_name: str):
    try:
        return jsonify(list_source_documents(collection_name))
    except CollectionServiceError as exc:
        return jsonify({"error": str(exc)}), exc.status_code


@api_v1_bp.post("/collections/<collection_name>/documents")
def upload_document_route(collection_name: str):
    file = request.files.get("file")
    role = request.form.get("role", "artifact")
    try:
        return jsonify(upload_document(collection_name, file, role=role)), 201
    except CollectionServiceError as exc:
        return jsonify({"error": str(exc)}), exc.status_code


@api_v1_bp.get("/collections/<collection_name>/references")
def collection_references(collection_name: str):
    try:
        return jsonify({"urls": get_references(collection_name)})
    except CollectionServiceError as exc:
        return jsonify({"error": str(exc)}), exc.status_code


@api_v1_bp.put("/collections/<collection_name>/references")
def update_collection_references(collection_name: str):
    data = request.get_json(silent=True) or {}
    urls = data.get("urls")
    if not isinstance(urls, list):
        return jsonify({"error": "urls must be a list of strings"}), 400
    try:
        return jsonify(set_references(collection_name, urls))
    except CollectionServiceError as exc:
        return jsonify({"error": str(exc)}), exc.status_code


@api_v1_bp.put("/collections/<collection_name>/criteria")
def save_collection_criteria_route(collection_name: str):
    data = request.get_json(silent=True) or {}
    try:
        return jsonify(
            save_collection_criteria(
                collection_name,
                data.get("criteria_set_name") or "custom",
                criteria=data.get("criteria"),
                text=data.get("text"),
            )
        )
    except CollectionServiceError as exc:
        return jsonify({"error": str(exc)}), exc.status_code


@api_v1_bp.get("/collections/<collection_name>/criteria/<criteria_set_name>")
def get_collection_criteria_route(collection_name: str, criteria_set_name: str):
    try:
        return jsonify(get_collection_criteria(collection_name, criteria_set_name))
    except CollectionServiceError as exc:
        return jsonify({"error": str(exc)}), exc.status_code


@api_v1_bp.get("/collections/<collection_name>/documents/<path:filename>/content")
def document_content_route(collection_name: str, filename: str):
    try:
        return jsonify(get_document_content(collection_name, filename))
    except CollectionServiceError as exc:
        return jsonify({"error": str(exc)}), exc.status_code


@api_v1_bp.post("/reviews")
def create_review():
    data = request.get_json(silent=True) or {}
    try:
        review_id = start_review(
            collection_name=data.get("collection_name"),
            pipeline_id=data.get("pipeline_id"),
            criteria_set_name=data.get("criteria_set_name"),
            artifact_ids=data.get("artifact_ids"),
            criteria_source_name=data.get("criteria_source_name"),
            reference_urls=data.get("reference_urls"),
            skip_existing=data.get("skip_existing", True),
        )
        return jsonify({"review_id": review_id, "status": "running"}), 201
    except ReviewServiceError as exc:
        return jsonify({"error": str(exc)}), exc.status_code


@api_v1_bp.get("/reviews/<review_id>")
def review_status(review_id: str):
    try:
        return jsonify(get_review_status(review_id))
    except ReviewServiceError as exc:
        return jsonify({"error": str(exc)}), exc.status_code


@api_v1_bp.get("/reviews/<review_id>/report")
def review_report(review_id: str):
    try:
        return jsonify(build_review_report(review_id))
    except ReviewServiceError as exc:
        return jsonify({"error": str(exc)}), exc.status_code


@api_v1_bp.post("/reviews/<review_id>/cancel")
def review_cancel(review_id: str):
    try:
        return jsonify(cancel_review(review_id))
    except ReviewServiceError as exc:
        return jsonify({"error": str(exc)}), exc.status_code


@api_v1_bp.get("/reviews/<review_id>/artifacts/<artifact_id>/outputs/<path:filename>")
def review_output_download(review_id: str, artifact_id: str, filename: str):
    try:
        file_path = get_output_file_path(review_id, artifact_id, filename)
        return send_file(file_path, as_attachment=False, download_name=filename)
    except ReviewServiceError as exc:
        return jsonify({"error": str(exc)}), exc.status_code
