"""
Prompt Loader module to extract prompts from MASTER_PROMPTS.txt.
"""

import re
from pathlib import Path
from typing import Optional, Dict

from brain.prompt_engine.core.logger import logger


class PromptLoader:
    """Loads and manages prompts from MASTER_PROMPTS.txt."""

    def __init__(self, prompt_file: str = None):
        """
        Initialize the prompt loader.

        Args:
            prompt_file: Path to the prompt file
        """
        if prompt_file is None:
            prompt_file = (
                Path(__file__).parent.parent / "prompts" / "MASTER_PROMPTS.txt"
            )
        else:
            prompt_file = Path(prompt_file)
        self.prompt_file = prompt_file
        self._prompts: Dict[int, str] = {}
        self._pdf_prompt: Optional[str] = None
        self._load_prompts()

    def _load_prompts(self) -> None:
        """Load all prompts from the prompt file using block-based parsing."""
        if not self.prompt_file.exists():
            logger.error(f"Prompt file not found: {self.prompt_file}")
            raise FileNotFoundError(f"Prompt file not found: {self.prompt_file}")

        with open(self.prompt_file, "r", encoding="utf-8") as f:
            content = f.read()

        self._pdf_prompt = self._extract_pdf_prompt(content)

        # Split on lines starting with "Prompt X" (where X is a digit)
        prompt_blocks = re.split(r"\n(?=Prompt\s+\d+)", content)

        for block in prompt_blocks:
            match = re.match(r"Prompt\s+(\d+)", block)
            if not match:
                continue

            prompt_id = int(match.group(1))

            # Remove the first line (title line) to get just the prompt text
            lines = block.split("\n", 1)
            prompt_text = lines[1].strip() if len(lines) > 1 else ""

            # Clean up dashes
            prompt_text = prompt_text.replace("----", "").strip()

            self._prompts[prompt_id] = prompt_text

        logger.info(f"Loaded {len(self._prompts)} prompts and PDF prompt")

    def _extract_pdf_prompt(self, content: str) -> str:
        """
        Extract the PDF retrieval prompt.

        Args:
            content: Full content of prompt file

        Returns:
            PDF prompt text
        """
        pdf_section_match = re.search(
            r"(usable Master Prompt.*?)(?=Master prompts:|$)", content, re.DOTALL
        )

        if pdf_section_match:
            pdf_prompt = pdf_section_match.group(1).strip()
            return pdf_prompt

        fallback_pattern = r"(Obtaining PDF downloads.*?)(?=Prompt \d|$)"
        fallback_match = re.search(fallback_pattern, content, re.DOTALL)

        if fallback_match:
            return fallback_match.group(1).strip()

        return "Provide the official NCERT website direct PDF link"

    def get_pdf_prompt(self) -> str:
        """Get the PDF retrieval prompt."""
        return self._pdf_prompt or "Provide the official NCERT website direct PDF link"

    def get_prompt(self, prompt_num: int) -> str:
        """
        Get a specific prompt by number.

        Args:
            prompt_num: Prompt number (0-4)

        Returns:
            Prompt text

        Raises:
            KeyError: If prompt number not found
        """
        if prompt_num not in self._prompts:
            raise KeyError(f"Prompt {prompt_num} not found")
        return self._prompts[prompt_num]

    @staticmethod
    def normalize_subject(subject: str) -> str:
        """Normalize subject name to standard form."""
        mapping = {
            "maths": "mathematics",
            "math": "mathematics",
            "science": "science",
            "physics": "physics",
            "chemistry": "chemistry",
            "biology": "biology",
        }
        return mapping.get(subject.lower(), subject.lower())

    @staticmethod
    def slugify(text: str) -> str:
        """Convert text to URL-friendly slug."""
        import re

        text = text.lower()
        text = re.sub(r"[^a-z0-9]+", "_", text)
        return text.strip("_")

    def inject_values(self, prompt: str, **kwargs) -> str:
        """
        Safely inject values into prompt templates without regex.
        Supports multiple placeholder styles.

        Args:
            prompt: Prompt template
            **kwargs: Key-value pairs to inject

        Returns:
            Prompt with injected values
        """
        result = prompt
        kwarg_dict = dict(kwargs)

        insert_patterns = {
            "(Insert the chapter name used in the previous prompts)": kwarg_dict.get(
                "chapter"
            ),
            "(Insert the chapter name used in previous prompts)": kwarg_dict.get(
                "chapter"
            ),
            "(Insert the chapter name)": kwarg_dict.get("chapter"),
            "[Insert the chapter name used in the previous prompts]": kwarg_dict.get(
                "chapter"
            ),
            "[Insert the chapter name]": kwarg_dict.get("chapter"),
            "[Chapter Name]": kwarg_dict.get("chapter"),
            "(Chapter Name)": kwarg_dict.get("chapter"),
            "(Insert the **selected story backbone output from the story backbone generation prompt**, specifically the **Core Narrative Premise of the chosen story**)": kwarg_dict.get(
                "story_backbone"
            ),
            "(Insert the selected story backbone output from the story backbone generation prompt, specifically the Core Narrative Premise of the chosen story)": kwarg_dict.get(
                "story_backbone"
            ),
            "(Insert the **previous learning step output from the learning step decomposition prompt**)": kwarg_dict.get(
                "previous_learning_step"
            ),
            "(Insert the previous learning step output from the learning step decomposition prompt)": kwarg_dict.get(
                "previous_learning_step"
            ),
            "(Insert the **current learning step from the learning step decomposition output**)": kwarg_dict.get(
                "current_learning_step"
            ),
            "(Insert the current learning step from the learning step decomposition output)": kwarg_dict.get(
                "current_learning_step"
            ),
            "(Insert the **next learning step from the learning step decomposition output**)": kwarg_dict.get(
                "next_learning_step"
            ),
            "(Insert the next learning step from the learning step decomposition output)": kwarg_dict.get(
                "next_learning_step"
            ),
            "(Insert the **Concept Inventory output generated from Prompt 0**)": kwarg_dict.get(
                "concept_inventory"
            ),
            "(Insert the Concept Inventory output generated from Prompt 0)": kwarg_dict.get(
                "concept_inventory"
            ),
            "(Insert the Concept Inventory)": kwarg_dict.get("concept_inventory"),
            "(Insert the **Concept Inventory** generated from Prompt 0)": kwarg_dict.get(
                "concept_inventory"
            ),
        }

        for placeholder, val in insert_patterns.items():
            if val:
                result = result.replace(placeholder, str(val))

        for key, value in kwarg_dict.items():
            if value is None:
                continue

            value_str = str(value)

            result = result.replace("{" + key + "}", value_str)
            result = result.replace("{" + key.upper() + "}", value_str)
            result = result.replace("[" + key.upper() + "]", value_str)
            result = result.replace("[" + key + "]", value_str)
            result = result.replace("(" + key + ")", value_str)
            result = result.replace("<" + key + ">", value_str)

        common_mappings = {
            "Enter Class": kwarg_dict.get("class_level", ""),
            "Enter Subject": kwarg_dict.get("subject", ""),
            "Enter Number": kwarg_dict.get("chapter_number", ""),
            "Enter Title": kwarg_dict.get("chapter_title", ""),
            "English/Hindi": kwarg_dict.get("medium", "English"),
            "Chapter Name": kwarg_dict.get("chapter_name", ""),
        }

        for placeholder, value in common_mappings.items():
            if value:
                result = result.replace("[" + placeholder + "]", str(value))
                result = result.replace("(" + placeholder + ")", str(value))
                result = result.replace("<" + placeholder + ">", str(value))

        return result

    def inject_prompt_values(self, prompt_num: int, **kwargs) -> str:
        """
        Get prompt and inject values.

        Args:
            prompt_num: Prompt number
            **kwargs: Values to inject

        Returns:
            Processed prompt
        """
        prompt = self.get_prompt(prompt_num)
        return self.inject_values(prompt, **kwargs)

    def format_pdf_prompt(self, **kwargs) -> str:
        """
        Format PDF retrieval prompt with values.

        Args:
            **kwargs: Values to inject (class, subject, chapter_number, etc.)

        Returns:
            Formatted PDF prompt
        """
        pdf_prompt = self.get_pdf_prompt()
        return self.inject_values(pdf_prompt, **kwargs)


def render_prompt(template: str, state) -> str:
    """
    Render prompt template with chapter metadata using safe formatting.

    Args:
        template: Prompt template string
        state: State manager instance

    Returns:
        Rendered prompt with chapter metadata
    """
    subject_id = state.subject.lower()
    chapter_id = state.chapter_title.lower().replace(" ", "_")
    chapter_number = state.chapter_number
    chapter_title = state.chapter_title
    board = "cbse"
    grade = state.class_level

    logger.info(
        f"Rendering prompt for {state.subject} Chapter {chapter_number}: {chapter_title}"
    )

    import re

    def replace_placeholder(match):
        key = match.group(1)
        replacements = {
            "subject_id": subject_id,
            "chapter_id": chapter_id,
            "chapter_number": chapter_number,
            "chapter_title": chapter_title,
            "board": board,
            "grade": grade,
        }
        return str(replacements.get(key, match.group(0)))

    pattern = (
        r"\{("
        + "|".join(
            [
                "subject_id",
                "chapter_id",
                "chapter_number",
                "chapter_title",
                "board",
                "grade",
            ]
        )
        + r")\}"
    )
    rendered = re.sub(pattern, replace_placeholder, template)

    logger.debug("Rendered Prompt Preview:")
    logger.debug(rendered[:1000])

    return rendered


_prompt_loader: Optional[PromptLoader] = None


def get_prompt_loader(prompt_file: str = "MASTER_PROMPTS.txt") -> PromptLoader:
    """
    Get the prompt loader singleton.

    Args:
        prompt_file: Path to prompt file

    Returns:
        PromptLoader instance
    """
    global _prompt_loader
    if _prompt_loader is None:
        _prompt_loader = PromptLoader(prompt_file)
    return _prompt_loader


def get_pdf_prompt() -> str:
    """Get the PDF retrieval prompt."""
    return get_prompt_loader().get_pdf_prompt()


def get_prompt(prompt_num: int) -> str:
    """Get a specific prompt by number."""
    return get_prompt_loader().get_prompt(prompt_num)
