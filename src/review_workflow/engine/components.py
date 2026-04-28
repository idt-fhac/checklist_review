import json
from pathlib import Path
from typing import Dict, Any, List, Optional

def get_components_root() -> Path:
    return Path(__file__).resolve().parent.parent / "components"

def list_components_metadata() -> Dict[str, List[Dict[str, Any]]]:
    root = get_components_root()
    components = {
        "pre_process": [],
        "review": [],
        "post_process": []
    }
    
    if not root.exists():
        return components

    for phase_dir in root.iterdir():
        if not phase_dir.is_dir() or phase_dir.name == "__pycache__":
            continue
            
        phase_name = phase_dir.name
        
        for comp_dir in phase_dir.iterdir():
            if not comp_dir.is_dir() or comp_dir.name == "__pycache__":
                continue
                
            meta_file = comp_dir / "metadata.json"
            if meta_file.exists():
                with open(meta_file, "r", encoding="utf-8") as f:
                    meta = json.load(f)
                    
                if "id" not in meta:
                    meta["id"] = comp_dir.name
                    
                c_type = meta.get("type", phase_name)
                
                if c_type in components:
                    components[c_type].append(meta)
                else:
                    if "other" not in components:
                        components["other"] = []
                    components["other"].append(meta)
                    
    return components

def get_component_metadata(component_id: str) -> Optional[Dict[str, Any]]:
    all_grouped = list_components_metadata()
    for group in all_grouped.values():
        for comp in group:
            if comp.get("id") == component_id:
                return comp
    return None

