from __future__ import annotations

import os
from pathlib import Path

from flask import Flask, jsonify


def create_app() -> Flask:
    base_dir = Path(__file__).resolve().parent

    app = Flask(__name__)

    output_dir = Path(os.environ.get("OUTPUT_DIR", base_dir / "outputs"))

    app.config.update(
        SECRET_KEY=os.environ.get("FLASK_SECRET_KEY", "dev-key"),
        OUTPUT_DIR=output_dir,
    )

    from src.web.api.routes import api_v1_bp

    app.register_blueprint(api_v1_bp)

    from src.core.workspace import ensure_guest_workspace_initialized

    ensure_guest_workspace_initialized()

    @app.get("/")
    def index():
        return jsonify(
            {
                "name": "checklist_reviewer",
                "api_version": "v1",
                "base_path": "/api/v1",
                "docs": {
                    "pipelines": "GET /api/v1/pipelines",
                    "create_collection": "POST /api/v1/collections",
                    "upload_rfp": "POST /api/v1/collections/{name}/documents (form: file, role=rfp)",
                    "upload_draft": "POST /api/v1/collections/{name}/documents (form: file, role=artifact)",
                    "reference_links": "PUT /api/v1/collections/{name}/references",
                    "start_review": "POST /api/v1/reviews",
                    "review_status": "GET /api/v1/reviews/{id}",
                    "review_report": "GET /api/v1/reviews/{id}/report",
                },
            }
        )

    @app.get("/health")
    def health():
        return jsonify({"status": "ok"})

    return app


app = create_app()

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5555, debug=False)
