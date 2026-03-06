"""
Image Prompt Agent module for generating image prompts from scenes.
"""

import json
from typing import Dict, Any, List

from brain.prompt_engine.core.logger import logger
from brain.prompt_engine.core.prompt_loader import get_prompt_loader, render_prompt
from brain.prompt_engine.core.state_manager import get_state_manager


class ImagePromptAgent:
    """Agent for generating image prompts from scenes."""

    def __init__(self):
        """Initialize image prompt agent."""
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
            ls_id = scene.get("learning_step_id", "LSX")

            logger.info(f"Generating prompt for {scene_id}")

            prompt = self._create_image_prompt(scene, state)

            image_prompts.append(
                {"learning_step_id": ls_id, "scene_id": scene_id, "prompt": prompt}
            )

        result = {
            "image_prompts": image_prompts,
            "total_scenes": len(all_scenes),
            "successful": len(image_prompts),
        }

        state.save_json("image_prompts.json", result)
        self._save_to_image_prompts_dir(state, result, all_scenes)

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

        story_bb = scenes_data.get("story_backbone", {})
        chars = scenes_data.get("character_registry", [])
        learning_steps = scenes_data.get("learning_steps", [])

        for step_data in learning_steps:
            step_id = step_data.get("learning_step_id", "LSX")
            scenes_list = step_data.get("scenes", [])

            if isinstance(scenes_list, list):
                for scene in scenes_list:
                    scene_id = scene.get("scene_id", "unknown")
                    scene_goal = scene.get("scene_goal", "")
                    concept_focus = scene.get("concept_focus", "")
                    dialogues = scene.get("dialogue", [])
                    narrative = scene.get("narrative", {})
                    visual = scene.get("visual_setting", {})

                    dialogue_texts = []
                    for d in dialogues:
                        if isinstance(d, dict):
                            speaker = d.get("speaker", "")
                            text = d.get("text", "")
                            dialogue_texts.append(f"{speaker}: {text}")
                        else:
                            dialogue_texts.append(str(d))

                    all_scenes.append(
                        {
                            "learning_step_id": step_id,
                            "scene_id": scene_id,
                            "scene_goal": scene_goal,
                            "concept_focus": concept_focus,
                            "dialogues": dialogue_texts,
                            "narrative": narrative.get("screenplay", "")
                            if isinstance(narrative, dict)
                            else "",
                            "visual_setting": visual,
                            "characters": chars,
                            "story_backbone": story_bb,
                        }
                    )

        return all_scenes

    def _create_image_prompt(self, scene: Dict[str, Any], state) -> str:
        """
        Create image prompt for a scene based on image_mode.

        Args:
            scene: Scene data
            state: State manager instance

        Returns:
            Formatted prompt for image generation
        """
        image_mode = getattr(state, "image_mode", "dialogue")

        print(f"[IMAGE PROMPT MODE] {image_mode}")

        scene_goal = scene.get("scene_goal", "")
        concept_focus = scene.get("concept_focus", "")
        dialogues = scene.get("dialogues", [])
        narrative = scene.get("narrative", "")

        dialogues_text = (
            "\n".join([f"- {d}" for d in dialogues]) if dialogues else "None"
        )

        visual_setting = scene.get("visual_setting", {})
        environment = visual_setting.get("environment", "")
        atmosphere = visual_setting.get("atmosphere", "")
        emotional_tone = visual_setting.get("emotional_tone", "")

        if image_mode == "overlay":
            # Overlay mode: explicitly exclude text, leave space for dialogue
            prompt = f"""Create an educational comic/illustration scene for later dialogue overlay.

Scene Goal: {scene_goal}
Concept: {concept_focus}
Mood: {emotional_tone}

Setting: {environment}
Atmosphere: {atmosphere}

Story: {narrative}

Important rules for overlay preparation:
- Do NOT include speech bubbles
- Do NOT include written text
- Do NOT render dialogue text inside the image
- Keep upper corners and lower corners visually clear for dialogue overlay
- Leave clean visual space around characters suitable for later dialogue overlay
- Focus on environment, character positions, and expressions
- Characters should have expressive poses and facial expressions that convey the story
- Background should be clean and not cluttered

Requirements:
- Educational comic style illustration
- Clean background appropriate to the setting
- Suitable for CBSE Grade 10 students
- Style: clean educational comic illustration, classroom teaching scene, clear board diagrams"""
        else:
            # Dialogue rendered mode: include dialogue for AI to render in image
            prompt = f"""Create an educational comic/illustration scene:

Scene Goal: {scene_goal}
Concept: {concept_focus}
Mood: {emotional_tone}

Setting: {environment}
Atmosphere: {atmosphere}

Story: {narrative}

Dialogue lines:
{dialogues_text}

Requirements:
- Educational comic style
- Include speech bubbles with the dialogue lines above
- Clear character expressions showing emotions
- Clean background appropriate to the setting
- Text in images should be in English
- Suitable for CBSE Grade 10 students
- Style: clean educational comic illustration, classroom teaching scene, clear board diagrams, readable visual layout
- clean readable English text, correct mathematical notation, no distorted characters"""

        scene_json = {
            "scene_id": scene.get("scene_id", ""),
            "scene_goal": scene_goal,
            "Teaching Narrative": narrative,
            "Concept Focus": concept_focus,
            "Character dialogues": dialogues_text,
            "image_mode": image_mode,
        }

        prompt = render_prompt(prompt, state)

        return prompt

    def _save_to_image_prompts_dir(
        self, state, result: Dict[str, Any], all_scenes: List[Dict[str, Any]]
    ) -> None:
        """
        Save image prompts to the image_prompts directory with proper folder structure.

        Args:
            state: State manager instance
            result: Image prompts result data
            all_scenes: List of all scenes with metadata
        """
        import json
        from pathlib import Path

        image_prompts_dir = state.image_prompts_dir

        filepath = image_prompts_dir / "image_prompts.json"
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)

        logger.debug(f"Saved image prompts to {filepath}")

        ls_folders = {}
        for img_prompt in result.get("image_prompts", []):
            scene_id = img_prompt.get("scene_id", "unknown")
            ls_id = img_prompt.get("learning_step_id", "LSX")
            prompt_text = img_prompt.get("prompt", "")

            if ls_id not in ls_folders:
                ls_folders[ls_id] = {"scenes": [], "prompts": {}}

            for scene in all_scenes:
                if (
                    scene.get("scene_id") == scene_id
                    and scene.get("learning_step_id") == ls_id
                ):
                    ls_folders[ls_id]["scenes"].append(scene)
                    ls_folders[ls_id]["prompts"][scene_id] = prompt_text
                    break

        for ls_id, data in ls_folders.items():
            ls_folder = image_prompts_dir / ls_id
            ls_folder.mkdir(exist_ok=True)

            scenes_data = {"learning_step_id": ls_id, "scenes": data["scenes"]}
            with open(ls_folder / "scenes.json", "w", encoding="utf-8") as f:
                json.dump(scenes_data, f, indent=2, ensure_ascii=False)

            for scene_id, prompt_text in data["prompts"].items():
                # Save as scene_image_prompt.txt
                prompt_file = ls_folder / f"scene_image_prompt.txt"
                with open(prompt_file, "w", encoding="utf-8") as f:
                    f.write(prompt_text)
                logger.debug(f"Saved prompt for {scene_id} to {prompt_file}")


def create_image_prompt_agent() -> ImagePromptAgent:
    """
    Factory function to create image prompt agent.

    Returns:
        ImagePromptAgent instance
    """
    return ImagePromptAgent()
