"""
LLM JSON Parser - Universal utility for parsing JSON from LLM responses.

Handles ALL common LLM output formats:
- Markdown code blocks ```json ... ```
- Plain JSON
- Python dicts using single quotes
- Trailing commas
- Multi-line reasoning before JSON
- Multiple JSON objects
- Extra text before/after JSON
"""

import json
import re
import ast
from typing import Any, Optional


def clean_llm_json(content: str) -> str:
    """
    Basic cleaning for markdown code blocks.

    Args:
        content: Raw LLM response string

    Returns:
        Cleaned JSON string
    """
    if not content:
        return content

    content = content.strip()

    # Remove markdown code blocks
    if content.startswith("```json"):
        content = content[7:]
    elif content.startswith("```"):
        content = content[3:]

    if content.endswith("```"):
        content = content[:-3]

    return content.strip()


def remove_trailing_commas(content: str) -> str:
    """Remove trailing commas before } or ]."""
    # Pattern to match trailing comma before } or ]
    content = re.sub(r",(\s*[}\]])", r"\1", content)
    return content


def convert_single_quotes(content: str) -> str:
    """
    Carefully convert single quotes to double quotes.
    Handles embedded single quotes in strings.
    """
    result = []
    i = 0
    in_string = False
    string_delimiter = None

    while i < len(content):
        char = content[i]

        if not in_string:
            if char in ('"', "'"):
                in_string = True
                string_delimiter = char
                result.append('"')
            else:
                result.append(char)
        else:
            if char == string_delimiter:
                # Check for escaped quote
                if i + 1 < len(content) and content[i + 1] == string_delimiter:
                    result.append('\\"')
                    i += 1
                else:
                    in_string = False
                    string_delimiter = None
                    result.append('"')
            elif char == "'" and string_delimiter == "'":
                # Replace single quote with escaped double quote inside single-quoted string
                result.append("\\'")
            else:
                result.append(char)

        i += 1

    return "".join(result)


def extract_json_objects(content: str) -> list:
    """Extract all potential JSON objects from content."""
    objects = []

    # Find all { } pairs
    stack = []
    start = -1

    for i, char in enumerate(content):
        if char == "{":
            if not stack:
                start = i
            stack.append(char)
        elif char == "}":
            if stack:
                stack.pop()
                if not stack and start != -1:
                    obj_str = content[start : i + 1]
                    objects.append(obj_str)
                    start = -1

    return objects


def parse_llm_json(
    content: str, default: Optional[dict] = None, debug: bool = True
) -> dict:
    """
    Universal JSON parser for ALL LLM output formats.

    Strategy:
    1. Remove markdown blocks
    2. Remove text before first { and after last }
    3. Attempt strict json.loads()
    4. Attempt ast.literal_eval()
    5. Convert single quotes to double quotes
    6. Remove trailing commas
    7. If multiple JSON objects, extract largest valid one
    8. Raise clear error if all fail

    Args:
        content: Raw LLM response
        default: Default dict to return if parsing fails completely
        debug: Whether to print debug messages

    Returns:
        Parsed JSON dictionary

    Raises:
        ValueError: If parsing fails and no default provided
    """
    if debug:
        print(f"[JSON PARSER] Raw response length: {len(content) if content else 0}")

    if not content:
        if default is not None:
            return default
        raise ValueError("LLM response is empty")

    original_content = content
    content = content.strip()

    # Strategy 1: Remove markdown code blocks ```json and ```
    if "```json" in content:
        start = content.find("```json") + len("```json")
        end = content.find("```", start)
        if end != -1:
            content = content[start:end]
    elif "```" in content:
        start = content.find("```") + 3
        end = content.find("```", start)
        if end != -1:
            content = content[start:end]

    # Strategy 2: Extract JSON between first { and last }
    first_brace = content.find("{")
    if first_brace == -1:
        # Try to find any JSON-like structure
        pass
    elif first_brace > 0:
        if debug:
            print(f"[JSON PARSER] Removing {first_brace} chars before first {{")
        content = content[first_brace:]

    last_brace = content.rfind("}")
    if last_brace != -1 and last_brace < len(content) - 1:
        if debug:
            print(
                f"[JSON PARSER] Removing {len(content) - last_brace - 1} chars after last }}"
            )
        content = content[: last_brace + 1]

    content = content.strip()

    if debug:
        print(f"[JSON PARSER] Extracted JSON length: {len(content)}")

    if not content:
        if default is not None:
            return default
        raise ValueError("No JSON found in LLM response")

    # Strategy 3: Attempt strict json.loads()
    try:
        result = json.loads(content)
        if debug:
            print("[JSON PARSER] Extracted JSON successfully")
        return result
    except json.JSONDecodeError as e:
        if debug:
            print(
                f"[JSON PARSER] Attempting recovery... (strict json.loads failed: {e.msg})"
            )

    # Strategy 4: Attempt Python dict parsing with ast.literal_eval()
    try:
        # Remove trailing commas first
        content_fixed = remove_trailing_commas(content)
        result = ast.literal_eval(content_fixed)
        if isinstance(result, dict):
            if debug:
                print(
                    "[JSON PARSER] Extracted JSON successfully (via ast.literal_eval)"
                )
            return result
    except (ValueError, SyntaxError) as e:
        if debug:
            print(f"[JSON PARSER] Attempting recovery... (ast.literal_eval failed)")

    # Strategy 5: Convert single quotes to double quotes
    try:
        content_fixed = convert_single_quotes(content)
        content_fixed = remove_trailing_commas(content_fixed)
        result = json.loads(content_fixed)
        if debug:
            print("[JSON PARSER] Extracted JSON successfully (via quote conversion)")
        return result
    except json.JSONDecodeError:
        if debug:
            print("[JSON PARSER] Attempting recovery... (quote conversion failed)")

    # Strategy 6: Remove trailing commas and retry
    try:
        content_fixed = remove_trailing_commas(content)
        result = json.loads(content_fixed)
        if debug:
            print("[JSON PARSER] Extracted JSON successfully (via comma removal)")
        return result
    except json.JSONDecodeError:
        if debug:
            print("[JSON PARSER] Attempting recovery... (comma removal failed)")

    # Strategy 7: If multiple JSON objects, find the largest valid one
    if debug:
        print("[JSON PARSER] Attempting recovery... (searching for valid JSON objects)")
    json_objects = extract_json_objects(content)
    if json_objects:
        # Try each object, return the largest that parses successfully
        largest_result = None
        largest_size = 0

        for obj in json_objects:
            try:
                result = json.loads(obj)
                if isinstance(result, dict):
                    obj_size = len(obj)
                    if obj_size > largest_size:
                        largest_result = result
                        largest_size = obj_size
            except json.JSONDecodeError:
                continue

        if largest_result:
            if debug:
                print(
                    f"[JSON PARSER] Extracted JSON successfully (largest of {len(json_objects)} objects)"
                )
            return largest_result

    # All strategies failed
    if default is not None:
        return default

    raise ValueError(
        f"Failed to parse JSON from LLM response. "
        f"Content length: {len(original_content)}, "
        f"Cleaned content: {content[:200]}..."
    )


def parse_llm_json_with_logging(
    content: str,
    logger: Optional[Any] = None,
    prompt_id: int = 0,
    raw_dir: Optional[str] = None,
) -> dict:
    """
    Parse JSON with automatic logging on failure.

    Args:
        content: Raw LLM response
        logger: Optional logger instance
        prompt_id: Prompt number for logging
        raw_dir: Optional directory to save failed raw response

    Returns:
        Parsed JSON dictionary
    """
    try:
        return parse_llm_json(content)
    except ValueError as e:
        # Log the failure
        if logger:
            logger.error(f"JSON parsing failed for prompt {prompt_id}: {e}")
            logger.error(f"Raw response (first 500 chars): {content[:500]}")

        # Save failed raw response if directory provided
        if raw_dir:
            from pathlib import Path
            from datetime import datetime

            raw_path = Path(raw_dir)
            raw_path.mkdir(parents=True, exist_ok=True)

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            failed_file = raw_path / f"prompt{prompt_id}_parse_failed_{timestamp}.txt"

            with open(failed_file, "w", encoding="utf-8") as f:
                f.write(f"JSON Parse Error: {e}\n")
                f.write(f"=" * 50 + "\n")
                f.write(content)

            if logger:
                logger.info(f"Saved failed response to: {failed_file}")

        raise


# Backwards compatibility
def extract_json_from_llm_response(content: str) -> str:
    """
    Legacy function - returns cleaned JSON string.
    Use parse_llm_json() instead for proper parsing.
    """
    cleaned = clean_llm_json(content)

    # Remove text before first { and after last }
    first_brace = cleaned.find("{")
    if first_brace == -1:
        raise ValueError("No JSON found in content")

    if first_brace > 0:
        cleaned = cleaned[first_brace:]

    last_brace = cleaned.rfind("}")
    if last_brace != -1 and last_brace < len(cleaned) - 1:
        cleaned = cleaned[: last_brace + 1]

    return cleaned.strip()
