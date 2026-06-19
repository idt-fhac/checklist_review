from __future__ import annotations

from flask import Blueprint, render_template

frontend_bp = Blueprint(
    "frontend",
    __name__,
    template_folder="templates",
    static_folder="static",
    static_url_path="/ui-static",
)


@frontend_bp.get("/")
def review_app():
    return render_template("review.html")
