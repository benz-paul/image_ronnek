"""
Image Prompt Agent module for generating image prompts from scenes.
"""

import json
from typing import Dict, Any, List

from core.logger import logger
from core.llm_client import create_llm_client
from core.prompt_loader import get_prompt_loader
from core.state_manager import get_state_manager


class ImagePromptAgent:
    """Agent for generating image prompts from scenes."""

    def __init__(self):
        """Initialize image prompt agent."""
        self.llm_client = create_llm_client()
        self.prompt_loader = get_prompt_loader()

    def run(self) -> Dict[str, Any]:
        """
        Run image prompt generation for all scenes.

        Returns:
            Image prompts data

        Raises:
            RuntimeError: If image prompt generation fails
        """
        logger.section("Prompt 4 - Image Prompt Generation")

        state = get_state_manager().get_current()
        if not state:
            raise RuntimeError("No chapter state found")

        scenes_full_path = state.json_dir / "scenes_full.json"

        if not scenes_full_path.exists():
            raise RuntimeError("scenes_full.json not found")

        with open(scenes_full_path, "r", encoding="utf-8") as f:
            scenes_data = json.load(f)

        all_scenes = self._extract_scenes(scenes_data)

        if not all_scenes:
            logger.warning("No scenes found to generate image prompts")
            return {"image_prompts": []}

        logger.info(f"Generating image prompts for {len(all_scenes)} scenes")

        image_prompts = []

        for scene in all_scenes:
            scene_id = scene.get("scene_id", "unknown")

            logger.info(f"Generating prompt for {scene_id}")

            prompt = self._create_image_prompt(scene)

            try:
                response = self.llm_client.call(prompt)

                image_prompts.append(
                    {"scene_id": scene_id, "prompt": response, "raw_response": response}
                )

            except Exception as e:
                logger.error(f"Image prompt generation failed for {scene_id}: {e}")
                image_prompts.append(
                    {"scene_id": scene_id, "prompt": None, "error": str(e)}
                )

        result = {
            "image_prompts": image_prompts,
            "total_scenes": len(all_scenes),
            "successful": len([p for p in image_prompts if p.get("prompt")]),
        }

        state.save_json("image_prompts.json", result)

        state.update("image_prompts", result)

        logger.info(
            f"Generated {result['successful']}/{result['total_scenes']} image prompts"
        )

        return result

    def _extract_scenes(self, scenes_data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Extract all scenes from the scenes data.

        Args:
            scenes_data: Full scenes data

        Returns:
            List of all scenes
        """
        all_scenes = []

        learning_steps = scenes_data.get("learning_steps", [])

        for step_data in learning_steps:
            step_scenes = step_data.get("scenes", {})

            learning_obj = step_scenes.get("learning_objectives", {})
            story_bb = step_scenes.get("story_backbone", {})
            chars = step_scenes.get("character_registry", [])
            steps = learning_obj.get("learning_steps", [])

            for step in steps:
                scenes_list = step.get("scenes", [])

                for scene in scenes_list:
                    scene_goal = scene.get("scene_goal", "")
                    concept_focus = scene.get("concept_focus", "")
                    dialogues = scene.get("dialogue", [])
                    narrative = scene.get("narrative", {})
                    visual = scene.get("visual_setting", {})

                    dialogue_texts = []
                    for d in dialogues:
                        speaker = d.get("speaker", "")
                        text = d.get("text", "")
                        dialogue_texts.append(f"{speaker}: {text}")

                    all_scenes.append(
                        {
                            "scene_id": scene.get("scene_id", ""),
                            "scene_goal": scene_goal,
                            "concept_focus": concept_focus,
                            "dialogues": dialogue_texts,
                            "narrative": narrative.get("screenplay", ""),
                            "visual_setting": visual,
                            "characters": chars,
                            "story_backbone": story_bb,
                        }
                    )

        return all_scenes

    def _create_image_prompt(self, scene: Dict[str, Any]) -> str:
        """
        Create image prompt for a scene.

        Args:
            scene: Scene data

        Returns:
            Formatted prompt for image generation
        """
        prompt_template = self.prompt_loader.get_prompt(4)

        scene_goal = scene.get("scene_goal", "")
        concept_focus = scene.get("concept_focus", "")
        dialogues = scene.get("dialogues", [])

        dialogues_text = "\n".join(dialogues) if dialogues else "No dialogues"

        narrative = scene.get("narrative", "")

        scene_json = {
            "scene_id": scene.get("scene_id", ""),
            "scene_goal": scene_goal,
            "Teaching Narrative": narrative,
            "Concept Focus": concept_focus,
            "Character dialogues": dialogues_text,
        }

        prompt = self.prompt_loader.inject_values(
            prompt_template,
            scene_id=scene.get("scene_id", ""),
            scene_goal=scene_goal,
            teaching_narrative=narrative,
            concept_focus=concept_focus,
            character_dialogues=dialogues_text,
            json_generated=json.dumps(scene_json, indent=2),
        )

        return prompt


def create_image_prompt_agent() -> ImagePromptAgent:
    """
    Factory function to create image prompt agent.

    Returns:
        ImagePromptAgent instance
    """
    return ImagePromptAgent()
