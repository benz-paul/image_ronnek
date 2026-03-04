"""
Prompt Loader module to extract prompts from MASTER_PROMPTS.txt.
"""

import re
from pathlib import Path
from typing import Optional, Dict

from core.logger import logger


class PromptLoader:
    """Loads and manages prompts from MASTER_PROMPTS.txt."""

    def __init__(self, prompt_file: str = "MASTER_PROMPTS.txt"):
        """
        Initialize the prompt loader.

        Args:
            prompt_file: Path to the prompt file
        """
        self.prompt_file = Path(prompt_file)
        self._prompts: Dict[int, str] = {}
        self._pdf_prompt: Optional[str] = None
        self._load_prompts()

    def _load_prompts(self) -> None:
        """Load all prompts from the prompt file."""
        if not self.prompt_file.exists():
            logger.error(f"Prompt file not found: {self.prompt_file}")
            raise FileNotFoundError(f"Prompt file not found: {self.prompt_file}")

        with open(self.prompt_file, "r", encoding="utf-8") as f:
            content = f.read()

        self._pdf_prompt = self._extract_pdf_prompt(content)

        prompt_pattern = r"Prompt\s+(\d+)\s*[–\-—]\s*(.*?)(?=----\s*$)"
        matches = re.findall(prompt_pattern, content, re.MULTILINE | re.DOTALL)

        for prompt_num, prompt_text in matches:
            prompt_num = int(prompt_num)
            prompt_text = prompt_text.strip()
            prompt_text = prompt_text.replace("----", "").strip()
            self._prompts[prompt_num] = prompt_text

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

    def inject_values(self, prompt: str, **kwargs) -> str:
        """
        Dynamically inject values into a prompt.

        Args:
            prompt: Prompt template
            **kwargs: Key-value pairs to inject

        Returns:
            Prompt with injected values
        """
        result = prompt

        common_mappings = {
            "Enter Class": kwargs.get("class_level", ""),
            "Enter Subject": kwargs.get("subject", ""),
            "Enter Number": kwargs.get("chapter_number", ""),
            "Enter Title": kwargs.get("chapter_title", ""),
            "English/Hindi": kwargs.get("medium", "English"),
            "Chapter Name": kwargs.get("chapter_name", ""),
        }

        for placeholder, value in common_mappings.items():
            if value:
                result = result.replace(f"[{placeholder}]", str(value))
                result = result.replace(f"({placeholder})", str(value))
                result = result.replace(f"<{placeholder}>", str(value))

        for key, value in kwargs.items():
            if not value:
                continue

            value_str = str(value)

            result = result.replace(f"[{key.upper()}]", value_str)
            result = result.replace(f"[{key}]", value_str)
            result = result.replace(f"({key})", value_str)
            result = result.replace(f"<{key}>", value_str)

            if "chapter" in key.lower():
                result = result.replace(
                    "(Insert the chapter name used in previous prompts)", value_str
                )
                result = result.replace(
                    "[Insert the chapter name used in previous prompts]", value_str
                )

            if "story" in key.lower() or "narrative" in key.lower():
                result = result.replace(
                    "(Insert the selected story backbone output from the previous prompt",
                    value_str,
                )
                result = result.replace(
                    "[Insert the selected story backbone output from the previous prompt",
                    value_str,
                )
                result = result.replace(
                    "selected story backbone output from the previous prompt — specifically",
                    value_str,
                )
                result = result.replace(
                    "selected story backbone output from the previous prompt — specifically the **Core Narrative Premise** of the chosen story",
                    value_str,
                )

            if "concept" in key.lower() or "inventory" in key.lower():
                result = result.replace(
                    "(Insert the **Concept Inventory output generated from Prompt 0**)",
                    value_str,
                )
                result = result.replace(
                    "[Insert the **Concept Inventory output generated from Prompt 0**]",
                    value_str,
                )
                result = result.replace(
                    "(Insert the Concept Inventory output generated from Prompt 0)",
                    value_str,
                )
                result = result.replace(
                    "[Output from Prompt 0 concept inventories]", value_str
                )

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
