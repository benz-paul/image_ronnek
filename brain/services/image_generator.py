"""
Image Generator Service - Generates images from scene data using various image models.

Supports:
- OpenAI GPT-image-1.5
- fal.ai Flux 2 Pro
- fal.ai Juggernaut
- Dialogue overlay mode for speech bubbles
"""

import json
import os
import base64
import requests
from pathlib import Path
from typing import Any, Dict, Optional

from openai import OpenAI

from brain.pipeline.state.pipeline_state import PipelineState
from brain.services.dialogue_overlay import overlay_dialogue_on_image
from utils.model_output_manager import (
    get_model_output_dir,
    create_run_folder,
    get_images_dir,
    get_current_run_folder,
)
from utils.image_repository import store_image_repository


IMAGE_SIZE = "1536x1024"


class ImageGeneratorService:
    """
    Service for generating images from scene data using various image models.
    Uses model-based output storage with quality subfolders.
    """

    def __init__(
        self,
        model: str = "gpt-image-1.5",
        temperature: float = 0.7,
        output_dir: str = "outputs/images",
        quality: str = "low",
        size: str = IMAGE_SIZE,
        background: str = "auto",
        image_mode: str = "dialogue",
        run_folder: Optional[str] = None,
    ):
        """
        Initialize the Image Generator Service.

        Args:
            model: Image generation model (default: gpt-image-1.5)
                   Other options: "fal-flux2pro", "fal-juggernaut"
            temperature: Sampling temperature
            output_dir: Legacy parameter (kept for compatibility)
            quality: Image quality setting (default: low)
            size: Image size - 1024x1024, 1536x1024, or 2048x2048 (default: 1536x1024)
            background: Background setting (default: auto)
            image_mode: "dialogue" (text inside image) or "overlay" (text overlay)
            run_folder: Path to the pipeline's current run folder. When provided,
                        ALL models (including Juggernaut) save images here under
                        images/LS{n}/ — prevents wrong-folder bugs.
        """
        self.model = model
        self.temperature = temperature
        self.quality = quality
        self.size = size
        self.background = background
        self.image_mode = image_mode
        self.use_fal = model.startswith("fal-")

        # Store the pipeline run folder so _get_image_path() always saves to the right place
        self._pipeline_run_folder: Optional[Path] = Path(run_folder) if run_folder else None

        if self.use_fal:
            fal_key = os.getenv("FAL_KEY") or os.getenv("FAL_API_KEY")
            if not fal_key:
                raise ValueError(
                    "Fal.ai API key not found. Set FAL_KEY or FAL_API_KEY in .env"
                )
            self.fal_key = fal_key
            self.fal_endpoint = self._get_fal_endpoint(model)
        else:
            api_key = os.getenv("OPENAI_API_KEY")
            if not api_key:
                raise ValueError("OPENAI_API_KEY environment variable not set")
            self.client = OpenAI(api_key=api_key)

        print(f"[MODEL] Image model selected: {model}")
        print(f"[MODE] Image rendering: {image_mode}")

        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        if self._pipeline_run_folder is None:
            self._ensure_run_folder()

    def _get_fal_endpoint(self, model: str) -> str:
        """Get the fal.ai endpoint for the given model."""
        endpoints = {
            "fal-flux2pro": "fal-ai/flux-pro/v2",
            "fal-juggernaut": "fal-ai/juggernaut-xl",
        }
        return endpoints.get(model, "fal-ai/flux-pro/v2")

    def _ensure_run_folder(self) -> None:
        """Ensure the run folder exists for this model."""
        model_dir = get_model_output_dir(self.model)
        existing_runs = []

        if model_dir.exists():
            for item in model_dir.iterdir():
                if item.is_dir() and item.name.startswith("run_"):
                    existing_runs.append(item.name)

        if not existing_runs:
            create_run_folder(self.model)

    def _get_model_run_folder(self) -> Path:
        """Get the current run folder for this model."""
        run_folder = get_current_run_folder(self.model)
        if run_folder is None:
            run_folder = create_run_folder(self.model)
        return run_folder

    def _get_image_path(self, learning_step_id: str, scene_id: str) -> Path:
        """
        Get the path to save an image with proper folder structure.

        When a pipeline run_folder is set (recommended), images are saved to:
          run_folder/images/{learning_step_id}/{scene_id}.png

        Legacy fallback (no run_folder): saves under the model run folder with
        mode/quality subfolders.

        Args:
            learning_step_id: Learning step ID (e.g., 'LS1')
            scene_id: Scene ID (e.g., 'S1' or 'LS1_S1')

        Returns:
            Path to save the image
        """
        if self._pipeline_run_folder is not None:
            # New canonical path: run_folder/images/LS1/LS1_S1.png
            ls_folder = self._pipeline_run_folder / "images" / learning_step_id
            ls_folder.mkdir(parents=True, exist_ok=True)
            # Normalise scene_id to avoid double prefix (LS1_LS1_S1)
            if scene_id.startswith(learning_step_id + "_"):
                filename = f"{scene_id}.png"
            else:
                filename = f"{learning_step_id}_{scene_id}.png"
            return ls_folder / filename

        # Legacy fallback — keep old behaviour for backwards compat
        run_folder = self._get_model_run_folder()
        if self.image_mode == "overlay":
            images_dir = run_folder / "images" / "overlay_dialogue" / self.quality
        else:
            images_dir = run_folder / "images" / "dialogue_rendered" / self.quality

        images_dir.mkdir(parents=True, exist_ok=True)
        ls_folder = images_dir / learning_step_id
        ls_folder.mkdir(exist_ok=True)
        return ls_folder / f"{scene_id}.png"

    def _generate_openai_image(self, prompt: str) -> Optional[bytes]:
        """Generate image using OpenAI API."""
        response = self.client.images.generate(
            model=self.model,
            prompt=prompt,
            size=self.size,
            quality=self.quality,
            background=self.background,
            n=1,
        )

        print(f"       DEBUG: OpenAI Response: {response}")

        if response.data:
            img_obj = response.data[0]
            if hasattr(img_obj, "url") and img_obj.url:
                img_response = requests.get(img_obj.url)
                img_response.raise_for_status()
                return img_response.content
            elif hasattr(img_obj, "b64_json") and img_obj.b64_json:
                return base64.b64decode(img_obj.b64_json)

        return None

    def _generate_fal_image(self, prompt: str) -> Optional[bytes]:
        """Generate image using fal.ai API with async polling."""
        import time

        headers = {
            "Authorization": f"Key {self.fal_key}",
            "Content-Type": "application/json",
        }

        payload = {
            "prompt": prompt,
            "image_size": {
                "width": 1536,
                "height": 1024,
            },
            "num_inference_steps": 30,
            "guidance_scale": 7.5,
        }

        # Submit the request
        response = requests.post(
            f"https://queue.fal.run/{self.fal_endpoint}",
            headers=headers,
            json=payload,
            timeout=120,
        )

        response.raise_for_status()
        result = response.json()

        print(f"       DEBUG: fal.ai initial response: {result}")

        # Check if we got an immediate result (synchronous)
        if "images" in result and result.get("images"):
            image_url = result["images"][0].get("url")
            if image_url:
                img_response = requests.get(image_url)
                img_response.raise_for_status()
                return img_response.content

        # Handle async queue response - poll for completion
        status_url = result.get("status_url")
        response_url = result.get("response_url")

        if not status_url:
            print(f"       WARNING: No status_url in fal.ai response")
            return None

        # Poll until completion
        max_attempts = 120  # 2 minutes max
        attempt = 0

        while attempt < max_attempts:
            time.sleep(2)
            attempt += 1

            status_response = requests.get(status_url, headers=headers)
            status_response.raise_for_status()
            status_result = status_response.json()

            status = status_result.get("status")
            print(f"[FAL STATUS] {status} (attempt {attempt}/{max_attempts})")

            if status == "COMPLETED":
                # Fetch the result
                if response_url:
                    final_response = requests.get(response_url, headers=headers)
                    final_response.raise_for_status()
                    final_result = final_response.json()

                    print(f"       DEBUG: fal.ai final response: {final_result}")

                    image_url = final_result.get("images", [{}])[0].get("url")
                    if image_url:
                        img_response = requests.get(image_url)
                        img_response.raise_for_status()
                        return img_response.content

                print(f"       WARNING: No image URL in completed response")
                return None

            elif status == "FAILED":
                error_msg = status_result.get("error", "Unknown error")
                print(f"[FAL ERROR] Image generation failed: {error_msg}")
                return None

            elif status in ("IN_QUEUE", "IN_PROGRESS"):
                # Continue polling
                continue

            else:
                print(f"       WARNING: Unknown fal.ai status: {status}")
                return None

        print(
            f"       WARNING: Fal.ai polling timed out after {max_attempts * 2} seconds"
        )
        return None

    def generate(
        self,
        prompt: str,
        learning_step_id: Optional[str] = None,
        scene_id: Optional[str] = None,
    ) -> str:
        """
        Generate an image from a text prompt.

        Args:
            prompt: Image generation prompt text
            learning_step_id: Learning step ID (e.g. 'LS1'). If not provided,
                              defaults to 'LS1'.
            scene_id: Scene ID (e.g. 'S1' or 'LS1_S1'). If not provided,
                      a timestamp-based ID is generated.

        Returns:
            Path to the generated image
        """
        import time
        import uuid

        if scene_id is None:
            scene_id = f"gen_{int(time.time())}_{uuid.uuid4().hex[:8]}"
        if learning_step_id is None:
            learning_step_id = "LS1"

        filepath = self._get_image_path(learning_step_id, scene_id)

        try:
            if self.use_fal:
                image_data = self._generate_fal_image(prompt)
            else:
                image_data = self._generate_openai_image(prompt)

            if not image_data:
                print(f"WARNING: No image data returned.")
                return str(filepath)

            with open(filepath, "wb") as f:
                f.write(image_data)

            print(f"Image saved: {filepath}")
            return str(filepath)

        except Exception as e:
            print(f"Error generating image: {e}")
            return str(filepath)

    def generate_image_prompt_text(self, scene_data: Dict[str, Any]) -> str:
        """
        Generate a text prompt from scene data for image generation.

        Supports two modes based on self.image_mode:
        - "dialogue_rendered": Include dialogue in prompt for AI to render
        - "overlay_dialogue": Exclude dialogue, leave space for overlay

        Args:
            scene_data: Scene information from learning step JSON

        Returns:
            Image generation prompt text
        """
        print(f"[IMAGE PROMPT MODE] {self.image_mode}")

        scene_id = scene_data.get("scene_id", "unknown")
        scene_goal = scene_data.get("scene_goal", "")
        concept_focus = scene_data.get("concept_focus", "")
        emotional_tone = scene_data.get("emotional_tone", "")

        visual_setting = scene_data.get("visual_setting", {})
        environment = visual_setting.get("environment", "")
        atmosphere = visual_setting.get("atmosphere", "")

        narrative = scene_data.get("narrative", {})
        screenplay = narrative.get("screenplay", "")
        camera_suggestion = narrative.get("camera_suggestion", "")

        dialogues = scene_data.get("dialogue", [])
        dialogue_text = "\n".join(
            [f"{d.get('speaker', 'Character')}: {d.get('text', '')}" for d in dialogues]
        )

        if self.image_mode == "overlay":
            # Overlay mode: explicitly exclude text, leave space for dialogue
            prompt = f"""Create an educational comic/illustration scene for later dialogue overlay.

Scene Goal: {scene_goal}
Concept: {concept_focus}
Mood: {emotional_tone}

Setting: {environment}
Atmosphere: {atmosphere}

Story: {screenplay}

Camera: {camera_suggestion}

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

Story: {screenplay}

Camera: {camera_suggestion}

Dialogue lines:
{dialogue_text}

Requirements:
- Educational comic style
- Include speech bubbles with the dialogue lines above
- Clear character expressions showing emotions
- Clean background appropriate to the setting
- Text in images should be in English
- Suitable for CBSE Grade 10 students
- Style: clean educational comic illustration, classroom teaching scene, clear board diagrams, readable visual layout
- clean readable English text, correct mathematical notation, no distorted characters"""

        return prompt

    def generate_image(
        self,
        scene_data: Dict[str, Any],
        state: PipelineState,
        learning_step_id: str = "LS1",
    ) -> Dict[str, Any]:
        """
        Generate an image for a scene using GPT-Image-1.5.

        Args:
            scene_data: Scene data from learning step JSON
            state: Current pipeline state
            learning_step_id: ID of the learning step

        Returns:
            Dictionary with image generation details:
            {
                "scene_id": str,
                "image_prompt": str,
                "image_path": str (path where image is saved)
            }
        """
        scene_id = scene_data.get("scene_id", "S1")

        image_prompt = self.generate_image_prompt_text(scene_data)

        filepath = self._get_image_path(learning_step_id, scene_id)

        try:
            if self.use_fal:
                image_data = self._generate_fal_image(image_prompt)
            else:
                image_data = self._generate_openai_image(image_prompt)

            if not image_data:
                print(f"       WARNING: No image data returned.")
                return {
                    "scene_id": scene_id,
                    "learning_step_id": learning_step_id,
                    "image_prompt": image_prompt,
                    "image_path": str(filepath),
                    "error": "No image data returned",
                    "full_scene_data": scene_data,
                }

            # Save the base image
            with open(filepath, "wb") as f:
                f.write(image_data)

            # Handle overlay if enabled
            overlay_applied = False
            overlay_path = None
            overlay_dialogue_path = None

            if self.image_mode == "overlay":
                try:
                    # Get overlay output path - save overlay images in same folder with _overlay suffix
                    # Path: run_folder/images/overlay_dialogue/<quality>/<learning_step_id>/

                    base_name = filepath.stem
                    overlay_path = filepath.parent / f"{base_name}_overlay.png"
                    overlay_dialogue_path = (
                        filepath.parent / f"{base_name}_dialogue.json"
                    )

                    # Apply dialogue overlay
                    overlay_result = overlay_dialogue_on_image(
                        base_image_path=str(filepath),
                        scene_json=scene_data,
                        output_path=str(overlay_path),
                    )

                    overlay_applied = True
                    print(f"[OVERLAY] Dialogue successfully rendered")
                    print(f"[OVERLAY] Saved: {overlay_path}")

                except RuntimeError as e:
                    print(f"[OVERLAY] Warning: Could not apply overlay: {e}")
                except Exception as e:
                    print(f"[OVERLAY] Error applying overlay: {e}")

            # Copy to image repository
            full_scene_id = f"{learning_step_id}_{scene_id}"
            repository_path = store_image_repository(
                image_path=str(filepath),
                prompt=image_prompt,
                scene_data=scene_data,
                scene_id=full_scene_id,
            )

            result = {
                "scene_id": scene_id,
                "learning_step_id": learning_step_id,
                "image_prompt": image_prompt,
                "image_path": str(filepath),
                "repository_path": repository_path,
                "full_scene_data": scene_data,
            }

            if overlay_applied and overlay_path:
                result["overlay_image_path"] = str(overlay_path)
                result["overlay_dialogue_path"] = str(overlay_dialogue_path)
                result["overlay_applied"] = True

            return result

        except Exception as e:
            print(f"Error generating image for {learning_step_id}_{scene_id}: {e}")
            return {
                "scene_id": scene_id,
                "learning_step_id": learning_step_id,
                "image_prompt": image_prompt,
                "image_path": str(filepath),
                "error": str(e),
                "full_scene_data": scene_data,
            }

    def generate_images_for_learning_step(
        self,
        learning_step_data: Dict[str, Any],
        state: PipelineState,
        learning_step_index: int,
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
                scene_data=scene, state=state, learning_step_id=learning_step_id
            )
            results.append(result)

        return results

    def save_image_prompts(
        self, results: list[Dict[str, Any]], run_folder: str
    ) -> None:
        """
        Save all generated image prompts to a JSON file.

        Args:
            results: List of image generation results
            run_folder: Run folder path
        """
        output_path = Path(run_folder) / "image_prompts.json"

        serializable_results = []
        for result in results:
            serializable_results.append(
                {
                    "scene_id": result.get("scene_id"),
                    "learning_step_id": result.get("learning_step_id"),
                    "image_prompt": result.get("image_prompt"),
                    "image_path": result.get("image_path"),
                }
            )

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(serializable_results, f, indent=2, ensure_ascii=False)


def create_image_generator() -> ImageGeneratorService:
    """Factory function to create ImageGeneratorService."""
    return ImageGeneratorService()
