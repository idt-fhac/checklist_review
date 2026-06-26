from typing import Any, Dict, List, Optional

from strands import Agent

from src.review_workflow.components.evaluators.criterion_evaluator.helpers import (
    clean_text_for_encoding,
)
from src.review_workflow.engine.tool_loader import (
    discover_review_tools,
    get_tool_as_tool_function,
)
from src.review_workflow.engine.utils import load_model_from_provider


def create_review_agent(
    provider_config: Dict[str, Any],
    config: Dict[str, Any],
    artifact_pages: Optional[List[Dict[str, Any]]] = None,
    context: Optional[Dict[str, Any]] = None,
) -> Agent:

    base_prompt = config.get(
        "system_prompt",
        "You are a question-answering assistant that reviews research papers.",
    )
    base_prompt += "\nAnswer the given question based the paper content.\n"
    base_prompt += "IMPORTANT: You MUST provide at least one supporting text either from the given paper content above or results from tool executions in your analysis. \n"
    base_prompt += "Each supporting text item MUST include:\n"
    base_prompt += "1. A page_number (the page where the text appears, or -1 for analysis-only supporting text that doesn't reference a specific page)\n"
    base_prompt += "2. A text_crop that is VERBATIM text from the paper (not a summary or paraphrase). For analysis-only items (page_number=-1), this can be your analysis text.\n"
    base_prompt += "3. A short_explanation that briefly explains why this supporting text is relevant to the answer\n"
    base_prompt += "You can include multiple supporting texts, some with page references and some as analysis-only.\n"

    uses_figure_tool = any(
        isinstance(item, dict) and "figure_reviewer" in item
        for item in (config.get("tools") or [])
    )
    if uses_figure_tool:
        base_prompt += (
            "\nFigure / visual routing: If figure_reviewer is available, any question about figures, plots, charts, diagrams, "
            "axes or labels on plots, colors in visuals, spatial layout of figures, or tables primarily understood from the "
            "rendered page (not answerable from captions alone), you MUST call figure_reviewer before finalizing your answer. "
            "Do not substitute only verbatim markdown excerpts for those cases. You may omit page_numbers to auto-scan "
            'available page images, or pass explicit page numbers inferred from the paper (e.g. figure captions, "page N").\n'
        )

    if config.get("use_search"):
        base_prompt += (
            "\nExternal verification: web_search is available. Use it when a criterion depends on facts outside the artifact "
            "(regulations, company credentials, market data, standards compliance, or verifiable public claims). "
            "Cite URLs from search results when they influence your answer.\n"
        )

    base_prompt = clean_text_for_encoding(base_prompt)

    # if artifact_pages:
    #     max_page = max((p.get("page_number", 0) for p in artifact_pages), default=0)
    #     additional_text = f"\n\nThe paper has {len(artifact_pages)} pages (pages 1-{max_page}). Use valid page numbers from this range when referencing specific pages."
    #     additional_text = clean_text_for_encoding(additional_text)
    #     base_prompt += additional_text

    base_prompt = clean_text_for_encoding(base_prompt)

    model = load_model_from_provider(provider_config)
    agent_tools = []

    # Discover available tools once
    tools_registry = discover_review_tools()

    if config.get("use_search") and "search_tool" in tools_registry:
        search_cfg = {"max_results": config.get("search_max_results")}
        if config.get("search_allowed_domains"):
            search_cfg["allowed_domains"] = config.get("search_allowed_domains")
        search_func = get_tool_as_tool_function(
            tool_id="search_tool",
            tool_config=search_cfg,
            context=context,
            tools_registry=tools_registry,
        )
        if search_func:
            agent_tools.append(search_func)
        elif context and context.get("log_callback"):
            context["log_callback"]("Failed to load web_search tool", "warning")

    # Dynamically load tools from config
    for tool_item in config.get("tools", []):
        if isinstance(tool_item, dict):
            for tool_id, tool_cfg in tool_item.items():
                # Check if tool exists in registry
                if tool_id not in tools_registry:
                    if context and context.get("log_callback"):
                        context["log_callback"](
                            f"Warning: Tool '{tool_id}' not found. Skipping.", "warning"
                        )
                    continue

                # Ensure provider_id is set if not provided
                if "provider_id" not in tool_cfg:
                    tool_cfg["provider_id"] = config.get("provider_id")

                # Get the tool function dynamically
                tool_func = get_tool_as_tool_function(
                    tool_id=tool_id,
                    tool_config=tool_cfg,
                    context=context,
                    tools_registry=tools_registry,
                )

                if tool_func:
                    agent_tools.append(tool_func)
                else:
                    if context and context.get("log_callback"):
                        context["log_callback"](
                            f"Failed to load tool: {tool_id}", "error"
                        )

    return Agent(model=model, system_prompt=base_prompt, tools=agent_tools)
