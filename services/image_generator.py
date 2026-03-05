"""
Image Generator Service - Generates images from scene data.

This service uses the LLM to generate image prompts (text descriptions)
that can be used with image generation models like DALL-E, Midjourney, etc.
"""

import json
import os
from pathlib import Path
from typing import Any, Dict, Optional

from langchain_openai import ChatOpenAI

from state.pipeline_state import PipelineState


class ImageGeneratorService:
    """
    Service for generating images from scene data.
    
    Since we're using GPT-4o-mini (text-based), this service:
    1. Takes scene data from learning step JSON
    2. Generates a detailed image prompt using Prompt 4
    3. Saves the generated prompts (for integration with image generation APIs)
    """
    
    def __init__(
        self,
        model: str = "gpt-4o-mini",
        temperature: float = 0.7,
        output_dir: str = "outputs/images"
    ):
        """
        Initialize the Image Generator Service.
        
        Args:
            model: LLM model to use
            temperature: Sampling temperature
            output_dir: Directory to save generated images/prompts
        """
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY environment variable not set")
        
        self.llm = ChatOpenAI(
            model=model,
            temperature=temperature,
            max_retries=3
        )
        
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Load Prompt 4 template
        prompt_path = Path(__file__).parent.parent / "prompts" / "prompt4.txt"
        if prompt_path.exists():
            with open(prompt_path, "r", encoding="utf-8") as f:
                self.prompt4_template = f.read()
        else:
            self.prompt4_template = ""
    
    def generate_image_prompt(
        self,
        scene_data: Dict[str, Any],
        chapter_info: Dict[str, Any]
    ) -> str:
        """
        Generate an image prompt from scene data.
        
        Args:
            scene_data: Scene information from learning step JSON
            chapter_info: Chapter context information
            
        Returns:
            Generated image prompt text
        """
        # Extract scene information
        scene_id = scene_data.get("scene_id", "unknown")
        scene_goal = scene_data.get("scene_goal", "")
        concept_focus = scene_data.get("concept_focus", "")
        emotional_tone = scene_data.get("emotional_tone", "")
        
        # Get visual settings
        visual_setting = scene_data.get("visual_setting", {})
        environment = visual_setting.get("environment", "")
        atmosphere = visual_setting.get("atmosphere", "")
        
        # Get narrative
        narrative = scene_data.get("narrative", {})
        screenplay = narrative.get("screenplay", "")
        camera_suggestion = narrative.get("camera_suggestion", "")
        
        # Get dialogues
        dialogues = scene_data.get("dialogue", [])
        dialogue_text = "\n".join([
            f"{d.get('speaker', 'Character')}: {d.get('text', '')}"
            for d in dialogues
        ])
        
        # Build the image generation prompt
        image_prompt = f"""
Create a visual scene for an educational comic/animation with the following details:

Scene ID: {scene_id}
Scene Goal: {scene_goal}
Concept Focus: {concept_focus}
Emotional Tone: {emotional_tone}

Setting:
- Environment: {environment}
- Atmosphere: {atmosphere}

Narrative: {screenplay}

Camera Direction: {camera_suggestion}

Characters and Dialogue:
{dialogue_text}

Please provide a detailed image generation prompt that:
1. Describes the visual composition of the scene
2. Includes character descriptions and positions
3. Specifies the mood and atmosphere
4. Is suitable for generation by AI image models (DALL-E, Midjourney, Stable Diffusion)
"""
        
        return image_prompt
    
    def generate_image(
        self,
        scene_data: Dict[str, Any],
        state: PipelineState,
        learning_step_id: str = "LS1"
    ) -> Dict[str, Any]:
        """
        Generate an image for a scene.
        
        This method:
        1. Generates an image prompt using Prompt 4 logic
        2. Returns the prompt (for use with external image generation APIs)
        
        Args:
            scene_data: Scene data from learning step JSON
            state: Current pipeline state
            learning_step_id: ID of the learning step
            
        Returns:
            Dictionary with image generation details:
            {
                "scene_id": str,
                "image_prompt": str,
                "image_path": str (path where image would be saved)
            }
        """
        scene_id = scene_data.get("scene_id", "S1")
        
        # Generate the image prompt
        image_prompt = self.generate_image_prompt(
            scene_data=scene_data,
            chapter_info={
                "chapter_name": state.user_inputs.chapter_name,
                "subject": state.user_inputs.subject,
                "class": state.user_inputs.class_level
            }
        )
        
        # Generate actual image using LLM (or would call external API)
        # For now, we'll save the prompt and simulate image generation
        response = self.llm.invoke(
            f"Generate a concise image generation prompt (max 500 words) for an AI image generator based on this scene description:\n\n{image_prompt}"
        )
        
        final_prompt = response.content if hasattr(response, 'content') else str(response)
        
        # Create filename
        filename = f"{learning_step_id}_{scene_id}.txt"
        filepath = self.output_dir / filename
        
        # Save the image prompt
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(final_prompt)
        
        return {
            "scene_id": scene_id,
            "learning_step_id": learning_step_id,
            "image_prompt": final_prompt,
            "image_path": str(filepath),
            "full_scene_data": scene_data
        }
    
    def generate_images_for_learning_step(
        self,
        learning_step_data: Dict[str, Any],
        state: PipelineState,
        learning_step_index: int
    ) -> list[Dict[str, Any]]:
        """
        Generate images for all scenes in a learning step.
        
        Args:
            learning_step_data: Learning step JSON data
            state: Current pipeline state
            learning_step_index: Index of the learning step
            
        Returns:
            List of generated image results
        """
        scenes = learning_step_data.get("scenes", [])
        learning_step_id = f"LS{learning_step_index + 1}"
        
        results = []
        for scene in scenes:
            result = self.generate_image(
                scene_data=scene,
                state=state,
                learning_step_id=learning_step_id
            )
            results.append(result)
        
        return results
    
    def save_image_prompts(self, results: list[Dict[str, Any]], run_folder: str) -> None:
        """
        Save all generated image prompts to a JSON file.
        
        Args:
            results: List of image generation results
            run_folder: Run folder path
        """
        output_path = Path(run_folder) / "image_prompts.json"
        
        # Convert to JSON-serializable format
        serializable_results = []
        for result in results:
            serializable_results.append({
                "scene_id": result.get("scene_id"),
                "learning_step_id": result.get("learning_step_id"),
                "image_prompt": result.get("image_prompt"),
                "image_path": result.get("image_path")
            })
        
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(serializable_results, f, indent=2, ensure_ascii=False)


def create_image_generator() -> ImageGeneratorService:
    """Factory function to create ImageGeneratorService."""
    return ImageGeneratorService()
