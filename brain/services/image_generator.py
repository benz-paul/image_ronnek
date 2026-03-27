"""
Image Generator Service - Generates images from scene data using various image models.

Supports:
- OpenAI GPT-image-1.5
- fal.ai Flux 2 Pro
- fal.ai Juggernaut Pro
- Dialogue overlay mode for speech bubbles

Fallback: if primary fal.ai model returns 5xx errors, automatically retries
with fal-ai/flux-2-pro (most reliable model).
"""

import json
import os
import base64
import requests
from pathlib import Path
from typing import Any, Dict, Optional

from utils.pipeline_logger import debug

from openai import OpenAI

from brain.pipeline.state.pipeline_state import PipelineState
from utils.model_output_manager import (
    get_model_output_dir,
    create_run_folder,
    get_images_dir,
    get_current_run_folder,
)
from utils.image_repository import store_image_repository


IMAGE_SIZE = "1536x1024"

# Global visual style anchor — injected as a suffix into every image prompt
# to keep consistent art style across all scenes and models.
# Derived from the "cinematic semi-realistic anime" aesthetic of the target output style.
GLOBAL_VISUAL_STYLE = (
    "\n\nGLOBAL STYLE LOCK (apply to EVERY scene, no exceptions):\n"
    "- Art style: cinematic semi-realistic anime — anime-styled characters in a photorealistic environment\n"
    "- Lighting: golden hour backlighting, warm amber rim light, soft shadows\n"
    "- Color palette: warm amber and soft teal contrast, rich but not oversaturated\n"
    "- Camera: cinematic depth of field, film still quality, varied shot composition\n"
    "- Character rendering: clean anime linework, expressive faces, consistent proportions\n"
    "- Background: detailed photorealistic school/outdoor environment\n"
    "- DO NOT vary the art style between scenes — every scene must feel like the same movie\n"
    "- Overall mood: cinematic, engaging, suitable for high school students"
)

# Per-model configs for fal.ai — each model has its own endpoint and accepted parameters.
# Flux 2 Pro is zero-config (no inference_steps/guidance_scale accepted).
# Juggernaut Pro (/pro endpoint) accepts tuning params. Both use enum strings for image_size.
# fallback_endpoint: used if the primary endpoint returns persistent 5xx errors.
FAL_MODEL_CONFIGS = {
    "fal-flux2pro": {
        "endpoint": "fal-ai/flux-2-pro",
        "fallback_endpoint": None,  # already the most reliable — no fallback needed
        "payload": {
            "image_size": "landscape_16_9",
            "output_format": "png",
        },
    },
    "fal-juggernaut": {
        "endpoint": "rundiffusion-fal/juggernaut-flux/pro",
        "fallback_endpoint": "fal-ai/flux-2-pro",  # fallback to Flux 2 Pro if 500s persist
        "payload": {
            "image_size": "landscape_16_9",
            "num_inference_steps": 28,
            "guidance_scale": 3.5,
            "output_format": "png",
            "negative_prompt": "blurry, low quality, distorted faces, extra limbs, extra fingers, deformed hands, text, watermark, signature, jpeg artifacts, ugly, duplicate, morbid",
        },
    },
}


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

        debug(f"[MODEL] Image model selected: {model}")
        debug(f"[MODE] Image rendering: {image_mode}")

        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        if self._pipeline_run_folder is None:
            self._ensure_run_folder()

    def _get_fal_endpoint(self, model: str) -> str:
        """Get the primary fal.ai endpoint for the given model."""
        config = FAL_MODEL_CONFIGS.get(model, FAL_MODEL_CONFIGS["fal-flux2pro"])
        return config["endpoint"]

    def _get_fal_fallback_endpoint(self, model: str) -> Optional[str]:
        """Get the fallback endpoint for a model (None if no fallback configured)."""
        config = FAL_MODEL_CONFIGS.get(model, {})
        return config.get("fallback_endpoint")

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

        # Legacy fallback
        run_folder = self._get_model_run_folder()
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

        debug(f"[DEBUG] OpenAI response: {response}")

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
        """Generate image using fal.ai API with async polling and fallback model."""
        import time

        headers = {
            "Authorization": f"Key {self.fal_key}",
            "Content-Type": "application/json",
        }

        # Append global style anchor to every prompt for visual consistency
        styled_prompt = prompt + GLOBAL_VISUAL_STYLE

        # Each model gets its own validated payload from FAL_MODEL_CONFIGS
        config  = FAL_MODEL_CONFIGS.get(self.model, FAL_MODEL_CONFIGS["fal-flux2pro"])
        payload = {"prompt": styled_prompt, **config["payload"]}

        debug(f"[FAL] Model: {self.model}, Endpoint: {self.fal_endpoint}, Prompt length: {len(styled_prompt)}")

        # Submit with retry logic — if primary endpoint keeps returning 5xx,
        # fall back to the configured fallback_endpoint (e.g. flux-2-pro)
        active_endpoint = self.fal_endpoint
        fallback_endpoint = self._get_fal_fallback_endpoint(self.model)

        submit_error = None
        for submit_retry in range(3):
            try:
                response = requests.post(
                    f"https://queue.fal.run/{active_endpoint}",
                    headers=headers,
                    json=payload,
                    timeout=120,
                )
                if response.status_code < 500:
                    submit_error = None
                    break
                submit_error = response.status_code
                debug(f"[FAL RETRY] Submit got {submit_error}, retry {submit_retry + 1}/3")
                time.sleep(2 ** submit_retry)
            except Exception as e:
                debug(f"[FAL RETRY] Submit exception: {e}, retry {submit_retry + 1}/3")
                time.sleep(2 ** submit_retry)
                continue

        # If primary endpoint failed and a fallback is configured, try it once
        if submit_error and fallback_endpoint and fallback_endpoint != active_endpoint:
            print(f"[FAL FALLBACK] Primary {active_endpoint} failed ({submit_error}), trying {fallback_endpoint}")
            fallback_config  = FAL_MODEL_CONFIGS.get("fal-flux2pro", {})
            fallback_payload = {"prompt": styled_prompt, **fallback_config.get("payload", {})}
            try:
                response = requests.post(
                    f"https://queue.fal.run/{fallback_endpoint}",
                    headers=headers,
                    json=fallback_payload,
                    timeout=120,
                )
                if response.status_code < 500:
                    active_endpoint = fallback_endpoint
                    submit_error    = None
                    print(f"[FAL FALLBACK] Using {fallback_endpoint} for this request")
                else:
                    print(f"[FAL FALLBACK] Fallback also failed ({response.status_code})")
            except Exception as e:
                print(f"[FAL FALLBACK] Fallback exception: {e}")

        if submit_error:
            print(f"[FAL ERROR] Submit returned {submit_error} after 3 retries (no working fallback)")
            return None

        response.raise_for_status()
        result = response.json()

        debug(f"[DEBUG] fal.ai initial response: {result}")

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

            # Status poll with retry for 5xx errors
            poll_error = None
            for poll_retry in range(3):
                try:
                    status_response = requests.get(status_url, headers=headers)
                    if status_response.status_code < 500:
                        poll_error = None
                        break
                    poll_error = status_response.status_code
                    debug(f"[FAL RETRY] Status poll got {poll_error}, retry {poll_retry + 1}/3")
                    time.sleep(2 ** poll_retry)
                except Exception as e:
                    debug(f"[FAL RETRY] Status poll exception: {e}, retry {poll_retry + 1}/3")
                    time.sleep(2 ** poll_retry)
                    continue

            if poll_error:
                print(f"[FAL ERROR] Status poll returned {poll_error} after 3 retries")
                return None

            status_response.raise_for_status()
            status_result = status_response.json()

            status = status_result.get("status")
            debug(f"[FAL STATUS] {status} (attempt {attempt}/{max_attempts})")

            if status == "COMPLETED":
                # Fetch the result
                if response_url:
                    final_response = requests.get(response_url, headers=headers)
                    final_response.raise_for_status()
                    final_result = final_response.json()

                    debug(f"[DEBUG] fal.ai final response: {final_result}")

                    # Check for error in response body
                    if final_result.get("error"):
                        print(f"[FAL ERROR] Model returned error: {final_result['error']}")
                        return None

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
    ) -> Optional[str]:
        """
        Generate an image from a text prompt.

        Args:
            prompt: Image generation prompt text
            learning_step_id: Learning step ID (e.g. 'LS1'). If not provided,
                              defaults to 'LS1'.
            scene_id: Scene ID (e.g. 'S1' or 'LS1_S1'). If not provided,
                      a timestamp-based ID is generated.

        Returns:
            Path to the saved image, or None if generation failed.
        """
        import time
        import uuid

        if scene_id is None:
            scene_id = f"gen_{int(time.time())}_{uuid.uuid4().hex[:8]}"
        if learning_step_id is None:
            learning_step_id = "LS1"

        filepath = self._get_image_path(learning_step_id, scene_id)

        # Prompt validation - skip if too short (indicates empty/plan-data fallback)
        prompt_len = len(prompt.strip()) if prompt else 0
        if prompt_len < 30:
            print(f"[IMAGE SKIP] {scene_id}: prompt too short ({prompt_len} chars), skipping to avoid API errors")
            debug(f"[IMAGE SKIP] {scene_id}: prompt was: {prompt[:100] if prompt else '(empty)'}")
            return None

        try:
            debug(f"[IMAGE PROMPT] {scene_id}: {prompt[:200]}")
            if self.use_fal:
                image_data = self._generate_fal_image(prompt)
            else:
                image_data = self._generate_openai_image(prompt)

            if not image_data:
                print(f"[IMAGE FAIL] No image data returned for {scene_id}. Check FAL_KEY/API key and endpoint.")
                return None

            with open(filepath, "wb") as f:
                f.write(image_data)

            return str(filepath)

        except Exception as e:
            print(f"[IMAGE ERROR] {scene_id}: {e}")
            return None

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
        debug(f"[IMAGE PROMPT MODE] {self.image_mode}")

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

        # Dialogue-in mode: AI renders speech bubbles with dialogue text
        prompt = f"""Create a cinematic illustration of characters in active conversation with speech bubbles:

Scene Goal: {scene_goal}
Concept: {concept_focus}
Mood: {emotional_tone}

Setting: {environment}
Atmosphere: {atmosphere}

Story: {screenplay}

Camera: {camera_suggestion}

Character direction:
- Characters should appear to be in active dialogue — open mouths, hand gestures, eye contact
- Facial expressions must convey the emotional tone: curiosity, confusion, excitement, realization
- Body language should be dynamic, not static poses
- If the concept involves numbers or sequences, show them physically in the environment (chalk on ground, numbers on whiteboard, tiles on a path)
- If the concept involves a formula, show components as physical objects characters interact with

Requirements:
- Cinematic composition with strong character expressions
- Clean detailed background appropriate to the setting
- Suitable for high school students"""

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

            # Copy to image repository
            full_scene_id = f"{learning_step_id}_{scene_id}"
            repository_path = store_image_repository(
                image_path=str(filepath),
                prompt=image_prompt,
                scene_data=scene_data,
                scene_id=full_scene_id,
            )

            return {
                "scene_id": scene_id,
                "learning_step_id": learning_step_id,
                "image_prompt": image_prompt,
                "image_path": str(filepath),
                "repository_path": repository_path,
                "full_scene_data": scene_data,
            }

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
