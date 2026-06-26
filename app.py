from __future__ import annotations

import os
from pathlib import Path

from flask import Flask, jsonify

from src.web.frontend.routes import frontend_bp


def create_app() -> Flask:
    base_dir = Path(__file__).resolve().parent

    app = Flask(__name__)

    output_dir = Path(os.environ.get("OUTPUT_DIR", base_dir / "outputs"))

    app.config.update(
        SECRET_KEY=os.environ.get("FLASK_SECRET_KEY", "dev-key"),
        OUTPUT_DIR=output_dir,
    )

    from src.web.api.routes import api_v1_bp

    app.register_blueprint(frontend_bp)
    app.register_blueprint(api_v1_bp)

    from src.core.workspace import ensure_guest_workspace_initialized

    ensure_guest_workspace_initialized()

    @app.get("/api")
    def api_index():
        return jsonify(
            {
                "name": "checklist_reviewer",
                "api_version": "v1",
                "base_path": "/api/v1",
            }
        )

    @app.get("/health")
    def health():
        return jsonify({"status": "ok"})

    return app


app = create_app()

if __name__ == "__main__":
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", 5555))
    app.run(host=host, port=port, debug=False)
