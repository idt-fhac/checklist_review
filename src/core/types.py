from typing import Any, Dict, Literal, Optional

from typing_extensions import TypedDict


class LLMProvider(TypedDict, total=False):
    id: str
    type: Literal["ollama", "openai", "litellm", "gemini"]
    name: str
    base_url: str
    api_key: Optional[str]
    model_name: Optional[str]
    port: Optional[int]
    params: Optional[Dict[str, Any]]
    is_embedding_model: bool
    accepts_image_input: bool
