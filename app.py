from __future__ import annotations

import os
from pathlib import Path

from flask import Flask, redirect, url_for, send_from_directory


def create_app() -> Flask:
    base_dir = Path(__file__).resolve().parent

    app = Flask(__name__)

    output_dir = Path(os.environ.get("OUTPUT_DIR", base_dir / "outputs"))

    app.config.update(
        SECRET_KEY=os.environ.get("FLASK_SECRET_KEY", "dev-key"),
        OUTPUT_DIR=output_dir,
    )

    from src.web.base.routes import base_bp
    from src.web.collection.routes import collection_bp
    from src.web.checklist_review.routes import checklist_review_bp
    from src.web.analysis.routes import analysis_bp
    from src.web.human_verification.routes import human_verification_bp
    from src.web.settings.routes import settings_bp
    from src.web.review_process_design.routes import review_process_design_bp
    from src.web.workspace.routes import workspace_bp

    app.register_blueprint(base_bp)
    app.register_blueprint(collection_bp)
    app.register_blueprint(checklist_review_bp)
    app.register_blueprint(analysis_bp)
    app.register_blueprint(human_verification_bp)
    app.register_blueprint(review_process_design_bp)
    app.register_blueprint(settings_bp)
    app.register_blueprint(workspace_bp)

    from src.core.workspace import (
        ensure_guest_workspace_initialized,
        get_active_workspace,
        list_workspaces,
    )

    ensure_guest_workspace_initialized()

    @app.context_processor
    def inject_workspace_data():
        return dict(
            workspaces=list_workspaces(),
            active_workspace=get_active_workspace()
        )

    @app.route("/")
    def index():
        from src.web.settings.services import SettingsManager
        settings = SettingsManager.load_settings()
        default_page = settings.get("default_page", "checklist_review")
        
        # Map page names to route names
        page_routes = {
            "checklist_review": "checklist_review.index",
            "collection": "collection.index",
            "analysis": "analysis.index",
            "human_verification": "human_verification.index",
            "review_process_design": "review_process_design.index",
            "settings": "settings.index",
        }
        
        route_name = page_routes.get(default_page, "checklist_review.index")
        return redirect(url_for(route_name))

    return app


app = create_app()

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5555, debug=False)
