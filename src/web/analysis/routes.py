from __future__ import annotations

from typing import Any, Dict
from pathlib import Path

from src.core.workspace import get_collections_dir
from flask import Blueprint, render_template, request, current_app, jsonify, send_from_directory

from src.core import storage

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
    collection_options = [{"name": c["name"], "slug": c.get("slug") or c["name"]} for c in collections_list]
    
    context: Dict[str, Any] = {
        "active_tab": "analysis",
        "collections": collection_options
    }
    return render_template("analysis/index.html", **context)

@analysis_bp.get("/api/collections")
def api_list_collections():
    """List all collections"""
    collections_root = get_collections_dir()
    collections = storage.list_collections(collections_root)
    # Filter out Temporary collection
    collections = [c for c in collections if c.get("name") != "Temporary"]
    return jsonify(collections)

@analysis_bp.get("/api/processes")
def api_list_processes():
    """List all globally available process definitions"""
    from pathlib import Path
    base_dir = Path(__file__).resolve().parent.parent.parent.parent
    return jsonify(storage.list_global_processes(base_dir))

@analysis_bp.get("/api/checklists")
def api_list_checklists():
    """List all checklists from workspaces/guest/checklists (global, not per collection)"""
    from pathlib import Path
    base_dir = Path(__file__).resolve().parent.parent.parent.parent
    all_checklists = storage.list_checklists(base_dir)
    from datetime import datetime
    all_checklists.sort(key=lambda x: x.get("created_at") if isinstance(x.get("created_at"), datetime) else datetime(1970, 1, 1), reverse=True)
    return jsonify(all_checklists)

@analysis_bp.get("/api/report")
def api_get_report():
    collection_name = request.args.get("collection_name")
    process_name = request.args.get("process_name")
    checklist_name = request.args.get("checklist_name")
    
    if not collection_name or not process_name:
        return jsonify({"error": "Missing parameters"}), 400
        
    collections_root = get_collections_dir()
    results_list = storage.list_generated_answers(collections_root, collection_name, process_name, checklist_name)
    
    total_papers = len(results_list)
    total_questions = 0
    total_automated_yes = 0
    total_automated_no = 0
    total_automated_na = 0
    verified_papers = 0
    total_verifications = 0
    human_agreed = 0
    human_disagreed = 0
    question_stats = {}
    
    for res_meta in results_list:
        paper_id = res_meta["paper_id"]
        answers = storage.load_generated_answer(collections_root, collection_name, paper_id, process_name, checklist_name)
        if not answers:
            continue
        
        verification = storage.load_human_verification(collections_root, collection_name, process_name, paper_id, checklist_name)
        ver_map = verification.get("verifications", {}) if verification else {}
        if ver_map:
            verified_papers += 1
        
        for ans in answers:
            total_questions += 1
            q_text = ans.get("question_text", "Unknown Question")
            val = ans.get("answer")
            q_id = ans.get("question_id")
            
            if q_text not in question_stats:
                question_stats[q_text] = {"total": 0, "yes": 0, "no": 0, "na": 0, "verified_count": 0, "agreed": 0}
            
            stats = question_stats[q_text]
            stats["total"] += 1
            
            if val is True:
                total_automated_yes += 1
                stats["yes"] += 1
            elif val is False:
                total_automated_no += 1
                stats["no"] += 1
            else:
                total_automated_na += 1
                stats["na"] += 1
            
            if q_id in ver_map:
                is_correct = ver_map[q_id].get("is_correct")
                if is_correct is not None:
                    total_verifications += 1
                    stats["verified_count"] += 1
                    if is_correct:
                        human_agreed += 1
                        stats["agreed"] += 1
                    else:
                        human_disagreed += 1

    automated_stats = {
        "total_papers": total_papers,
        "total_questions": total_questions,
        "distribution": {
            "yes": total_automated_yes,
            "no": total_automated_no,
            "na": total_automated_na
        }
    }
    
    human_stats = {
        "verified_papers_count": verified_papers,
        "verification_coverage_pct": round((verified_papers / total_papers * 100), 1) if total_papers > 0 else 0,
        "total_verifications": total_verifications,
        "agreement": {
            "agreed": human_agreed,
            "disagreed": human_disagreed,
            "agreement_rate": round((human_agreed / total_verifications * 100), 1) if total_verifications > 0 else 0
        }
    }
    
    breakdown = [
        {
            "question": q_text,
            "yes_pct": round(s["yes"] / s["total"] * 100, 1) if s["total"] > 0 else 0,
            "no_pct": round(s["no"] / s["total"] * 100, 1) if s["total"] > 0 else 0,
            "yes_count": s["yes"],
            "no_count": s["no"],
            "total": s["total"],
            "agreement_rate": round(s["agreed"] / s["verified_count"] * 100, 1) if s["verified_count"] > 0 else 0,
            "verified_count": s["verified_count"],
            "agreed_count": s["agreed"],
            "disagreed_count": s["verified_count"] - s["agreed"],
        }
        for q_text, s in question_stats.items()
    ]
        
    return jsonify({
        "automated": automated_stats,
        "human": human_stats,
        "breakdown": breakdown
    })
