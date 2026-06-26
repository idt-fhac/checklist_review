import pickle
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
from sklearn.metrics.pairwise import cosine_similarity

from src.core.criteria import criteria_set_stem
from src.core.embedding import Embedding


def _slug(name: str) -> str:
    return name.strip().replace(" ", "_").lower() or "process"


def _chunk_by_page(
    text: str, artifact_pages: Optional[List[Dict[str, Any]]] = None
) -> List[Dict[str, Any]]:
    chunks = []
    chunk_id = 0
    artifact_pages = artifact_pages or []

    if artifact_pages:
        for page_info in artifact_pages:
            page_num = page_info.get("page_number", chunk_id + 1)
            page_content = page_info.get("content", page_info.get("text", ""))

            if not page_content.strip():
                continue

            page_marker = f"--- end of page={page_num} ---"
            start_pos = text.find(page_marker)

            if start_pos >= 0:
                prev_markers = list(
                    re.finditer(r"---\s+end\s+of\s+page=\d+\s+---", text[:start_pos])
                )
                start = prev_markers[-1].end() if prev_markers else 0
                end = start_pos
            else:
                start = chunk_id * 2000
                end = start + len(page_content)

            chunks.append(
                {
                    "id": chunk_id,
                    "text": page_content.strip(),
                    "start": start,
                    "end": end,
                    "page_number": page_num,
                }
            )
            chunk_id += 1
        return chunks

    page_markers = list(re.finditer(r"---\s+end\s+of\s+page=(\d+)\s+---", text))

    if not page_markers:
        return [
            {
                "id": 0,
                "text": text.strip(),
                "start": 0,
                "end": len(text),
                "page_number": 1,
            }
        ]

    start = 0
    for marker in page_markers:
        page_num = int(marker.group(1))
        end = marker.start()
        chunk_text = text[start:end].strip()

        if chunk_text:
            chunks.append(
                {
                    "id": chunk_id,
                    "text": chunk_text,
                    "start": start,
                    "end": end,
                    "page_number": page_num,
                }
            )
            chunk_id += 1

        start = marker.end()

    if start < len(text):
        chunk_text = text[start:].strip()
        if chunk_text:
            last_page = int(page_markers[-1].group(1))
            chunks.append(
                {
                    "id": chunk_id,
                    "text": chunk_text,
                    "start": start,
                    "end": len(text),
                    "page_number": last_page + 1,
                }
            )

    return chunks


def _chunk_by_paragraph(text: str) -> List[Dict[str, Any]]:
    chunks = []
    chunk_id = 0
    paragraph_pattern = r"\n\s*\n|\n(?=\s{2,})"
    paragraphs = re.split(paragraph_pattern, text)

    start = 0
    for para in paragraphs:
        para = para.strip()
        if not para:
            continue

        para_start = text.find(para, start)
        if para_start == -1:
            para_start = start
        para_end = para_start + len(para)

        chunks.append(
            {"id": chunk_id, "text": para, "start": para_start, "end": para_end}
        )
        chunk_id += 1
        start = para_end

    return (
        chunks
        if chunks
        else [{"id": 0, "text": text.strip(), "start": 0, "end": len(text)}]
    )


def _extract_page_info_from_chunk(
    chunk_text: str,
    chunk_start: int,
    chunk_end: int,
    artifact_pages: List[Dict[str, Any]],
    full_text: str,
) -> Optional[int]:
    page_markers = list(
        re.finditer(r"---\s+end\s+of\s+page=(\d+)\s+---", full_text[:chunk_end])
    )
    if page_markers:
        return int(page_markers[-1].group(1))

    if not artifact_pages:
        return None

    chunk_lower = chunk_text.lower().strip()
    chunk_sample = chunk_lower[:200] if len(chunk_lower) > 200 else chunk_lower

    for page_info in artifact_pages:
        page_content = page_info.get("content", "").lower()
        page_num = page_info.get("page_number")

        if chunk_sample and len(chunk_sample) > 50 and chunk_sample in page_content:
            return page_num
        if len(chunk_sample) > 100 and chunk_sample[:100] in page_content:
            return page_num

    all_markers = list(re.finditer(r"---\s+end\s+of\s+page=(\d+)\s+---", full_text))
    if all_markers:
        closest_marker = min(all_markers, key=lambda m: abs(m.end() - chunk_start))
        return int(closest_marker.group(1))

    return None


class RAG:
    def __init__(self, embedding_provider_id: Optional[str] = None):
        if not embedding_provider_id:
            raise ValueError(
                "RAG requires an embedding provider; select one in the Question Reviewer node."
            )
        self.embedding_model_type = "provider"
        self.embedding_model = None
        self.embedder = Embedding(embedding_provider_id=embedding_provider_id)

    def create_vector_db(
        self,
        paper_content: str,
        artifact_pages: Optional[List[Dict[str, Any]]] = None,
        db_path: Optional[Path] = None,
        chunking_strategy: str = "page",
        force_recreate: bool = False,
        log_callback: Optional[callable] = None,
    ) -> Path:
        if not db_path:
            raise ValueError("db_path is required")

        if db_path.exists() and not force_recreate:
            try:
                existing = load_vector_db(db_path)
                if existing.get("embedding_model_type") == "tfidf":
                    db_path.unlink(missing_ok=True)
                else:
                    return db_path
            except Exception:
                db_path.unlink(missing_ok=True)

        if chunking_strategy == "page":
            chunks = _chunk_by_page(paper_content, artifact_pages or [])
        elif chunking_strategy == "paragraph":
            chunks = _chunk_by_paragraph(paper_content)
        else:
            raise ValueError(f"Unknown chunking strategy: {chunking_strategy}")

        if log_callback:
            log_callback(f"Created {len(chunks)} chunks from paper", "info")

        chunk_texts = [chunk["text"] for chunk in chunks]
        embeddings_list = []
        for text in chunk_texts:
            embeddings_list.append(self.embedder.embed(text))
        embeddings = np.array(embeddings_list, dtype=np.float32)
        vectorizer_data = {
            "type": "provider",
            "model": self.embedding_model,
            "base_url": None,
        }

        artifact_pages = artifact_pages or []
        for chunk in chunks:
            if "page_number" not in chunk or chunk.get("page_number") is None:
                page_num = _extract_page_info_from_chunk(
                    chunk["text"],
                    chunk["start"],
                    chunk["end"],
                    artifact_pages,
                    paper_content,
                )
                chunk["page_number"] = page_num if page_num is not None else -1

        db_data = {
            "chunks": chunks,
            "embeddings": embeddings,
            "vectorizer": vectorizer_data,
            "embedding_model_type": self.embedding_model_type,
            "embedding_model": self.embedding_model,
            "chunking_strategy": chunking_strategy,
            "num_chunks": len(chunks),
        }

        db_path.parent.mkdir(parents=True, exist_ok=True)
        with open(db_path, "wb") as f:
            pickle.dump(db_data, f)

        return db_path

    def retrieve_relevant_chunks(
        self,
        question: str,
        db_path: Path,
        top_k: int = 5,
        log_callback: Optional[callable] = None,
    ) -> List[Dict[str, Any]]:
        db_data = load_vector_db(db_path)
        chunks = db_data["chunks"]
        embeddings = db_data["embeddings"]
        if db_data.get("embedding_model_type") == "tfidf":
            raise ValueError(
                "Vector DB was created with TF-IDF (no longer supported for RAG). "
                "Delete the vector DB file or run with 'Force Recreate' to rebuild with an embedding provider."
            )
        question_embedding = self.embedder.embed(question)
        similarities = cosine_similarity(question_embedding.reshape(1, -1), embeddings)[
            0
        ]
        top_indices = np.argsort(similarities)[::-1][:top_k]

        results = []
        for idx in top_indices:
            chunk = chunks[idx].copy()
            chunk["similarity"] = float(similarities[idx])
            results.append(chunk)

        return results


def create_vector_db(
    paper_content: str,
    artifact_pages: Optional[List[Dict[str, Any]]] = None,
    db_path: Optional[Path] = None,
    embedding_provider_id: Optional[str] = None,
    chunking_strategy: str = "page",
    force_recreate: bool = False,
    log_callback: Optional[callable] = None,
) -> Path:
    rag = RAG(embedding_provider_id=embedding_provider_id)
    return rag.create_vector_db(
        paper_content=paper_content,
        artifact_pages=artifact_pages,
        db_path=db_path,
        chunking_strategy=chunking_strategy,
        force_recreate=force_recreate,
        log_callback=log_callback,
    )


def load_vector_db(db_path: Path) -> Dict[str, Any]:
    with open(db_path, "rb") as f:
        return pickle.load(f)


def retrieve_relevant_chunks(
    question: str,
    db_path: Path,
    embedding_provider_id: str,
    top_k: int = 5,
    log_callback: Optional[callable] = None,
) -> List[Dict[str, Any]]:
    rag = RAG(embedding_provider_id=embedding_provider_id)
    return rag.retrieve_relevant_chunks(question, db_path, top_k, log_callback)


def format_chunks_for_prompt(chunks: List[Dict[str, Any]]) -> str:
    formatted_parts = []
    for i, chunk in enumerate(chunks, 1):
        chunk_text = chunk.get("text", "").strip()
        page_number = chunk.get("page_number", -1)
        formatted_parts.append(chunk_text)
        formatted_parts.append(
            f"PAGE NUMBER {page_number if page_number > 0 else 'Unknown'}"
        )
        if i < len(chunks):
            formatted_parts.append("=" * 80)
    return "\n\n".join(formatted_parts)


def get_vector_db_path(
    collection_name: str,
    pipeline_name: str,
    artifact_name: str,
    project_root: Optional[Path] = None,
    criteria_set_name: Optional[str] = None,
    collections_root: Optional[Path] = None,
) -> Path:
    if collections_root is None:
        if project_root is None:
            project_root = (
                Path(__file__).resolve().parent.parent.parent.parent.parent.parent
            )
        collections_root = project_root / "workspaces" / "guest" / "collections"

    paper_dir = (
        Path(collections_root)
        / _slug(collection_name)
        / "review_runs"
        / _slug(pipeline_name)
    )

    # If criteria_set_name is provided, add it to the path
    if criteria_set_name:
        criteria_set_name_clean = criteria_set_stem(criteria_set_name)
        paper_dir = paper_dir / _slug(criteria_set_name_clean)

    paper_dir = paper_dir / artifact_name
    paper_dir.mkdir(parents=True, exist_ok=True)
    return paper_dir / "vector_db.pkl"
