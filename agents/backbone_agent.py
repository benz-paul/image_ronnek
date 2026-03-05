"""
Backbone Agent module for generating story backbone possibilities.
"""

import json
import re
from typing import Dict, Any, List, Optional

from core.logger import logger
from core.llm_client import create_llm_client
from core.prompt_loader import get_prompt_loader, render_prompt
from core.state_manager import get_state_manager


class BackboneAgent:
    """Agent for generating story backbone possibilities."""

    def __init__(self):
        """Initialize backbone agent."""
        self.llm_client = create_llm_client()
        self.prompt_loader = get_prompt_loader()

    def run(self) -> Dict[str, Any]:
        """
        Run the story backbone generation.

        Returns:
            Selected story backbone data

        Raises:
            RuntimeError: If backbone generation fails
        """
        logger.section("Prompt 1 - Story Backbone Generation")

        state = get_state_manager().get_current()
        if not state:
            raise RuntimeError("No chapter state found")

        concept_inventory = state.get("concept_inventory")
        if not concept_inventory:
            raise RuntimeError("Concept inventory not found")

        prompt_template = self.prompt_loader.get_prompt(1)

        concepts_text = self._format_concepts(concept_inventory)

        prompt = self.prompt_loader.inject_values(
            prompt_template,
            chapter=state.get_chapter_name(),
            concept_inventory=concepts_text,
        )

        prompt = render_prompt(prompt, state)

        logger.info("Generating story backbone possibilities...")

        state.save_prompt(1, prompt)
        state.save_prompt(1, prompt, suffix="final")

        try:
            response = self.llm_client.call(prompt)

            state.save_raw_response(1, response)
            state.save_output("story_backbone.txt", response)

            selected_story = self._select_best_story(response)

            state.update(
                "story_backbones", {"raw_text": response, "selected": selected_story}
            )
            state.update("selected_story", selected_story)

            logger.info(f"Selected story: {selected_story.get('title', 'Unknown')}")

            return selected_story

        except Exception as e:
            logger.error(f"Backbone generation failed: {e}", exc_info=True)
            raise RuntimeError(f"Backbone generation failed: {e}") from e

    def _format_concepts(self, concept_data: Dict[str, Any]) -> str:
        """
        Format concepts for prompt injection.

        Args:
            concept_data: Concept inventory data

        Returns:
            Formatted concepts text
        """
        concepts = concept_data.get("concepts", [])
        if not concepts:
            return concept_data.get("raw_text", "No concepts available")

        lines = []
        for concept in concepts:
            name = concept.get("concept", "")
            desc = concept.get("description", "")
            if name:
                lines.append(f"{name} - {desc}")

        return "\n".join(lines)

    def _parse_backbone_response(self, response: str) -> Dict[str, Any]:
        """
        Parse the backbone response.

        Args:
            response: Raw LLM response

        Returns:
            Parsed backbone data
        """
        stories = []

        story_sections = re.split(r"\n\s*\d+\.\s+", response)

        for section in story_sections:
            if not section.strip():
                continue

            title_match = re.search(
                r"(?:Story Title|Title)[:\s]+(.+?)(?:\n|$)", section, re.IGNORECASE
            )
            if not title_match:
                continue

            title = title_match.group(1).strip()

            premise_match = re.search(
                r"(?:Core Narrative Premise|Narrative Premise)[:\s]+(.+?)(?=\n\d+\.|$)",
                section,
                re.DOTALL | re.IGNORECASE,
            )
            premise = premise_match.group(1).strip() if premise_match else ""

            coverage_match = re.search(
                r"Overall Concept Coverage[:\s]*(\d+)\s*%", section, re.IGNORECASE
            )
            coverage = int(coverage_match.group(1)) if coverage_match else 0

            pedagogical_match = re.search(
                r"Pedagogical Strength[:\s]*(\d+)\s*%", section, re.IGNORECASE
            )
            pedagogical = int(pedagogical_match.group(1)) if pedagogical_match else 0

            stories.append(
                {
                    "title": title,
                    "core_premise": premise,
                    "coverage_percentage": coverage,
                    "pedagogical_strength": pedagogical,
                    "raw_section": section,
                }
            )

        if not stories:
            logger.warning("Could not parse structured stories, storing raw text")
            return {"raw_text": response, "stories": []}

        stories.sort(
            key=lambda x: (x["coverage_percentage"] + x["pedagogical_strength"]) / 2,
            reverse=True,
        )

        return {"stories": stories, "raw_text": response}

    def _select_best_story(self, response: str) -> Dict[str, Any]:
        """
        Select the best story from the raw response.

        Args:
            response: Raw LLM response text

        Returns:
            Selected story with title and core_premise
        """
        import re

        title_patterns = [
            r'(?:###\s*\d+\.?\s*Title:?\s*["\']?)([^"\'\n]+)',
            r"(?:###\s*Story\s*Backbone\s*\d+)[:\s]+([^\n]+)",
            r"(?:^\d+\.\s+\*?\*?Story\s*Title\*?\*?)[:\s]+([^\n]+)",
            r'Title[:\s]+["\']([^"\']+)["\']',
            r'\*\*Title[:\s]+\*\*["\']?([^"\']+)["\']?',
        ]

        title = None
        for pattern in title_patterns:
            match = re.search(pattern, response, re.MULTILINE | re.IGNORECASE)
            if match:
                title = match.group(1).strip().strip('*"')
                break

        if not title:
            title = "First Story"

        premise_patterns = [
            r"(?:Core Narrative Premise|Story Premise)[:\s\*]+(.+?)(?=\n\d+\.|\n---|\n\*\*|\nOverall|\Z)",
            r"\*\*Core Narrative Premise[:\s]+\*\*\s*(.+?)(?=\n\d+\.|\n---|\n\*\*|\nOverall|\Z)",
            r"(?:Premise|Core Narrative)[:\s]+(.+?)(?=\n\d+\.|\n---|\nOverall|\Z)",
        ]

        premise = None
        for pattern in premise_patterns:
            match = re.search(pattern, response, re.DOTALL | re.IGNORECASE)
            if match:
                premise = match.group(1).strip()
                if len(premise) > 50:
                    break

        if not premise:
            premise = response[:500]

        coverage_pattern = r"Overall Concept Coverage.*?(\d+)\s*%"
        coverage_match = re.search(coverage_pattern, response, re.IGNORECASE)
        coverage = int(coverage_match.group(1)) if coverage_match else 0

        pedagogical_pattern = r"Pedagogical Strength.*?(\d+)\s*%"
        pedagogical_match = re.search(pedagogical_pattern, response, re.IGNORECASE)
        pedagogical = int(pedagogical_match.group(1)) if pedagogical_match else 0

        logger.info(f"Selected story: {title}")
        logger.info(f"  Coverage: {coverage}%")
        logger.info(f"  Pedagogical: {pedagogical}%")

        return {
            "title": title,
            "core_premise": premise,
            "coverage_percentage": coverage,
            "pedagogical_strength": pedagogical,
            "raw_text": response,
        }


def create_backbone_agent() -> BackboneAgent:
    """
    Factory function to create backbone agent.

    Returns:
        BackboneAgent instance
    """
    return BackboneAgent()
