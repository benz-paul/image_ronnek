"""
Scene Generator Agent module for generating scenes for each learning step.
"""

import json
from typing import Dict, Any, List, Optional

from core.logger import logger
from core.llm_client import create_llm_client
from core.prompt_loader import get_prompt_loader
from core.state_manager import get_state_manager


class SceneGeneratorAgent:
    """Agent for generating scenes for learning steps."""

    def __init__(self):
        """Initialize scene generator agent."""
        self.llm_client = create_llm_client()
        self.prompt_loader = get_prompt_loader()

    def run(self) -> Dict[str, Any]:
        """
        Run the scene generation for all learning steps.

        Returns:
            Combined scenes data for all learning steps

        Raises:
            RuntimeError: If scene generation fails
        """
        logger.section("Prompt 3 - Scene Generation")

        state = get_state_manager().get_current()
        if not state:
            raise RuntimeError("No chapter state found")

        selected_story = state.get("selected_story")
        if not selected_story:
            raise RuntimeError("Selected story not found")

        learning_steps = state.get("learning_steps", {})
        steps = learning_steps.get("learning_steps", [])

        if not steps:
            raise RuntimeError("No learning steps found")

        all_scenes = {}

        for idx, step in enumerate(steps):
            step_id = step.get("step_id", f"LS{idx + 1}")

            previous_step = steps[idx - 1] if idx > 0 else None
            current_step = step
            next_step = steps[idx + 1] if idx < len(steps) - 1 else None

            logger.info(f"Generating scenes for {step_id}")

            scenes = self._generate_step_scenes(
                step_id=step_id,
                current_step=current_step,
                previous_step=previous_step,
                next_step=next_step,
                selected_story=selected_story,
                chapter_name=state.get_chapter_name(),
            )

            all_scenes[step_id] = scenes

            state.save_json(f"scenes_{step_id}.json", scenes)

        combined_scenes = self._combine_scenes(all_scenes)

        state.save_json("scenes_full.json", combined_scenes)

        state.update("scenes", all_scenes)

        logger.info(f"Generated scenes for {len(steps)} learning steps")

        return combined_scenes

    def _generate_step_scenes(
        self,
        step_id: str,
        current_step: Dict[str, Any],
        previous_step: Optional[Dict[str, Any]],
        next_step: Optional[Dict[str, Any]],
        selected_story: Dict[str, Any],
        chapter_name: str,
    ) -> Dict[str, Any]:
        """
        Generate scenes for a single learning step.

        Args:
            step_id: Learning step ID
            current_step: Current learning step data
            previous_step: Previous learning step (or None)
            next_step: Next learning step (or None)
            selected_story: Selected story backbone
            chapter_name: Chapter name

        Returns:
            Scenes data for the learning step
        """
        prompt_template = self.prompt_loader.get_prompt(3)

        prev_step_text = self._format_step(previous_step) if previous_step else ""
        current_step_text = self._format_step(current_step)
        next_step_text = self._format_step(next_step) if next_step else ""

        prompt = self.prompt_loader.inject_values(
            prompt_template,
            chapter=chapter_name,
            story_backbone=selected_story.get("core_premise", ""),
            previous_learning_step=prev_step_text,
            current_learning_step=current_step_text,
            next_learning_step=next_step_text,
        )

        state = get_state_manager().get_current()
        if state:
            state.save_prompt(3, prompt, suffix=step_id)

        try:
            response = self.llm_client.call_with_json_output(prompt)

            if state:
                state.save_raw_response(3, json.dumps(response), suffix=step_id)

            return response

        except Exception as e:
            logger.error(f"Scene generation failed for {step_id}: {e}")

            if state:
                state.save_raw_response(3, str(e), suffix=step_id)

            return {"error": str(e), "step_id": step_id}

    def _format_step(self, step: Optional[Dict[str, Any]]) -> str:
        """
        Format a learning step for prompt injection.

        Args:
            step: Learning step data

        Returns:
            Formatted step text
        """
        if not step:
            return "No previous/next step available"

        step_id = step.get("step_id", "")
        title = step.get("title", "")
        concepts = step.get("concepts", [])
        narrative = step.get("narrative_moment", "")

        concepts_text = "\n".join([f"- {c}" for c in concepts])

        return f"""
Learning Step {step_id}: {title}

Concepts:
{concepts_text}

Narrative Moment:
{narrative}
"""

    def _combine_scenes(self, all_scenes: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
        """
        Combine scenes from all learning steps into one structure.

        Args:
            all_scenes: Dictionary of scenes by learning step

        Returns:
            Combined scenes data
        """
        combined = {"total_learning_steps": len(all_scenes), "learning_steps": []}

        for step_id, scenes in all_scenes.items():
            combined["learning_steps"].append({"step_id": step_id, "scenes": scenes})

        return combined


def create_scene_generator_agent() -> SceneGeneratorAgent:
    """
    Factory function to create scene generator agent.

    Returns:
        SceneGeneratorAgent instance
    """
    return SceneGeneratorAgent()
