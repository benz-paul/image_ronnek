"""
Learning Steps Agent module for decomposing chapter into learning steps.
"""

import json
import re
from typing import Dict, Any, List, Optional

from core.logger import logger
from core.llm_client import create_llm_client
from core.prompt_loader import get_prompt_loader, render_prompt
from core.state_manager import get_state_manager


class LearningStepsAgent:
    """Agent for decomposing chapter into learning steps."""

    def __init__(self):
        """Initialize learning steps agent."""
        self.llm_client = create_llm_client()
        self.prompt_loader = get_prompt_loader()

    def run(self) -> Dict[str, Any]:
        """
        Run the learning step decomposition.

        Returns:
            Learning steps data

        Raises:
            RuntimeError: If learning step decomposition fails
        """
        logger.section("Prompt 2 - Learning Steps Decomposition")

        state = get_state_manager().get_current()
        if not state:
            raise RuntimeError("No chapter state found")

        concept_inventory = state.get("concept_inventory")
        if not concept_inventory:
            raise RuntimeError("Concept inventory not found")

        selected_story = state.get("selected_story")
        if not selected_story:
            raise RuntimeError("Selected story not found")

        prompt_template = self.prompt_loader.get_prompt(2)

        concepts_text = self._format_concepts(concept_inventory)

        prompt = self.prompt_loader.inject_values(
            prompt_template,
            chapter=state.get_chapter_name(),
            selected_story_narrative=selected_story.get("core_premise", ""),
            concept_inventory=concepts_text,
        )

        prompt = render_prompt(prompt, state)

        logger.info("Decomposing chapter into learning steps...")

        state.save_prompt(2, prompt)
        state.save_prompt(2, prompt, suffix="final")

        try:
            response = self.llm_client.call(prompt)

            state.save_raw_response(2, response)
            state.save_output("learning_steps.txt", response)

            steps_data = {"raw_text": response}
            state.save_json("learning_steps.json", steps_data)
            state.update("learning_steps", steps_data)

            logger.info("Decomposed chapter into learning steps")

            return steps_data

        except Exception as e:
            logger.error(f"Learning step decomposition failed: {e}", exc_info=True)
            raise RuntimeError(f"Learning step decomposition failed: {e}") from e

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

    def _parse_steps_response(self, response: str) -> Dict[str, Any]:
        """
        Parse the learning steps response.

        Args:
            response: Raw LLM response

        Returns:
            Parsed learning steps data
        """
        learning_steps = []

        step_pattern = r"(?:Learning Step|Step)\s*([A-Z0-9]+)[:\s]*(.+?)(?=(?:Learning Step|Step)\s*[A-Z0-9]+:|$)"
        step_matches = re.finditer(step_pattern, response, re.DOTALL | re.IGNORECASE)

        for match in step_matches:
            step_id = match.group(1).strip()
            step_content = match.group(2).strip()

            title_match = re.search(
                r"(?:Title|Learning Step Title)[:\s]*(.+?)(?:\n|$)",
                step_content,
                re.IGNORECASE,
            )
            title = title_match.group(1).strip() if title_match else f"Step {step_id}"

            concepts_match = re.search(
                r"(?:Concepts Introduced|Concepts)[:\s]*(.+?)(?=\nNarrative|$)",
                step_content,
                re.DOTALL | re.IGNORECASE,
            )
            concepts_text = concepts_match.group(1).strip() if concepts_match else ""

            concepts_list = []
            for line in concepts_text.split("\n"):
                line = line.strip().lstrip("*-").strip()
                if line:
                    concepts_list.append(line)

            narrative_match = re.search(
                r"Narrative Moment[:\s]*(.+?)(?=(?:Concept Coverage|Do NOT)|$)",
                step_content,
                re.DOTALL | re.IGNORECASE,
            )
            narrative = narrative_match.group(1).strip() if narrative_match else ""

            learning_steps.append(
                {
                    "step_id": step_id,
                    "title": title,
                    "concepts": concepts_list,
                    "narrative_moment": narrative,
                }
            )

        if not learning_steps:
            logger.warning("Could not parse structured learning steps")
            return {"raw_text": response, "learning_steps": []}

        return {"learning_steps": learning_steps, "raw_text": response}

    def get_learning_steps(self) -> List[Dict[str, Any]]:
        """
        Get the learning steps from state.

        Returns:
            List of learning steps
        """
        state = get_state_manager().get_current()
        if not state:
            return []

        steps_data = state.get("learning_steps", {})
        return steps_data.get("learning_steps", [])


def create_learning_steps_agent() -> LearningStepsAgent:
    """
    Factory function to create learning steps agent.

    Returns:
        LearningStepsAgent instance
    """
    return LearningStepsAgent()
