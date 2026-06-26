from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from src.review_workflow.components.evaluators.criterion_evaluator.helpers import (
    get_project_root,
)
from src.review_workflow.components.evaluators.criterion_evaluator.rag import (
    RAG,
    format_chunks_for_prompt,
    get_vector_db_path,
)


def prepare_rag_context(
    md_content: str,
    artifact_pages: List[Dict[str, Any]],
    criterion_text: str,
    collection_name: str,
    pipeline_name: str,
    artifact_name: str,
    criteria_set_name: str,
    config: Dict[str, Any],
    log_callback,
    collections_root: Optional[Path] = None,
) -> Tuple[str, Optional[List[Dict[str, Any]]]]:
    if not config.get("use_rag", False):
        return md_content, artifact_pages

    embedding_provider_id = config.get("rag_embedding_provider_id") or None
    if not embedding_provider_id:
        raise ValueError(
            "RAG is enabled but no Embedding Provider is selected. "
            "Select an embedding provider in the Question Reviewer node (Process Designer)."
        )

    rag_config = {
        "top_k": config.get("rag_top_k", 5),
        "force_recreate": config.get("rag_force_recreate", False),
        "chunking_strategy": config.get("rag_chunking_strategy", "page"),
    }

    db_path = get_vector_db_path(
        collection_name,
        pipeline_name,
        artifact_name,
        get_project_root(),
        criteria_set_name,
        collections_root,
    )
    rag = RAG(embedding_provider_id=embedding_provider_id)
    rag.create_vector_db(
        paper_content=md_content,
        artifact_pages=artifact_pages,
        db_path=db_path,
        chunking_strategy=rag_config["chunking_strategy"],
        force_recreate=rag_config["force_recreate"],
        log_callback=log_callback,
    )

    relevant_chunks = rag.retrieve_relevant_chunks(
        question=criterion_text,
        db_path=db_path,
        top_k=rag_config["top_k"],
        log_callback=None,
    )

    if relevant_chunks:
        if log_callback:
            log_callback(f"Retrieved {len(relevant_chunks)} relevant chunks", "info")
        return format_chunks_for_prompt(relevant_chunks), None

    return md_content, artifact_pages
