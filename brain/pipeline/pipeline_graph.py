"""
LangGraph Pipeline - Main orchestration graph for the agentic pipeline.

This module defines the LangGraph workflow that:
- Manages state transitions
- Coordinates agents
- Handles loops for learning steps and scenes
- Integrates LangSmith tracing
"""

import os
import json
import re
import time
from pathlib import Path
from datetime import datetime
from typing import Any, Dict, List, Optional, Union

# ============================================================================
# DEBUG MODE CONFIGURATION
# ============================================================================
DEBUG_MODE = True
DEBUG_MAX_LS = 1        # Limit to 1 learning step per run (all scenes within it)
DEBUG_OUTPUT_DIR = "outputs/debug_run"
# ============================================================================

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI

# Import our custom modules
from brain.pipeline.state.pipeline_state import (
    PipelineState,
    create_initial_state,
    SceneSelection,
)
from brain.agents.flow_tracker_agent import FlowTrackerAgent, PipelineStage

from brain.services.audio_generator import AudioGeneratorService
from brain.services.image_generator import ImageGeneratorService
from brain.services.ppt_generator import PPTGeneratorService
from brain.services.prompt_builder import PromptBuilder
from utils.model_output_manager import (
    create_run_folder,
    get_current_run_folder,
    save_prompt,
    save_raw_output,
    save_parsed,
    save_scenes,
    save_image,
    save_ppt,
    save_summary,
    update_run_metadata,
    save_audio_manifest,
)
from utils.json_utils import safe_parse, safe_parse_with_retry
from utils.pipeline_logger import debug, log


# =============================================================================
# DEBUG CAPTURE HELPERS
# =============================================================================


def _ensure_debug_dir():
    """Create debug output directory if it doesn't exist."""
    if DEBUG_MODE:
        Path(DEBUG_OUTPUT_DIR).mkdir(parents=True, exist_ok=True)
        debug(f"[DEBUG] Debug output directory: {DEBUG_OUTPUT_DIR}")


def _save_debug_json(filename: str, data: Any) -> None:
    """Save data to debug JSON file."""
    if DEBUG_MODE:
        filepath = Path(DEBUG_OUTPUT_DIR) / filename
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, default=str)
        debug(f"[DEBUG] Saved: {filepath}")


def _capture_state(state: PipelineState, label: str) -> None:
    """Capture current state to debug file."""
    if DEBUG_MODE:
        state_dict = {
            "timestamp": datetime.now().isoformat(),
            "label": label,
            "learning_steps_list": state.learning_steps_list,
            "active_learning_steps": getattr(state, "active_learning_steps", []),
            "scenes": state.scenes,
            "scene_plans": state.scene_plans,
            "current_learning_step_index": state.current_learning_step_index,
            "current_scene_index": state.current_scene_index,
            "generate_images": state.generate_images,
            "generation_mode": state.generation_mode,
            "image_model": state.image_model,
            "run_folder": state.run_folder,
        }
        _save_debug_json(f"state_{label}.json", state_dict)


# Debug storage for image prompts
_image_debug_data = []


def _capture_image_prompt(
    ls_key: str, scene_idx: int, image_prompt: str, scene_data: dict = None
) -> None:
    """Capture image prompt during generation."""
    if DEBUG_MODE:
        _image_debug_data.append(
            {
                "timestamp": datetime.now().isoformat(),
                "learning_step": ls_key,
                "scene_index": scene_idx,
                "image_prompt": image_prompt,
                "scene_data": scene_data,
            }
        )


def _save_image_debug() -> None:
    """Save captured image prompts to file."""
    if DEBUG_MODE and _image_debug_data:
        _save_debug_json("image_prompts.json", _image_debug_data)
        debug(f"[DEBUG] Saved {len(_image_debug_data)} image prompts")


def _debug_print_state(label: str, state: PipelineState) -> None:
    """Print formatted debug state."""
    if DEBUG_MODE:
        debug(f"\n{'=' * 60}")
        debug(f"[DEBUG STATE] {label}")
        debug(f"{'=' * 60}")
        debug(f"  LS count: {len(state.learning_steps_list)}")
        debug(
            f"  LS IDs: {[ls.get('learning_step_id', f'LS{i}') for i, ls in enumerate(state.learning_steps_list)]}"
        )
        debug(f"  Scenes keys: {list(state.scenes.keys())}")
        debug(f"  Scene counts: {[(k, len(v)) for k, v in state.scenes.items()]}")
        debug(f"  Current LS index: {state.current_learning_step_index}")
        debug(f"  Current Scene index: {state.current_scene_index}")
        debug(f"  Generate images: {state.generate_images}")
        debug(f"  Generation mode: {state.generation_mode}")
        debug(f"  Image model: {state.image_model}")
        debug(f"{'=' * 60}\n")


# =============================================================================
# GLOBAL VALIDATION FUNCTIONS
# =============================================================================


def validate_prompt(prompt: str) -> None:
    """
    Validate that a prompt has no unreplaced placeholders.

    Detects ONLY real placeholders, ignoring:
    - JSON examples like { "key": "value" }
    - Known safe words: json, example, output, format, rules, etc.

    Args:
        prompt: The prompt string to validate

    Raises:
        ValueError: If unreplaced placeholders are detected
    """
    if not prompt:
        raise ValueError("Prompt is empty")

    # Known safe words to ignore (case-insensitive)
    safe_words = {
        "json",
        "example",
        "examples",
        "output",
        "format",
        "formats",
        "rules",
        "rule",
        "important",
        "constraint",
        "constraints",
        "input",
        "inputs",
        "goal",
        "goals",
        "context",
        "contexts",
        "title",
        "titles",
        "scene_id",
        "scene_ids",
        "phase",
        "phases",
        "chapter",
        "chapters",
        "class",
        "classes",
        "subject",
        "subjects",
        "medium",
        "media",
        "learning_step",
        "learning_steps",
        "character",
        "characters",
        "dialogue",
        "dialogues",
        "narrative",
        "screenplay",
        "concept",
        "concepts",
        "narrator",
        "voice",
        "audio",
        "text",
        "type",
        "brackets",
        "parentheses",
        "speaker",
    }

    # Pattern 1: [something] - square brackets
    square_bracket_pattern = r"\[([^\[\]]+)\]"
    square_matches = re.findall(square_bracket_pattern, prompt)

    # Pattern 2: {word} - curly braces with only word characters (no JSON)
    # This catches {chapter_name} but NOT { "key": "value" }
    curly_brace_pattern = r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}"
    curly_matches = re.findall(curly_brace_pattern, prompt)

    # Combine and filter
    all_matches = square_matches + curly_matches

    # Filter out safe words and very short matches
    actual_placeholders = []
    for match in all_matches:
        match_lower = match.strip().lower()

        # Skip if it's a safe word
        if match_lower in safe_words:
            continue
        # Skip if it's too short (likely part of other words)
        if len(match.strip()) <= 1:
            continue
        # Skip if it contains spaces (likely not a placeholder)
        if " " in match:
            continue
        actual_placeholders.append(match.strip())

    # Get unique placeholders
    unique_placeholders = list(set(actual_placeholders))

    if unique_placeholders:
        print("\n" + "!" * 60)
        print("WARNING: Unreplaced placeholders detected!")
        print(f"Found: {unique_placeholders}")
        print("!" * 60)
        # Don't raise error - just warn, let LLM try anyway
        # The validation is informational


def validate_scene_schema(scene: Dict[str, Any], index: int) -> bool:
    """
    Validate a single scene has required fields.

    Required fields:
    - scene_id or id
    - title or scene_goal or description

    Optional but expected:
    - dialogue
    - narrative

    Args:
        scene: The scene dictionary to validate
        index: Scene index for error messages

    Returns:
        True if valid, False otherwise
    """
    # Check for ID field (scene_id or id)
    has_id = "scene_id" in scene or "id" in scene

    # Check for title/description field
    has_content = (
        "title" in scene
        or "scene_goal" in scene
        or "description" in scene
        or "goal" in scene
    )

    if not has_id:
        print(f"    ⚠ Scene {index}: Missing scene_id/id")
        return False

    if not has_content:
        print(f"    ⚠ Scene {index}: Missing title/description/goal")
        return False

    return True


def validate_scenes_response(
    scenes_json: Dict[str, Any], ls_id: str, raw_response: str
) -> List[Dict[str, Any]]:
    """
    Validate that scenes were successfully generated with proper schema.

    Checks:
    1. Scenes exist (list not empty)
    2. Each scene is a dictionary
    3. Required fields present (scene_id, title/description)

    Args:
        scenes_json: Parsed JSON response from LLM
        ls_id: Learning step ID for logging
        raw_response: Raw LLM response for debugging

    Returns:
        List of validated scenes

    Raises:
        ValueError: If validation fails
    """
    # Try to extract scenes from different JSON structures
    scenes = scenes_json.get("scenes", [])

    # If scenes not at root, check inside learning_steps array
    if not scenes and "learning_steps" in scenes_json:
        learning_steps_arr = scenes_json.get("learning_steps", [])
        for ls in learning_steps_arr:
            ls_scenes = ls.get("scenes", [])
            if ls_scenes:
                scenes = ls_scenes
                break

    # If still no scenes, check scene_plan
    if not scenes and "scene_plan" in scenes_json:
        scenes = scenes_json.get("scene_plan", [])

    # VALIDATION 1: Check scenes exist
    if not scenes or len(scenes) == 0:
        print("\n" + "!" * 60)
        print("ERROR: Scene generation failed - no scenes returned!")
        print(f"Learning Step: {ls_id}")
        print("!" * 60)
        print("\nRaw LLM Response:")
        print("-" * 60)
        print(raw_response[:2000] if raw_response else "Empty response")
        print("-" * 60)
        print("\nParsed JSON keys:")
        print(list(scenes_json.keys()))
        print("!" * 60 + "\n")
        raise ValueError(
            f"Scene generation failed for {ls_id} - no scenes returned. "
            f"Pipeline execution stopped."
        )

    # VALIDATION 2: Check scenes is a list
    if not isinstance(scenes, list):
        print("\n" + "!" * 60)
        print("ERROR: Invalid scene structure - not a list!")
        print(f"Type received: {type(scenes)}")
        print("!" * 60)
        print("\nRaw LLM Response:")
        print("-" * 60)
        print(raw_response[:2000])
        print("-" * 60 + "\n")
        raise ValueError(
            f"Invalid scene structure for {ls_id} - scenes is not a list. "
            f"Pipeline execution stopped."
        )

    # VALIDATION 3: Check each scene has required fields
    valid_scenes = []
    invalid_count = 0

    debug(f"\n  Validating {len(scenes)} scenes...")

    for i, scene in enumerate(scenes):
        if not isinstance(scene, dict):
            debug(f"    ⚠ Scene {i + 1}: Not a dictionary, skipping")
            invalid_count += 1
            continue

        if validate_scene_schema(scene, i + 1):
            valid_scenes.append(scene)
        else:
            invalid_count += 1

    # If all scenes invalid, fail
    if not valid_scenes:
        print("\n" + "!" * 60)
        print("ERROR: Invalid scene structure - no valid scenes found!")
        print(f"Learning Step: {ls_id}")
        print("!" * 60)
        print("\nAll scenes missing required fields:")
        print("  Required: scene_id, title/description/goal")
        print("\nRaw LLM Response:")
        print("-" * 60)
        print(raw_response[:2000])
        print("-" * 60 + "\n")
        raise ValueError(
            f"Invalid scene structure for {ls_id} - all scenes missing required fields. "
            f"Pipeline execution stopped."
        )

    # Report validation results
    if invalid_count > 0:
        debug(f"  ⚠ {invalid_count} scenes had missing optional fields (acceptable)")

    debug(f"  ✓ Validated {len(valid_scenes)} scenes for {ls_id}")
    return valid_scenes


# Set up LangSmith if available
def setup_langsmith():
    """Configure LangSmith for tracing."""
    langsmith_api_key = os.getenv("LANGSMITH_API_KEY")
    langsmith_project = os.getenv("LANGSMITH_PROJECT", "storytelling-pipeline")

    if langsmith_api_key:
        os.environ["LANGSMITH_API_KEY"] = langsmith_api_key
        os.environ["LANGSMITH_PROJECT"] = langsmith_project
        os.environ["LANGSMITH_TRACING"] = "true"
        return True
    return False


class LLMService:
    """
    Service for executing LLM calls using DeepSeek V3.2 via OpenRouter API.
    Supports reasoning mode for enhanced output.
    """

    def __init__(self, model: str = "deepseek", temperature: float = 0.65):
        """
        Initialize LLM service.

        Args:
            model: Model name (currently only deepseek is supported)
            temperature: Sampling temperature
        """
        self.model = model
        self.default_temperature = temperature

        # Check API key
        api_key = os.getenv("OPENROUTER_API_KEY")
        if not api_key:
            raise ValueError(
                "OPENROUTER_API_KEY environment variable not set. "
                "Please set OPENROUTER_API_KEY in your .env file."
            )

        print(f"[MODEL] Using DeepSeek V3.2 via OpenRouter (reasoning enabled)")

    def invoke(
        self,
        prompt: str,
        system_message: Optional[str] = None,
        attachments: Optional[list] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Invoke the LLM with a prompt using OpenRouter DeepSeek V3.2.

        Args:
            prompt: User prompt
            system_message: Optional system message
            attachments: Optional list of file paths (PDFs, images) to attach
            temperature: Override default temperature for this call
            max_tokens: Override max tokens for this call

        Returns:
            Dict with "content" and "usage" keys
        """
        import requests
        import json

        api_key = os.getenv("OPENROUTER_API_KEY")
        if not api_key:
            raise ValueError("OPENROUTER_API_KEY not set")

        # Build messages
        messages = []

        if system_message:
            messages.append({"role": "system", "content": system_message})

        messages.append(
            {
                "role": "system",
                "content": "You must respond in valid JSON format. Always return JSON.",
            }
        )

        # Build user message with attachments
        user_content = prompt

        if attachments:
            for attachment_path in attachments:
                if Path(attachment_path).exists():
                    file_path = Path(attachment_path)

                    if file_path.suffix.lower() == ".pdf":
                        from pypdf import PdfReader

                        pdf_text = []
                        reader = PdfReader(attachment_path)
                        for page in reader.pages:
                            text = page.extract_text()
                            if text:
                                pdf_text.append(text)

                        full_text = "\n\n".join(pdf_text)
                        user_content += (
                            f"\n\n[PDF CONTENT FROM {file_path.name}]\n{full_text}"
                        )

        messages.append({"role": "user", "content": user_content})

        # Build payload
        temp = temperature if temperature is not None else self.default_temperature
        tokens = max_tokens if max_tokens is not None else 4096

        payload = {
            "model": "deepseek/deepseek-v3.2",
            "messages": messages,
            "temperature": temp,
            "max_tokens": tokens,
        }

        # Make request with retry logic for timeouts
        max_retries = 3
        response = None

        for attempt in range(max_retries):
            try:
                response = requests.post(
                    url="https://openrouter.ai/api/v1/chat/completions",
                    headers={
                        "Authorization": "Bearer " + api_key,
                        "Content-Type": "application/json",
                    },
                    json=payload,
                    timeout=120,
                )
                break
            except (
                requests.exceptions.Timeout,
                requests.exceptions.ChunkedEncodingError,
                requests.exceptions.ConnectionError,
            ) as e:
                if attempt < max_retries - 1:
                    print(
                        f"[RETRY] Network error (attempt {attempt + 1}/{max_retries}), retrying in 5s..."
                    )
                    time.sleep(5)
                    continue
                else:
                    print(f"[ERROR] Network error after {max_retries} attempts: {e}")
                    raise Exception(f"LLM request failed after {max_retries} attempts: {e}")

        # Handle errors
        if response.status_code != 200:
            print(response.text)
            raise Exception("LLM API failed")

        # Extract response
        response_json = response.json()

        # Extract usage for tracking
        usage = response_json.get("usage", {})
        prompt_tokens = usage.get("prompt_tokens", 0)
        completion_tokens = usage.get("completion_tokens", 0)
        total_tokens = usage.get("total_tokens", 0)

        # OpenRouter returns cost in USD
        cost = usage.get("cost", 0)

        debug(
            f"[TOKENS] prompt={prompt_tokens}, completion={completion_tokens}, total={total_tokens}, cost=${cost}"
        )

        content = response_json["choices"][0]["message"].get("content")

        # HANDLE EMPTY RESPONSE
        if not content:
            print("[WARNING] Empty content from LLM, retrying...")

            # Retry without reasoning
            retry_payload = {
                "model": "deepseek/deepseek-v3.2",
                "messages": messages,
                "temperature": temp,
                "max_tokens": tokens,
            }

            try:
                retry_resp = requests.post(
                    url="https://openrouter.ai/api/v1/chat/completions",
                    headers={
                        "Authorization": "Bearer " + api_key,
                        "Content-Type": "application/json",
                    },
                    json=retry_payload,
                    timeout=120,
                )
                if retry_resp.status_code == 200:
                    retry_json = retry_resp.json()
                    content = retry_json["choices"][0]["message"].get("content")
            except Exception:
                pass  # content stays None, fallback handles it below

            if not content:
                print("[FALLBACK] Using minimal fallback output")
                content = '{"concepts": ["Basic Concept"]}'

        debug(f"\n[LLM RAW RESPONSE]\n{response_json}")
        debug(f"\n[LLM CONTENT]\n{content[:500] if content else 'EMPTY'}")

        # Log to LangSmith if available
        try:
            from langsmith import get_current_run_tree

            run = get_current_run_tree()
            if run:
                run.metadata["tokens"] = total_tokens
                run.metadata["prompt_tokens"] = prompt_tokens
                run.metadata["completion_tokens"] = completion_tokens
                run.metadata["cost"] = cost
        except Exception:
            pass  # LangSmith not available

        # Return content and usage
        return {
            "content": content,
            "usage": {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": total_tokens,
                "cost": cost,
            },
        }


class PipelineGraph:
    """
    Main LangGraph pipeline for the storytelling pipeline.
    """

    def __init__(self):
        """Initialize the pipeline."""
        # Set up LangSmith
        setup_langsmith()

        # Initialize services
        self.llm_service = LLMService()
        self.flow_tracker = FlowTrackerAgent()
        self.image_generator = None  # Initialized in run()
        self.ppt_generator = PPTGeneratorService()
        self.prompt_builder = PromptBuilder()

        # Create the graph
        self.graph = self._create_graph()

    def _create_graph(self) -> StateGraph:
        """
        Create the LangGraph state graph.

        Returns:
            Compiled StateGraph
        """
        # Define the graph
        graph = StateGraph(PipelineState)

        # Add nodes - SIMPLIFIED LINEAR FLOW
        # FIX #6: _node_user_input removed from graph entirely.
        # main.py already asks all questions before pipeline.run() is called,
        # so adding it here would make the user answer the same questions twice.
        graph.add_node("initialize", self._node_initialize)
        graph.add_node("execute_prompt0", self._node_execute_prompt0)
        graph.add_node("execute_prompt1", self._node_execute_prompt1)
        graph.add_node("execute_prompt2", self._node_execute_prompt2)
        graph.add_node("execute_prompt3a", self._node_execute_prompt3a)
        graph.add_node("execute_prompt3b", self._node_execute_prompt3b)
        # FIX #16: _node_execute_prompt3 is NOT registered as a graph node because
        # no edge connects to it. It still exists as a helper method.
        graph.add_node("execute_prompt4", self._node_execute_prompt4)
        graph.add_node("build_audio_manifest", self._node_build_audio_manifest)
        graph.add_node("generate_ppt", self._node_generate_ppt)

        # Set entry point
        graph.set_entry_point("initialize")

        # SCENE GENERATION FLOW: initialize → p0 → p1 → p2 → 3A (planning) → 3B (generation) → loops
        graph.add_edge("initialize", "execute_prompt0")
        graph.add_edge("execute_prompt0", "execute_prompt1")
        graph.add_edge("execute_prompt1", "execute_prompt2")
        graph.add_edge("execute_prompt2", "execute_prompt3a")

        # Router for scene planning (3A) - always goes to 3B
        def router_prompt3a(state: PipelineState) -> str:
            """Router for prompt3a - go to prompt3b for scene generation."""
            return "execute_prompt3b"

        # Router for scene generation (3B) - loops through scenes
        def router_prompt3b(state: PipelineState) -> str:
            """Router for prompt3b - process all scenes for current LS, then next LS."""

            current_ls_idx = state.current_learning_step_index
            current_scene_idx = state.current_scene_index

            # Use actual learning_step_id
            if current_ls_idx < len(state.learning_steps_list):
                ls_key = state.learning_steps_list[current_ls_idx].get(
                    "learning_step_id", f"LS{current_ls_idx + 1}"
                )
            else:
                ls_key = f"LS{current_ls_idx + 1}"

            scene_plan = state.scene_plans.get(ls_key, [])
            total_scenes = len(scene_plan)

            # HARD STOP - bounds check BEFORE logging
            if total_scenes == 0:
                debug(f"[ROUTER] {ls_key} has no scenes planned → go to prompt4")
                return "execute_prompt4"

            # Guard: only log when index is in bounds
            if current_scene_idx < total_scenes:
                debug(f"[ROUTER] {ls_key} scene {current_scene_idx + 1}/{total_scenes}")

            # HARD STOP - scene index out of bounds means this LS is done
            if current_scene_idx >= total_scenes:
                debug(f"[ROUTER] All {total_scenes} scenes generated for {ls_key}")

                # LS1 MODE → STOP AFTER FIRST LS
                if state.generation_mode == "ls1":
                    return "execute_prompt4"

                # Move to next LS or end
                if current_ls_idx + 1 >= len(state.learning_steps_list):
                    return "execute_prompt4"
                else:
                    return "execute_prompt3a"

            # SINGLE SCENE MODE - fast testing
            # FIX #10: Do NOT mutate state inside a router - LangGraph discards it.
            # Index reset is handled via single_scene_done flag in _node_execute_prompt3b.
            if (
                state.test_mode
                and getattr(state, "scene_generation_scope", None) == "single"
            ):
                if current_scene_idx >= 1:
                    debug("[DEBUG] Single scene mode → END scene gen, go to prompt4")
                    return "execute_prompt4"
                else:
                    debug("[DEBUG] Single scene mode → generate first scene")
                    return "execute_prompt3b"

            # LOOP THROUGH SCENES (full mode)
            return "execute_prompt3b"

        graph.add_conditional_edges(
            "execute_prompt3a",
            router_prompt3a,
            {
                "execute_prompt3b": "execute_prompt3b",
                END: END,
            },
        )

        graph.add_conditional_edges(
            "execute_prompt3b",
            router_prompt3b,
            {
                "execute_prompt3b": "execute_prompt3b",
                "execute_prompt3a": "execute_prompt3a",
                "execute_prompt4": "execute_prompt4",
            },
        )

        def router_after_prompt4(state: PipelineState) -> str:
            """Pure router - decides whether to loop back to prompt4 or generate_ppt."""

            # No images → go directly to generate_ppt
            if not state.generate_images:
                debug("[ROUTER] Image generation disabled → generate_ppt")
                return "generate_ppt"

            # Check bounds
            ls_index = state.current_learning_step_index
            scene_index = state.current_scene_index

            if ls_index >= len(state.learning_steps_list):
                debug("[ROUTER] All learning steps processed → generate_ppt")
                return "generate_ppt"

            # Use actual learning_step_id
            if ls_index < len(state.learning_steps_list):
                ls_key = state.learning_steps_list[ls_index].get(
                    "learning_step_id", f"LS{ls_index + 1}"
                )
            else:
                ls_key = f"LS{ls_index + 1}"

            scene_plan = state.scene_plans.get(ls_key, [])
            current_ls = state.learning_steps_list[ls_index] if ls_index < len(state.learning_steps_list) else {}

            # Single-scene mode: cap to only generated scenes (not the full plan)
            single_done = getattr(state, "single_scene_done", False)
            if single_done:
                total_scenes = len(current_ls.get("scenes", []))
                debug(f"[DEBUG] Single-scene mode: limiting to {total_scenes} generated scene(s), not {len(scene_plan)} planned")
            else:
                total_scenes = len(scene_plan)

            # LS1-only mode → only process LS1 scenes
            if state.generation_mode == "ls1":
                if scene_index >= total_scenes:
                    debug("[ROUTER] LS1-only: all scenes done → generate_ppt")
                    return "generate_ppt"
                debug(f"[ROUTER] LS1-only: scene {scene_index + 1}/{total_scenes}")
                return "execute_prompt4"

            # Full mode - continue through all scenes and LS
            if scene_index < len(scene_plan):
                debug(f"[ROUTER] Scene {scene_index + 1}/{len(scene_plan)}")
                return "execute_prompt4"

            # Move to next LS
            next_ls = ls_index + 1
            if next_ls >= len(state.learning_steps_list):
                debug("[ROUTER] All LS complete → generate_ppt")
                return "generate_ppt"

            debug(f"[ROUTER] Moving to LS{next_ls + 1}")
            return "execute_prompt4"

        graph.add_conditional_edges(
            "execute_prompt4",
            router_after_prompt4,
            {
                "execute_prompt4": "execute_prompt4",
                "generate_ppt": "build_audio_manifest",
                END: END,
            },
        )

        # audio manifest → ppt → end
        graph.add_edge("build_audio_manifest", "generate_ppt")
        graph.add_edge("generate_ppt", END)

        # Compile with checkpointer
        checkpointer = MemorySaver()
        app = graph.compile(checkpointer=checkpointer)

        print("[PIPELINE] Compiled successfully")
        return app

    def _node_initialize(self, state: PipelineState) -> Dict[str, Any]:
        """
        Initialize node - set up run folder.

        FIX #7: Only ONE run folder is created here. The second create_run_folder()
        call that existed inside _node_initialize is removed; the folder created
        in run() is the authoritative one and is already in state when this node fires.

        Args:
            state: Current pipeline state

        Returns:
            State updates
        """
        # run_folder and model_run_folder are already set by run() before the graph
        # starts. Just propagate them so LangGraph persists the values.
        active_folder = state.model_run_folder or state.run_folder
        print(f"\n[INIT] Run folder: {active_folder}")

        return {
            "current_prompt_id": "prompt0",
            "run_folder": state.run_folder,
            "model_run_folder": state.model_run_folder,
        }

    def _node_execute_prompt0(self, state: PipelineState) -> Dict[str, Any]:
        """
        Execute Prompt 0 - Concept Inventory Extraction with global extraction.
        Uses 2-pass approach for comprehensive concept extraction.

        Args:
            state: Current pipeline state

        Returns:
            State updates
        """
        import json

        run_folder = Path(state.model_run_folder or state.run_folder)
        chapter_name = state.user_inputs.chapter_name

        # Get full chapter text from PDF
        full_text = ""
        if state.pdf_path and Path(state.pdf_path).exists():
            from pypdf import PdfReader

            reader = PdfReader(state.pdf_path)
            pages_text = []
            for page in reader.pages:
                text = page.extract_text()
                if text:
                    pages_text.append(text)
            full_text = "\n\n".join(pages_text)
            print(f"  Extracted {len(pages_text)} pages from PDF")

        if not full_text:
            raise ValueError("No chapter text available for concept extraction")

        debug(f"[DEBUG] Full text length: {len(full_text)}")

        # STEP 1 — First pass (extract concept titles only), retry once on bad response
        prompt1 = self.prompt_builder.get_prompt(
            "prompt0a",
            CHAPTER_TEXT=full_text[:35000],
        )
        print("  First pass: Full extraction...")
        concepts_pass1 = {"_error": "not_run"}
        for _attempt in range(2):
            result1 = self.llm_service.invoke(prompt1, max_tokens=3000, temperature=0.2)
            response1 = result1["content"]
            concepts_pass1 = safe_parse(response1, prompt_type="concepts")
            debug(f"[DEBUG] Prompt0 response length: {len(str(response1))}")
            if "_error" not in concepts_pass1 and "_invalid" not in concepts_pass1:
                break
            if _attempt == 0:
                print("  [RETRY] Pass 1 returned invalid content, retrying...")
        if "_error" in concepts_pass1 or "_invalid" in concepts_pass1:
            print("  [WARNING] Pass 1 failed — continuing with pass 2 full extraction")

        # STEP 2 — Second pass (gap detection)
        # If pass 1 failed, pass empty list so pass 2 does a full extraction
        concepts_list1 = concepts_pass1.get("concepts", []) if "_error" not in concepts_pass1 and "_invalid" not in concepts_pass1 else []
        prompt2 = self.prompt_builder.get_prompt(
            "prompt0b",
            EXISTING_CONCEPTS=json.dumps({"concepts": concepts_list1}),
        )
        print("  Second pass: Gap detection...")
        result2 = self.llm_service.invoke(prompt2, max_tokens=1000, temperature=0.2)
        response2 = result2["content"]
        concepts_pass2 = safe_parse(response2, prompt_type="concepts")

        # STEP 3 — Merge (both are now lists of concept titles)
        # concepts_list1 already set above (empty if pass 1 failed)
        concepts_list2 = concepts_pass2.get("concept_titles", []) or concepts_pass2.get("concepts", [])

        # Combine and deduplicate
        all_concepts = concepts_list1 + concepts_list2
        final_concepts = list(
            dict.fromkeys(all_concepts)
        )  # Preserve order, remove duplicates

        debug(f"[DEBUG] Total concepts: {len(final_concepts)}")

        state.prompt0_output = {"concepts": final_concepts}

        # STEP 4 — Save
        save_prompt(run_folder, 0, prompt1)
        save_raw_output(run_folder, 0, response1)
        save_parsed(run_folder, "concepts", state.prompt0_output)

        print(f"  ✓ Extracted {len(final_concepts)} concepts")
        print(f"  ✓ Saved to: parsed/concepts.json")

        return {
            "prompt0_output": {"concepts": final_concepts},
            "current_prompt_id": "prompt1",
        }

    def _node_execute_prompt1(self, state: PipelineState) -> Dict[str, Any]:
        """
        Execute Prompt 1 - Story Backbone Generation.

        Args:
            state: Current pipeline state

        Returns:
            State updates
        """
        import json

        run_folder = Path(state.model_run_folder or state.run_folder)

        chapter_name = state.user_inputs.chapter_name
        concepts = json.dumps(state.prompt0_output)

        prompt = self.prompt_builder.get_prompt(
            "prompt1",
            CHAPTER_NAME=chapter_name,
            CONCEPTS=concepts,
        )

        result = self.llm_service.invoke(prompt, temperature=0.7)
        response = result["content"]
        story = safe_parse(response, prompt_type="story")

        state.prompt1_output = story
        state.selected_story = story

        save_prompt(run_folder, 1, prompt)
        save_raw_output(run_folder, 1, response)
        save_parsed(run_folder, "story", story)

        print(f"  ✓ Saved parsed story to: parsed/story.json")

        return {
            "prompt1_output": story,
            "selected_story": story,
            "current_prompt_id": "prompt2",
        }

    def _node_execute_prompt2(self, state: PipelineState) -> Dict[str, Any]:
        """
        Execute Prompt 2 - Learning Steps Decomposition.

        Args:
            state: Current pipeline state

        Returns:
            State updates
        """
        import json

        run_folder = Path(state.model_run_folder or state.run_folder)

        story = json.dumps(state.prompt1_output)
        concepts = json.dumps(state.prompt0_output)

        prompt = self.prompt_builder.get_prompt(
            "prompt2",
            STORY_BACKBONE=story,
            CONCEPTS=concepts,
        )

        result = self.llm_service.invoke(prompt, temperature=0.4)
        response = result["content"]
        learning_steps = safe_parse(response, prompt_type="learning_steps")

        state.prompt2_output = learning_steps
        state.learning_steps_list = learning_steps.get("learning_steps", [])

        # FAIL FAST if learning steps extraction failed
        if len(state.learning_steps_list) == 0:
            if "_error" in learning_steps or "_invalid" in learning_steps:
                reason = learning_steps.get("_reason") or learning_steps.get("message") or "unknown error"
                raise Exception(f"Learning steps extraction failed: {reason}")
            raise Exception("Learning steps extraction returned empty list")

        save_prompt(run_folder, 2, prompt)
        save_raw_output(run_folder, 2, response)
        save_parsed(run_folder, "learning_steps", learning_steps)

        # LS1-only mode: filter to only first learning step
        learning_steps_list = learning_steps.get("learning_steps", [])
        if state.generation_mode == "ls1":
            learning_steps_list = learning_steps_list[:1]
            debug(f"[MODE] LS1-only mode: Processing only first learning step")
            debug(f"[MODE] Only LS1.json will be saved in learning_steps/")

        # UPDATE STATE - critical synchronization
        state.learning_steps_list = learning_steps_list
        state.active_learning_steps = learning_steps_list

        debug(f"[DEBUG] Total learning steps: {len(state.learning_steps_list)}")
        debug(
            f"[DEBUG] LS list: {[ls.get('learning_step_id', f'LS{i + 1}') for i, ls in enumerate(state.learning_steps_list)]}"
        )

        # Save individual learning step files
        learning_steps_dir = run_folder / "learning_steps"
        learning_steps_dir.mkdir(exist_ok=True)

        # Clear existing files in learning_steps/ to ensure clean state
        for existing_file in learning_steps_dir.glob("*.json"):
            existing_file.unlink()

        validated_learning_steps = []

        for i, ls in enumerate(learning_steps_list):
            ls_id = ls.get("learning_step_id", f"LS{i + 1}")

            # Robust key mapping with fallbacks
            concepts_introduced = ls.get("concepts_introduced")
            if concepts_introduced is None:
                concepts_introduced = ls.get("concepts_covered", [])
                if concepts_introduced != []:
                    debug(
                        f"[WARNING] Using fallback key: concepts_covered → concepts_introduced for {ls_id}"
                    )

            narrative_moment = ls.get("narrative_moment")
            if narrative_moment is None or narrative_moment == "":
                narrative_moment = ls.get("description", "")
                if narrative_moment != "":
                    debug(
                        f"[WARNING] Using fallback key: description → narrative_moment for {ls_id}"
                    )

            # Validate required fields
            if not concepts_introduced:
                debug(
                    f"[WARNING] Missing concepts_introduced for {ls_id}, using empty list"
                )
                concepts_introduced = []

            if not narrative_moment:
                debug(
                    f"[WARNING] Missing narrative_moment for {ls_id}, using placeholder"
                )
                narrative_moment = f"Learning step about {ls.get('title', ls_id)}"

            # Build validated learning step
            validated_ls = {
                "learning_step_id": ls_id,
                "title": ls.get("title", f"Learning Step {i + 1}"),
                "concepts_introduced": concepts_introduced
                if isinstance(concepts_introduced, list)
                else [],
                "narrative_moment": narrative_moment,
                "scenes": [],
            }
            validated_learning_steps.append(validated_ls)

            # Format: only this learning step's data
            ls_data = {
                "learning_step_id": ls_id,
                "title": validated_ls["title"],
                "concepts_introduced": validated_ls["concepts_introduced"],
                "narrative_moment": validated_ls["narrative_moment"],
            }

            ls_filename = f"{ls_id}.json"
            ls_filepath = learning_steps_dir / ls_filename
            with open(ls_filepath, "w", encoding="utf-8") as f:
                json.dump(ls_data, f, indent=2, ensure_ascii=False)

            debug(f"[LS STORAGE] Saved {ls_id} → learning_steps/{ls_filename}")

        print(f"  ✓ Saved parsed learning_steps to: parsed/learning_steps.json")
        print(
            f"  ✓ Saved {len(validated_learning_steps)} individual learning step files"
        )

        # DEBUG MODE: Limit to DEBUG_MAX_LS learning steps
        if DEBUG_MODE:
            _ensure_debug_dir()
            debug(f"[DEBUG] Limiting to {DEBUG_MAX_LS} learning step(s)")
            validated_learning_steps = validated_learning_steps[:DEBUG_MAX_LS]
            _save_debug_json(
                "learning_steps_after_prompt2.json", validated_learning_steps
            )
            _debug_print_state("After Prompt2 (LS Limited)", state)

        return {
            "prompt2_output": learning_steps,
            "learning_steps_list": validated_learning_steps,
            "active_learning_steps": validated_learning_steps,
            "current_prompt_id": "prompt3",
        }

    def _node_execute_prompt3a(self, state: PipelineState) -> Dict[str, Any]:
        """
        Execute Prompt 3A - Scene Planning.
        Generates a scene plan for the current learning step.

        Args:
            state: Current pipeline state

        Returns:
            State updates with scene plan
        """
        import json

        current_index = state.current_learning_step_index

        if not state.learning_steps_list:
            print("[PIPELINE ERROR] No learning steps generated from Prompt 2.")
            return {"learning_steps_list": state.learning_steps_list}

        debug(f"[DEBUG] Active LS count: {len(state.learning_steps_list)}")

        if current_index >= len(state.learning_steps_list):
            print(
                f"\n[PROMPT3A] Completed all {len(state.learning_steps_list)} learning steps"
            )
            return {
                "learning_steps_list": state.learning_steps_list,
                "current_learning_step_index": current_index,
            }

        learning_step = state.learning_steps_list[current_index]
        ls_id = learning_step.get("learning_step_id", f"LS{current_index + 1}")

        # Use actual learning_step_id as ls_key for consistency
        ls_key = ls_id

        print(f"\n{'=' * 60}")
        print(f"  [PLAN] Building scene plan for {ls_id} ({current_index + 1}/{len(state.learning_steps_list)})...")

        run_folder = Path(state.model_run_folder or state.run_folder)

        story_data = state.prompt1_output or {}
        story_context = {
            "title": story_data.get("title", ""),
            "core_premise": story_data.get("core_premise", ""),
            "characters": story_data.get("characters", []),
        }

        previous_step_last_scene = None
        if current_index > 0:
            prev_step = state.learning_steps_list[current_index - 1]
            if prev_step.get("scenes"):
                previous_step_last_scene = (
                    prev_step["scenes"][-1] if prev_step["scenes"] else None
                )

        prev_scene_str = (
            json.dumps(previous_step_last_scene)
            if previous_step_last_scene
            else "None (this is the first step)"
        )
        plan_prompt = self.prompt_builder.get_prompt(
            "prompt3a",
            STORY_TITLE=story_context.get("title", ""),
            STORY_PREMISE=story_context.get("core_premise", ""),
            CHARACTER_REGISTRY=json.dumps(story_context.get("characters", [])),
            PREVIOUS_STEP_LAST_SCENE=prev_scene_str,
            LS_ID=ls_id,
            LS_TITLE=learning_step.get("title", ""),
            LS_CONCEPTS=json.dumps(learning_step.get("concepts_introduced", [])),
            LS_NARRATIVE=learning_step.get("narrative_moment", ""),
        )
        # SKIP IF EXISTS - prevent re-planning
        if ls_key in state.scene_plans and len(state.scene_plans[ls_key]) > 0:
            debug(f"[DEBUG] Using existing scene plan for {ls_key}")
            scene_plan = state.scene_plans[ls_key]
        else:
            # Retry logic for scene planning
            max_retries = 3
            retry_count = 0
            scene_plan = []

            while retry_count < max_retries:
                result = self.llm_service.invoke(
                    plan_prompt, temperature=0.4, max_tokens=3000
                )
                response = result["content"]

                # Trust the parser, not string endings
                try:
                    parsed = safe_parse(response, prompt_type="scene_plan")

                    if "_error" in parsed or "_invalid" in parsed:
                        print(
                            f"[ERROR] Scene plan parse failed: {parsed.get('_reason', 'unknown')}"
                        )
                        retry_count += 1
                        continue

                    scene_plan = parsed.get("scene_plan", [])

                    # Minimum 8 scenes, more is okay
                    if len(scene_plan) < 8:
                        print(
                            f"[VALIDATION] Only {len(scene_plan)} scenes (need 8+). Retrying..."
                        )
                        retry_count += 1
                        continue

                    print(f"  [PLAN] {ls_key}: {len(scene_plan)} scenes planned")
                    break

                except Exception as e:
                    print(f"[WARNING] Failed to parse scene plan: {e}")
                    retry_count += 1
                    continue

            # If all retries failed, create minimal plan and continue
            if len(scene_plan) < 8:
                print(
                    f"[WARNING] Scene planning failed after {max_retries} retries for {ls_key}"
                )
                print(f"[WARNING] Creating minimal plan and continuing to next LS")
                scene_plan = [
                    {
                        "scene_id": f"S{i + 1}",
                        "phase": "MICRO_LEARN",
                        "summary": f"Scene {i + 1} - explanation",
                        "concept_focus": "core concept",
                    }
                    for i in range(10)
                ]

        state.scene_plans[ls_key] = scene_plan
        state.learning_steps_list[current_index]["scene_plan"] = scene_plan

        save_prompt(
            run_folder,
            3,
            f"[3A] Scene Plan for {ls_id}\n\n{plan_prompt}",
            ls_index=current_index,
        )

        print(f"  ✓ Scene plan saved for {ls_key} ({len(scene_plan)} scenes)")

        return {
            "learning_steps_list": state.learning_steps_list,
            "scene_plans": state.scene_plans,
            "current_scene_index": 0,  # Reset scene counter for this new LS
        }

    def _node_execute_prompt3b(self, state: PipelineState) -> Dict[str, Any]:
        """
        Execute Prompt 3B - Scene Generation.
        Generates individual scenes based on the scene plan.

        Args:
            state: Current pipeline state

        Returns:
            State updates with generated scenes
        """
        import json

        current_ls_index = state.current_learning_step_index
        current_scene_index = state.current_scene_index

        debug(f"[DEBUG] Active LS count: {len(state.learning_steps_list)}")

        if not state.learning_steps_list:
            print("[PIPELINE ERROR] No learning steps.")
            return {"learning_steps_list": state.learning_steps_list}

        if current_ls_index >= len(state.learning_steps_list):
            debug(f"[PROMPT3B] Completed all learning steps")
            return {
                "learning_steps_list": state.learning_steps_list,
                "current_learning_step_index": current_ls_index + 1,
            }

        learning_step = state.learning_steps_list[current_ls_index]
        ls_id = learning_step.get("learning_step_id", f"LS{current_ls_index + 1}")

        # Use actual learning_step_id for scene_plans lookup
        ls_key = ls_id
        scene_plan = state.scene_plans.get(ls_key, [])

        # Fallback: try index-based key if actual key not found
        if not scene_plan:
            index_key = f"LS{current_ls_index + 1}"
            scene_plan = state.scene_plans.get(index_key, [])
            if scene_plan:
                ls_key = index_key

        debug(f"[DEBUG] Scene plan count: {len(scene_plan)}, LS: {ls_id}")

        if not scene_plan:
            print(f"[ERROR] No scene plan for {ls_key} → skipping to next LS")
            return {
                "learning_steps_list": state.learning_steps_list,
                "current_learning_step_index": current_ls_index + 1,
                "current_scene_index": 0,
            }

        if current_scene_index >= len(scene_plan):
            debug(f"[PROMPT3B] All {len(scene_plan)} scenes completed for {ls_key}")
            return {
                "learning_steps_list": state.learning_steps_list,
                "current_learning_step_index": current_ls_index + 1,
                "current_scene_index": 0,
                "scenes": state.scenes,
            }

        current_plan = scene_plan[current_scene_index]
        scene_id = current_plan.get("scene_id", f"S{current_scene_index + 1}")

        # Print LS banner on first scene of each learning step
        if current_scene_index == 0:
            ls_title = learning_step.get("title", ls_key)
            print(f"\n{'═' * 56}")
            print(f"  [{ls_key}] {ls_title}")
            print(f"{'═' * 56}")
        print(f"  [SCENE] {scene_id} ({current_scene_index + 1}/{len(scene_plan)}) — {current_plan.get('phase', 'SCENE')}")

        run_folder = Path(state.model_run_folder or state.run_folder)

        story_data = state.prompt1_output or {}
        story_context = {
            "title": story_data.get("title", ""),
            "core_premise": story_data.get("core_premise", ""),
            "characters": story_data.get("characters", []),
        }

        existing_scenes = state.scenes.get(ls_key, [])
        previous_scene = existing_scenes[-1] if existing_scenes else None

        previous_step_last_scene = None
        if current_ls_index > 0:
            # FIX #15: Use actual learning_step_id not hardcoded f"LS{current_ls_index}"
            prev_ls = state.learning_steps_list[current_ls_index - 1]
            prev_ls_key = prev_ls.get(
                "learning_step_id", f"LS{current_ls_index}"
            )
            prev_scenes = state.scenes.get(prev_ls_key, [])
            if prev_scenes:
                previous_step_last_scene = prev_scenes[-1]

        scene_phase = current_plan.get("phase", "MICRO_LEARN")
        prev_scene_str = (
            json.dumps(previous_scene) if previous_scene else "This is the first scene."
        )
        story_summary_str = state.story_summary if state.story_summary else "No scenes generated yet."
        scene_prompt = self.prompt_builder.get_prompt(
            "prompt3b",
            SCENE_ID=scene_id,
            SCENE_PHASE=scene_phase,
            SCENE_SUMMARY=current_plan.get("summary", ""),
            CONCEPT_FOCUS=current_plan.get("concept_focus", ""),
            STORY_TITLE=story_context.get("title", ""),
            STORY_PREMISE=story_context.get("core_premise", ""),
            CHARACTER_REGISTRY=json.dumps(story_context.get("characters", [])),
            LS_ID=ls_id,
            LS_TITLE=learning_step.get("title", ""),
            LS_CONCEPTS=json.dumps(learning_step.get("concepts_introduced", [])),
            STORY_SUMMARY=story_summary_str,
            PREVIOUS_SCENE=prev_scene_str,
            TOTAL_SCENES=str(len(scene_plan)),
        )

        temp = 0.7 if current_plan.get("phase") == "HOOK" else 0.6

        result = self.llm_service.invoke(
            scene_prompt, temperature=temp, max_tokens=1500
        )
        response = result["content"]

        try:
            parsed = safe_parse(response, prompt_type="scene")
            scene = parsed if isinstance(parsed, dict) else parsed.get("scene", parsed)
            scene["scene_id"] = scene_id
            scene["phase"] = current_plan.get("phase", "MICRO_LEARN")
        except Exception as e:
            print(f"  [WARNING] Failed to parse scene {scene_id}: {e}")
            scene = {
                "scene_id": scene_id,
                "phase": current_plan.get("phase", "MICRO_LEARN"),
                "setting": "Generated scene",
                "characters": [],
                "action": "Scene generation failed",
                "dialogue": [],
                "learning_moment": "",
                "transition_hint": "",
                "narrator_audio_text": "",
                "character_dialogues": [],
            }

        if ls_key not in state.scenes:
            state.scenes[ls_key] = []
        state.scenes[ls_key].append(scene)

        state.learning_steps_list[current_ls_index]["scenes"] = state.scenes[ls_key]

        import os

        # Save to new per-LS subfolder: scenes/LS{n}/LS{n}_{scene_id}.json
        scenes_ls_dir = os.path.join(str(run_folder), "scenes", ls_key)
        os.makedirs(scenes_ls_dir, exist_ok=True)

        scene_filename = f"{ls_key}_{scene_id}.json"
        scene_path = os.path.join(scenes_ls_dir, scene_filename)
        with open(scene_path, "w", encoding="utf-8") as f:
            json.dump(scene, f, indent=2, ensure_ascii=False)

        debug(f"[SCENE GEN] {ls_key}_{scene_id} saved to scenes/{ls_key}/{scene_filename}")

        # STORY SUMMARY — append 1-sentence summary, keep last 5 for continuity injection
        narration = scene.get("narrator_audio_text", "") or scene.get("action", "")
        short_narration = narration[:120] + "..." if len(narration) > 120 else narration
        scene_summary_line = f"- {ls_key}_{scene_id} ({scene.get('phase', '')}): {short_narration}"
        existing_summaries = [s for s in state.story_summary.split("\n") if s.strip()]
        existing_summaries.append(scene_summary_line)
        state.story_summary = "\n".join(existing_summaries[-8:])

        next_scene_index = current_scene_index + 1

        # FIX #10: routers cannot mutate state — set flag here so prompt4 resets
        # indices to 0 when entering from single-scene mode.
        single_scene_mode = (
            state.test_mode
            and getattr(state, "scene_generation_scope", None) == "single"
        )
        single_scene_done = single_scene_mode and (next_scene_index == 1)

        return {
            "learning_steps_list": state.learning_steps_list,
            "scenes": state.scenes,
            "current_scene_index": next_scene_index,
            "single_scene_done": single_scene_done,
            "story_summary": state.story_summary,
        }

    def _node_execute_prompt3(self, state: PipelineState) -> Dict[str, Any]:
        """
        Execute Prompt 3 - Wrapper that calls 3A then 3B in sequence.
        Kept as a helper method for backward compatibility; NOT registered as a graph node.

        Args:
            state: Current pipeline state

        Returns:
            State updates
        """
        result_3a = self._node_execute_prompt3a(state)

        if "scene_plan" not in result_3a:
            return result_3a

        state.scene_plans = result_3a.get("scene_plans", {})
        state.current_scene_index = 0

        result_3b = self._node_execute_prompt3b(state)

        return result_3b

    def _node_execute_prompt4(self, state: PipelineState) -> Dict[str, Any]:
        """Pure node - generates ONE image per call. Router handles loop/termination."""
        import json

        debug(f"[DEBUG] Prompt4 entry: generate_images={state.generate_images}, ls={state.current_learning_step_index}, scene={state.current_scene_index}")

        # FIX #9: Do NOT force generate_images to True here. Respect the user's
        # choice that was set in run() and passed through state. The router already
        # short-circuits to generate_ppt when generate_images is False, so this
        # node is only reached when the user actually wants images.
        if not state.generate_images:
            debug("[DEBUG] generate_images=False → skipping image generation")
            return {"is_complete": True}

        # RECOVERY FIX: Inject scenes from state.scenes into state.learning_steps_list
        if state.scenes and not any(
            ls.get("scenes") for ls in state.learning_steps_list
        ):
            debug("[RECOVERY] Injecting scenes into learning_steps_list...")
            for i, ls in enumerate(state.learning_steps_list):
                # FIX #15: use actual learning_step_id instead of hardcoded index
                ls_key = ls.get("learning_step_id", f"LS{i + 1}")
                if ls_key in state.scenes:
                    ls["scenes"] = state.scenes[ls_key]
                    debug(f"[RECOVERY] Injected {len(state.scenes[ls_key])} scenes into {ls_key}")

        # FAIL FAST: Check learning_steps_list is not empty
        if not state.learning_steps_list:
            print("[ERROR] learning_steps_list is empty before image stage!")
            return {"skip_image_generation": True, "is_complete": True}

        # DEFENSIVE FILTER: Only process LS with scenes
        valid_ls = []
        for ls in state.learning_steps_list:
            scenes = ls.get("scenes", [])
            ls_id = ls.get("learning_step_id", "UNKNOWN")
            if scenes:
                valid_ls.append(ls)
            else:
                print(f"[WARNING] Skipping LS without scenes: {ls_id}")

        if valid_ls:
            state.learning_steps_list = valid_ls
            debug(f"[DEBUG] Filtered to {len(valid_ls)} LS with scenes")
        else:
            print("[ERROR] No LS with scenes found!")
            return {"skip_image_generation": True, "is_complete": True}

        run_folder = Path(state.model_run_folder or state.run_folder)

        # FIX #10: honor single_scene_done flag set by _node_execute_prompt3b.
        # Routers cannot mutate state, so the flag signals that image gen
        # should start from index 0 even though the counter says otherwise.
        if getattr(state, "single_scene_done", False):
            ls_index = 0
            scene_index = 0
            debug("[DEBUG] single_scene_done=True → resetting ls_index=0, scene_index=0")
        else:
            ls_index = state.current_learning_step_index
            scene_index = state.current_scene_index

        # Use actual learning_step_id, not hardcoded index
        if ls_index < len(state.learning_steps_list):
            ls_key = state.learning_steps_list[ls_index].get(
                "learning_step_id", f"LS{ls_index + 1}"
            )
        else:
            ls_key = f"LS{ls_index + 1}"

        scene_plan = state.scene_plans.get(ls_key, [])

        # FIX #12: TRANSITION FIX: when all scenes have just been generated,
        # scene_index lands at len(scene_plan) (e.g. 10 for a 10-scene plan).
        # This is not an error - it means scene-generation just finished and
        # image generation should start from scene 0.
        if scene_plan and scene_index >= len(scene_plan):
            debug(f"[DEBUG] scene_index {scene_index} >= plan length {len(scene_plan)} - resetting to 0")
            scene_index = 0
            ls_index = 0

        # HARD SAFETY GUARD - only bail if there is genuinely no plan
        if not scene_plan:
            print(f"[ERROR] No scene plan found for {ls_key} - skipping safely")
            return {"skip_image_generation": True, "is_complete": True}

        # Get current learning step with scenes injected
        if ls_index >= len(state.learning_steps_list):
            print(
                f"[ERROR] ls_index {ls_index} out of bounds (max: {len(state.learning_steps_list) - 1})"
            )
            return {"skip_image_generation": True, "is_complete": True}

        current_ls = state.learning_steps_list[ls_index]
        parsed_scenes = current_ls.get("scenes", [])

        # Fallback: Use scenes from state.scenes if not in learning step
        if not parsed_scenes:
            # Try multiple key formats (LS1, LS_1, etc.)
            for key_format in [ls_key, f"LS{ls_index + 1}", f"LS_{ls_index + 1}"]:
                if key_format in state.scenes:
                    print(f"[RECOVERY] Using scenes from state.scenes[{key_format}]")
                    parsed_scenes = state.scenes[key_format]
                    state.learning_steps_list[ls_index]["scenes"] = parsed_scenes
                    break

        scene_plan_entry = scene_plan[scene_index]
        scene_id = scene_plan_entry.get(
            "scene_id", f"LS{ls_index + 1}_S{scene_index + 1}"
        )

        scene = None
        for s in parsed_scenes:
            if s.get("scene_id") == scene_id:
                scene = s
                break

        if not scene:
            print(f"[WARNING] No parsed scene for {scene_id}, using plan data")
            scene = scene_plan_entry

        debug(f"[PROMPT4] Processing scene {scene_index + 1}/{len(scene_plan)} for {ls_key}")

        story_data = state.prompt1_output or {}
        characters = story_data.get("characters", [])

        character_map = {}
        for char in characters:
            name = char.get("name", "")
            visual_desc = char.get("visual_description", "")
            if name:
                character_map[name.lower()] = visual_desc

        scene_characters = scene.get("characters", [])
        character_details = []
        for char_name in scene_characters:
            if isinstance(char_name, str):
                char_lower = char_name.lower()
                if char_lower in character_map:
                    character_details.append(
                        f"{char_name}: {character_map[char_lower]}"
                    )
                else:
                    character_details.append(char_name)

        scene_action = scene.get("action", scene.get("narrative", ""))
        scene_setting = scene.get("setting", "")
        scene_dialogue = scene.get("dialogue", [])
        scene_learning = scene.get("learning_moment", scene.get("concept_focus", ""))
        ls_concepts = current_ls.get("concepts_introduced", [])

        scene_data = {
            "scene_id": scene_id,
            "setting": scene_setting,
            "action": scene_action,
            "characters": character_details if character_details else scene_characters,
            "dialogue": scene_dialogue,
            "learning": scene_learning,
            "concepts": ls_concepts,
        }

        input_data = {
            "setting": scene_setting,
            "characters": character_details if character_details else scene_characters,
            "action": scene_action,
            "dialogue": scene_dialogue,
        }

        # Build dialogue lines for speech bubbles
        dialogue_lines = []
        for d in scene_dialogue:
            if isinstance(d, dict):
                speaker = d.get("speaker", "Character")
                text = d.get("text", "")
                dialogue_lines.append(f"{speaker}: {text}")
            elif isinstance(d, str):
                dialogue_lines.append(d)
        dialogue_text = "\n".join(dialogue_lines) if dialogue_lines else "(no dialogue)"

        # Build character anchor from story backbone — injected into every Prompt 4 call
        char_anchor_lines = []
        for char in characters:
            name = char.get("name", "")
            visual_desc = char.get("visual_description", "")
            if name and visual_desc:
                char_anchor_lines.append(f"  - {name}: {visual_desc}")
        char_anchor = (
            "\n\nCHARACTER LOCK — use EXACT same appearance in every scene:\n"
            + "\n".join(char_anchor_lines)
        ) if char_anchor_lines else ""

        dialogue_instruction = (
            f"DIALOGUE MODE - Include speech bubbles with EXACT text:\n"
            f"Use EXACT dialogue below in speech bubbles:\n{dialogue_text}\n\n"
            "Speech bubbles must be clearly readable with correct English text.\n"
            "Keep each bubble SHORT — match the exact text provided, no additions."
            + char_anchor
        )

        prompt = self.prompt_builder.get_prompt(
            "prompt4",
            SCENE_DATA=json.dumps(input_data, indent=2),
            DIALOGUE_INSTRUCTION=dialogue_instruction,
        )

        result = self.llm_service.invoke(prompt)
        response_content = result["content"].strip()

        parsed, attempts, success = safe_parse_with_retry(
            response_content, max_retries=2, prompt_type="prompt4"
        )

        if not success or "_fatal_error" in parsed:
            print(
                f"[FATAL] Scene generation failed for {scene_id} after {attempts} attempts"
            )
            print(
                f"[FATAL] Preview: {parsed.get('_raw_preview', response_content)[:200]}..."
            )
            raise Exception(f"Scene generation failed for {scene_id}")

        if "_error" in parsed or "_invalid" in parsed:
            print(
                f"[WARNING] Parse issue for {scene_id}: {parsed.get('_reason', 'unknown')}"
            )
            visual_prompt = response_content
        else:
            # FIX #11: LLM returns "visual_prompt" key, not "prompt".
            # Try "visual_prompt" first, then fall back to "prompt" for safety.
            visual_prompt = (
                parsed.get("visual_prompt") or parsed.get("prompt") or response_content
            )

        debug(f"[PROMPT4] dialogue_in prompt: {visual_prompt[:100]}...")

        # DEBUG MODE: Capture image prompts
        if DEBUG_MODE:
            _capture_image_prompt(ls_key, scene_index, visual_prompt, parsed)

        # Simple flow: pass LLM-generated prompt directly to image model
        # FIX #21: pipeline_graph always calls generate(prompt_str) which returns
        # a str path or None on failure. generate() is the correct call here.
        print(f"  [IMAGE] {scene_id} ({scene_index + 1}/{len(scene_plan)}) — generating...", end="", flush=True)
        image_path = self.image_generator.generate(
            prompt=visual_prompt,
            learning_step_id=ls_key,
            scene_id=scene_id,
        )
        if image_path is not None:
            save_image(run_folder, ls_index, scene_index, image_path, image_prompt=visual_prompt)
            new_image_paths = state.image_paths + [image_path]
            print(f" → saved")
        else:
            # Save only the .txt prompt for debugging; image generation failed
            save_image(run_folder, ls_index, scene_index, "", image_prompt=visual_prompt)
            new_image_paths = state.image_paths
            print(f" → FAILED")

        # Calculate next indices with proper bounds checking
        next_scene = scene_index + 1
        next_ls = ls_index

        if next_scene >= len(scene_plan):
            # Finished all scenes for this LS
            next_ls = ls_index + 1
            next_scene = 0
            if next_ls < len(state.learning_steps_list):
                print(f"→ Moving to LS{next_ls + 1}")

        return {
            "learning_steps_list": state.learning_steps_list,  # persist filtered+injected list
            "image_paths": new_image_paths,
            "current_image_index": state.current_image_index + 1,
            "current_scene_index": next_scene,
            "current_learning_step_index": next_ls,
            "single_scene_done": False,  # clear flag after first use
        }

    def _node_build_audio_manifest(self, state: PipelineState) -> Dict[str, Any]:
        """
        Generate TTS audio for all scenes using Amazon Polly, then save manifest.
        Replaces the old manifest-only approach — now actually synthesizes MP3 files.
        """
        run_folder = Path(state.model_run_folder or state.run_folder)

        # Build scenes_by_ls dict from state
        scenes_by_ls: Dict[str, list] = {}
        for ls_key, scenes in state.scenes.items():
            scenes_by_ls[ls_key] = scenes

        if not scenes_by_ls:
            print("  [AUDIO] No scenes found — skipping audio generation")
            return {"audio_manifest": {}}

        if not getattr(state, "generate_audio", True):
            print("  [AUDIO] Skipped (generate_audio=False)")
            return {"audio_manifest": {}}

        try:
            audio_service = AudioGeneratorService(run_folder=str(run_folder))
            manifest = audio_service.generate_audio_for_all_scenes(
                scenes_by_ls=scenes_by_ls,
                learning_steps_list=getattr(state, "learning_steps", []),
            )
            total_scenes = sum(len(v) for v in scenes_by_ls.values())
            print(f"  ✓ Audio generated for {total_scenes} scenes → audio/")
        except Exception as e:
            print(f"  [AUDIO] Generation failed: {e}")
            manifest = {}

        return {"audio_manifest": manifest}

    def _node_generate_ppt(self, state: PipelineState) -> Dict[str, Any]:
        """
        Generate the final PowerPoint presentation.

        Args:
            state: Current pipeline state

        Returns:
            State updates
        """
        # Generate PPT
        active_folder = state.model_run_folder or state.run_folder
        output_path = self.ppt_generator.generate_ppt(
            state=state,
            learning_steps_dir=str(Path(active_folder) / "learning_steps"),
            output_filename="lesson_output.pptx",
        )

        state.ppt_output_path = output_path
        state.is_complete = True

        return {"ppt_output_path": output_path, "is_complete": True}

    # -------------------------------------------------------------------------
    # Private parse helpers – kept for backward compatibility but not used by
    # the graph nodes directly (nodes use safe_parse / safe_parse_with_retry).
    # -------------------------------------------------------------------------

    def _parse_concepts(self, response: str) -> List[Dict[str, Any]]:
        """Parse the concept inventory response."""
        try:
            response = response.strip()
            if response.startswith("```json"):
                response = response[7:]
            elif response.startswith("```"):
                response = response[3:]
            if response.endswith("```"):
                response = response[:-3]

            data = json.loads(response.strip())

            if isinstance(data, list):
                return data
            elif isinstance(data, dict):
                if "concepts" in data:
                    return data["concepts"]
                elif "concept_inventory" in data:
                    return data["concept_inventory"]
                return [data]
        except json.JSONDecodeError:
            pass

        return [{"raw_text": response}]

    def _parse_story_backbone(self, response: str) -> Dict[str, Any]:
        """Parse the story backbone response to extract selected story."""
        response = response.strip()
        if response.startswith("```json"):
            response = response[7:]
        elif response.startswith("```"):
            response = response[3:]
        if response.endswith("```"):
            response = response[:-3]
        response = response.strip()

        try:
            data = json.loads(response)
            selected = data.get("selected_story", {})
            if selected:
                title = selected.get("title", "Selected Story")
                core_premise = selected.get(
                    "core_narrative_premise", ""
                ) or selected.get("core_premise", "")
                return {
                    "title": title,
                    "core_premise": core_premise,
                    "raw_response": response,
                }

            stories = data.get("stories", [])
            if stories:
                first_story = stories[0]
                title = first_story.get("title", "Selected Story")
                core_premise = first_story.get(
                    "core_narrative_premise", ""
                ) or first_story.get("core_premise", "")
                return {
                    "title": title,
                    "core_premise": core_premise,
                    "raw_response": response,
                }

            return {
                "title": "Selected Story",
                "core_premise": "",
                "raw_response": response,
            }

        except json.JSONDecodeError as e:
            debug(f"  DEBUG: JSON parsing failed: {e}")
            title = "Selected Story"
            title_match = re.search(
                r"(?:Title|Story)[:\s]+\*?(.+?)(?:\n|$|\*\*)", response, re.IGNORECASE
            )
            if title_match:
                title = title_match.group(1).strip()
                title = re.sub(r"^\*+|\*+$", "", title).strip()
                title = re.sub(
                    r"^(?:Overview|Story Overview)[:\s]*",
                    "",
                    title,
                    flags=re.IGNORECASE,
                ).strip()

            core_premise = ""
            premise_match = re.search(
                r"(?:Core Narrative Premise|Core Premise)[:\s]*\n?(.+?)(?=\n\n|\n###|\n---|$)",
                response,
                re.DOTALL | re.IGNORECASE,
            )
            if premise_match:
                core_premise = premise_match.group(1).strip()

            return {
                "title": title,
                "core_premise": core_premise,
                "raw_response": response,
            }

    def _parse_learning_steps(self, response: str) -> list:
        """Parse learning steps from prompt 2 output."""
        response = response.strip()
        if response.startswith("```json"):
            response = response[7:]
        elif response.startswith("```"):
            response = response[3:]
        if response.endswith("```"):
            response = response[:-3]
        response = response.strip()

        try:
            data = json.loads(response)
            learning_steps = data.get("learning_steps", [])
            debug(f"  DEBUG: Parsed {len(learning_steps)} learning steps from JSON")
            return learning_steps
        except json.JSONDecodeError as e:
            debug(f"  DEBUG: JSON parsing failed: {e}")

        learning_steps = []
        ls_pattern = r"(?:\d+[.\s]+|LS\d+[.\s-]+)\*?([^\n]+)\*?"
        matches = list(re.finditer(ls_pattern, response, re.IGNORECASE))

        for i, match in enumerate(matches):
            title = match.group(1).strip()[:100]
            start_pos = match.end()
            next_pos = matches[i + 1].start() if i + 1 < len(matches) else len(response)
            between_text = response[start_pos:next_pos].strip()
            narrative = (
                between_text[:500]
                if between_text
                else f"Learning step {i + 1}: {title}"
            )
            narrative = re.sub(r"^[\s\d\.\-\*]+", "", narrative, flags=re.MULTILINE)
            narrative = narrative.split("\n\n")[0][:500]

            learning_steps.append(
                {
                    "learning_step_id": f"LS{i + 1}",
                    "title": title,
                    "concepts_introduced": [],
                    "narrative_moment": narrative,
                    "scenes": [],
                }
            )

        return learning_steps

    def _parse_scenes_json(self, response: str) -> Dict[str, Any]:
        """Parse scenes JSON from prompt 3 response."""
        response = response.strip()

        if response.startswith("```json"):
            response = response[7:]
        elif response.startswith("```"):
            response = response[3:]

        if response.endswith("```"):
            response = response[:-3]

        response = response.strip()

        try:
            parsed_json = json.loads(response)

            if "response" in parsed_json:
                parsed_json = parsed_json["response"]
                debug("[SCENE JSON NORMALIZED] Unwrapped 'response' field")

            if "data" in parsed_json:
                parsed_json = parsed_json["data"]
                debug("[SCENE JSON NORMALIZED] Unwrapped 'data' field")

            debug(f"[SCENE JSON NORMALIZED] Keys: {list(parsed_json.keys())}")

            return parsed_json
        except json.JSONDecodeError:
            return {
                "scenes": [
                    {
                        "scene_id": "S1",
                        "scene_order": 1,
                        "scene_phase": "hook",
                        "scene_goal": "Generated scene",
                        "concept_focus": "",
                        "emotional_tone": "neutral",
                        "visual_setting": {"environment": "", "atmosphere": ""},
                        "narrative": {
                            "screenplay": response[:500],
                            "camera_suggestion": "",
                            "action_flow": "",
                        },
                        "dialogue": [],
                    }
                ]
            }

    def run(
        self,
        chapter_name: str,
        class_level: str,
        subject: str,
        chapter_number: str = "",
        chapter_title: str = "",
        medium: str = "English",
        pdf_path: Optional[str] = None,
        generation_mode: str = "full",
        text_model: str = "deepseek",
        image_model: str = "gpt-image-1.5",
        image_mode: str = "dialogue",
        generate_images: bool = False,
        generate_audio: bool = True,
        test_mode: bool = False,
        scene_generation_scope: str = "multiple",
    ) -> dict:
        """
        Run the complete pipeline.

        Args:
            chapter_name: Full name of the chapter
            chapter_title: Short title
            class_level: Class level
            subject: Subject
            chapter_number: Chapter number
            medium: Language medium
            pdf_path: Path to PDF file (if already available)
            generation_mode: "full" or "ls1" for LS1-only generation
            text_model: Text model to use
            image_model: Image model to use
            image_mode: "dialogue" or "overlay"
            generate_images: Whether to generate images (asked in main.py before run())
            generate_audio: Whether to generate audio via Polly (asked in main.py before run())
            test_mode: If True, enable human-in-the-loop checkpoints
            scene_generation_scope: "single" or "multiple" (for fast testing)

        Returns:
            Final pipeline result dict
        """
        # Use chapter_title for folder naming, fallback to chapter_name if not provided
        folder_title = chapter_title if chapter_title else chapter_name

        # Create initial state
        state = create_initial_state(
            chapter_name=chapter_name,
            chapter_title=chapter_title,
            class_level=class_level,
            subject=subject,
            chapter_number=chapter_number,
            medium=medium,
        )

        # Set generation mode
        state.generation_mode = generation_mode

        # Set text model
        state.text_model = text_model

        # Set image model
        state.image_model = image_model

        # Set default image mode (dialogue inside image)
        state.image_mode = image_mode

        # FIX #4/#5/#18: generate_images is now a proper parameter accepted here
        # and passed from main.py after asking the user. Honour it exactly as given.
        state.generate_images = generate_images

        # generate_audio controls whether Polly TTS is called
        state.generate_audio = generate_audio

        # Set test_mode for human-in-the-loop checkpoints
        state.test_mode = test_mode
        if test_mode:
            debug(f"[MODE] Test Mode: Human-in-the-loop checkpoints ENABLED")

        # Set scene generation scope
        state.scene_generation_scope = scene_generation_scope

        debug(f"[MODEL] Text model: {text_model}, Image model: {image_model}, Generate images: {state.generate_images}")

        # Reinitialize LLM service with selected model
        self.llm_service = LLMService(model=text_model)

        # Set PDF path if provided
        if pdf_path:
            state.pdf_path = pdf_path
            state.pdf_source = "provided"

        # Create run folder FIRST so we can pass its path to ImageGeneratorService.
        # This ensures ALL models (including Juggernaut) save images to the correct
        # run-scoped location: run_folder/images/LS{n}/
        chapter = (
            f"Class {class_level} {subject} Chapter {chapter_number} {chapter_title}"
        )
        model_run_folder = create_run_folder(
            text_model,
            chapter=chapter,
            text_model=text_model,
            image_model=image_model,
            image_mode=state.image_mode,
        )
        state.model_run_folder = str(model_run_folder)

        # Create legacy run folder for backward compatibility
        folder_name = f"{class_level}_{subject}_{folder_title}".lower().replace(
            " ", "_"
        )
        state.run_folder = f"outputs/{folder_name}"
        Path(state.run_folder).mkdir(parents=True, exist_ok=True)
        (Path(state.run_folder) / "learning_steps").mkdir(exist_ok=True)
        (Path(state.run_folder) / "images").mkdir(exist_ok=True)
        (Path(state.run_folder) / "prompts").mkdir(exist_ok=True)
        (Path(state.run_folder) / "outputs").mkdir(exist_ok=True)

        # Initialize ImageGeneratorService AFTER run folder is created.
        # Pass model_run_folder so _get_image_path() always resolves to the
        # correct per-run location — fixes the Juggernaut wrong-folder bug.
        self.image_generator = ImageGeneratorService(
            model=image_model,
            image_mode=state.image_mode,
            run_folder=str(model_run_folder),
        )

        # Run the graph
        config = {
            "configurable": {"thread_id": "storytelling-pipeline"},
            # FIX #13: recursion_limit raised to 300. Full mode with 10 scenes × N
            # learning steps easily exceeds the old limit of 100.
            "recursion_limit": 300,
        }

        # FIX #8: stream_mode="values" so each snapshot IS the full accumulated state.
        # Default mode yields {"node_name": update_dict}; the last chunk has no
        # "__root__" key so the old code always returned the original empty state,
        # making image_paths always show 0.
        final_state = {}
        for state_snapshot in self.graph.stream(state, config, stream_mode="values"):
            final_state = state_snapshot

        def _get(key, default=None):
            if isinstance(final_state, dict):
                return final_state.get(key, default)
            return getattr(final_state, key, default)

        ls_list = _get("learning_steps_list", [])
        image_paths_list = _get("image_paths", [])
        ppt_output = _get("ppt_output_path", "")
        final_model_run_folder = _get("model_run_folder", state.model_run_folder or "")

        if final_model_run_folder:
            model_run_path = Path(final_model_run_folder)
            if model_run_path.exists():
                update_run_metadata(model_run_path, {"learning_steps": len(ls_list)})

        # DEBUG MODE: Save final debug data
        if DEBUG_MODE:
            _save_image_debug()

            final_summary = {
                "timestamp": datetime.now().isoformat(),
                "learning_steps_count": len(ls_list),
                "image_paths_count": len(image_paths_list),
                "image_paths": image_paths_list,
                "ppt_output": ppt_output,
                "model_run_folder": final_model_run_folder,
                "final_state": {
                    "learning_steps_list": ls_list,
                    "scenes": state.scenes if hasattr(state, "scenes") else {},
                },
            }
            _save_debug_json("final_summary.json", final_summary)
            debug(f"[DEBUG] Final debug data saved to {DEBUG_OUTPUT_DIR}/")

        return {
            "run_folder": final_model_run_folder,
            "learning_steps_list": ls_list,
            "image_paths": image_paths_list,
            "ppt_output_path": ppt_output,
        }


def create_pipeline_graph() -> PipelineGraph:
    """Factory function to create PipelineGraph."""
    return PipelineGraph()