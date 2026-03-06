"""
LLM Response Extractor - Universal response content extraction.

Supports:
- response.content (OpenAI, LangChain)
- response.text (some providers)
- response.response (nested)
- Raw string responses
- Dict responses with 'content' or 'text' keys
"""

from typing import Any, Optional


def extract_llm_content(response):
    if response is None:
        print("Extracted LLM content length: 0")
        return ""

    # Standard OpenAI / LangChain
    if hasattr(response, "content") and response.content:
        result = str(response.content).strip()
        print(f"Extracted LLM content length: {len(result)}")
        return result

    # message.content (some LangChain wrappers)
    if hasattr(response, "message"):
        msg = response.message
        if hasattr(msg, "content") and msg.content:
            result = str(msg.content).strip()
            print(f"Extracted LLM content length: {len(result)}")
            return result

    # generations format
    if hasattr(response, "generations"):
        try:
            content = response.generations[0][0].text
            result = str(content).strip()
            print(f"Extracted LLM content length: {len(result)}")
            return result
        except Exception:
            pass

    # dictionary responses
    if isinstance(response, dict):
        if "content" in response:
            result = str(response["content"]).strip()
            print(f"Extracted LLM content length: {len(result)}")
            return result
        if "text" in response:
            result = str(response["text"]).strip()
            print(f"Extracted LLM content length: {len(result)}")
            return result

    # final fallback
    result = str(response).strip()
    print(f"Extracted LLM content length: {len(result)}")
    return result


def extract_llm_usage(response: Any) -> Optional[dict]:
    """
    Extract token usage from LLM response.

    Args:
        response: LLM response object

    Returns:
        Dict with input_tokens, output_tokens, and total_tokens, or None
    """
    if response is None:
        return None

    usage = None

    # Try attribute access
    if hasattr(response, "usage"):
        usage = response.usage

    # Try dict access
    if usage is None and isinstance(response, dict):
        usage = response.get("usage")

    # Try response_metadata for OpenAI responses
    if usage is None and hasattr(response, "response_metadata"):
        metadata = response.response_metadata
        if isinstance(metadata, dict):
            usage = metadata.get("token_usage")

    if usage is None:
        return None

    # Extract values from usage
    input_tokens = None
    output_tokens = None
    total_tokens = None

    # Input tokens
    if hasattr(usage, "prompt_tokens"):
        input_tokens = usage.prompt_tokens
    elif hasattr(usage, "input_tokens"):
        input_tokens = usage.input_tokens
    elif isinstance(usage, dict):
        input_tokens = usage.get("prompt_tokens") or usage.get("input_tokens")

    # Output tokens
    if hasattr(usage, "completion_tokens"):
        output_tokens = usage.completion_tokens
    elif hasattr(usage, "output_tokens"):
        output_tokens = usage.output_tokens
    elif isinstance(usage, dict):
        output_tokens = usage.get("completion_tokens") or usage.get("output_tokens")

    # Total tokens
    if hasattr(usage, "total_tokens"):
        total_tokens = usage.total_tokens
    elif isinstance(usage, dict):
        total_tokens = usage.get("total_tokens")

    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens,
    }
