from typing import Optional, Sequence
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
import requests

from src.core.providers import get_provider, get_provider_for_purpose, load_all_providers


class Embedding:
    def __init__(
        self,
        use_visualization_settings: bool = False,
        embedding_provider_id: Optional[str] = None,
    ):
        """
        embedding_provider_id: when set (non-empty), use this provider (e.g. for RAG).
        use_visualization_settings: when True and no embedding_provider_id, use default embedding from config.
        """

        if embedding_provider_id:
            self._embedding_type = "provider"
            self._vectorizer = None
            provider = get_provider(embedding_provider_id)
            if provider:
                self._base_url = provider.get("base_url", "").rstrip("/")
                self._model = provider.get("model_name") or ""
                self._provider_type = provider.get("type", "ollama")
                self._embedding_provider_id = embedding_provider_id
                self._provider_api_key = provider.get("api_key")
                self._provider_port = provider.get("port")
            else:
                raise ValueError(
                    f"Embedding provider '{embedding_provider_id}' not found in config/providers.yaml."
                )
        elif use_visualization_settings:
            default_embedding = get_provider_for_purpose("embedding")
            if default_embedding:
                self._embedding_type = "provider"
                self._base_url = default_embedding.get("base_url", "").rstrip("/")
                self._model = default_embedding.get("model_name") or ""
                self._provider_type = default_embedding.get("type", "ollama")
                self._embedding_provider_id = default_embedding.get("id")
                self._provider_api_key = default_embedding.get("api_key")
                self._provider_port = default_embedding.get("port")
                self._vectorizer = None
            else:
                self._embedding_type = "tfidf"
                self._vectorizer = TfidfVectorizer(max_features=512, stop_words="english")
                self._fitted = False
                self._base_url = None
                self._model = None
                self._provider_type = None
                self._embedding_provider_id = None
                self._provider_api_key = None
                self._provider_port = None
        else:
            raise ValueError("Embedding requires either embedding_provider_id or use_visualization_settings=True.")

    def embed(self, text: str) -> np.ndarray:
        if self._embedding_type == "tfidf":
            if not self._fitted:
                self._vectorizer.fit([text])
                self._fitted = True
            return self._vectorizer.transform([text]).toarray()[0].astype(np.float32)
        else:
            # Support both ollama and OpenAI-compatible embedding APIs
            if self._provider_type == "ollama":
                response = requests.post(
                    f"{self._base_url}/api/embeddings",
                    json={"model": self._model, "prompt": text},
                    timeout=120
                )
            else:
                # OpenAI-compatible API
                headers = {"Content-Type": "application/json"}
                if self._provider_api_key:
                    headers["Authorization"] = f"Bearer {self._provider_api_key}"
                
                # Handle port in base_url if needed
                base_url = self._base_url
                if self._provider_port and ":" not in base_url.split("//")[-1].split("/")[0]:
                    from urllib.parse import urlparse, urlunparse
                    parsed = urlparse(base_url)
                    if not parsed.port:
                        netloc = f"{parsed.netloc}:{self._provider_port}"
                        base_url = urlunparse((parsed.scheme, netloc, parsed.path, parsed.params, parsed.query, parsed.fragment))
                
                response = requests.post(
                    f"{base_url}/v1/embeddings",
                    headers=headers,
                    json={"model": self._model, "input": text},
                    timeout=120
                )
            
            response.raise_for_status()
            data = response.json()
            # Handle both ollama format and OpenAI format
            if "embedding" in data:
                embedding = data["embedding"]
            elif "data" in data and len(data["data"]) > 0:
                embedding = data["data"][0].get("embedding")
            else:
                raise ValueError("Embedding response missing data")
            if not embedding:
                raise ValueError("Embedding response missing data")
            return np.array(embedding, dtype=np.float32)
    
    def embed_batch(self, texts: Sequence[str]) -> np.ndarray:
        if self._embedding_type == "tfidf":
            if not self._fitted:
                self._vectorizer.fit(texts)
                self._fitted = True
            return self._vectorizer.transform(texts).toarray().astype(np.float32)
        else:
            embeddings = []
            for text in texts:
                embeddings.append(self.embed(text))
            return np.array(embeddings, dtype=np.float32)
    
    @property
    def vectorizer(self):
        return self._vectorizer
