from typing import Dict, Any, List, Tuple, Optional
from pathlib import Path

from src.review_workflow.components.evaluators.question_reviewer.rag import (
    RAG,
    get_vector_db_path,
    format_chunks_for_prompt
)
from src.review_workflow.components.evaluators.question_reviewer.helpers import get_project_root


def prepare_rag_context(
    md_content: str,
    paper_pages: List[Dict[str, Any]],
    question_text: str,
    collection_name: str,
    review_process_name: str,
    paper_name: str,
    checklist_name: str,
    config: Dict[str, Any],
    log_callback,
    collections_root: Optional[Path] = None
) -> Tuple[str, Optional[List[Dict[str, Any]]]]:
    if not config.get("use_rag", False):
        return md_content, paper_pages

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

    db_path = get_vector_db_path(collection_name, review_process_name, paper_name, get_project_root(), checklist_name, collections_root)
    rag = RAG(embedding_provider_id=embedding_provider_id)
    rag.create_vector_db(
        paper_content=md_content,
        paper_pages=paper_pages,
        db_path=db_path,
        chunking_strategy=rag_config["chunking_strategy"],
        force_recreate=rag_config["force_recreate"],
        log_callback=log_callback
    )
    
    relevant_chunks = rag.retrieve_relevant_chunks(
        question=question_text,
        db_path=db_path,
        top_k=rag_config["top_k"],
        log_callback=None,
    )
    
    if relevant_chunks:
        if log_callback:
            log_callback(f"Retrieved {len(relevant_chunks)} relevant chunks", "info")
        return format_chunks_for_prompt(relevant_chunks), None
    
    return md_content, paper_pages
