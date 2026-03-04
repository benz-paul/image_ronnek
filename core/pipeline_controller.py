"""
Pipeline Controller module for orchestrating the storytelling pipeline.
"""

from typing import Optional, Dict, Any

from core.logger import logger
from core.state_manager import get_state_manager
from agents.pdf_agent import create_pdf_agent
from agents.concept_agent import create_concept_agent
from agents.backbone_agent import create_backbone_agent
from agents.learning_steps_agent import create_learning_steps_agent
from agents.scene_generator_agent import create_scene_generator_agent
from agents.image_prompt_agent import create_image_prompt_agent


class PipelineController:
    """Orchestrates the multi-step storytelling pipeline."""

    def __init__(self):
        """Initialize pipeline controller."""
        self.state_manager = get_state_manager()
        self.agents = {}

    def initialize_agents(self) -> None:
        """Initialize all agents."""
        self.agents = {
            "pdf": create_pdf_agent(),
            "concept": create_concept_agent(),
            "backbone": create_backbone_agent(),
            "learning_steps": create_learning_steps_agent(),
            "scene_generator": create_scene_generator_agent(),
            "image_prompt": create_image_prompt_agent(),
        }
        logger.info("All agents initialized")

    def run(
        self,
        class_level: str,
        subject: str,
        chapter_number: str,
        chapter_title: str,
        medium: str,
        generate_image_prompts: bool = False,
    ) -> Dict[str, Any]:
        """
        Run the complete pipeline.

        Args:
            class_level: Class level (e.g., "10")
            subject: Subject (e.g., "Physics")
            chapter_number: Chapter number
            chapter_title: Chapter title
            medium: Medium (English/Hindi)
            generate_image_prompts: Whether to generate image prompts

        Returns:
            Pipeline execution results

        Raises:
            RuntimeError: If pipeline execution fails
        """
        logger.section("Starting Pipeline")

        logger.info(
            f"Chapter: Class {class_level} {subject} Chapter {chapter_number} {chapter_title}"
        )
        logger.info(f"Medium: {medium}")

        self.state_manager.create_chapter(
            class_level=class_level,
            subject=subject,
            chapter_number=chapter_number,
            chapter_title=chapter_title,
            medium=medium,
        )

        self.initialize_agents()

        results = {
            "pdf": None,
            "concept_inventory": None,
            "story_backbone": None,
            "learning_steps": None,
            "scenes": None,
            "image_prompts": None,
        }

        try:
            results["pdf"] = self.agents["pdf"].run()

            results["concept_inventory"] = self.agents["concept"].run()

            results["story_backbone"] = self.agents["backbone"].run()

            results["learning_steps"] = self.agents["learning_steps"].run()

            results["scenes"] = self.agents["scene_generator"].run()

            if generate_image_prompts:
                results["image_prompts"] = self.agents["image_prompt"].run()

            logger.section("Pipeline Complete")
            current_state = self.state_manager.get_current()
            folder_name = (
                current_state.get_folder_name() if current_state else "unknown"
            )
            logger.info(f"Chapter run saved to: runs/{folder_name}")

            return results

        except Exception as e:
            logger.error(f"Pipeline execution failed: {e}", exc_info=True)
            current_state = self.state_manager.get_current()
            if current_state:
                logger.info(
                    f"Partial results saved to: runs/{current_state.get_folder_name()}"
                )
            raise

    def run_image_prompts_only(self) -> Dict[str, Any]:
        """
        Run only the image prompt generation step.

        Returns:
            Image prompts results

        Raises:
            RuntimeError: If image prompt generation fails
        """
        logger.section("Running Image Prompt Generation")

        if not self.agents:
            self.initialize_agents()

        return self.agents["image_prompt"].run()


def create_pipeline_controller() -> PipelineController:
    """
    Factory function to create pipeline controller.

    Returns:
        PipelineController instance
    """
    return PipelineController()
