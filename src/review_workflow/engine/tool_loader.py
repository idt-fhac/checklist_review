"""
Utility module for dynamically discovering and loading review tools.
"""
import json
import importlib
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional, Type

from src.review_workflow.engine.base import BaseComponent

logger = logging.getLogger("ToolLoader")

# Path to evaluator components (tools + question_reviewer live here; tools are filtered by metadata)
REVIEW_COMPONENTS_DIR = Path(__file__).resolve().parent.parent / "components" / "evaluators"


def discover_review_tools() -> Dict[str, Dict[str, Any]]:
    """
    Discover all available review tools by scanning the review components directory.
    
    Returns:
        Dictionary mapping tool IDs to their metadata
    """
    tools = {}
    
    if not REVIEW_COMPONENTS_DIR.exists():
        logger.warning(f"Review components directory not found: {REVIEW_COMPONENTS_DIR}")
        return tools
    
    # Scan each subdirectory in the review components directory
    for component_dir in REVIEW_COMPONENTS_DIR.iterdir():
        if not component_dir.is_dir():
            continue
        
        # Skip question_reviewer as it's not a tool
        if component_dir.name == "question_reviewer":
            continue
        
        metadata_path = component_dir / "metadata.json"
        if not metadata_path.exists():
            logger.debug(f"No metadata.json found for {component_dir.name}, skipping")
            continue
        
        try:
            with open(metadata_path, "r", encoding="utf-8") as f:
                metadata = json.load(f)
            
            # Only include components marked as tools
            if metadata.get("type") == "tool":
                tool_id = metadata.get("id")
                if tool_id:
                    tools[tool_id] = {
                        "metadata": metadata,
                        "component_dir": component_dir,
                        "module_path": f"src.review_workflow.components.evaluators.{component_dir.name}.component"
                    }
                    logger.info(f"Discovered tool: {tool_id}")
        except Exception as e:
            logger.warning(f"Failed to load metadata for {component_dir.name}: {e}")
    
    return tools


def load_tool_class(tool_id: str, tools_registry: Optional[Dict[str, Dict[str, Any]]] = None) -> Optional[Type[BaseComponent]]:
    """
    Dynamically load the component class for a given tool ID.
    
    Args:
        tool_id: The ID of the tool to load
        tools_registry: Optional pre-discovered tools registry. If not provided, will discover tools.
    
    Returns:
        The component class or None if not found
    """
    if tools_registry is None:
        tools_registry = discover_review_tools()
    
    if tool_id not in tools_registry:
        logger.error(f"Tool {tool_id} not found in registry")
        return None
    
    tool_info = tools_registry[tool_id]
    module_path = tool_info["module_path"]
    
    try:
        # Import the module
        module = importlib.import_module(module_path)
        
        # Find the component class (typically named after the directory, e.g., VibeChecker, GithubChecker)
        # Try common naming patterns
        class_name = tool_info["component_dir"].name.replace("_", " ").title().replace(" ", "")
        
        # Look for the class in the module
        component_class = None
        for attr_name in dir(module):
            if attr_name.startswith("_"):
                continue
            try:
                attr = getattr(module, attr_name)
                if (isinstance(attr, type) and 
                    issubclass(attr, BaseComponent) and 
                    attr != BaseComponent and
                    attr_name.lower() == class_name.lower()):
                    component_class = attr
                    break
            except (TypeError, AttributeError):
                continue
        
        # If not found with expected name, try to find any BaseComponent subclass
        if component_class is None:
            for attr_name in dir(module):
                if attr_name.startswith("_"):
                    continue
                try:
                    attr = getattr(module, attr_name)
                    if (isinstance(attr, type) and 
                        issubclass(attr, BaseComponent) and 
                        attr != BaseComponent):
                        component_class = attr
                        logger.info(f"Found component class {attr_name} for tool {tool_id}")
                        break
                except (TypeError, AttributeError):
                    continue
        
        if component_class is None:
            logger.error(f"Could not find component class for tool {tool_id} in {module_path}")
            return None
        
        return component_class
    except Exception as e:
        logger.error(f"Failed to load tool class for {tool_id}: {e}")
        return None


def instantiate_tool(tool_id: str, tool_config: Dict[str, Any], 
                    tools_registry: Optional[Dict[str, Dict[str, Any]]] = None) -> Optional[BaseComponent]:
    """
    Instantiate a tool component with the given configuration.
    
    Args:
        tool_id: The ID of the tool to instantiate
        tool_config: Configuration dictionary for the tool
        tools_registry: Optional pre-discovered tools registry
    
    Returns:
        Instantiated tool component or None if failed
    """
    component_class = load_tool_class(tool_id, tools_registry)
    if component_class is None:
        return None
    
    try:
        return component_class(config=tool_config)
    except Exception as e:
        logger.error(f"Failed to instantiate tool {tool_id}: {e}")
        return None


def get_tool_as_tool_function(tool_id: str, tool_config: Dict[str, Any], 
                             context: Optional[Dict[str, Any]] = None,
                             tools_registry: Optional[Dict[str, Dict[str, Any]]] = None):
    """
    Get the tool function from a tool component using its as_tool() method.
    
    Args:
        tool_id: The ID of the tool
        tool_config: Configuration dictionary for the tool
        context: Optional context dictionary (for tools that need it, like github_checker)
        tools_registry: Optional pre-discovered tools registry
    
    Returns:
        The tool function (decorated with @tool) or None if failed
    """
    tool_instance = instantiate_tool(tool_id, tool_config, tools_registry)
    if tool_instance is None:
        return None
    
    if not hasattr(tool_instance, "as_tool"):
        logger.error(f"Tool {tool_id} does not have an as_tool() method")
        return None
    
    try:
        # All tools now have a consistent signature: as_tool(collection_name, review_process_name, checklist_name, paper_name, log_callback=None)
        # If context is provided, extract the standard parameters
        if context:
            collection_name = context.get("collection_name")
            review_process_name = context.get("review_process_name")
            checklist_name = context.get("checklist_name")
            paper_name = context.get("paper_name")
            log_callback = context.get("log_callback")
            
            # Check if required parameters are present
            if not all([collection_name, review_process_name, paper_name]):
                missing = [k for k, v in {
                    "collection_name": collection_name,
                    "review_process_name": review_process_name,
                    "paper_name": paper_name
                }.items() if not v]
                error_msg = f"Tool {tool_id} requires context parameters that are missing: {missing}. Available context keys: {list(context.keys())}"
                logger.error(error_msg)
                if log_callback:
                    log_callback(error_msg, "error")
                return None
            
            token_usage_accumulator = context.get("token_usage_accumulator")
            collections_root = context.get("collections_root")
            return tool_instance.as_tool(
                collection_name=collection_name,
                review_process_name=review_process_name,
                checklist_name=checklist_name or "",
                paper_name=paper_name,
                log_callback=log_callback,
                token_usage_accumulator=token_usage_accumulator,
                collections_root=collections_root,
            )
        else:
            # No context provided - this shouldn't happen in normal operation
            error_msg = f"Tool {tool_id} requires context but none was provided"
            logger.error(error_msg)
            return None
    except Exception as e:
        error_msg = f"Failed to get tool function for {tool_id}: {e}"
        logger.error(error_msg, exc_info=True)
        # Also log to callback if available
        if context and context.get("log_callback"):
            context["log_callback"](f"{error_msg}. Check server logs for details.", "error")
        return None
