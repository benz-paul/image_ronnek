import json
import re


def fix_common_json_issues(text: str) -> str:
    """
    Fix common JSON issues from LLM outputs.

    Args:
        text: Raw JSON string with issues

    Returns:
        Fixed JSON string
    """
    if not text:
        return text

    # Replace smart quotes with normal quotes
    text = text.replace('"', '"').replace('"', '"')
    text = text.replace(""", "'").replace(""", "'")

    # Fix double quotes inside strings (replace with escaped quotes)
    # This is tricky - be careful not to break valid JSON
    # Look for patterns like: "key": "value with "quoted" text"
    text = re.sub(r'(?<!\\)"(?=[^"]*")', '\\"', text)

    # Remove trailing commas before } or ]
    text = re.sub(r",\s*}", "}", text)
    text = re.sub(r",\s*]", "]", text)

    # Fix single quotes used as string delimiters (Python-style)
    # Only fix if it looks like the JSON was generated incorrectly
    if text.count("'") > text.count('"') and text.count("'") > 5:
        text = text.replace("'", '"')

    # Remove BOM or other invisible characters
    text = text.replace("\ufeff", "")

    # Fix common LLM mistakes like \n outside strings
    # This is very aggressive - only do if simple fixes fail
    lines = text.split("\n")
    fixed_lines = []
    for line in lines:
        # Skip comment lines that LLM might add
        if line.strip().startswith("//") or line.strip().startswith("#"):
            continue
        fixed_lines.append(line)
    text = "\n".join(fixed_lines)

    return text


def extract_json(text: str) -> str:
    """
    Extract valid JSON from LLM response text.
    Handles reasoning noise by finding the first { and last }.

    Args:
        text: Raw LLM response text

    Returns:
        Extracted JSON string (cleaned)

    Raises:
        ValueError: If no JSON found after all attempts
    """
    if not text:
        raise ValueError("Empty response")

    # Try to find JSON block
    start = text.find("{")
    end = text.rfind("}")

    if start == -1 or end == -1:
        # Try array format
        start = text.find("[")
        end = text.rfind("]")
        if start == -1 or end == -1:
            print("\n[WARNING] No JSON found in response")
            print(f"Response preview: {text[:200]}...")
            raise ValueError("No JSON found")

    json_str = text[start : end + 1]

    # First attempt - return as-is if valid
    try:
        json.loads(json_str)
        return json_str
    except json.JSONDecodeError:
        pass

    # Second attempt - fix common issues
    fixed_json = fix_common_json_issues(json_str)
    try:
        json.loads(fixed_json)
        return fixed_json
    except json.JSONDecodeError:
        pass

    # Third attempt - more aggressive cleaning
    # Remove all non-printable characters
    cleaned = "".join(
        char for char in fixed_json if char.isprintable() or char in "\n\t"
    )
    try:
        json.loads(cleaned)
        return cleaned
    except json.JSONDecodeError:
        pass

    # Fourth attempt - try to extract just the inner content
    # Sometimes LLM wraps JSON in markdown code blocks incorrectly
    if "```" in text:
        for block in text.split("```"):
            block = block.strip()
            if block.startswith("{") or block.startswith("["):
                try:
                    json.loads(block)
                    return block
                except:
                    fixed = fix_common_json_issues(block)
                    try:
                        json.loads(fixed)
                        return fixed
                    except:
                        continue

    print("\n[WARNING] JSON parsing failed after all attempts")
    print(f"Attempted JSON (first 500 chars): {json_str[:500]}...")
    raise ValueError("Could not parse JSON")


def safe_parse(text: str, fallback: dict = None) -> dict:
    """
    Extract and parse JSON from LLM response with robust fallback.

    Args:
        text: Raw LLM response text
        fallback: Fallback dict if parsing fails (default: empty dict)

    Returns:
        Parsed JSON as dict
    """
    if fallback is None:
        fallback = {}

    try:
        clean = extract_json(text)
        return json.loads(clean)
    except (json.JSONDecodeError, ValueError) as e:
        print(f"[WARNING] JSON parsing failed: {e}")
        print("[WARNING] Using fallback empty dict to prevent pipeline crash")

        # Try best-effort partial extraction
        partial = try_partial_extraction(text)
        if partial:
            print("[INFO] Extracted partial JSON data")
            return partial

        return fallback


def try_partial_extraction(text: str) -> dict:
    """
    Try to extract partial JSON data from malformed text.
    Uses regex to find key-value pairs.

    Args:
        text: Raw text that might contain JSON-like data

    Returns:
        Partial dict with extracted data, or empty dict
    """
    result = {}

    try:
        # Try to find learning_steps array
        ls_match = re.search(r'"learning_steps"\s*:\s*\[(.*?)\]', text, re.DOTALL)
        if ls_match:
            result["learning_steps"] = []
            # Try to extract individual steps
            step_pattern = r"\{[^{}]*\}"
            steps = re.findall(step_pattern, ls_match.group(1))
            for step in steps:
                try:
                    # Clean and try to parse each step
                    cleaned_step = fix_common_json_issues(step)
                    step_dict = json.loads(cleaned_step)
                    result["learning_steps"].append(step_dict)
                except:
                    # Extract what we can
                    title_match = re.search(r'"title"\s*:\s*"([^"]*)"', step)
                    if title_match:
                        result["learning_steps"].append({"title": title_match.group(1)})

        # Try to find scene_plan array
        plan_match = re.search(r'"scene_plan"\s*:\s*\[(.*?)\]', text, re.DOTALL)
        if plan_match:
            result["scene_plan"] = []

        # Try to find concepts array
        concepts_match = re.search(r'"concepts"\s*:\s*\[(.*?)\]', text, re.DOTALL)
        if concepts_match:
            concepts_text = concepts_match.group(1)
            # Extract quoted strings
            concepts = re.findall(r'"([^"]*)"', concepts_text)
            if concepts:
                result["concepts"] = concepts

        # Try to find story/title info
        title_match = re.search(r'"title"\s*:\s*"([^"]*)"', text)
        if title_match:
            result["title"] = title_match.group(1)

    except Exception as e:
        print(f"[DEBUG] Partial extraction error: {e}")

    return result if result else {}


def fallback_dict_or_empty() -> dict:
    """
    Returns an empty dict for fallback.

    Returns:
        Empty dict
    """
    return {}
