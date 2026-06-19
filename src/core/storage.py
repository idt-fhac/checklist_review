from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

ISO_FORMAT = "%Y-%m-%dT%H-%M-%S"
META_FILE = "collection.json"
PLOT_FILE = "plot.json"
SELECTED_FILE = "selected_list.json"
LEGACY_SELECTED_FILE = "selected_list.txt"

# New collection layout (source/pdf, source/metadata, source/md, collection_artifacts/)
COLLECTION_ARTIFACTS_DIR = "collection_artifacts"
SOURCE_PDF_DIR = "source/pdf"
SOURCE_METADATA_DIR = "source/metadata"
SOURCE_MD_DIR = "source/md"
SELECTED_PAPERS_FILE = "selected_papers.json"
COLLECTION_EMB_FILE = "collection_emb.json"


def _collections_root(collections_root: Path) -> Path:
    root = Path(collections_root)
    root.mkdir(parents=True, exist_ok=True)
    return root


def _slug(name: str) -> str:
    return name.strip().replace(" ", "_").lower() or "collection"


def _collection_dir(collections_root: Path, collection_name: str, create: bool = True) -> Path:
    directory = _collections_root(collections_root) / _slug(collection_name)
    if create:
        directory.mkdir(parents=True, exist_ok=True)
    return directory


def _collection_artifacts_dir(collection_dir: Path, create: bool = True) -> Path:
    path = collection_dir / COLLECTION_ARTIFACTS_DIR
    if create:
        path.mkdir(parents=True, exist_ok=True)
    return path


def _source_pdf_dir(collection_dir: Path, create: bool = True) -> Path:
    path = collection_dir / SOURCE_PDF_DIR
    if create:
        path.mkdir(parents=True, exist_ok=True)
    return path


def _source_metadata_dir(collection_dir: Path, create: bool = True) -> Path:
    path = collection_dir / SOURCE_METADATA_DIR
    if create:
        path.mkdir(parents=True, exist_ok=True)
    return path


def _source_md_dir(collection_dir: Path, create: bool = True) -> Path:
    path = collection_dir / SOURCE_MD_DIR
    if create:
        path.mkdir(parents=True, exist_ok=True)
    return path


def _meta_path(collection_dir: Path) -> Path:
    return collection_dir / COLLECTION_ARTIFACTS_DIR / META_FILE


def _selected_papers_file_path(collection_dir: Path) -> Path:
    return collection_dir / COLLECTION_ARTIFACTS_DIR / SELECTED_PAPERS_FILE


def _collection_emb_path(collection_dir: Path) -> Path:
    return collection_dir / COLLECTION_ARTIFACTS_DIR / COLLECTION_EMB_FILE


def _vis_dir(collection_dir: Path) -> Path:
    path = collection_dir / "vis"
    path.mkdir(parents=True, exist_ok=True)
    return path

def _selected_papers_dir(collection_dir: Path) -> Path:
    path = collection_dir / "selected_papers"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _load_selected_from_dir(directory: Path) -> List[Dict[str, Any]]:
    # New layout: collection_artifacts/selected_papers.json
    json_path = _selected_papers_file_path(directory)
    if json_path.exists():
        try:
            with json_path.open(encoding="utf-8") as fp:
                data = json.load(fp)
                if isinstance(data, list):
                    return data
        except Exception:
            pass
    # Legacy: selected_papers/list.json
    selected_dir = directory / "selected_papers"
    if selected_dir.exists():
        list_path = selected_dir / "list.json"
        if list_path.exists():
            try:
                with list_path.open(encoding="utf-8") as fp:
                    return json.load(fp)
            except Exception:
                pass
    json_path = directory / SELECTED_FILE
    if json_path.exists():
        try:
            with json_path.open(encoding="utf-8") as fp:
                data = json.load(fp)
                if isinstance(data, list):
                    return data
        except Exception:
            pass
    legacy_path = directory / LEGACY_SELECTED_FILE
    if legacy_path.exists():
        try:
            with legacy_path.open(encoding="utf-8") as fp:
                entries = []
                for line in fp:
                    line = line.strip()
                    if not line:
                        continue
                    entries.append({"filename": line, "paper_id": line, "title": line})
                return entries
        except Exception:
            pass
    return []


def _checklists_dir(base_dir: Path) -> Path:
    from src.core.workspace import get_checklists_dir
    return get_checklists_dir()


def _reviews_dir(collection_dir: Path) -> Path:
    path = Path(collection_dir) / "reviews"
    path.mkdir(parents=True, exist_ok=True)
    return path


def save_collection(collections_root: Path, collection_name: str, payload: Dict[str, Any]) -> Path:
    directory = _collection_dir(collections_root, collection_name)
    _collection_artifacts_dir(directory)
    path = _meta_path(directory)
    if "collection_name" not in payload:
        payload["collection_name"] = collection_name
    
    with path.open("w", encoding="utf-8") as fp:
        json.dump(payload, fp, indent=2)
    return path


def list_collections(collections_root: Path) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    root = _collections_root(collections_root)
    for directory in sorted(root.iterdir()):
        if not directory.is_dir():
            continue
        # Skip internal dirs (e.g. .review_tasks for task persistence)
        if directory.name.startswith("."):
            continue
        meta_path = _meta_path(directory)
        if not meta_path.exists():
            meta_path = directory / META_FILE  # legacy
        updated_at = datetime.fromtimestamp(meta_path.stat().st_mtime) if meta_path.exists() else datetime.fromtimestamp(directory.stat().st_mtime)
        display_name = directory.name
        if meta_path.exists():
            try:
                with meta_path.open(encoding="utf-8") as fp:
                    meta = json.load(fp)
                    if isinstance(meta, dict) and "collection_name" in meta:
                        display_name = meta["collection_name"]
            except Exception:
                pass
        items.append({
            "name": display_name,
            "slug": directory.name,
            "path": str(meta_path if meta_path.exists() else directory),
            "dir": str(directory),
            "updated_at": updated_at,
            "selected_files": _load_selected_from_dir(directory),
        })
    return items


def load_collection(collections_root: Path, collection_name: str) -> Dict[str, Any] | None:
    directory = _collection_dir(collections_root, collection_name, create=False)
    meta_path = _meta_path(directory)
    if not meta_path.exists():
        meta_path = directory / META_FILE  # legacy
    if not meta_path.exists():
        slug_name = _slug(collection_name)
        directory = _collections_root(collections_root) / slug_name
        meta_path = _meta_path(directory)
        if not meta_path.exists():
            meta_path = directory / META_FILE
        if not meta_path.exists():
            return None
    
    with meta_path.open(encoding="utf-8") as fp:
        data = json.load(fp)
    
    # Load selected files and filter to only include papers that actually exist
    selected_files = _load_selected_from_dir(directory)
    papers = data.get("papers", [])
    
    # Create a set of valid paper identifiers for quick lookup
    valid_paper_ids = set()
    valid_filenames = set()
    for paper in papers:
        paper_id = paper.get("paper_id") or paper.get("arxiv_id")
        if paper_id:
            valid_paper_ids.add(paper_id)
        filename = paper.get("filename")
        if filename:
            valid_filenames.add(filename)
    
    # Filter selected files to only include papers that exist
    filtered_selected = [
        entry for entry in selected_files
        if (entry.get("paper_id") in valid_paper_ids
            or entry.get("arxiv_id") in valid_paper_ids
            or entry.get("filename") in valid_filenames)
    ]
    
    # If any were filtered out, save the cleaned list
    if len(filtered_selected) != len(selected_files):
        save_selected_list(collections_root, collection_name, filtered_selected)
    
    data["selected_files"] = filtered_selected
    return data


def save_plot(collections_root: Path, collection_name: str, plot_payload: Dict[str, Any]) -> Path:
    directory = _collection_dir(collections_root, collection_name)
    _collection_artifacts_dir(directory)
    path = _collection_emb_path(directory)
    with path.open("w", encoding="utf-8") as fp:
        json.dump(plot_payload, fp)
    return path


def load_plot(collections_root: Path, collection_name: str) -> Dict[str, Any] | None:
    directory = _collection_dir(collections_root, collection_name, create=False)
    path = _collection_emb_path(directory)
    if not path.exists():
        path = directory / COLLECTION_ARTIFACTS_DIR / "selected_papers_emb.json"  # legacy name
    if not path.exists():
        path = directory / "vis" / "embs.json"  # legacy
    if not path.exists():
        path = directory / PLOT_FILE  # legacy
    if not path.exists():
        return None
    try:
        with path.open(encoding="utf-8") as fp:
            return json.load(fp)
    except Exception:
        return None


def get_visualization_status(collections_root: Path, collection_name: str) -> Dict[str, Any]:
    directory = _collection_dir(collections_root, collection_name, create=False)
    meta_path = _meta_path(directory)
    if not meta_path.exists():
        meta_path = directory / META_FILE  # legacy
    plot_path = _collection_emb_path(directory)
    if not plot_path.exists():
        plot_path = directory / COLLECTION_ARTIFACTS_DIR / "selected_papers_emb.json"  # legacy name
    if not plot_path.exists():
        plot_path = directory / "vis" / "embs.json"  # legacy
    if not plot_path.exists():
        plot_path = directory / PLOT_FILE  # legacy
    if not plot_path.exists():
        return {"status": "missing", "message": "No visualization generated."}
    meta_mtime = meta_path.stat().st_mtime if meta_path.exists() else 0
    plot_mtime = plot_path.stat().st_mtime
    is_stale = meta_mtime > plot_mtime
    return {
        "status": "stale" if is_stale else "ok",
        "message": "Visualization might be outdated." if is_stale else "Up to date."
    }


def save_checklist(collections_root: Path, collection_name: str, checklist: List[Dict[str, Any]]) -> Path:
    """Save checklist to global workspaces/guest/checklists directory"""
    timestamp = datetime.utcnow().strftime(ISO_FORMAT)
    # Get base directory (project root)
    base_dir = Path(__file__).resolve().parent.parent.parent
    path = _checklists_dir(base_dir) / f"{timestamp}.json"
    with path.open("w", encoding="utf-8") as fp:
        json.dump(checklist, fp, indent=2)
    return path


def list_checklists(base_dir: Path) -> List[Dict[str, Any]]:
    """List all checklists from workspaces/guest/checklists directory (global, not per collection)"""
    items: List[Dict[str, Any]] = []
    checklist_dir = _checklists_dir(base_dir)
    
    if not checklist_dir.exists():
        return items
    
    # Only list JSON files (no PDF support)
    for json_file in sorted(checklist_dir.glob("*.json")):
        stem = json_file.stem
        items.append({
            "name": stem,
            "path": str(json_file),
            "created_at": datetime.fromtimestamp(json_file.stat().st_mtime),
        })
    
    return items


def load_checklist(path: str) -> List[Dict[str, Any]]:
    target = Path(path)
    if not target.exists():
        return []
    with target.open(encoding="utf-8") as fp:
        data = json.load(fp)
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        return [data]
    return []


def save_review(collections_root: Path, checklist_identifier: str, payload: Dict[str, Any]) -> Path:
    """Save review - checklist_identifier can be a checklist name or path"""
    timestamp = datetime.utcnow().strftime(ISO_FORMAT)
    checklist_path = Path(checklist_identifier)
    if checklist_path.exists():
        # If it's a path to a checklist in workspaces/guest/checklists, we need to find the collection
        # For now, we'll use a default collection or extract from payload
        collection_name = payload.get("collection", "default")
        collection_dir = _collection_dir(collections_root, collection_name)
    else:
        # Assume checklist_identifier is a collection name (legacy behavior)
        collection_dir = _collection_dir(collections_root, checklist_identifier)
    path = _reviews_dir(collection_dir) / f"{timestamp}.json"
    with path.open("w", encoding="utf-8") as fp:
        json.dump(payload, fp, indent=2)
    return path


def save_selected_list(collections_root: Path, collection_name: str, entries: List[Dict[str, Any]]) -> Path:
    directory = _collection_dir(collections_root, collection_name)
    _collection_artifacts_dir(directory)
    path = _selected_papers_file_path(directory)
    with path.open("w", encoding="utf-8") as fp:
        json.dump(entries, fp, indent=2)
    return path


def load_selected_list(collections_root: Path, collection_name: str) -> List[Dict[str, Any]]:
    directory = _collection_dir(collections_root, collection_name, create=False)
    if not directory.exists():
        return []
    return _load_selected_from_dir(directory)


def list_selected_files(collections_root: Path, collection_name: str) -> List[Dict[str, Any]]:
    directory = _collection_dir(collections_root, collection_name, create=False)
    selected_files = _load_selected_from_dir(directory)
    results: List[Dict[str, Any]] = []
    pdf_dir = _source_pdf_dir(directory, create=False)
    for entry in selected_files:
        filename = entry.get("filename")
        if not filename:
            continue
        pdf_path = pdf_dir / filename if pdf_dir.exists() else directory / "source" / filename  # legacy
        results.append({
            "filename": filename,
            "pdf_path": str(pdf_path),
            "title": entry.get("title"),
            "paper_id": entry.get("paper_id"),
        })
    return results

def create_new_collection(collections_root: Path, name: str | None = None) -> str:
    root = _collections_root(collections_root)
    if not name:
        idx = 1
        while True:
            name = f"new_collection_{idx}"
            path = root / _slug(name)
            if not path.exists():
                break
            idx += 1
    original_name = name
    directory = _collection_dir(collections_root, name, create=True)
    _source_pdf_dir(directory)
    _source_metadata_dir(directory)
    _source_md_dir(directory)
    _collection_artifacts_dir(directory)
    save_collection(collections_root, name, {
        "collection_name": original_name,
        "source_folder": SOURCE_PDF_DIR,
        "papers": [],
        "generated_at": datetime.utcnow().isoformat()
    })
    # Process definitions are now global, so we don't create process_definitions directory in collections
        
    return original_name

def rename_collection(collections_root: Path, old_name: str, new_name: str) -> bool:
    old_dir = _collection_dir(collections_root, old_name, create=False)
    if not old_dir.exists():
        old_slug = _slug(old_name)
        old_dir = _collections_root(collections_root) / old_slug
        if not old_dir.exists():
            return False
    
    new_slug = _slug(new_name)
    new_dir = _collections_root(collections_root) / new_slug
    
    if new_dir.exists():
        return False
    shutil.move(str(old_dir), str(new_dir))
    payload = load_collection(collections_root, new_slug)
    if payload:
        payload["collection_name"] = new_name
        payload["source_folder"] = SOURCE_PDF_DIR
        save_collection(collections_root, new_slug, payload)
        
    return True

def delete_collection(collections_root: Path, collection_name: str) -> bool:
    directory = _collection_dir(collections_root, collection_name, create=False)
    if directory.exists() and directory.is_dir():
        shutil.rmtree(directory)
        return True
    return False


def migrate_collection_to_new_structure(collections_root: Path, collection_name: str) -> bool:
    """
    Migrate a collection from the old layout (source/, source_extracted/, collection.json at root,
    selected_papers/list.json, vis/embs.json) to the new layout (source/pdf, source/metadata, source/md,
    collection_artifacts/collection.json, selected_papers.json, collection_emb.json).
    Returns True if migration was performed or not needed (already new), False on error.
    """
    directory = _collection_dir(collections_root, collection_name, create=False)
    if not directory.exists():
        return False
    artifacts_dir = directory / COLLECTION_ARTIFACTS_DIR
    legacy_meta = directory / META_FILE
    if legacy_meta.exists() and not (artifacts_dir / META_FILE).exists():
        artifacts_dir.mkdir(parents=True, exist_ok=True)
        with legacy_meta.open(encoding="utf-8") as fp:
            payload = json.load(fp)
        for p in payload.get("papers", []):
            fp_val = p.get("file_path", "")
            if fp_val and "source/pdf" not in fp_val:
                fn = p.get("filename") or Path(fp_val).name
                if fn:
                    p["file_path"] = f"{SOURCE_PDF_DIR}/{fn}"
        payload["source_folder"] = SOURCE_PDF_DIR
        (artifacts_dir / META_FILE).write_text(json.dumps(payload, indent=2), encoding="utf-8")
        legacy_meta.unlink()
    old_selected = directory / "selected_papers" / "list.json"
    if old_selected.exists():
        artifacts_dir.mkdir(parents=True, exist_ok=True)
        selected_path = artifacts_dir / SELECTED_PAPERS_FILE
        if not selected_path.exists():
            shutil.copy2(old_selected, selected_path)
        old_selected.unlink()
        try:
            if not any((directory / "selected_papers").iterdir()):
                (directory / "selected_papers").rmdir()
        except Exception:
            pass
    old_embs = directory / "vis" / "embs.json"
    if old_embs.exists():
        artifacts_dir.mkdir(parents=True, exist_ok=True)
        emb_path = artifacts_dir / COLLECTION_EMB_FILE
        if not emb_path.exists():
            shutil.copy2(old_embs, emb_path)
        old_embs.unlink()
        try:
            if not any((directory / "vis").iterdir()):
                (directory / "vis").rmdir()
        except Exception:
            pass
    old_source = directory / "source"
    if old_source.exists() and old_source.is_dir():
        pdf_dir = directory / SOURCE_PDF_DIR
        pdf_dir.mkdir(parents=True, exist_ok=True)
        for f in old_source.iterdir():
            if f.is_file() and f.suffix.lower() == ".pdf":
                dest = pdf_dir / f.name
                if not dest.exists():
                    shutil.move(str(f), str(dest))
        try:
            if not any(old_source.iterdir()):
                old_source.rmdir()
        except Exception:
            pass
    old_extracted = directory / "source_extracted"
    if old_extracted.exists() and old_extracted.is_dir():
        md_dir = directory / SOURCE_MD_DIR
        meta_dir = directory / SOURCE_METADATA_DIR
        md_dir.mkdir(parents=True, exist_ok=True)
        meta_dir.mkdir(parents=True, exist_ok=True)
        for f in old_extracted.iterdir():
            if f.is_file():
                if f.suffix.lower() == ".md":
                    dest = md_dir / f.name
                    if not dest.exists():
                        shutil.move(str(f), str(dest))
                elif f.suffix.lower() == ".json":
                    dest = meta_dir / f.name
                    if not dest.exists():
                        shutil.move(str(f), str(dest))
        try:
            if not any(old_extracted.iterdir()):
                old_extracted.rmdir()
        except Exception:
            pass
    return True


def remove_paper_from_review_processes(
    collections_root: Path, collection_name: str, paper_filename: str
) -> None:
    """
    Remove all review data for a paper (including human_verification.json and answers)
    from every review process and checklist folder. Call this whenever a paper is deleted.
    """
    directory = _collection_dir(collections_root, collection_name, create=False)
    review_processes_dir = directory / "review_processes"
    if not review_processes_dir.exists() or not review_processes_dir.is_dir():
        return
    paper_filename = (paper_filename or "").strip()
    if not paper_filename:
        return
    if not paper_filename.endswith(".pdf"):
        paper_filename = f"{paper_filename}.pdf"
    paper_names_to_check = [paper_filename]
    if paper_filename.endswith(".pdf"):
        paper_names_to_check.append(Path(paper_filename).stem)
    else:
        paper_names_to_check.append(f"{paper_filename}.pdf")
    for process_dir in review_processes_dir.iterdir():
        if not process_dir.is_dir():
            continue
        for paper_name in paper_names_to_check:
            paper_folder = process_dir / paper_name
            if paper_folder.exists() and paper_folder.is_dir():
                try:
                    shutil.rmtree(paper_folder)
                except Exception:
                    pass
        for subdir in process_dir.iterdir():
            if not subdir.is_dir():
                continue
            for paper_name in paper_names_to_check:
                paper_folder = subdir / paper_name
                if paper_folder.exists() and paper_folder.is_dir():
                    try:
                        shutil.rmtree(paper_folder)
                    except Exception:
                        pass


def remove_paper(collections_root: Path, collection_name: str, paper_id: str) -> bool:
    payload = load_collection(collections_root, collection_name)
    if not payload:
        return False
    
    papers = payload.get("papers", [])
    target = next((p for p in papers if p.get("paper_id") == paper_id or p.get("arxiv_id") == paper_id), None)
    
    new_papers = [
        p for p in papers 
        if p.get("paper_id") != paper_id and p.get("arxiv_id") != paper_id
    ]
    
    if len(papers) == len(new_papers):
        return False
    if target:
        filename = target.get("filename") or Path(target.get("file_path", "")).name
        if filename:
            directory = _collection_dir(collections_root, collection_name, create=False)
            
            # Delete PDF and extracted files (new layout: source/pdf, source/md, source/metadata)
            pdf_stem = Path(filename).stem
            source_file = _source_pdf_dir(directory, create=False) / filename
            if not source_file.exists():
                source_file = directory / "source" / filename  # legacy
            if source_file.exists():
                try:
                    source_file.unlink()
                except Exception:
                    pass
            md_dir = _source_md_dir(directory, create=False)
            meta_dir = _source_metadata_dir(directory, create=False)
            if md_dir.exists():
                md_file = md_dir / f"{pdf_stem}.md"
                if md_file.exists():
                    try:
                        md_file.unlink()
                    except Exception:
                        pass
            if meta_dir.exists():
                json_file = meta_dir / f"{pdf_stem}.json"
                if json_file.exists():
                    try:
                        json_file.unlink()
                    except Exception:
                        pass
            # Legacy: source_extracted
            legacy_extracted = directory / "source_extracted"
            if legacy_extracted.exists():
                for f in (legacy_extracted / f"{pdf_stem}.md", legacy_extracted / f"{pdf_stem}.json"):
                    if f.exists():
                        try:
                            f.unlink()
                        except Exception:
                            pass
            
            # Remove paper from selected files list
            selected_files = load_selected_list(collections_root, collection_name)
            if selected_files:
                # Remove entries matching paper_id, arxiv_id, or filename
                updated_selected = [
                    entry for entry in selected_files
                    if entry.get("paper_id") != paper_id
                    and entry.get("arxiv_id") != paper_id
                    and entry.get("filename") != filename
                ]
                if len(updated_selected) != len(selected_files):
                    # Only save if something was removed
                    save_selected_list(collections_root, collection_name, updated_selected)

            remove_paper_from_review_processes(collections_root, collection_name, filename)

    payload["papers"] = new_papers
    save_collection(collections_root, collection_name, payload)
    
    # Remove paper from all review_processes (including when target had no filename)
    paper_filename = None
    if target:
        paper_filename = target.get("filename") or Path(target.get("file_path", "")).name
    if not paper_filename:
        paper_filename = paper_id
    remove_paper_from_review_processes(collections_root, collection_name, paper_filename)
    
    return True


def remove_all_papers(collections_root: Path, collection_name: str) -> bool:
    """
    Remove all papers from a collection.
    Deletes all PDF files, extracted markdown/JSON files, and clears selected files.
    
    Args:
        collections_root: Root directory for collections
        collection_name: Name of the collection
        
    Returns:
        True if successful, False otherwise
    """
    payload = load_collection(collections_root, collection_name)
    if not payload:
        return False
    
    papers = payload.get("papers", [])
    if not papers:
        return True  # Already empty
    
    directory = _collection_dir(collections_root, collection_name, create=False)
    if not directory.exists():
        return False
    
    pdf_dir = _source_pdf_dir(directory, create=False)
    md_dir = _source_md_dir(directory, create=False)
    meta_dir = _source_metadata_dir(directory, create=False)
    legacy_source = directory / "source"
    legacy_extracted = directory / "source_extracted"
    deleted_count = 0
    for paper in papers:
        filename = paper.get("filename") or Path(paper.get("file_path", "")).name
        if not filename:
            continue
        pdf_stem = Path(filename).stem
        # PDF
        for d in (pdf_dir, legacy_source):
            if d.exists():
                f = d / filename
                if f.exists():
                    try:
                        f.unlink()
                        deleted_count += 1
                    except Exception:
                        pass
                    break
        # MD and metadata (new + legacy)
        for d in (md_dir, legacy_extracted):
            if d.exists():
                for ext in (".md", ".json"):
                    f = d / f"{pdf_stem}{ext}"
                    if f.exists():
                        try:
                            f.unlink()
                        except Exception:
                            pass
        if meta_dir.exists():
            f = meta_dir / f"{pdf_stem}.json"
            if f.exists():
                try:
                    f.unlink()
                except Exception:
                    pass
        remove_paper_from_review_processes(collections_root, collection_name, filename)
    
    # Clear selected files list
    try:
        save_selected_list(collections_root, collection_name, [])
    except Exception:
        pass
    
    # Update collection payload
    payload["papers"] = []
    save_collection(collections_root, collection_name, payload)
    
    return True


def _generated_dir(collection_dir: Path) -> Path:
    path = collection_dir / "generated"
    path.mkdir(parents=True, exist_ok=True)
    return path


# Global process definitions (config/pipelines)
def _global_processes_dir(base_dir: Path) -> Path:
    from src.core.config_loader import get_repo_config_dir
    return get_repo_config_dir() / "pipelines"


def list_global_processes(base_dir: Path) -> List[Dict[str, Any]]:
    """List all pipelines declared in config/pipelines/."""
    from src.core.config_loader import list_pipelines

    results = []
    for item in list_pipelines():
        pipeline_id = item["id"]
        results.append(
            {
                "name": item.get("name", pipeline_id),
                "slug": pipeline_id,
                "filename": f"{pipeline_id}.yaml",
                "path": item.get("path"),
                "updated_at": datetime.fromtimestamp(Path(item["path"]).stat().st_mtime)
                if item.get("path") and Path(item["path"]).exists()
                else datetime.utcnow(),
                "data": {"name": item.get("name"), "profile": item.get("profile")},
            }
        )
    return results


def load_global_process(base_dir: Path, process_name: str) -> Dict[str, Any] | None:
    """Load a pipeline from config/pipelines/ as a read-only flow graph."""
    from src.review_workflow.engine.pipeline_loader import load_pipeline_flow

    try:
        return load_pipeline_flow(process_name)
    except FileNotFoundError:
        slug = _slug(process_name)
        try:
            return load_pipeline_flow(slug)
        except FileNotFoundError:
            return None


def save_global_process(base_dir: Path, process_name: str, data: Dict[str, Any]) -> Path:
    """Pipelines are config-managed; UI mutation is not supported."""
    raise PermissionError(
        "Pipelines are defined in config/pipelines/*.yaml and cannot be saved from the UI."
    )


def delete_global_process(base_dir: Path, process_name: str) -> bool:
    """Pipelines are config-managed; UI deletion is not supported."""
    return False


def list_generated_answers(collections_root: Path, collection_name: str, process_name: str = None, checklist_name: str = None) -> List[Dict[str, Any]]:
    directory = _collection_dir(collections_root, collection_name, create=False)
    if not directory.exists():
        return []
    
    if not process_name:
         return []
    proc_dir = directory / "review_processes" / _slug(process_name)
    if not proc_dir.exists():
        proc_dir = directory / "review_processes" / process_name
    if not proc_dir.exists():
        return []
    
    # If checklist_name is provided, look in checklist subdirectory
    if checklist_name:
        checklist_name_clean = checklist_name
        if checklist_name_clean.endswith('.json'):
            checklist_name_clean = checklist_name_clean[:-5]
        checklist_dir = proc_dir / _slug(checklist_name_clean)
        if not checklist_dir.exists():
            checklist_dir = proc_dir / checklist_name_clean
        if not checklist_dir.exists():
            return []
        proc_dir = checklist_dir
        
    results = []
    for paper_dir in sorted(proc_dir.iterdir()):
        if not paper_dir.is_dir():
             continue
             
        answers_file = paper_dir / "answers.json"
        if answers_file.exists():
             results.append({
                "paper_id": paper_dir.name, 
                "filename": paper_dir.name,
                "path": str(answers_file),
                "generated_at": datetime.fromtimestamp(answers_file.stat().st_mtime),
                "status": "completed"
            })
            
    return results


def get_review_paper_dir(
    collections_root: Path,
    collection_name: str,
    process_name: str,
    checklist_name: str,
    paper_id: str,
) -> Path | None:
    """Return the paper directory (collection/.../process/checklist/paper_id) for a review result, or None if it does not exist."""
    directory = _collection_dir(collections_root, collection_name, create=False)
    if not directory.exists() or not process_name:
        return None
    base_path = directory / "review_processes" / _slug(process_name)
    if not base_path.exists():
        base_path = directory / "review_processes" / process_name
    if not base_path.exists():
        return None
    if checklist_name:
        checklist_name_clean = checklist_name.rstrip(".json") if checklist_name.endswith(".json") else checklist_name
        check_dir = base_path / _slug(checklist_name_clean)
        if not check_dir.exists():
            check_dir = base_path / checklist_name_clean
        if not check_dir.exists():
            return None
        base_path = check_dir
    paper_dir = base_path / paper_id
    return paper_dir if paper_dir.exists() and paper_dir.is_dir() else None


def get_review_outputs_dir(
    collections_root: Path,
    collection_name: str,
    process_name: str,
    checklist_name: str,
    paper_id: str,
) -> Path | None:
    """Return the outputs/ directory for a given review result, or None if it does not exist."""
    paper_dir = get_review_paper_dir(collections_root, collection_name, process_name, checklist_name, paper_id)
    if not paper_dir:
        return None
    outputs_dir = paper_dir / "outputs"
    return outputs_dir if outputs_dir.exists() else None


def list_review_outputs(
    collections_root: Path,
    collection_name: str,
    process_name: str,
    checklist_name: str,
    paper_id: str,
) -> List[Dict[str, Any]]:
    """List files in the outputs/ folder for a review result. Returns list of {name, type} (type: 'md'|'pdf'|'json'|'other')."""
    outputs_dir = get_review_outputs_dir(collections_root, collection_name, process_name, checklist_name, paper_id)
    if not outputs_dir:
        return []
    result = []
    for f in sorted(outputs_dir.iterdir()):
        if not f.is_file():
            continue
        name = f.name
        suffix = f.suffix.lower()
        if suffix == ".md":
            ftype = "md"
        elif suffix == ".pdf":
            ftype = "pdf"
        elif suffix == ".json":
            ftype = "json"
        else:
            ftype = "other"
        result.append({"name": name, "type": ftype})
    return result


def load_generated_answer(collections_root: Path, collection_name: str, paper_id: str, process_name: str = None, checklist_name: str = None) -> Dict[str, Any] | None:
    directory = _collection_dir(collections_root, collection_name, create=False)
    
    if process_name:
        # Build base path
        base_path = directory / "review_processes" / _slug(process_name)
        if not base_path.exists():
            base_path = directory / "review_processes" / process_name
        
        # If checklist_name is provided, add it to the path
        if checklist_name:
            checklist_name_clean = checklist_name
            if checklist_name_clean.endswith('.json'):
                checklist_name_clean = checklist_name_clean[:-5]
            base_path = base_path / _slug(checklist_name_clean)
            if not base_path.exists():
                base_path = base_path.parent / checklist_name_clean
        
        # Try slug first (since data is saved with slugs), then exact match for backward compatibility
        path = base_path / paper_id / "answers.json"
        if not path.exists():
            # Try without checklist for backward compatibility
            path = directory / "review_processes" / _slug(process_name) / paper_id / "answers.json"
            if not path.exists():
                path = directory / "review_processes" / process_name / paper_id / "answers.json"
    else:
        path = _generated_dir(directory) / f"{paper_id}.json"
        
    if not path.exists():
        return None
        
    try:
        with path.open(encoding="utf-8") as fp:
            return json.load(fp)
    except:
        return None


def delete_generated_answer(collections_root: Path, collection_name: str, paper_id: str, process_name: str = None, checklist_name: str = None) -> bool:
    directory = _collection_dir(collections_root, collection_name, create=False)
    
    if process_name:
        # Build base path
        base_path = directory / "review_processes" / _slug(process_name)
        if not base_path.exists():
            base_path = directory / "review_processes" / process_name
        
        # If checklist_name is provided, add it to the path
        if checklist_name:
            checklist_name_clean = checklist_name
            if checklist_name_clean.endswith('.json'):
                checklist_name_clean = checklist_name_clean[:-5]
            base_path = base_path / _slug(checklist_name_clean)
            if not base_path.exists():
                base_path = base_path.parent / checklist_name_clean
        
        # Try slug first (since data is saved with slugs), then exact match for backward compatibility
        paper_folder = base_path / paper_id
        if not paper_folder.exists():
            # Try without checklist for backward compatibility
            paper_folder = directory / "review_processes" / _slug(process_name) / paper_id
            if not paper_folder.exists():
                paper_folder = directory / "review_processes" / process_name / paper_id
    else:
         gen_dir = _generated_dir(directory)
         path = gen_dir / f"{paper_id}.json"
         if path.exists():
             try:
                 path.unlink()
                 return True
             except:
                 return False
         return False
    
    # Delete the entire paper folder
    if paper_folder.exists() and paper_folder.is_dir():
        try:
            shutil.rmtree(paper_folder)
            return True
        except:
            return False
    return False

def rename_process_folders(collections_root: Path, old_process_name: str, new_process_name: str) -> Dict[str, Any]:
    """
    Rename process folders in all collections when a process is renamed.
    Returns a dict with 'renamed' (list of successful renames) and 'errors' (list of errors).
    """
    result = {"renamed": [], "errors": []}
    old_slug = _slug(old_process_name)
    new_slug = _slug(new_process_name)
    
    # If slugs are the same, no rename needed (just display name change)
    if old_slug == new_slug:
        return result
    
    collections_root_path = _collections_root(collections_root)
    if not collections_root_path.exists():
        return result
    
    for collection_dir in collections_root_path.iterdir():
        if not collection_dir.is_dir():
            continue
        
        review_processes_dir = collection_dir / "review_processes"
        if not review_processes_dir.exists():
            continue
        
        # Try both slug and exact name for old folder
        old_folder = review_processes_dir / old_slug
        if not old_folder.exists():
            old_folder = review_processes_dir / old_process_name
        
        if old_folder.exists() and old_folder.is_dir():
            new_folder = review_processes_dir / new_slug
            if new_folder.exists():
                result["errors"].append(f"Collection {collection_dir.name}: target folder already exists")
                continue
            
            try:
                old_folder.rename(new_folder)
                result["renamed"].append(collection_dir.name)
            except Exception as e:
                result["errors"].append(f"Collection {collection_dir.name}: {str(e)}")
    
    return result


def delete_process_folders(collections_root: Path, process_name: str) -> Dict[str, Any]:
    """
    Delete process folders in all collections when a process is deleted.
    Returns a dict with 'deleted' (list of successful deletions) and 'errors' (list of errors).
    """
    result = {"deleted": [], "errors": []}
    process_slug = _slug(process_name)
    
    collections_root_path = _collections_root(collections_root)
    if not collections_root_path.exists():
        return result
    
    for collection_dir in collections_root_path.iterdir():
        if not collection_dir.is_dir():
            continue
        
        review_processes_dir = collection_dir / "review_processes"
        if not review_processes_dir.exists():
            continue
        
        # Try both slug and exact name
        process_folder = review_processes_dir / process_slug
        if not process_folder.exists():
            process_folder = review_processes_dir / process_name
        
        if process_folder.exists() and process_folder.is_dir():
            try:
                shutil.rmtree(process_folder)
                result["deleted"].append(collection_dir.name)
            except Exception as e:
                result["errors"].append(f"Collection {collection_dir.name}: {str(e)}")
    
    return result


def rename_checklist_folders(collections_root: Path, old_checklist_name: str, new_checklist_name: str) -> Dict[str, Any]:
    """
    Rename checklist folders in all collections and all processes when a checklist is renamed.
    Returns a dict with 'renamed' (list of successful renames) and 'errors' (list of errors).
    """
    result = {"renamed": [], "errors": []}
    old_slug = _slug(old_checklist_name)
    new_slug = _slug(new_checklist_name)
    
    # If slugs are the same, no rename needed (just display name change)
    if old_slug == new_slug:
        return result
    
    collections_root_path = _collections_root(collections_root)
    if not collections_root_path.exists():
        return result
    
    for collection_dir in collections_root_path.iterdir():
        if not collection_dir.is_dir():
            continue
        
        review_processes_dir = collection_dir / "review_processes"
        if not review_processes_dir.exists():
            continue
        
        # Iterate through all process folders
        for process_dir in review_processes_dir.iterdir():
            if not process_dir.is_dir():
                continue
            
            # Try both slug and exact name for old checklist folder
            old_checklist_folder = process_dir / old_slug
            if not old_checklist_folder.exists():
                old_checklist_folder = process_dir / old_checklist_name
            
            if old_checklist_folder.exists() and old_checklist_folder.is_dir():
                new_checklist_folder = process_dir / new_slug
                if new_checklist_folder.exists():
                    result["errors"].append(f"Collection {collection_dir.name}, Process {process_dir.name}: target folder already exists")
                    continue
                
                try:
                    old_checklist_folder.rename(new_checklist_folder)
                    result["renamed"].append(f"{collection_dir.name}/{process_dir.name}")
                except Exception as e:
                    result["errors"].append(f"Collection {collection_dir.name}, Process {process_dir.name}: {str(e)}")
    
    return result


def delete_checklist_folders(collections_root: Path, checklist_name: str) -> Dict[str, Any]:
    """
    Delete checklist folders in all collections and all processes when a checklist is deleted.
    Returns a dict with 'deleted' (list of successful deletions) and 'errors' (list of errors).
    """
    result = {"deleted": [], "errors": []}
    checklist_slug = _slug(checklist_name)
    
    collections_root_path = _collections_root(collections_root)
    if not collections_root_path.exists():
        return result
    
    for collection_dir in collections_root_path.iterdir():
        if not collection_dir.is_dir():
            continue
        
        review_processes_dir = collection_dir / "review_processes"
        if not review_processes_dir.exists():
            continue
        
        # Iterate through all process folders
        for process_dir in review_processes_dir.iterdir():
            if not process_dir.is_dir():
                continue
            
            # Try both slug and exact name
            checklist_folder = process_dir / checklist_slug
            if not checklist_folder.exists():
                checklist_folder = process_dir / checklist_name
            
            if checklist_folder.exists() and checklist_folder.is_dir():
                try:
                    shutil.rmtree(checklist_folder)
                    result["deleted"].append(f"{collection_dir.name}/{process_dir.name}")
                except Exception as e:
                    result["errors"].append(f"Collection {collection_dir.name}, Process {process_dir.name}: {str(e)}")
    
    return result


def process_result_exists(collections_root: Path, collection_name: str, process_name: str, paper_name: str, checklist_name: str = None) -> bool:
    directory = _collection_dir(collections_root, collection_name, create=False)
    
    # Build base path
    base_path = directory / "review_processes" / _slug(process_name)
    if not base_path.exists():
        base_path = directory / "review_processes" / process_name
    
    # If checklist_name is provided, add it to the path
    if checklist_name:
        checklist_name_clean = checklist_name
        if checklist_name_clean.endswith('.json'):
            checklist_name_clean = checklist_name_clean[:-5]
        base_path = base_path / _slug(checklist_name_clean)
        if not base_path.exists():
            base_path = base_path.parent / checklist_name_clean
    
    path = base_path / paper_name / "answers.json"
    if not path.exists():
        # Try without checklist for backward compatibility
        path = directory / "review_processes" / _slug(process_name) / paper_name / "answers.json"
        if not path.exists():
            path = directory / "review_processes" / process_name / paper_name / "answers.json"
    return path.exists()

def load_human_verification(collections_root: Path, collection_name: str, process_name: str, paper_id: str, checklist_name: str = None) -> Dict[str, Any] | None:
    directory = _collection_dir(collections_root, collection_name, create=False)
    
    # Build base path
    base_path = directory / "review_processes" / _slug(process_name)
    if not base_path.exists():
        base_path = directory / "review_processes" / process_name
    
    # If checklist_name is provided, add it to the path
    if checklist_name:
        checklist_name_clean = checklist_name
        if checklist_name_clean.endswith('.json'):
            checklist_name_clean = checklist_name_clean[:-5]
        base_path = base_path / _slug(checklist_name_clean)
        if not base_path.exists():
            base_path = base_path.parent / checklist_name_clean
    
    path = base_path / paper_id / "human_verification.json"
    if not path.exists():
        # Try without checklist for backward compatibility
        path = directory / "review_processes" / _slug(process_name) / paper_id / "human_verification.json"
        if not path.exists():
            path = directory / "review_processes" / process_name / paper_id / "human_verification.json"
    
    if not path.exists():
        return None
        
    try:
        with path.open(encoding="utf-8") as fp:
            return json.load(fp)
    except:
        return None

def save_human_verification(collections_root: Path, collection_name: str, process_name: str, paper_id: str, data: Dict[str, Any], checklist_name: str = None) -> Path:
    directory = _collection_dir(collections_root, collection_name, create=False)
    
    # Build base path
    base_path = directory / "review_processes" / _slug(process_name)
    
    # If checklist_name is provided, add it to the path
    if checklist_name:
        checklist_name_clean = checklist_name
        if checklist_name_clean.endswith('.json'):
            checklist_name_clean = checklist_name_clean[:-5]
        base_path = base_path / _slug(checklist_name_clean)
    
    output_dir = base_path / paper_id
    output_dir.mkdir(parents=True, exist_ok=True)
    
    path = output_dir / "human_verification.json"
    with path.open("w", encoding="utf-8") as fp:
        json.dump(data, fp, indent=2)
    return path
