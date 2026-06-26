"""
Token usage accumulation for paper review.
One accumulator per paper review; use add() after each Strands agent response.
Usage: response.metrics.accumulated_usage (dict with inputTokens, outputTokens, totalTokens).
Model id: agent.model.config.get("model_id") (e.g. "openai/gpt-oss-120b").
"""

from typing import Any, Dict


def create_accumulator() -> Dict[str, Any]:
    """One Token Calculator per paper review. Tracks totals and per-model counts."""
    return {
        "total_input_tokens": 0,
        "total_output_tokens": 0,
        "total_tokens": 0,
        "by_model": {},
    }


def add(accumulator: Dict[str, Any], response: Any, agent: Any) -> None:
    """
    Accumulate usage from a Strands agent response.
    Uses response.metrics.accumulated_usage and agent.model.config["model_id"].
    """
    if accumulator is None or response is None:
        return
    metrics = getattr(response, "metrics", None)
    if metrics is None:
        return
    usage = getattr(metrics, "accumulated_usage", None)
    if not isinstance(usage, dict):
        return
    inp = int(usage.get("inputTokens", 0) or 0)
    out = int(usage.get("outputTokens", 0) or 0)
    total = int(usage.get("totalTokens", 0) or 0)
    if inp == 0 and out == 0 and total == 0:
        return
    config = getattr(getattr(agent, "model", None), "config", None) or {}
    model_id = (
        config.get("model_id", "unknown") if isinstance(config, dict) else "unknown"
    )
    accumulator["total_input_tokens"] = accumulator.get("total_input_tokens", 0) + inp
    accumulator["total_output_tokens"] = accumulator.get("total_output_tokens", 0) + out
    accumulator["total_tokens"] = accumulator.get("total_tokens", 0) + total
    by_model = accumulator.setdefault("by_model", {})
    entry = by_model.setdefault(
        model_id, {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
    )
    entry["input_tokens"] = entry.get("input_tokens", 0) + inp
    entry["output_tokens"] = entry.get("output_tokens", 0) + out
    entry["total_tokens"] = entry.get("total_tokens", 0) + total


def get_summary(accumulator: Dict[str, Any]) -> Dict[str, Any]:
    """Read-only summary for storage and API."""
    return {
        "total_input_tokens": accumulator.get("total_input_tokens", 0),
        "total_output_tokens": accumulator.get("total_output_tokens", 0),
        "total_tokens": accumulator.get("total_tokens", 0),
        "by_model": dict(accumulator.get("by_model", {})),
    }
