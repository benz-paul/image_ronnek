import json
import re
from typing import Optional, Callable, Any, Dict


def fix_common_json_issues(text: str) -> str:
    """Fix common JSON issues from LLM outputs."""
    if not text:
        return text

    # FIX: replaced the aggressive quote-escaping regex that was here.
    # The original  re.sub(r'(?<!\\)"(?=[^"]*")', '\\"', text)  would corrupt
    # perfectly valid JSON by escaping structural quote characters.
    # Safe replacements only: fancy/curly quotes → straight quotes.
    text = text.replace("\u201c", '"').replace("\u201d", '"')  # " "
    text = text.replace("\u2018", "'").replace("\u2019", "'")  # ' '

    # Trailing commas before } or ]
    text = re.sub(r",\s*}", "}", text)
    text = re.sub(r",\s*]", "]", text)

    # FIX: removed the aggressive  if text.count("'") > text.count('"'): replace("'", '"')
    # This was replacing apostrophes/contractions inside string values, corrupting them.

    # Fix ALL invalid JSON escape sequences.
    # Valid JSON escapes after \: " \ / b f n r t u
    # Any \X where X is not in that set is invalid → remove the backslash.
    # This handles \' \* \( \` \- etc. that LLMs commonly produce.
    # Note: \\ (escaped backslash) and \uXXXX are untouched because \ and u are excluded.
    text = re.sub(r'\\([^"\\/bfnrtu])', r'\1', text)

    # BOM removal
    text = text.replace("\ufeff", "")

    # Strip JS/Python comment lines
    lines = text.split("\n")
    fixed_lines = []
    for line in lines:
        if line.strip().startswith("//") or line.strip().startswith("#"):
            continue
        fixed_lines.append(line)
    text = "\n".join(fixed_lines)

    return text


def auto_fix_json(text: str) -> str:
    """Smart JSON auto-fix layer 1 - basic cleanup."""
    if not text:
        return text

    # FIX: removed  text.replace('""', '"')
    # '""' is a valid JSON empty string value.  Replacing it produces broken JSON
    # e.g. {"core_premise": ""} becomes {"core_premise": "} which fails to parse.

    text = text.replace("\n", " ")
    text = text.replace("\r", " ")
    text = text.strip()
    text = re.sub(r"\s+", " ", text)

    return text


def aggressive_json_fix(text: str) -> str:
    """Smart JSON auto-fix layer 2 - aggressive cleanup."""
    text = re.sub(r"[^\x20-\x7E\x09\x0A\x0D]", "", text)
    text = re.sub(r",\s*}", "}", text)
    text = re.sub(r",\s*]", "]", text)
    return text


def extract_json(text: str) -> str:
    """Extract valid JSON from LLM response text."""
    if not text:
        raise ValueError("Empty response")

    json_str = None

    if "```" in text:
        for block in text.split("```"):
            block = block.strip()
            # Strip language identifier (json, JSON, python, etc.)
            if block and not block.startswith("{") and not block.startswith("["):
                first_line_end = block.find("\n")
                if 0 < first_line_end <= 10:
                    block = block[first_line_end:].strip()
            if block.startswith("{") or block.startswith("["):
                candidates = [
                    block,
                    fix_common_json_issues(block),
                    auto_fix_json(block),
                ]
                for candidate in candidates:
                    try:
                        json.loads(candidate)
                        json_str = candidate
                        break
                    except json.JSONDecodeError:
                        continue

    if json_str is None:
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and start < end:
            json_str = text[start : end + 1]

    if json_str is None:
        start = text.find("[")
        end = text.rfind("]")
        if start != -1 and end != -1 and start < end:
            json_str = text[start : end + 1]

    if json_str is None:
        raise ValueError("No JSON found in response")

    last_error = None
    for fixer in [
        lambda x: x,
        fix_common_json_issues,
        auto_fix_json,
        aggressive_json_fix,
    ]:
        try:
            fixed = fixer(json_str)
            json.loads(fixed)
            return fixed
        except json.JSONDecodeError as e:
            last_error = e
            continue

    # Print diagnostic info to help debug the exact failure
    if last_error is not None:
        ctx_start = max(0, last_error.pos - 60)
        ctx_end = min(len(json_str), last_error.pos + 60)
        print(f"[JSON DEBUG] Parse error: {last_error.msg} at pos {last_error.pos}")
        print(f"[JSON DEBUG] Context: ...{repr(json_str[ctx_start:ctx_end])}...")
    raise ValueError("Could not parse JSON after all fix attempts")


# =============================================================================
# TYPE-SPECIFIC VALIDATORS
# =============================================================================


def validate_concepts(data: dict) -> bool:
    """Validate concepts/knowledge inventory data."""
    if not isinstance(data, dict):
        return False
    return "concepts" in data or "concept_titles" in data or "knowledge_items" in data


def validate_story(data: dict) -> bool:
    """Validate story backbone data."""
    if not isinstance(data, dict):
        return False
    required = ["title", "core_premise", "characters"]
    return all(k in data for k in required)


def validate_learning_steps(data: dict) -> bool:
    """Validate learning steps data."""
    if not isinstance(data, dict):
        return False
    if "learning_steps" not in data:
        return False
    if not isinstance(data["learning_steps"], list):
        return False
    if len(data["learning_steps"]) == 0:
        return False
    return True


def validate_scene(data: dict) -> bool:
    """Validate single scene data."""
    if not isinstance(data, dict):
        return False
    required = ["scene_id", "phase", "setting", "characters", "action", "dialogue"]
    return all(k in data for k in required)


def validate_scene_plan(data: dict) -> bool:
    """Validate scene plan data (array of scenes)."""
    if not isinstance(data, dict):
        return False
    if "scene_plan" not in data:
        return False
    if not isinstance(data["scene_plan"], list):
        return False
    if len(data["scene_plan"]) == 0:
        return False
    return True


def get_validator(prompt_type: str) -> Callable[[dict], bool]:
    """Get the correct validator for a prompt type."""
    validators = {
        "prompt0": validate_concepts,
        "prompt1": validate_story,
        "prompt2": validate_learning_steps,
        "prompt3": validate_scene,
        "prompt3a": validate_scene_plan,
        "prompt4": lambda d: "prompt" in d or "visual_prompt" in d,
        "concepts": validate_concepts,
        "story": validate_story,
        "learning_steps": validate_learning_steps,
        "scene": validate_scene,
        "scene_plan": validate_scene_plan,
    }
    return validators.get(prompt_type, lambda d: True)


# =============================================================================
# PARSING FUNCTIONS
# =============================================================================


def safe_parse(text: str, validate: bool = True, prompt_type: str = "general") -> dict:
    """
    Extract and parse JSON with optional validation.

    Args:
        text: Raw LLM response
        validate: Whether to validate structure
        prompt_type: Type for validation ("concepts", "story", "learning_steps", "scene", "scene_plan")

    Returns:
        Parsed dict with "_error" or "_invalid" keys on failure
    """
    try:
        clean = extract_json(text)
        parsed = json.loads(clean)

        if validate:
            validator = get_validator(prompt_type)
            if not validator(parsed):
                print(f"[VALIDATION] {prompt_type}: missing required keys")
                print(f"[VALIDATION] Keys found: {list(parsed.keys())}")
                return {
                    "_invalid": True,
                    "_reason": f"validation_failed_for_{prompt_type}",
                    "_prompt_type": prompt_type,
                    "_raw_preview": text[:500],
                }

        return parsed

    except (json.JSONDecodeError, ValueError) as e:
        print(f"[ERROR] JSON parsing failed: {e}")
        return {
            "_error": "json_parse_failed",
            "message": str(e),
            "_prompt_type": prompt_type,
            "_raw_preview": text[:500],
        }


def safe_parse_with_retry(
    text: str, max_retries: int = 2, prompt_type: str = "general"
) -> tuple[dict, int, bool]:
    """
    Parse JSON with RETRY logic and type-specific validation.

    Args:
        text: Raw LLM response
        max_retries: Maximum retry attempts
        prompt_type: Type for validation

    Returns:
        (parsed_dict, attempts_used, success_flag)
    """
    validator = get_validator(prompt_type)

    for attempt in range(max_retries):
        parsed = safe_parse(text, validate=False, prompt_type=prompt_type)

        if "_error" not in parsed and "_invalid" not in parsed:
            if validator(parsed):
                return parsed, attempt + 1, True
            else:
                print(f"[VALIDATION] {prompt_type}: failed validation check")

        if attempt < max_retries - 1:
            print(
                f"[RETRY] Parsing failed (attempt {attempt + 1}/{max_retries}), retrying..."
            )

    return (
        {
            "_fatal_error": True,
            "_attempts": max_retries,
            "_prompt_type": prompt_type,
            "_raw_preview": text[:500],
        },
        max_retries,
        False,
    )


def try_partial_extraction(text: str, target_type: str = "general") -> dict:
    """Attempt partial extraction from malformed JSON."""
    result = {"_partial": True, "_target_type": target_type}

    try:
        if target_type == "learning_steps":
            ls_match = re.search(r'"learning_steps"\s*:\s*\[(.*?)\]', text, re.DOTALL)
            if ls_match:
                result["learning_steps"] = []
                step_pattern = r"\{[^{}]*\}"
                steps = re.findall(step_pattern, ls_match.group(1))
                for step in steps:
                    try:
                        cleaned_step = fix_common_json_issues(step)
                        step_dict = json.loads(cleaned_step)
                        result["learning_steps"].append(step_dict)
                    except Exception:
                        title_match = re.search(r'"title"\s*:\s*"([^"]*)"', step)
                        if title_match:
                            result["learning_steps"].append(
                                {"title": title_match.group(1)}
                            )

        elif target_type == "concepts":
            concepts_match = re.search(r'"concepts"\s*:\s*\[(.*?)\]', text, re.DOTALL)
            if concepts_match:
                concepts_text = concepts_match.group(1)
                concepts = re.findall(r'"([^"]*)"', concepts_text)
                if concepts:
                    result["concepts"] = concepts

        elif target_type == "story":
            title_match = re.search(r'"title"\s*:\s*"([^"]*)"', text)
            if title_match:
                result["title"] = title_match.group(1)
            premise_match = re.search(r'"core_premise"\s*:\s*"([^"]*)"', text)
            if premise_match:
                result["core_premise"] = premise_match.group(1)

        if len(result) > 2:
            return result

    except Exception as e:
        print(f"[DEBUG] Partial extraction error: {e}")

    return {
        "_error": "partial_extraction_failed",
        "_target_type": target_type,
        "_raw_preview": text[:300],
    }
