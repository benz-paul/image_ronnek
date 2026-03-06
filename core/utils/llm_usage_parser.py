"""
LLM Usage Parser - Universal token usage extraction.

Supports:
- OpenAI format: usage.prompt_tokens, usage.completion_tokens
- DeepSeek format: usage.input_tokens, usage.output_tokens
- Anthropic format: usage.input_tokens, usage.output_tokens
"""

from typing import Optional, Tuple, Any


def extract_token_usage(response: Any) -> Tuple[Optional[int], Optional[int]]:
    """
    Extract token usage from LLM response.

    Supports:
    - OpenAI: response.usage.prompt_tokens, response.usage.completion_tokens
    - OpenAI LangChain: response.response_metadata["token_usage"]
    - DeepSeek: response.usage.input_tokens, response.usage.output_tokens
    - Anthropic: response.usage.input_tokens, response.usage.output_tokens

    Args:
        response: LLM response object

    Returns:
        Tuple of (input_tokens, output_tokens). Returns (None, None) if unavailable.
    """
    if response is None:
        return None, None

    # Try to get usage attribute
    usage = None

    # Check if response has usage attribute
    if hasattr(response, "usage"):
        usage = response.usage
    elif isinstance(response, dict) and "usage" in response:
        usage = response["usage"]

    # Try response_metadata for LangChain OpenAI responses
    if usage is None and hasattr(response, "response_metadata"):
        metadata = response.response_metadata
        if isinstance(metadata, dict):
            usage = metadata.get("token_usage")

    # Try usage_metadata for some LangChain responses
    if usage is None and hasattr(response, "usage_metadata"):
        metadata = response.usage_metadata
        if isinstance(metadata, dict):
            usage = metadata

    if usage is None:
        return None, None

    input_tokens = None
    output_tokens = None

    # Try OpenAI format first
    if hasattr(usage, "prompt_tokens"):
        input_tokens = usage.prompt_tokens
    elif hasattr(usage, "input_tokens"):
        input_tokens = usage.input_tokens
    elif isinstance(usage, dict):
        input_tokens = usage.get("prompt_tokens") or usage.get("input_tokens")

    # Try OpenAI format first
    if hasattr(usage, "completion_tokens"):
        output_tokens = usage.completion_tokens
    elif hasattr(usage, "output_tokens"):
        output_tokens = usage.output_tokens
    elif isinstance(usage, dict):
        output_tokens = usage.get("completion_tokens") or usage.get("output_tokens")

    return input_tokens, output_tokens
