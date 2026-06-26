from __future__ import annotations

from typing import Any, Dict, List, Sequence

import numpy as np
import plotly.graph_objects as go
from sklearn.decomposition import PCA
from sklearn.preprocessing import StandardScaler

from src.core.embedding import Embedding


class VisualizationError(RuntimeError):
    pass


def list_available_models() -> List[str]:
    from src.core.providers import get_ollama_models, load_all_providers

    ollama_providers = [p for p in load_all_providers() if p["type"] == "ollama"]
    base_url = (
        ollama_providers[0]["base_url"]
        if ollama_providers
        else "http://localhost:11434"
    )
    return get_ollama_models(base_url)


def embed_texts(texts: Sequence[str], model: str | None = None) -> np.ndarray:
    embedder = Embedding(use_visualization_settings=True)
    try:
        return embedder.embed_batch(texts)
    except ValueError:
        return np.zeros((len(texts), 2))


def reduce_embeddings(embeddings: np.ndarray) -> np.ndarray:
    if embeddings.shape[0] == 0:
        return embeddings
    n_samples = embeddings.shape[0]
    n_features = embeddings.shape[1]
    if n_features < 2:
        padded = np.zeros((n_samples, 2))
        padded[:, :n_features] = embeddings
        return padded
    scaler = StandardScaler()
    normalized = scaler.fit_transform(embeddings)
    n_components = min(2, n_samples, n_features)
    if n_components < 2:
        padded = np.zeros((n_samples, 2))
        padded[:, :n_components] = normalized[:, :n_components]
        return padded
    reducer = PCA(n_components=2)
    return reducer.fit_transform(normalized)


def build_plot(
    records: Sequence[Dict[str, Any]], coordinates: np.ndarray
) -> Dict[str, Any]:
    xs = coordinates[:, 0].tolist() if len(coordinates) else [0] * len(records)
    ys = coordinates[:, 1].tolist() if len(coordinates) else [0] * len(records)
    fig = go.Figure(
        data=[
            go.Scatter(
                x=xs,
                y=ys,
                mode="markers",
                marker=dict(
                    size=12,
                    color="#2563eb",
                    opacity=0.85,
                    line=dict(color="#0f172a", width=1),
                ),
                text=[
                    record.get("title", record.get("paper_id")) for record in records
                ],
                customdata=[
                    {
                        "title": record.get("title", record.get("paper_id")),
                        "paper_id": record.get("paper_id"),
                        "url": record.get("url"),
                        "filename": record.get("filename"),
                    }
                    for record in records
                ],
                hovertemplate="%{text}<extra></extra>",
            )
        ]
    )
    fig.update_layout(
        template="plotly_white",
        height=420,
        margin=dict(l=0, r=0, t=30, b=0),
        xaxis=dict(title="Component 1", gridcolor="#e2e8f0"),
        yaxis=dict(title="Component 2", gridcolor="#e2e8f0"),
        plot_bgcolor="#ffffff",
        paper_bgcolor="#ffffff",
        dragmode="lasso",
        selectdirection="any",
    )
    return fig.to_plotly_json()


def visualize_collection(
    collection_payload: Dict[str, Any], model: str | None = None
) -> Dict[str, Any]:
    papers = collection_payload.get("papers", [])
    if not papers:
        raise VisualizationError("Collection does not contain any papers.")

    # Load abstracts from source/metadata JSON files if not in paper data
    import json
    from pathlib import Path

    from src.core import storage

    collection_name = collection_payload.get("collection_name", "")
    collections_root_str = collection_payload.get("_collections_root", "collections")
    collections_root = Path(collections_root_str)

    abstracts = []
    for paper in papers:
        abstract = paper.get("abstract") or paper.get("summary") or ""
        if not abstract:
            paper_id = paper.get("paper_id")
            if paper_id:
                try:
                    collection_dir = storage._collection_dir(
                        collections_root, collection_name, create=False
                    )
                    stem = Path(paper_id).stem
                    meta_dir = storage._source_metadata_dir(
                        collection_dir, create=False
                    )
                    json_path = (
                        (meta_dir / f"{stem}.json") if meta_dir.exists() else None
                    )
                    if not json_path or not json_path.exists():
                        json_path = collection_dir / "source_extracted" / f"{stem}.json"
                    if json_path.exists():
                        with json_path.open("r", encoding="utf-8") as f:
                            metadata = json.load(f)
                            abstract = metadata.get("abstract", "")
                except Exception:
                    pass
        abstracts.append(abstract)

    if not any(abstracts):
        raise VisualizationError("No abstracts available to visualize.")

    from src.core.providers import get_provider_for_purpose

    default_embedding = get_provider_for_purpose("embedding")
    target_model = model or (
        default_embedding.get("model_name") if default_embedding else None
    )
    method = "provider" if default_embedding else "tfidf"

    embeddings = embed_texts(abstracts, model=target_model)
    coords = reduce_embeddings(embeddings)
    plot = build_plot(papers, coords)

    return {
        "plot": plot,
        "paper_count": len(papers),
        "model": "TF-IDF" if method == "tfidf" else (target_model or "default"),
    }
