from flask import Blueprint

base_bp = Blueprint(
    "base",
    __name__,
    template_folder="templates",
    static_folder="static",
    static_url_path="/base/static",
)
