"""
PromptBuilder — Loads prompts from assets/prompts/MASTER_PROMPTS.txt and fills
placeholders before returning the final prompt string.

Usage:
    pb = PromptBuilder()
    prompt = pb.get_prompt("prompt1", CHAPTER_TITLE="Motion", CHAPTER_SUMMARY="...")

Placeholder formats supported:
    [VARIABLE_NAME]   — square-bracket style (preferred in MASTER_PROMPTS.txt)
    {variable_name}   — curly-brace style (legacy support)

Raises ValueError if any placeholder remains unfilled after substitution.
"""

import re
from pathlib import Path
from typing import Dict

DEFAULT_PROMPTS_FILE = Path(__file__).parents[2] / "assets" / "prompts" / "MASTER_PROMPTS.txt"

# Delimiter that separates prompt sections in MASTER_PROMPTS.txt
SECTION_DELIMITER = "----"

# Regex to extract prompt ID from section header, e.g. "## Prompt 3B: Scene Generation"
HEADER_RE = re.compile(
    r"##\s*Prompt\s*(\d+[A-Za-z]?)\s*:", re.IGNORECASE
)


def _normalize_id(raw: str) -> str:
    """Convert header number like '3B' → 'prompt3b', '0' → 'prompt0'."""
    return f"prompt{raw.lower()}"


class PromptBuilder:
    """
    Loads MASTER_PROMPTS.txt once on init, parses into a dict keyed by prompt ID,
    and fills placeholders on each get_prompt() call.
    """

    def __init__(self, prompts_file: str | Path = DEFAULT_PROMPTS_FILE):
        self._prompts: Dict[str, str] = {}
        self._load(Path(prompts_file))

    def _load(self, path: Path) -> None:
        if not path.exists():
            raise FileNotFoundError(
                f"MASTER_PROMPTS.txt not found at {path}. "
                "Run from the project root or pass an explicit prompts_file path."
            )
        text = path.read_text(encoding="utf-8")
        self._parse(text)

    def _parse(self, text: str) -> None:
        """Split text on exactly '----' lines and register each section by prompt ID."""
        # Match exactly 4 dashes (not more) to avoid splitting on ---- separator lines
        # that appear inside prompt bodies as visual dividers
        sections = re.split(r"(?m)^----\s*$", text)
        for section in sections:
            section = section.strip()
            if not section:
                continue
            lines = section.splitlines()
            # Find first non-empty line that matches a header
            for line in lines:
                m = HEADER_RE.search(line)
                if m:
                    prompt_id = _normalize_id(m.group(1))
                    # Body is everything after the header line
                    header_idx = lines.index(line)
                    body = "\n".join(lines[header_idx + 1 :]).strip()
                    self._prompts[prompt_id] = body
                    break

        if not self._prompts:
            raise ValueError(
                "No prompt sections found in MASTER_PROMPTS.txt. "
                "Sections must start with '## Prompt N:' and be separated by '----' lines."
            )

    def available_prompts(self) -> list[str]:
        return sorted(self._prompts.keys())

    def get_prompt(self, prompt_id: str, **variables) -> str:
        """
        Return the prompt for prompt_id with all [VARIABLE] and {variable}
        placeholders replaced by the provided keyword arguments.

        Args:
            prompt_id: One of "prompt0", "prompt1", "prompt2",
                       "prompt3a", "prompt3b", "prompt4"
            **variables: Placeholder values keyed by placeholder name
                         (case-insensitive for [VARIABLE] style).

        Returns:
            The fully-substituted prompt string.

        Raises:
            KeyError: If prompt_id is not found.
            ValueError: If any placeholder remains unfilled after substitution.
        """
        if prompt_id not in self._prompts:
            available = ", ".join(self.available_prompts())
            raise KeyError(
                f"Prompt '{prompt_id}' not found. Available: {available}"
            )

        text = self._prompts[prompt_id]

        # Replace [VARIABLE_NAME] style (case-insensitive key lookup)
        upper_vars = {k.upper(): v for k, v in variables.items()}

        def replace_bracket(m):
            key = m.group(1).upper()
            if key in upper_vars:
                return str(upper_vars[key])
            return m.group(0)  # leave unfilled for error detection below

        # Only match [UPPERCASE_WORD] style — not JSON arrays or prose
        text = re.sub(r"\[([A-Z][A-Z0-9_]*)\]", replace_bracket, text)

        # Replace {variable_name} style (exact key match, then upper fallback)
        def replace_curly(m):
            key = m.group(1)
            if key in variables:
                return str(variables[key])
            if key.upper() in upper_vars:
                return str(upper_vars[key.upper()])
            return m.group(0)  # leave unfilled

        text = re.sub(r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}", replace_curly, text)

        # Validate: detect any remaining unfilled placeholders
        _validate_no_placeholders(text, prompt_id)

        return text


# Safe words that appear in JSON examples or instructions — not real placeholders
_SAFE_WORDS = frozenset({
    "json", "example", "examples", "output", "format", "formats",
    "rules", "rule", "important", "constraint", "constraints",
    "input", "inputs", "goal", "goals", "context", "contexts",
    "title", "titles", "scene_id", "phase", "chapter", "class",
    "subject", "medium", "learning_step", "learning_steps",
    "character", "characters", "dialogue", "dialogues",
    "narrative", "screenplay", "concept", "concepts",
    "narrator", "voice", "audio", "text", "type",
    "brackets", "parentheses", "speaker", "tags",
})


def _validate_no_placeholders(text: str, prompt_id: str) -> None:
    """Raise ValueError if any real placeholder is still present in text."""
    # Only flag [UPPERCASE_WORD] style — ignore JSON arrays, prose, etc.
    bracket_matches = re.findall(r"\[([A-Z][A-Z0-9_]*)\]", text)
    curly_matches = re.findall(r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}", text)

    unfilled = []
    for m in bracket_matches + curly_matches:
        if m.strip().lower() not in _SAFE_WORDS:
            unfilled.append(m)

    if unfilled:
        raise ValueError(
            f"Prompt '{prompt_id}' has unfilled placeholders after substitution: "
            f"{unfilled}. Pass them as keyword arguments to get_prompt()."
        )
