"""
Concept Agent module for extracting chapter concept inventory.
"""

import json
import re
from typing import Dict, Any, List

from core.logger import logger
from core.llm_client import create_llm_client
from core.prompt_loader import get_prompt_loader
from core.state_manager import get_state_manager


class ConceptAgent:
    """Agent for extracting concept inventory from chapter PDF."""

    def __init__(self):
        """Initialize concept agent."""
        self.llm_client = create_llm_client()
        self.prompt_loader = get_prompt_loader()

    def run(self) -> Dict[str, Any]:
        """
        Run the concept inventory extraction.

        Returns:
            Concept inventory data

        Raises:
            RuntimeError: If concept extraction fails
        """
        logger.section("Prompt 0 - Concept Inventory")

        state = get_state_manager().get_current()
        if not state:
            raise RuntimeError("No chapter state found")

        pdf_path = state.pdf_path
        if not pdf_path or not pdf_path.exists():
            raise RuntimeError("PDF not found")

        prompt_template = self.prompt_loader.get_prompt(0)

        prompt = self.prompt_loader.inject_values(
            prompt_template, chapter=state.get_chapter_name()
        )

        logger.info("Extracting concept inventory from chapter...")

        state.save_prompt(0, prompt)

        try:
            response = self.llm_client.call(prompt, attachments=[str(pdf_path)])

            state.save_raw_response(0, response)

            concept_data = self._parse_concept_response(response)

            state.save_json("concept_inventory.json", concept_data)
            state.save_output("concept_inventory.txt", response)

            state.update("concept_inventory", concept_data)

            logger.info(f"Extracted {len(concept_data.get('concepts', []))} concepts")

            return concept_data

        except Exception as e:
            logger.error(f"Concept extraction failed: {e}", exc_info=True)
            raise RuntimeError(f"Concept extraction failed: {e}") from e

    def _parse_concept_response(self, response: str) -> Dict[str, Any]:
        """
        Parse the concept inventory response.

        Args:
            response: Raw LLM response

        Returns:
            Parsed concept data
        """
        concepts = []

        lines = response.strip().split("\n")

        for line in lines:
            line = line.strip()
            if not line:
                continue

            match = re.match(r"^\d+[\.\)]\s*(.+?)\s*[-–—]\s*(.+)$", line)
            if match:
                concept_name = match.group(1).strip()
                description = match.group(2).strip()
                concepts.append({"concept": concept_name, "description": description})
            elif re.match(r"^\d+[\.\)]\s*.+$", line):
                parts = line.split("-", 1)
                if len(parts) == 2:
                    concepts.append(
                        {"concept": parts[0].strip(), "description": parts[1].strip()}
                    )

        if not concepts:
            logger.warning("Could not parse structured concepts, storing raw text")
            return {"raw_text": response, "concepts": []}

        return {"concepts": concepts, "raw_text": response}


def create_concept_agent() -> ConceptAgent:
    """
    Factory function to create concept agent.

    Returns:
        ConceptAgent instance
    """
    return ConceptAgent()
