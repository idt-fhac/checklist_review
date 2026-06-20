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


@frontend_bp.get("/review/<review_id>")
def review_app_deep_link(review_id: str):
    return render_template("review.html")
