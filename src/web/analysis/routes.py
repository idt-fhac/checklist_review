from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Dict

from flask import Blueprint, jsonify, render_template, request, send_from_directory

from src.core import storage
from src.core.workspace import get_collections_dir

analysis_bp = Blueprint("analysis", __name__, url_prefix="/analysis", template_folder="templates")


@analysis_bp.route("/static/<path:filename>")
def analysis_static(filename):
    base_dir = Path(__file__).resolve().parent.parent.parent.parent
    static_dir = base_dir / "src" / "web" / "analysis" / "static"
    return send_from_directory(str(static_dir), filename)


@analysis_bp.route("/", methods=["GET"])
def index():
    collections_root = get_collections_dir()
    collections_list = storage.list_collections(collections_root)
    collection_options = [
        {"name": c["name"], "slug": c.get("slug") or c["name"]} for c in collections_list
    ]

    context: Dict[str, Any] = {
        "active_tab": "analysis",
        "collections": collection_options,
    }
    return render_template("analysis/index.html", **context)


@analysis_bp.get("/api/collections")
def api_list_collections():
    """List all collections."""
    collections_root = get_collections_dir()
    collections = storage.list_collections(collections_root)
    collections = [c for c in collections if c.get("name") != "Temporary"]
    return jsonify(collections)


@analysis_bp.get("/api/pipelines")
def api_list_pipelines():
    """List pipelines from config/pipelines/."""
    base_dir = Path(__file__).resolve().parent.parent.parent.parent
    return jsonify(storage.list_global_processes(base_dir))


@analysis_bp.get("/api/criteria-sets")
def api_list_criteria_sets():
    """List criteria sets from the active workspace."""
    base_dir = Path(__file__).resolve().parent.parent.parent.parent
    criteria_sets = storage.list_criteria_sets(base_dir)
    criteria_sets.sort(
        key=lambda x: x.get("created_at")
        if isinstance(x.get("created_at"), datetime)
        else datetime(1970, 1, 1),
        reverse=True,
    )
    return jsonify(criteria_sets)


@analysis_bp.get("/api/report")
def api_get_report():
    collection_name = request.args.get("collection_name")
    pipeline_id = request.args.get("pipeline_id")
    criteria_set_name = request.args.get("criteria_set_name")

    if not collection_name or not pipeline_id:
        return jsonify({"error": "Missing parameters"}), 400

    collections_root = get_collections_dir()
    results_list = storage.list_evaluations(
        collections_root, collection_name, pipeline_id, criteria_set_name
    )

    total_artifacts = len(results_list)
    total_criteria = 0
    total_yes = 0
    total_no = 0
    total_na = 0
    criterion_stats: Dict[str, Dict[str, int]] = {}

    for res_meta in results_list:
        artifact_id = res_meta["artifact_id"]
        evaluations = storage.load_evaluation(
            collections_root,
            collection_name,
            artifact_id,
            pipeline_id,
            criteria_set_name,
        )
        if not evaluations:
            continue

        items = evaluations if isinstance(evaluations, list) else evaluations.get("evaluations", [])
        if isinstance(evaluations, dict) and not items:
            items = list(evaluations.values()) if evaluations else []

        for entry in items:
            if not isinstance(entry, dict):
                continue
            total_criteria += 1
            label = entry.get("criterion_text") or entry.get("description") or "Unknown criterion"
            val = entry.get("answer")

            if label not in criterion_stats:
                criterion_stats[label] = {"total": 0, "yes": 0, "no": 0, "na": 0}

            stats = criterion_stats[label]
            stats["total"] += 1

            if val is True:
                total_yes += 1
                stats["yes"] += 1
            elif val is False:
                total_no += 1
                stats["no"] += 1
            else:
                total_na += 1
                stats["na"] += 1

    automated_stats = {
        "total_artifacts": total_artifacts,
        "total_criteria": total_criteria,
        "distribution": {
            "yes": total_yes,
            "no": total_no,
            "na": total_na,
        },
    }

    breakdown = [
        {
            "criterion": label,
            "yes_pct": round(s["yes"] / s["total"] * 100, 1) if s["total"] > 0 else 0,
            "no_pct": round(s["no"] / s["total"] * 100, 1) if s["total"] > 0 else 0,
            "yes_count": s["yes"],
            "no_count": s["no"],
            "total": s["total"],
        }
        for label, s in criterion_stats.items()
    ]

    return jsonify({
        "automated": automated_stats,
        "breakdown": breakdown,
    })
