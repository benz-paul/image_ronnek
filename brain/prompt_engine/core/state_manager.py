"""
State Manager module to handle pipeline state and chapter run directories.
"""

import json
from pathlib import Path
from typing import Any, Dict, Optional
from datetime import datetime

from brain.prompt_engine.core.logger import logger


class ChapterState:
    """Manages state for a single chapter run."""

    def __init__(
        self,
        class_level: str,
        subject: str,
        chapter_number: str,
        chapter_title: str,
        medium: str,
    ):
        """
        Initialize chapter state.

        Args:
            class_level: Class (e.g., "10")
            subject: Subject (e.g., "Physics")
            chapter_number: Chapter number
            chapter_title: Chapter title
            medium: Medium (English/Hindi)
        """
        self.class_level = class_level
        self.subject = subject
        self.chapter_number = chapter_number
        self.chapter_title = chapter_title
        self.medium = medium

        folder_name = f"{class_level}_{subject}_{chapter_title}".lower().replace(
            " ", "_"
        )
        self.run_folder = Path("runs") / folder_name
        self._create_directories()

        self.data: Dict[str, Any] = {
            "class": class_level,
            "subject": subject,
            "chapter_number": chapter_number,
            "chapter_title": chapter_title,
            "medium": medium,
            "pdf_url": None,
            "pdf_path": None,
            "concept_inventory": None,
            "story_backbones": None,
            "selected_story": None,
            "learning_steps": None,
            "scenes": {},
            "image_prompts": {},
            "created_at": datetime.now().isoformat(),
        }

    def _create_directories(self) -> None:
        """Create all required subdirectories for the chapter run."""
        self.run_folder.mkdir(parents=True, exist_ok=True)

        subdirs = ["prompts", "outputs", "raw", "json", "image_prompts"]
        for subdir in subdirs:
            (self.run_folder / subdir).mkdir(exist_ok=True)

    @property
    def prompts_dir(self) -> Path:
        """Get prompts directory."""
        return self.run_folder / "prompts"

    @property
    def outputs_dir(self) -> Path:
        """Get outputs directory."""
        return self.run_folder / "outputs"

    @property
    def raw_dir(self) -> Path:
        """Get raw directory."""
        return self.run_folder / "raw"

    @property
    def json_dir(self) -> Path:
        """Get JSON directory."""
        return self.run_folder / "json"

    @property
    def image_prompts_dir(self) -> Path:
        """Get image prompts directory."""
        return self.run_folder / "image_prompts"

    @property
    def pdf_path(self) -> Optional[Path]:
        """Get PDF path if available."""
        return self.run_folder / "chapter.pdf"

    def save_prompt(
        self, prompt_num: int | str, prompt_text: str, suffix: str = ""
    ) -> None:
        """
        Save sent prompt to file.

        Args:
            prompt_num: Prompt number (can be int or string like "pdf")
            prompt_text: The prompt that was sent
            suffix: Optional suffix for filename
        """
        prompt_str = str(prompt_num)
        suffix_part = f"_{suffix}" if suffix else ""
        filename = f"prompt{prompt_str}{suffix_part}_sent.txt"
        filepath = self.prompts_dir / filename

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(prompt_text)

        logger.debug(f"Saved prompt to {filepath}")

    def save_raw_response(
        self, prompt_num: int | str, response: Any, suffix: str = ""
    ) -> None:
        """
        Save raw LLM response.

        Args:
            prompt_num: Prompt number (can be int or string like "pdf")
            response: Raw response from LLM (can be string or dict)
            suffix: Optional suffix for filename
        """
        prompt_str = str(prompt_num)
        suffix_part = f"_{suffix}" if suffix else ""
        filename = f"prompt{prompt_str}_raw{suffix_part}.txt"
        filepath = self.raw_dir / filename

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(response)

        logger.debug(f"Saved raw response to {filepath}")

    def save_output(self, name: str, content: str) -> None:
        """
        Save output file.

        Args:
            name: Output filename
            content: Content to save
        """
        filepath = self.outputs_dir / name

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)

        logger.debug(f"Saved output to {filepath}")

    def save_json(self, name: str, data: Dict[str, Any], suffix: str = "") -> None:
        """
        Save JSON file.

        Args:
            name: JSON filename
            data: Data to save as JSON
            suffix: Optional suffix for filename
        """
        suffix_part = f"_{suffix}" if suffix else ""
        name_with_suffix = name.replace(".json", f"{suffix_part}.json")
        filepath = self.json_dir / name_with_suffix

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        logger.debug(f"Saved JSON to {filepath}")

    def update(self, key: str, value: Any) -> None:
        """
        Update state data.

        Args:
            key: Data key
            value: Data value
        """
        self.data[key] = value

    def get(self, key: str, default: Any = None) -> Any:
        """
        Get state data.

        Args:
            key: Data key
            default: Default value if key not found

        Returns:
            Data value or default
        """
        return self.data.get(key, default)

    def get_chapter_name(self) -> str:
        """
        Get formatted chapter name.

        Returns:
            Chapter name (e.g., "Class 10 Physics Chapter 12 Electricity")
        """
        return f"Class {self.class_level} {self.subject} Chapter {self.chapter_number} {self.chapter_title}"

    def get_folder_name(self) -> str:
        """
        Get folder name for this run.

        Returns:
            Folder name
        """
        return self.run_folder.name


class StateManager:
    """Manages state across pipeline execution."""

    def __init__(self):
        """Initialize state manager."""
        self.current_chapter: Optional[ChapterState] = None
        self.history: list[ChapterState] = []

    def create_chapter(
        self,
        class_level: str,
        subject: str,
        chapter_number: str,
        chapter_title: str,
        medium: str,
    ) -> ChapterState:
        """
        Create new chapter state.

        Args:
            class_level: Class
            subject: Subject
            chapter_number: Chapter number
            chapter_title: Chapter title
            medium: Medium

        Returns:
            New ChapterState instance
        """
        self.current_chapter = ChapterState(
            class_level=class_level,
            subject=subject,
            chapter_number=chapter_number,
            chapter_title=chapter_title,
            medium=medium,
        )

        logger.info(f"Created chapter run: {self.current_chapter.get_folder_name()}")
        return self.current_chapter

    def get_current(self) -> Optional[ChapterState]:
        """
        Get current chapter state.

        Returns:
            Current ChapterState or None
        """
        return self.current_chapter

    def save_history(self) -> None:
        """Save current chapter to history."""
        if self.current_chapter:
            self.history.append(self.current_chapter)


_state_manager: Optional[StateManager] = None


def get_state_manager() -> StateManager:
    """
    Get state manager singleton.

    Returns:
        StateManager instance
    """
    global _state_manager
    if _state_manager is None:
        _state_manager = StateManager()
    return _state_manager
