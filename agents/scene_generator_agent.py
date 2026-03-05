"""
Scene Generator Agent module for generating scenes for each learning step.
"""

import json
from typing import Dict, Any, List, Optional

from core.logger import logger
from core.llm_client import create_llm_client
from core.prompt_loader import get_prompt_loader, render_prompt
from core.state_manager import get_state_manager


class SceneGeneratorAgent:
    """Agent for generating scenes for learning steps."""

    def __init__(self):
        """Initialize scene generator agent."""
        self.llm_client = create_llm_client()
        self.prompt_loader = get_prompt_loader()

    def _validate_learning_alignment(self, state) -> None:
        """
        Validate that required data exists before scene generation.

        Args:
            state: State manager instance

        Raises:
            RuntimeError: If validation fails
        """
        concept_inventory = state.get("concept_inventory")
        if not concept_inventory:
            raise RuntimeError("Concept inventory not found - pipeline drift detected")

        concepts = concept_inventory.get("concepts", [])
        if not concepts or len(concepts) == 0:
            raise RuntimeError("Concept inventory is empty - pipeline drift detected")

        learning_steps = state.get("learning_steps")
        if not learning_steps:
            raise RuntimeError("Learning steps not found - pipeline drift detected")

        learning_steps_raw = learning_steps.get("raw_text", "")
        if not learning_steps_raw:
            raise RuntimeError("Learning steps is empty - pipeline drift detected")

        logger.info(
            f"Validation passed: {len(concepts)} concepts, learning steps present"
        )

    def _validate_learning_steps(self, state) -> None:
        """
        Validate that learning steps exist and have required fields.

        Args:
            state: State manager instance

        Raises:
            RuntimeError: If validation fails
        """
        concept_inventory = state.get("concept_inventory")
        learning_steps = state.get("learning_steps")

        if not concept_inventory:
            raise RuntimeError("Concept inventory not found")

        if not learning_steps:
            raise RuntimeError("Learning steps not found")

        learning_steps_raw = learning_steps.get("raw_text", "")
        if not learning_steps_raw:
            raise RuntimeError("Learning steps is empty")

        logger.info(f"Learning steps validated: ready for scene generation")

    def _validate_scenes(self, state, scenes_data: Dict[str, Any]) -> None:
        """
        Validate scenes data exists.

        Args:
            state: State manager instance
            scenes_data: Generated scenes data

        Raises:
            RuntimeError: If validation fails
        """
        raw_text = scenes_data.get("raw_text", "")
        if not raw_text:
            raise RuntimeError("Scenes data is empty")

        logger.info("Scenes validated: generated successfully")

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

        self._validate_learning_alignment(state)
        self._validate_learning_steps(state)

        concept_inventory = state.get("concept_inventory")
        if not concept_inventory:
            raise RuntimeError("Concept inventory not found in state")

        selected_story = state.get("selected_story")
        if not selected_story:
            raise RuntimeError("Selected story not found")

        learning_steps = state.get("learning_steps", {})
        learning_steps_raw = learning_steps.get("raw_text", "")

        if not learning_steps_raw:
            raise RuntimeError("No learning steps found")

        logger.info("Parsing learning steps from text...")

        steps = self._parse_learning_steps(learning_steps_raw)
        logger.info(f"Found {len(steps)} learning steps to process")

        logger.info("Generating scenes for each learning step...")

        all_step_outputs = []

        for i, step in enumerate(steps):
            step_id = step.get("step_id", f"LS{i + 1}")
            logger.info(f"Processing {step_id} ({i + 1}/{len(steps)})")

            prev_step = steps[i - 1] if i > 0 else None
            next_step = steps[i + 1] if i < len(steps) - 1 else None

            step_result = self._generate_single_step_scenes(
                step=step,
                prev_step=prev_step,
                next_step=next_step,
                selected_story=selected_story,
                concept_inventory=concept_inventory,
                chapter_name=state.get_chapter_name(),
                state=state,
                step_index=i,
            )

            state.save_json(f"scenes_{step_id}.json", step_result)

            all_step_outputs.append(step_result)

        combined_scenes = self._combine_step_outputs(
            all_step_outputs, selected_story, concept_inventory, state
        )

        state.save_json("scenes_full.json", combined_scenes)
        state.save_output("scenes.txt", json.dumps(combined_scenes, indent=2))

        state.update("scenes", combined_scenes)

        logger.info(f"Generated scenes for all {len(steps)} learning steps")

        return combined_scenes

    def _parse_learning_steps(self, raw_text: str) -> List[Dict[str, Any]]:
        """
        Parse learning steps from raw text.
        Extracts full raw text for each learning step to pass to scene generator.

        Args:
            raw_text: Raw text containing learning steps

        Returns:
            List of parsed learning steps with full raw content
        """
        import re

        steps = []

        step_sections = re.split(r"####\s+Learning\s+Step\s+\d+", raw_text)
        step_sections = [
            s.strip() for s in step_sections if s.strip() and "Learning Step ID" in s
        ]

        for idx, section in enumerate(step_sections):
            ls_id_match = re.search(
                r"\*\*Learning Step ID:\*\*\s+([A-Z0-9]+)", section, re.IGNORECASE
            )
            step_id = ls_id_match.group(1).strip() if ls_id_match else f"LS{idx + 1}"

            title_match = re.search(
                r"\*\*Learning Step Title:\*\*\s+(.+?)(?:\n\*\*|\n\n|$)",
                section,
                re.IGNORECASE,
            )
            title = title_match.group(1).strip() if title_match else f"Step {step_id}"

            concepts_text = ""
            concepts_match = re.search(
                r"\*\*Concepts Introduced:\*\*(.+?)(?:\*\*Narrative|$)",
                section,
                re.DOTALL | re.IGNORECASE,
            )
            if concepts_match:
                concepts_raw = concepts_match.group(1).strip()
                concepts_lines = [
                    line.strip().lstrip("-•").strip()
                    for line in concepts_raw.split("\n")
                    if line.strip()
                ]
                concepts_text = "\n".join(f"- {line}" for line in concepts_lines)

            narrative_match = re.search(
                r"\*\*Narrative Moment:\*\*(.+?)(?=\n####|\n\n---|\n---|$)",
                section,
                re.DOTALL | re.IGNORECASE,
            )
            narrative = narrative_match.group(1).strip() if narrative_match else ""

            steps.append(
                {
                    "step_id": step_id,
                    "title": title,
                    "concepts": concepts_text,
                    "narrative": narrative,
                    "raw": section,
                    "full_text": f"""Learning Step {step_id}
Learning Step Title: {title}
Concepts Introduced: {concepts_text}
Narrative Moment: {narrative}""",
                }
            )

        if not steps:
            logger.warning(
                "Could not parse learning steps, using full text as single step"
            )
            steps.append(
                {
                    "step_id": "LS1",
                    "title": "All Steps",
                    "concepts": "",
                    "narrative": raw_text,
                    "raw": raw_text,
                    "full_text": raw_text,
                }
            )

        logger.info(f"Parsed {len(steps)} learning steps")
        return steps

    def _generate_single_step_scenes(
        self,
        step: Dict[str, Any],
        prev_step: Optional[Dict[str, Any]],
        next_step: Optional[Dict[str, Any]],
        selected_story: Dict[str, Any],
        concept_inventory: Dict[str, Any],
        chapter_name: str,
        state,
        step_index: int,
    ) -> Dict[str, Any]:
        """
        Generate scenes for a single learning step.

        Args:
            step: Current learning step
            prev_step: Previous learning step
            next_step: Next learning step
            selected_story: Selected story backbone
            concept_inventory: Concept inventory
            chapter_name: Chapter name
            state: State manager
            step_index: Index of current step

        Returns:
            Scenes for this learning step
        """
        prompt_template = self.prompt_loader.get_prompt(3)

        concept_text = json.dumps(concept_inventory, indent=2)

        subject_raw = state.get("subject", "science").lower()
        chapter_num = state.get("chapter_number", "11")
        chapter_title_raw = state.get("chapter_title", "")

        subject_normalized = self.prompt_loader.normalize_subject(subject_raw)
        chapter_id = self.prompt_loader.slugify(chapter_title_raw)

        prev_step_text = prev_step.get("full_text", "") if prev_step else ""
        current_step_text = step.get("full_text", "")
        next_step_text = next_step.get("full_text", "") if next_step else ""

        characters = self._extract_characters_from_story(selected_story)

        prompt = self.prompt_loader.inject_values(
            prompt_template,
            chapter=chapter_name,
            subject_id=subject_normalized,
            chapter_id=chapter_id,
            chapter_title=chapter_name,
            concept_inventory=concept_text,
            story_backbone=selected_story.get("core_premise", ""),
            story_title=selected_story.get("title", ""),
            core_premise=selected_story.get("core_premise", ""),
            story_theme=selected_story.get("theme", "educational"),
            story_tone=selected_story.get("tone", "engaging"),
            story_goal=selected_story.get(
                "story_goal", "Explain concepts through storytelling"
            ),
            previous_learning_step=prev_step_text,
            current_learning_step=current_step_text,
            next_learning_step=next_step_text,
            char1_id=characters[0].get("id", "Character1")
            if len(characters) > 0
            else "Character1",
            char1_role=characters[0].get("role", "protagonist")
            if len(characters) > 0
            else "protagonist",
            char1_appearance=characters[0].get("appearance", "Character appearance")
            if len(characters) > 0
            else "Character appearance",
            char1_traits=characters[0].get("traits", '[" trait1", "trait2"]')
            if len(characters) > 0
            else '["trait1", "trait2"]',
            char2_id=characters[1].get("id", "Character2")
            if len(characters) > 1
            else "Character2",
            char2_role=characters[1].get("role", "mentor")
            if len(characters) > 1
            else "mentor",
            char2_appearance=characters[1].get("appearance", "Character appearance")
            if len(characters) > 1
            else "Character appearance",
            char2_traits=characters[1].get("traits", '["trait1", "trait2"]')
            if len(characters) > 1
            else '["trait1", "trait2"]',
        )

        if "[(" in prompt or "(Insert" in prompt:
            logger.warning(
                f"Possible unresolved placeholders in prompt for {step.get('step_id')}"
            )

        step_suffix = step.get("step_id", f"LS{step_index + 1}")
        state.save_prompt(3, prompt, suffix=step_suffix)
        state.save_prompt(3, prompt, suffix=f"{step_suffix}_final")

        try:
            response = self.llm_client.call(prompt)
            state.save_raw_response(
                3, response, suffix=step.get("step_id", f"LS{step_index + 1}")
            )

            parsed = self._extract_json(response)
            return parsed

        except Exception as e:
            logger.error(f"Scene generation failed for {step.get('step_id')}: {e}")
            return {"error": str(e), "step_id": step.get("step_id")}

    def _format_step(self, step: Optional[Dict[str, Any]]) -> str:
        """Format a learning step for prompt injection."""
        if not step:
            return ""
        return f"""
Learning Step: {step.get("step_id", "")}
Title: {step.get("title", "")}
Concepts: {step.get("concepts", "")}
Narrative: {step.get("narrative", "")}
""".strip()

    def _extract_characters_from_story(
        self, selected_story: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Extract characters from the story backbone."""
        import re

        characters = []
        core_premise = selected_story.get("core_premise", "")

        name_patterns = [
            r"\b([A-Z][a-z]+)\b",
            r"named\s+([A-Z][a-z]+)",
            r"called\s+([A-Z][a-z]+)",
            r"([A-Z][a-z]+)\s+and\s+([A-Z][a-z]+)",
        ]

        found_names = set()
        for pattern in name_patterns:
            matches = re.findall(pattern, core_premise)
            for match in matches:
                if isinstance(match, tuple):
                    found_names.update(match)
                else:
                    common_words = {
                        "The",
                        "A",
                        "An",
                        "In",
                        "On",
                        "At",
                        "For",
                        "With",
                        "This",
                        "That",
                        "They",
                        "She",
                        "He",
                        "It",
                    }
                    if match not in common_words and len(match) > 2:
                        found_names.add(match)

        names_list = list(found_names)[:4]

        for i, name in enumerate(names_list):
            role = "protagonist" if i == 0 else ("mentor" if i == 1 else "character")
            characters.append(
                {
                    "id": name,
                    "role": role,
                    "appearance": f"Character {name}",
                    "traits": '["curious", "eager"]',
                }
            )

        if len(characters) < 2:
            characters.append(
                {
                    "id": "Guide",
                    "role": "mentor",
                    "appearance": "An elderly guide",
                    "traits": '["wise", "patient"]',
                }
            )

        return characters[:2]

    def _extract_json(self, response: str) -> Dict[str, Any]:
        """Extract JSON from LLM response."""
        import re

        response = response.strip()

        json_match = re.search(r"\{[\s\S]*\}", response)
        if json_match:
            try:
                return json.loads(json_match.group())
            except json.JSONDecodeError:
                pass

        try:
            return json.loads(response)
        except json.JSONDecodeError:
            return {"raw_text": response}

    def _combine_step_outputs(
        self,
        step_outputs: List[Dict[str, Any]],
        selected_story: Dict[str, Any],
        concept_inventory: Dict[str, Any],
        state,
    ) -> Dict[str, Any]:
        """Combine all step outputs into final scenes structure."""
        subject = state.get("subject", "science").lower()
        chapter_num = state.get("chapter_number", "11")

        all_learning_steps = []
        for step_output in step_outputs:
            if "learning_steps" in step_output:
                all_learning_steps.extend(step_output["learning_steps"])
            elif "error" not in step_output:
                all_learning_steps.append(step_output)

        return {
            "academic_context": {
                "subject_id": subject,
                "chapter_id": f"{subject}_chapter_{chapter_num}",
                "title": state.get_chapter_name(),
                "board": "cbse",
                "grade": 10,
            },
            "story_backbone": {
                "title": selected_story.get("title", ""),
                "core_premise": selected_story.get("core_premise", ""),
                "theme": selected_story.get("theme", "educational"),
                "tone": selected_story.get("tone", "engaging"),
                "story_goal": selected_story.get("story_goal", ""),
            },
            "learning_objectives": {
                "difficulty": "beginner",
                "learning_mode": "conceptual_story_based",
            },
            "learning_steps": all_learning_steps,
        }


def create_scene_generator_agent() -> SceneGeneratorAgent:
    """
    Factory function to create scene generator agent.

    Returns:
        SceneGeneratorAgent instance
    """
    return SceneGeneratorAgent()
