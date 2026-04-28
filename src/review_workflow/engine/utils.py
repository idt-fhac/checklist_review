from typing import Dict, Any
from strands.models.ollama import OllamaModel
from strands.models.openai import OpenAIModel
from strands.models.gemini import GeminiModel
from strands.models.litellm import LiteLLMModel
from strands.types.tools import ToolResult


def load_model_from_provider(provider_config: Dict[str, Any]) -> Any:
    ptype = provider_config.get("type")

    if ptype == "ollama":
        base_url = provider_config.get("base_url", "http://localhost:11434")
        model_id = provider_config.get("model_name", "llama3")
        return OllamaModel(host=base_url, model_id=model_id)

    elif ptype == "openai":
        model_name = provider_config.get("model_name", "gpt-4o")
        api_key = provider_config.get("api_key")
        base_url = provider_config.get("base_url")

        if not api_key:
            raise ValueError("API key is required for OpenAI provider.")

        client_args: Dict[str, Any] = {
            "api_key": api_key,
        }
        
        if base_url:
            client_args["base_url"] = base_url

        return OpenAIModel(client_args=client_args, model_id=model_name)

    elif ptype == "gemini":
        model_name = provider_config.get("model_name", "gemini-2.5-flash")
        api_key = provider_config.get("api_key")

        if not api_key:
            raise ValueError("API key is required for Gemini provider.")

        client_args: Dict[str, Any] = {
            "api_key": api_key,
        }

        return GeminiModel(client_args=client_args, model_id=model_name)

    elif ptype == "litellm":
        model_name = provider_config.get("model_name", "gpt-4o")
        api_key = provider_config.get("api_key")
        base_url = provider_config.get("base_url")
        port = provider_config.get("port")

        if base_url and isinstance(base_url, str):
            base_url = base_url.strip()
            if not base_url:
                base_url = None

        if base_url and port:
            from urllib.parse import urlparse, urlunparse

            parsed = urlparse(base_url)
            if not parsed.port:
                netloc = parsed.netloc
                if netloc:
                    netloc = f"{netloc}:{port}"
                    base_url = urlunparse(
                        (
                            parsed.scheme or "http",
                            netloc,
                            parsed.path,
                            parsed.params,
                            parsed.query,
                            parsed.fragment,
                        )
                    )

        client_args: Dict[str, Any] = {}
        if api_key:
            client_args["api_key"] = api_key
        if base_url:
            client_args["base_url"] = base_url

        if base_url:
            try:
                import litellm

                litellm.use_litellm_proxy = True
            except ImportError:
                pass

        # return LiteLLMModel(model_id=model_name, client_args=client_args)
        return LiteLLMModelStringToolContent(
            model_id=model_name, client_args=client_args
        )

    else:
        raise ValueError(f"Unknown provider type: {ptype}")


# FIX FOR LITELLM TO SUPPORT TOOL CALLS
def _content_list_to_string(content_list: list) -> str | None:
    """If content is a list of text-only blocks, return concatenated string; else None."""
    if not content_list or not all(
        isinstance(c, dict) and c.get("type") == "text" and "text" in c
        for c in content_list
    ):
        return None
    return "".join(c.get("text", "") for c in content_list)


class LiteLLMModelStringToolContent(LiteLLMModel):
    """LiteLLM model that works across backends (Mistral, gpt-oss-120b, etc.).

    - Sends tool message content as a string (required by e.g. Mistral).
    - Strips reasoning/thinking content in multi-turn (not supported by some
      Chat Completions APIs, and can cause content.0 validation errors).
    - Uses string content for system and for user/assistant when text-only, so
      backends that expect string (not array) message content don't 400.
    """

    @classmethod
    def _format_system_messages(
        cls, system_prompt=None, *, system_prompt_content=None, **kwargs
    ) -> list:
        # Use string system content so backends that don't support array content don't 400.
        formatted = super()._format_system_messages(
            system_prompt=system_prompt,
            system_prompt_content=system_prompt_content,
            **kwargs,
        )
        if not formatted:
            return []
        msg = formatted[0]
        content = msg.get("content")
        if isinstance(content, list):
            s = _content_list_to_string(content)
            if s is not None:
                msg = {**msg, "content": s}
        return [msg]

    @classmethod
    def format_request_tool_message(cls, tool_result: ToolResult, **kwargs) -> dict:
        msg = super().format_request_tool_message(tool_result, **kwargs)
        content = msg.get("content")
        if isinstance(content, list) and all(
            isinstance(c, dict) and c.get("type") == "text" for c in content
        ):
            msg["content"] = "".join(c.get("text", "") for c in content)
        return msg

    @classmethod
    def format_request_message_content(cls, content: dict, **kwargs) -> dict | None:
        """Drop reasoning/thinking blocks so they are not sent in multi-turn."""
        if content.get("reasoningContent") is not None:
            return None
        return super().format_request_message_content(content, **kwargs)

    @classmethod
    def _format_regular_messages(cls, messages, **kwargs) -> list:
        # Ensure each message's content is a list so it isn't consumed by two iterations.
        messages = [
            {
                **msg,
                "content": list(msg["content"])
                if not isinstance(msg.get("content"), list)
                else msg["content"],
            }
            for msg in messages
        ]
        formatted = super()._format_regular_messages(messages, **kwargs)
        # Strip None/thinking and optionally collapse text-only to string for compatibility.
        out = []
        for msg in formatted:
            content = msg.get("content")
            if isinstance(content, list):
                content = [
                    c
                    for c in content
                    if c is not None
                    and isinstance(c, dict)
                    and c.get("type") != "thinking"
                ]
                # Backends like gpt-oss-120b can reject array content; use string when text-only.
                as_str = _content_list_to_string(content)
                msg = {
                    **msg,
                    "content": as_str
                    if as_str is not None
                    else content
                    if content
                    else "",
                }
            out.append(msg)
        return out

    @classmethod
    def format_request_messages(
        cls, messages, system_prompt=None, *, system_prompt_content=None, **kwargs
    ) -> list:
        formatted = super().format_request_messages(
            messages,
            system_prompt=system_prompt,
            system_prompt_content=system_prompt_content,
            **kwargs,
        )
        # Final pass: ensure no thinking blocks, string content when text-only, empty string not empty list.
        result = []
        for msg in formatted:
            content = msg.get("content")
            if isinstance(content, list):
                content = [
                    c
                    for c in content
                    if isinstance(c, dict) and c.get("type") != "thinking"
                ]
                content = list(content)
                as_str = _content_list_to_string(content)
                msg = {
                    **msg,
                    "content": as_str
                    if as_str is not None
                    else (content if content else ""),
                }
            result.append(msg)
        return [
            m for m in result if m.get("tool_calls") or m.get("content") is not None
        ]
