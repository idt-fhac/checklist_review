from __future__ import annotations

import json
import logging
import re
import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Tuple

from src.core.workspace import get_collections_dir, get_process_definitions_dir
from flask import Blueprint, current_app, jsonify, render_template, request

from src.review_workflow.engine.components import get_components_root, list_components_metadata, get_component_metadata
from src.core import storage

review_process_design_bp = Blueprint("review_process_design", __name__, url_prefix="/review_process_design", template_folder="templates")
logger = logging.getLogger(__name__)


def _active_process_definitions_dir() -> Path:
    """Process JSON files for the workspace selected in the session."""
    return get_process_definitions_dir()


@review_process_design_bp.route("/static/<path:filename>")
def review_process_design_static(filename):
    from flask import send_from_directory
    base_dir = Path(__file__).resolve().parent.parent.parent.parent
    static_dir = base_dir / "src" / "web" / "review_process_design" / "static"
    return send_from_directory(str(static_dir), filename)


@review_process_design_bp.route("/", methods=["GET"])
def index():
    context: Dict[str, Any] = {
        "active_tab": "review_process_design",
    }
    return render_template("review_process_design/index.html", **context)


@review_process_design_bp.get("/api/components")
def api_list_components():
    grouped = list_components_metadata()
    components = []
    for group in grouped.values():
        components.extend(group)
    return jsonify(components)


@review_process_design_bp.get("/api/providers")
def api_list_providers():
    from src.web.settings.services import SettingsManager
    providers = SettingsManager.load_secrets()
    embedding_only = request.args.get("embedding_only", "").lower() in ("1", "true", "yes")
    if embedding_only:
        provider_list = [
            {"id": p["id"], "name": p["name"], "type": p["type"]}
            for p in providers
            if p.get("is_embedding_model", False)
        ]
    else:
        # Filter out embedding models - only show non-embedding models for LLM
        provider_list = [
            {"id": p["id"], "name": p["name"], "type": p["type"]}
            for p in providers
            if not p.get("is_embedding_model", False)
        ]
    return jsonify(provider_list)


@review_process_design_bp.get("/api/processes")
def api_list_processes():
    """List process definitions for the active workspace."""
    processes_dir = _active_process_definitions_dir()
    
    results = []
    for file in sorted(processes_dir.glob("*.json")):
        content_name = None
        try:
            with open(file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                content_name = data.get("name")
        except Exception:
            pass

        # Use original name from JSON if available, otherwise use file stem
        display_name = content_name if content_name else file.stem
        slug_name = file.stem  # File is stored with slug name

        from datetime import datetime
        results.append({
            "name": display_name,
            "slug": slug_name,
            "filename": file.name,
            "path": str(file),
            "updated_at": datetime.fromtimestamp(file.stat().st_mtime),
            "data": { "name": content_name } if content_name else {}
        })
    return jsonify(results)


@review_process_design_bp.get("/api/processes/<process_name>")
def api_get_process(process_name):
    """Get a process definition from the active workspace."""
    processes_dir = _active_process_definitions_dir()
    
    path = processes_dir / f"{process_name}.json"
    if not path.exists():
        from src.core.storage import _slug
        path = processes_dir / f"{_slug(process_name)}.json"
    
    # If still not found and it's the default process, check process_definitions one more time
    if not path.exists() and (process_name == "default_review" or _slug(process_name) == "default_review"):
        process_def_path = processes_dir / "default_review.json"
        if process_def_path.exists():
            path = process_def_path
    
    if not path.exists():
        return jsonify({"error": "Process not found"}), 404
        
    try:
        with path.open(encoding="utf-8") as fp:
            return jsonify(json.load(fp))
    except Exception as e:
        logger.error(f"Error loading process: {e}")
        return jsonify({"error": f"Failed to load process: {str(e)}"}), 500


@review_process_design_bp.post("/api/processes")
def api_save_process():
    """Save a process definition in the active workspace."""
    data = request.get_json()
    process_name = data.get("name")
    process_data = data.get("data")
    
    if not process_name:
        return jsonify({"error": "Missing name"}), 400
        
    if process_name == "default_review":
         return jsonify({"error": "Cannot overwrite default process. Please use Save As."}), 400
    
    processes_dir = _active_process_definitions_dir()

    from src.core.storage import _slug
    slug_name = _slug(process_name)
    path = processes_dir / f"{slug_name}.json"
    
    if "name" not in process_data or process_data.get("name") != process_name:
        process_data["name"] = process_name
    
    try:
        with path.open("w", encoding="utf-8") as fp:
            json.dump(process_data, fp, indent=2)
        return jsonify({"success": True})
    except Exception as e:
        logger.error(f"Error saving process: {e}")
        return jsonify({"error": f"Failed to save process: {str(e)}"}), 500


@review_process_design_bp.delete("/api/processes/<process_name>")
def api_delete_process(process_name):
    """Delete a process definition from the active workspace."""
    if process_name == "default_review":
        return jsonify({"error": "Cannot delete the default process"}), 400
    
    processes_dir = _active_process_definitions_dir()

    from src.core.storage import _slug
    slug_name = _slug(process_name)
    process_file = processes_dir / f"{slug_name}.json"
    if not process_file.exists():
        process_file = processes_dir / f"{process_name}.json"
    
    if process_file.exists():
        try:
            process_file.unlink()
            
            # Delete process folders in all collections
            collections_root = get_collections_dir()
            folder_result = storage.delete_process_folders(collections_root, process_name)
            
            if folder_result["errors"]:
                logger.warning(f"Some process folders could not be deleted: {folder_result['errors']}")
            
            message = f"Process '{process_name}' deleted successfully"
            if folder_result["deleted"]:
                message += f" ({len(folder_result['deleted'])} folder(s) deleted)"
            if folder_result["errors"]:
                message += f" ({len(folder_result['errors'])} error(s))"
            
            return jsonify({"success": True, "message": message, "folder_result": folder_result})
        except Exception as e:
            logger.error(f"Error deleting process: {e}")
            return jsonify({"error": f"Failed to delete process: {str(e)}"}), 500
    else:
        return jsonify({"error": "Process not found"}), 404


@review_process_design_bp.post("/api/processes/<process_name>/rename")
def api_rename_process(process_name):
    """Rename a process definition in the active workspace."""
    data = request.get_json()
    new_name = data.get("new_name")
    
    if not new_name:
        return jsonify({"error": "Missing new_name"}), 400
    
    if process_name == "default_review":
        return jsonify({"error": "Cannot rename the default process"}), 400
    
    processes_dir = _active_process_definitions_dir()

    from src.core.storage import _slug
    
    # Helper function to convert to slug
    def to_slug(name: str) -> str:
        if not name:
            return "process"
        return name.strip().replace(" ", "_").lower() or "process"
    
    # Load the process
    path = processes_dir / f"{process_name}.json"
    if not path.exists():
        path = processes_dir / f"{_slug(process_name)}.json"
    
    if not path.exists():
        return jsonify({"error": "Process not found"}), 404
    
    try:
        with path.open(encoding="utf-8") as fp:
            process_data = json.load(fp)
    except Exception as e:
        logger.error(f"Error loading process for rename: {e}")
        return jsonify({"error": f"Failed to load process: {str(e)}"}), 500
    
    # Check if new name already exists
    current_slug = to_slug(process_name)
    new_name_slug = to_slug(new_name)
    
    if new_name_slug != current_slug:
        # Check if another process with the new slug already exists
        existing_files = list(processes_dir.glob("*.json"))
        for existing_file in existing_files:
            if existing_file.stem == new_name_slug and existing_file.stem != current_slug:
                return jsonify({"error": "A process with this name already exists"}), 400
    
    try:
        # Save with new name
        new_path = processes_dir / f"{new_name_slug}.json"
        process_data["name"] = new_name
        with new_path.open("w", encoding="utf-8") as fp:
            json.dump(process_data, fp, indent=2)
        
        # Rename process folders in all collections (before deleting old process)
        collections_root = get_collections_dir()
        folder_result = storage.rename_process_folders(collections_root, process_name, new_name)
        
        if folder_result["errors"]:
            logger.warning(f"Some process folders could not be renamed: {folder_result['errors']}")
        
        # Delete old process
        if new_path != path and path.exists():
            path.unlink()
        
        message = f"Process renamed successfully"
        if folder_result["renamed"]:
            message += f" ({len(folder_result['renamed'])} folder(s) renamed)"
        if folder_result["errors"]:
            message += f" ({len(folder_result['errors'])} error(s))"
        
        return jsonify({"message": message, "new_name": new_name, "folder_result": folder_result})
    except Exception as e:
        logger.error(f"Error renaming process: {e}")
        return jsonify({"error": f"Failed to rename process: {str(e)}"}), 500


# --- Component import validation ---
_REVIEW_COMPONENTS_DIR = get_components_root() / "review"
_VALID_COMPONENT_TYPE = re.compile(r"^[a-z][a-z0-9_]*$")


def _validate_component_zip(zip_path: Path, extract_dir: Path) -> Tuple[bool, str, Path, str]:
    """
    Extract zip and find exactly one folder that contains metadata.json and component.py.
    That folder may contain any other files. Returns (ok, error_message, component_dir_path, folder_name).
    """
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            if not zf.namelist():
                return False, "The ZIP file is empty.", Path(), ""
    except zipfile.BadZipFile:
        return False, "The file is not a valid ZIP archive.", Path(), ""
    except Exception as e:
        return False, f"Cannot read ZIP file: {str(e)}", Path(), ""

    extract_dir.mkdir(parents=True, exist_ok=True)
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(extract_dir)
    except Exception as e:
        return False, f"Failed to extract ZIP: {str(e)}", Path(), ""

    def has_required_files(d: Path) -> bool:
        return (d / "metadata.json").exists() and (d / "component.py").exists()

    # Collect every folder that contains both metadata.json and component.py (root or any subdir)
    candidates: List[Path] = []
    if has_required_files(extract_dir):
        candidates.append(extract_dir)
    for item in extract_dir.iterdir():
        if item.is_dir() and has_required_files(item):
            candidates.append(item)

    if len(candidates) == 0:
        return False, "ZIP must contain a folder with metadata.json and component.py (and may contain other files).", extract_dir, ""
    if len(candidates) > 1:
        return False, "ZIP must contain exactly one folder that has metadata.json and component.py.", extract_dir, ""

    component_dir = candidates[0]
    folder_name = component_dir.name if component_dir != extract_dir else None  # root: get name from metadata

    meta_file = component_dir / "metadata.json"
    try:
        with open(meta_file, "r", encoding="utf-8") as f:
            meta = json.load(f)
    except json.JSONDecodeError as e:
        return False, f"metadata.json is not valid JSON: {str(e)}", component_dir, ""
    if not isinstance(meta, dict):
        return False, "metadata.json must be a JSON object.", component_dir, ""

    meta_id = meta.get("id")
    if not meta_id or not isinstance(meta_id, str):
        return False, "metadata.json must contain an 'id' field (string).", component_dir, ""
    if folder_name is not None and meta_id != folder_name:
        return False, f"metadata.json 'id' must match the folder name: '{folder_name}'.", component_dir, ""
    if not _VALID_COMPONENT_TYPE.match(meta_id):
        return False, "Component id must be lowercase letters, numbers, and underscores (e.g. my_component).", component_dir, ""
    if meta_id in ("question_reviewer", "__pycache__"):
        return False, f"Component id '{meta_id}' is reserved.", component_dir, ""

    ctype = meta.get("type")
    if not ctype or not isinstance(ctype, str):
        return False, "metadata.json must contain a 'type' field (e.g. 'tool', 'review', 'post_process').", component_dir, ""
    allowed = ("tool", "review", "post_process", "pre_process")
    if ctype not in allowed:
        return False, f"metadata.json 'type' must be one of: {', '.join(allowed)}.", component_dir, ""

    name = folder_name if folder_name is not None else meta_id
    return True, "", component_dir, name


@review_process_design_bp.post("/api/components/import")
def api_import_component():
    """Import a review component from an uploaded ZIP file."""
    if "file" not in request.files:
        return jsonify({"error": "No file uploaded. Please choose a ZIP file."}), 400
    f = request.files["file"]
    if not f.filename:
        return jsonify({"error": "No file selected."}), 400
    if not f.filename.lower().endswith(".zip"):
        return jsonify({"error": "File must be a ZIP archive (.zip)."}), 400

    if not _REVIEW_COMPONENTS_DIR.exists():
        _REVIEW_COMPONENTS_DIR.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as tmpdir:
        zip_path = Path(tmpdir) / "upload.zip"
        try:
            f.save(str(zip_path))
        except Exception as e:
            logger.error(f"Error saving upload: {e}")
            return jsonify({"error": "Failed to save uploaded file."}), 500

        ok, err, component_dir, folder_name = _validate_component_zip(zip_path, Path(tmpdir) / "extract")
        if not ok:
            return jsonify({"error": err}), 400

        target = _REVIEW_COMPONENTS_DIR / folder_name
        if target.exists():
            return jsonify({"error": f"A component named '{folder_name}' already exists. Remove or rename it first."}), 400

        try:
            target.mkdir(parents=True, exist_ok=False)
            for item in component_dir.iterdir():
                dest = target / item.name
                if item.is_file():
                    shutil.copy2(item, dest)
                elif item.is_dir() and item.name != "__pycache__":
                    shutil.copytree(item, dest, dirs_exist_ok=False)
        except Exception as e:
            logger.error(f"Error copying component: {e}")
            return jsonify({"error": f"Failed to install component: {str(e)}"}), 500

    return jsonify({
        "success": True,
        "message": f"Component '{folder_name}' was added successfully. It will appear in the tools list.",
        "component_id": folder_name,
    })


# Review components that cannot be deleted (built-in). Pre-process and post-process are always protected.
_PROTECTED_REVIEW_COMPONENT_IDS = frozenset({"question_reviewer", "github_checker", "figure_reviewer", "specialist"})


@review_process_design_bp.delete("/api/components/<component_id>")
def api_delete_component(component_id: str):
    """Delete a user-added review/tool component. Built-in and pre/post-process components cannot be deleted."""
    if component_id in _PROTECTED_REVIEW_COMPONENT_IDS:
        return jsonify({"error": f"Component '{component_id}' is built-in and cannot be deleted."}), 400
    target = _REVIEW_COMPONENTS_DIR / component_id
    if not target.exists():
        return jsonify({"error": f"Component '{component_id}' not found."}), 404
    if not target.is_dir():
        return jsonify({"error": f"Invalid component path."}), 400
    meta_file = target / "metadata.json"
    if meta_file.exists():
        try:
            with open(meta_file, "r", encoding="utf-8") as f:
                meta = json.load(f)
            ctype = meta.get("type")
            if ctype in ("pre_process", "post_process"):
                return jsonify({"error": "Pre-process and post-process components cannot be deleted."}), 400
        except Exception:
            pass
    try:
        shutil.rmtree(target)
    except Exception as e:
        logger.error(f"Error deleting component {component_id}: {e}")
        return jsonify({"error": f"Failed to delete component: {str(e)}"}), 500
    return jsonify({"success": True, "message": f"Component '{component_id}' was removed."})
