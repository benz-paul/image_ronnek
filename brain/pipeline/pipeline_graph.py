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
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

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

from brain.services.image_generator import ImageGeneratorService
from brain.services.ppt_generator import PPTGeneratorService
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
)
from utils.json_utils import safe_parse


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

    print(f"\n  Validating {len(scenes)} scenes...")

    for i, scene in enumerate(scenes):
        if not isinstance(scene, dict):
            print(f"    ⚠ Scene {i + 1}: Not a dictionary, skipping")
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
        print(f"  ⚠ {invalid_count} scenes had missing optional fields (acceptable)")

    print(f"  ✓ Validated {len(valid_scenes)} scenes for {ls_id}")
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

        # Make request
        response = requests.post(
            url="https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": "Bearer " + api_key,
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=120,
        )

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

        # Debug token usage
        print(
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

            if not content:
                print("[FALLBACK] Using minimal fallback output")
                content = '{"concepts": ["Basic Concept"]}'

        # Debug
        print("\n[LLM RAW RESPONSE]")
        print(response_json)

        print("\n[LLM CONTENT]")
        print(content[:500] if content else "EMPTY")

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
        self.image_generator = ImageGeneratorService()
        self.ppt_generator = PPTGeneratorService()

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
        graph.add_node("initialize", self._node_initialize)
        graph.add_node(
            "user_input", self._node_user_input
        )  # NEW: Simple 3-question input
        graph.add_node("execute_prompt0", self._node_execute_prompt0)
        graph.add_node("execute_prompt1", self._node_execute_prompt1)
        graph.add_node("execute_prompt2", self._node_execute_prompt2)
        graph.add_node("execute_prompt3a", self._node_execute_prompt3a)
        graph.add_node("execute_prompt3b", self._node_execute_prompt3b)
        graph.add_node("execute_prompt3", self._node_execute_prompt3)
        graph.add_node("execute_prompt4", self._node_execute_prompt4)
        graph.add_node("generate_ppt", self._node_generate_ppt)

        # Set entry point
        graph.set_entry_point("initialize")

        # SCENE GENERATION FLOW: 3A (planning) → 3B (generation) → loops
        graph.add_edge("initialize", "user_input")
        graph.add_edge("user_input", "execute_prompt0")
        graph.add_edge("execute_prompt0", "execute_prompt1")
        graph.add_edge("execute_prompt1", "execute_prompt2")
        graph.add_edge("execute_prompt2", "execute_prompt3a")

        # Router for scene planning (3A) - decides whether to plan next LS or go to 3B
        def router_prompt3a(state: PipelineState) -> str:
            """Router for prompt3a - go to prompt3b for scene generation."""
            next_node = "execute_prompt3b"
            # Safety check
            if next_node not in ["execute_prompt3b"]:
                print(
                    f"[WARNING] Invalid node: {next_node}, falling back to execute_prompt3b"
                )
                next_node = "execute_prompt3b"
            print(f"[DEBUG] Next node: {next_node}")
            return next_node

        # Router for scene generation (3B) - loops through scenes
        def router_prompt3b(state: PipelineState) -> str:
            """Router for prompt3b - process all scenes for current LS, then next LS."""

            current_ls_idx = state.current_learning_step_index
            current_scene_idx = state.current_scene_index

            ls_key = f"LS{current_ls_idx + 1}"
            scene_plan = state.scene_plans.get(ls_key, [])

            print(
                f"[DEBUG] Router: {ls_key} scene {current_scene_idx + 1}/{len(scene_plan)}"
            )

            # LOOP THROUGH SCENES
            if current_scene_idx < len(scene_plan):
                next_node = "execute_prompt3b"
                print(f"[DEBUG] Next node: {next_node}")
                return next_node

            # LS1 MODE → STOP AFTER FIRST LS
            if state.generation_mode == "ls1":
                next_node = "execute_prompt4"

            else:
                total_ls = len(state.learning_steps_list)

                # FULL MODE → CONTINUE OR END
                if current_ls_idx + 1 >= total_ls:
                    next_node = "execute_prompt4"
                else:
                    next_node = "execute_prompt3a"

            # SAFETY GUARD (CLEAN)
            valid_nodes = ["execute_prompt3b", "execute_prompt3a", "execute_prompt4"]

            if next_node not in valid_nodes:
                print(
                    f"[WARNING] Invalid node: {next_node}, fallback to execute_prompt4"
                )
                next_node = "execute_prompt4"

            print(f"[DEBUG] Next node: {next_node}")
            return next_node

        graph.add_conditional_edges(
            "execute_prompt3a",
            router_prompt3a,
            {
                "execute_prompt3b": "execute_prompt3b",
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

        # Router for prompt4 loop (if images requested)
        def router_prompt4(state: PipelineState):
            if not state.generate_images:
                print("[DEBUG] Next node: END")
                return END

            total_scenes = sum(len(scenes) for scenes in state.scenes.values())

            if state.current_image_index >= total_scenes:
                print("[DEBUG] Next node: END")
                return END

            print("[DEBUG] Next node: execute_prompt4")
            return "execute_prompt4"

        graph.add_conditional_edges(
            "execute_prompt4", router_prompt4, {"execute_prompt4": "execute_prompt4"}
        )

        # Compile with checkpointer
        checkpointer = MemorySaver()
        app = graph.compile(checkpointer=checkpointer)

        print("[PIPELINE] Compiled successfully")
        return app

    def _node_initialize(self, state: PipelineState) -> Dict[str, Any]:
        """
        Initialize node - set up run folder.

        Args:
            state: Current pipeline state

        Returns:
            State updates
        """
        # Create simple run folder with timestamp
        run_folder = create_run_folder(
            chapter=state.user_inputs.chapter_name,
            class_level=state.user_inputs.class_level,
            subject=state.user_inputs.subject,
        )

        # Store run folder in state
        state.run_folder = str(run_folder)
        state.model_run_folder = str(run_folder)

        # Set initial prompt ID
        state.current_prompt_id = "prompt0"

        print(f"\n[INIT] Run folder created: {run_folder.name}")

        return {"current_prompt_id": "prompt0", "run_folder": str(run_folder)}

    def _node_user_input(self, state: PipelineState) -> Dict[str, Any]:
        """
        SIMPLIFIED: Get user input for pipeline flow.

        Asks only 3 simple questions:
        1. Generate (1) One learning step or (2) All?
        2. Generate scenes? (y/n)
        3. Generate images? (y/n)

        Args:
            state: Current pipeline state

        Returns:
            State updates with generation_mode and flags
        """
        print("\n" + "=" * 60)
        print("  PIPELINE CONFIGURATION")
        print("=" * 60)

        # Question 1: Learning Steps
        print("\n[1/3] Learning Steps:")
        print("  (1) Generate ONE learning step (LS1)")
        print("  (2) Generate ALL learning steps")

        while True:
            ls_choice = input("  Enter choice (1/2): ").strip()
            if ls_choice in ["1", "2"]:
                break
            print("  Please enter 1 or 2")

        if ls_choice == "1":
            generation_mode = "ls1"
            print("  → Mode: LS1 only")
        else:
            generation_mode = "full"
            print("  → Mode: All Learning Steps")

        # Question 2: Scenes
        print("\n[2/3] Scene Generation:")
        print("  Generate scenes for learning steps? (y/n)")

        while True:
            scenes_choice = input("  Enter choice (y/n): ").strip().lower()
            if scenes_choice in ["y", "n", "yes", "no"]:
                break
            print("  Please enter y or n")

        generate_scenes = scenes_choice in ["y", "yes"]
        if generate_scenes:
            print("  → Yes, generate scenes")
        else:
            print("  → No, skip scene generation")

        # Question 3: Images
        print("\n[3/3] Image Generation:")
        print("  Generate images for scenes? (y/n)")

        while True:
            images_choice = input("  Enter choice (y/n): ").strip().lower()
            if images_choice in ["y", "n", "yes", "no"]:
                break
            print("  Please enter y or n")

        generate_images = images_choice in ["y", "yes"]
        if generate_images:
            print("  → Yes, generate images")
        else:
            print("  → No, skip image generation")

        print("\n" + "=" * 60)
        print("  Starting pipeline...")
        print("=" * 60 + "\n")

        # Update config with user choices
        if state.run_folder:
            update_run_metadata(
                Path(state.run_folder),
                {
                    "generation_mode": generation_mode,
                    "generate_images": generate_images,
                    "generate_scenes": generate_scenes,
                },
            )

        return {
            "generation_mode": generation_mode,
            "generate_images": generate_images,
            "generate_scenes": generate_scenes,
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

        run_folder = Path(state.run_folder)
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

        print(f"[DEBUG] Full text length: {len(full_text)}")

        # STEP 1 — First pass (extract concept titles only)
        prompt1 = f"""
Extract a COMPLETE list of concepts from this chapter.

IMPORTANT:
- Return ONLY concept TITLES (short)
- DO NOT explain
- DO NOT add long descriptions
- Keep each concept 3-6 words max

RULES:
- Do NOT miss any concept
- Prefer over-extraction
- Include formulas, ideas, problem types

STRICT FILTERING RULE:

Do NOT include:

* examples
* case studies
* word problems
* story-based scenarios
* application-specific situations (e.g., taxi fare, rabbits, salary cases)

ONLY include:

* definitions
* formulas
* properties
* relationships between concepts
* mathematical structures

If an item is an example of a concept, DO NOT include it.

OUTPUT:

Return ONLY JSON:
{{
  "concepts": [
    "Concept 1",
    "Concept 2",
    "Concept 3"
  ]
}}

TEXT:
{full_text[:12000]}
"""
        print("  First pass: Full extraction...")
        result1 = self.llm_service.invoke(prompt1, max_tokens=2000, temperature=0.2)
        response1 = result1["content"]
        concepts_pass1 = safe_parse(response1)
        print("[DEBUG] Prompt0 response length:", len(str(response1)))

        # STEP 2 — Second pass (gap detection)
        prompt2 = f"""
You already extracted concepts.

Here is the current list:

{json.dumps(concepts_pass1)}

Find IMPORTANT missing concepts.
Return ONLY concept TITLES (short), 3-6 words max.

RULES:
- Only add missing ones
- Do NOT repeat
- Focus on gaps

STRICT FILTERING RULE:

Do NOT include:

* examples
* case studies
* word problems
* story-based scenarios
* application-specific situations (e.g., taxi fare, rabbits, salary cases)

ONLY include:

* definitions
* formulas
* properties
* relationships between concepts
* mathematical structures

If an item is an example of a concept, DO NOT include it.

Return ONLY JSON:
{{
  "concept_titles": [
    "Missing Concept 1",
    "Missing Concept 2"
  ]
}}
"""
        print("  Second pass: Gap detection...")
        result2 = self.llm_service.invoke(prompt2, max_tokens=1000, temperature=0.2)
        response2 = result2["content"]
        concepts_pass2 = safe_parse(response2)

        # STEP 3 — Merge (both are now lists of concept titles)
        concepts_list1 = concepts_pass1.get("concepts", [])
        concepts_list2 = concepts_pass2.get("concept_titles", [])

        # Combine and deduplicate
        all_concepts = concepts_list1 + concepts_list2
        final_concepts = list(
            dict.fromkeys(all_concepts)
        )  # Preserve order, remove duplicates

        print(f"[DEBUG] Total concepts: {len(final_concepts)}")

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

        run_folder = Path(state.run_folder)

        chapter_name = state.user_inputs.chapter_name
        concepts = json.dumps(state.prompt0_output)

        prompt = f"""
Chapter: {chapter_name}
Concepts: {concepts}

IMPORTANT: You must create a story with MINIMUM 2 MAIN CHARACTERS.

Character Requirements:
- Each character must have: name, role, personality, visual_description
- Characters must interact in scenes through dialogue
- Story must be visual and cinematic
- Characters should be relatable to students (e.g., student, teacher, friend, family)

Return ONLY JSON:
{{
  "title": "...",
  "core_premise": "...",
  "characters": [
    {{
      "name": "...",
      "role": "...",
      "personality": "...",
      "visual_description": "..."
    }},
    {{
      "name": "...",
      "role": "...",
      "personality": "...",
      "visual_description": "..."
    }}
  ]
}}

CRITICAL: characters array must have at least 2 entries.
"""

        result = self.llm_service.invoke(prompt, temperature=0.7)
        response = result["content"]
        story = safe_parse(response)

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

        run_folder = Path(state.run_folder)

        story = json.dumps(state.prompt1_output)
        concepts = json.dumps(state.prompt0_output)

        prompt = f"""
Story: {story}
Concepts: {concepts}

Return ONLY JSON:
{{
  "learning_steps": [...]
}}

STRICT OUTPUT ENFORCEMENT:

You MUST follow the exact JSON schema.

Each learning step MUST contain:

* "learning_step_id"
* "title"
* "concepts_introduced"
* "narrative_moment"

DO NOT use:

* step_number
* description
* concepts_covered

If any of these incorrect keys are used, the output is INVALID.

---

SELF-CHECK BEFORE OUTPUT:

Before returning the final JSON:

1. Ensure every learning step contains:

   * learning_step_id (LS1, LS2, ...)
   * title (non-empty)
   * concepts_introduced (must NOT be empty)
   * narrative_moment (minimum 5 lines)

2. If ANY field is missing or empty:
   REGENERATE the entire output.

3. Ensure JSON is valid and parsable.

---

Output ONLY valid JSON
"""

        result = self.llm_service.invoke(prompt, temperature=0.4)
        response = result["content"]
        learning_steps = safe_parse(response)

        state.prompt2_output = learning_steps
        state.learning_steps_list = learning_steps.get("learning_steps", [])

        save_prompt(run_folder, 2, prompt)
        save_raw_output(run_folder, 2, response)
        save_parsed(run_folder, "learning_steps", learning_steps)

        # LS1-only mode: filter to only first learning step
        learning_steps_list = learning_steps.get("learning_steps", [])
        if state.generation_mode == "ls1":
            learning_steps_list = learning_steps_list[:1]
            print(f"[MODE] LS1-only mode: Processing only first learning step")
            print(f"[MODE] Only LS1.json will be saved in learning_steps/")

        print(
            f"[DEBUG] LS after filter: {[ls.get('learning_step_id', f'LS{i + 1}') for i, ls in enumerate(learning_steps_list)]}"
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
                    print(
                        f"[WARNING] Using fallback key: concepts_covered → concepts_introduced for {ls_id}"
                    )

            narrative_moment = ls.get("narrative_moment")
            if narrative_moment is None or narrative_moment == "":
                narrative_moment = ls.get("description", "")
                if narrative_moment != "":
                    print(
                        f"[WARNING] Using fallback key: description → narrative_moment for {ls_id}"
                    )

            # Validate required fields
            if not concepts_introduced:
                print(
                    f"[WARNING] Missing concepts_introduced for {ls_id}, using empty list"
                )
                concepts_introduced = []

            if not narrative_moment:
                print(
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

            print(f"[LS STORAGE] Saved {ls_id} → learning_steps/{ls_filename}")

        print(f"  ✓ Saved parsed learning_steps to: parsed/learning_steps.json")
        print(
            f"  ✓ Saved {len(validated_learning_steps)} individual learning step files"
        )

        return {
            "prompt2_output": learning_steps,
            "learning_steps_list": validated_learning_steps,
            "current_prompt_id": "prompt3",
        }

    def _node_ls_selection(self, state: PipelineState) -> Dict[str, Any]:
        """
        Human-in-the-loop checkpoint: Select learning steps to process.

        When TEST_MODE=True: Displays all learning steps and asks user to select.
        When TEST_MODE=False: Automatically selects all learning steps.

        Args:
            state: Current pipeline state

        Returns:
            State updates with selected_learning_steps list
        """
        learning_steps = state.learning_steps_list

        # PRODUCTION MODE: Auto-select all learning steps
        if not state.test_mode:
            print("\n[CHECKPOINT] Production Mode - Auto-selecting all learning steps")
            selected = list(range(len(learning_steps)))
            state.checkpoint_history.append(
                f"LS Selection (AUTO): All {len(learning_steps)} steps selected"
            )

            return {
                "selected_learning_steps": selected,
                "ls_selection_made": True,
                "current_learning_step_index": selected[0] if selected else 0,
                "current_scene_index": 0,
                "checkpoint_history": state.checkpoint_history,
            }

        # TEST_MODE: Show interactive selection
        print("\n" + "=" * 60)
        print("  CHECKPOINT: Learning Step Selection")
        print("  " + "=" * 58)

        print(f"\n  Total Learning Steps Generated: {len(learning_steps)}")
        print("\n  Available Learning Steps:")
        print("-" * 60)

        for i, ls in enumerate(learning_steps):
            ls_id = ls.get("learning_step_id", f"LS{i + 1}")
            title = ls.get(
                "title", ls.get("learning_step_title", f"Learning Step {i + 1}")
            )
            print(f"  {i + 1}. [{ls_id}] {title}")

        print("-" * 60)
        print("\n  Select learning steps to process:")
        print("    a) One learning step")
        print("    b) Multiple learning steps")
        print("    c) All learning steps")

        while True:
            choice = input("\n  Enter choice (a/b/c): ").strip().lower()

            if choice == "a":
                # Single learning step
                while True:
                    try:
                        ls_num = int(input("  Enter learning step number: ").strip())
                        if 1 <= ls_num <= len(learning_steps):
                            selected = [ls_num - 1]  # Convert to 0-based index
                            break
                        else:
                            print(
                                f"    Please enter a number between 1 and {len(learning_steps)}"
                            )
                    except ValueError:
                        print("    Please enter a valid number")

                print(f"\n  ✓ Selected Learning Step {ls_num}")
                state.checkpoint_history.append(f"LS Selection: Step {ls_num} selected")
                break

            elif choice == "b":
                # Multiple learning steps
                while True:
                    try:
                        ls_nums = input(
                            "  Enter learning step numbers (e.g., 1,3,5): "
                        ).strip()
                        selected = []
                        for num_str in ls_nums.split(","):
                            num = int(num_str.strip())
                            if 1 <= num <= len(learning_steps):
                                selected.append(num - 1)  # Convert to 0-based
                            else:
                                print(f"    Invalid number {num}, skipping")

                        if selected:
                            break
                        else:
                            print("    Please enter at least one valid number")
                    except ValueError:
                        print("    Please enter valid numbers")

                selected_display = [f"LS{i + 1}" for i in sorted(set(selected))]
                print(f"\n  ✓ Selected Learning Steps: {', '.join(selected_display)}")
                state.checkpoint_history.append(
                    f"LS Selection: Steps {', '.join(selected_display)} selected"
                )
                break

            elif choice == "c":
                # All learning steps
                selected = list(range(len(learning_steps)))
                print(f"\n  ✓ Selected ALL {len(learning_steps)} Learning Steps")
                state.checkpoint_history.append(
                    f"LS Selection: All {len(learning_steps)} steps selected"
                )
                break

            else:
                print("    Invalid choice. Please enter a, b, or c.")

        print(f"\n  Selected Learning Steps: {selected}")

        # Store selection in state
        state.selected_learning_steps = selected
        state.ls_selection_made = True

        # Reset indices for processing selected steps
        state.current_learning_step_index = selected[0] if selected else 0
        state.current_scene_index = 0

        print(f"\n  Proceeding to scene generation for selected learning steps...")

        return {
            "selected_learning_steps": selected,
            "ls_selection_made": True,
            "current_learning_step_index": state.current_learning_step_index,
            "current_scene_index": 0,
            "checkpoint_history": state.checkpoint_history,
        }

    def _node_scene_selection(self, state: PipelineState) -> Dict[str, Any]:
        """
        Human-in-the-loop checkpoint: Select scenes to generate images for.

        When TEST_MODE=True: Displays scenes and asks user to select.
        When TEST_MODE=False: Automatically selects all scenes.

        Args:
            state: Current pipeline state

        Returns:
            State updates with selected_scenes list
        """
        learning_steps = state.learning_steps_list

        # PRODUCTION MODE: Auto-select all scenes
        if not state.test_mode:
            print("\n[CHECKPOINT] Production Mode - Auto-selecting all scenes")
            selected = []
            for ls_idx, ls in enumerate(learning_steps):
                scenes = ls.get("scenes", [])
                for s_idx in range(len(scenes)):
                    selected.append(
                        SceneSelection(
                            ls_index=ls_idx,
                            scene_index=s_idx,
                            scene_id=scenes[s_idx].get("scene_id", f"S{s_idx + 1}"),
                            scene_goal=scenes[s_idx].get("scene_goal", ""),
                        )
                    )

            state.checkpoint_history.append(
                f"Scene Selection (AUTO): All {len(selected)} scenes selected"
            )

            # Set default image generation mode for production
            state.image_generation_scope = "multiple"
            state.overlay_mode = "overlay"
            state.image_mode = "overlay"

            return {
                "selected_scenes": selected,
                "scene_selection_made": True,
                "image_generation_scope": "multiple",
                "overlay_mode": "overlay",
                "image_mode": "overlay",
                "current_learning_step_index": selected[0].ls_index if selected else 0,
                "current_scene_index": selected[0].scene_index if selected else 0,
                "checkpoint_history": state.checkpoint_history,
            }

        # TEST_MODE: Show interactive selection
        print("\n" + "=" * 60)
        print("  CHECKPOINT: Scene Selection")
        print("  " + "=" * 58)

        # Display scenes grouped by learning step
        print("\n  Scenes by Learning Step:")
        print("-" * 60)

        scene_count = 0
        for ls_idx, ls in enumerate(learning_steps):
            ls_id = ls.get("learning_step_id", f"LS{ls_idx + 1}")
            title = ls.get("title", f"Learning Step {ls_idx + 1}")
            scenes = ls.get("scenes", [])

            print(f"\n  [{ls_id}] {title}")
            print(f"      Scenes: {len(scenes)}")

            for s_idx, scene in enumerate(scenes):
                scene_count += 1
                scene_id = scene.get("scene_id", f"S{s_idx + 1}")
                scene_goal = scene.get("scene_goal", scene.get("scene_phase", ""))
                print(f"        {scene_count}. [{scene_id}] {scene_goal[:50]}...")

        print("\n" + "-" * 60)
        print(f"  Total Scenes: {scene_count}")
        print("\n  Select scenes to generate images for:")
        print("    a) One scene")
        print("    b) Multiple scenes")
        print("    c) All scenes")

        while True:
            choice = input("\n  Enter choice (a/b/c): ").strip().lower()

            if choice == "a":
                # Single scene
                while True:
                    try:
                        scene_num = int(input("  Enter scene number: ").strip())
                        if 1 <= scene_num <= scene_count:
                            break
                        else:
                            print(
                                f"    Please enter a number between 1 and {scene_count}"
                            )
                    except ValueError:
                        print("    Please enter a valid number")

                # Convert to LS index and scene index and wrap in list
                selected_scene = self._convert_scene_number_to_selection(
                    scene_num, learning_steps
                )
                selected = [selected_scene]
                print(f"\n  ✓ Selected Scene {scene_num}")
                state.checkpoint_history.append(
                    f"Scene Selection: Scene {scene_num} selected"
                )
                break

            elif choice == "b":
                # Multiple scenes
                while True:
                    try:
                        scene_nums = input(
                            "  Enter scene numbers (e.g., 1,3,5): "
                        ).strip()
                        selected = []
                        for num_str in scene_nums.split(","):
                            num = int(num_str.strip())
                            if 1 <= num <= scene_count:
                                sel = self._convert_scene_number_to_selection(
                                    num, learning_steps
                                )
                                selected.append(sel)
                            else:
                                print(f"    Invalid number {num}, skipping")

                        if selected:
                            break
                        else:
                            print("    Please enter at least one valid number")
                    except ValueError:
                        print("    Please enter valid numbers")

                # Deduplicate and sort
                seen = set()
                unique_selected = []
                for sel in selected:
                    key = (sel.ls_index, sel.scene_index)
                    if key not in seen:
                        seen.add(key)
                        unique_selected.append(sel)
                selected = unique_selected

                selected_display = [
                    f"LS{sel.ls_index + 1}-S{sel.scene_index + 1}" for sel in selected
                ]
                print(f"\n  ✓ Selected Scenes: {', '.join(selected_display)}")
                state.checkpoint_history.append(
                    f"Scene Selection: Scenes {', '.join(selected_display)} selected"
                )
                break

            elif choice == "c":
                # All scenes
                selected = []
                for ls_idx, ls in enumerate(learning_steps):
                    scenes = ls.get("scenes", [])
                    for s_idx in range(len(scenes)):
                        selected.append(
                            SceneSelection(
                                ls_index=ls_idx,
                                scene_index=s_idx,
                                scene_id=scenes[s_idx].get("scene_id", f"S{s_idx + 1}"),
                                scene_goal=scenes[s_idx].get("scene_goal", ""),
                            )
                        )

                print(f"\n  ✓ Selected ALL {len(selected)} Scenes")
                state.checkpoint_history.append(
                    f"Scene Selection: All {len(selected)} scenes selected"
                )
                break

            else:
                print("    Invalid choice. Please enter a, b, or c.")

        print(f"\n  Selected Scenes: {len(selected)}")

        # Store selection in state
        state.selected_scenes = selected
        state.scene_selection_made = True

        # Set initial indices
        if selected:
            state.current_learning_step_index = selected[0].ls_index
            state.current_scene_index = selected[0].scene_index
        else:
            state.current_learning_step_index = 0
            state.current_scene_index = 0

        # Ask about image generation mode
        print("\n" + "-" * 60)
        print("  Image Generation Options:")
        print("    a) Generate image for single scene")
        print("    b) Generate images for multiple scenes")

        while True:
            img_choice = input("\n  Enter choice (a/b): ").strip().lower()

            if img_choice == "a":
                state.image_generation_scope = "single"
                print("    ✓ Mode: Single scene")
                break
            elif img_choice == "b":
                state.image_generation_scope = "multiple"
                print("    ✓ Mode: Multiple scenes")
                break
            else:
                print("    Invalid choice. Please enter a or b.")

        # Ask about dialogue overlay mode
        print("\n  Dialogue Rendering:")
        print("    a) Overlay dialogue on image (add speech bubbles)")
        print("    b) Generate dialogue directly in image prompt")

        while True:
            overlay_choice = input("\n  Enter choice (a/b): ").strip().lower()

            if overlay_choice == "a":
                state.overlay_mode = "overlay"
                print("    ✓ Mode: Speech bubble overlay")
                break
            elif overlay_choice == "b":
                state.overlay_mode = "dialogue_in_image"
                print("    ✓ Mode: Dialogue in image")
                break
            else:
                print("    Invalid choice. Please enter a or b.")

        # Update image_mode based on overlay_mode
        state.image_mode = state.overlay_mode

        print("\n  Proceeding to image generation...")

        return {
            "selected_scenes": selected,
            "scene_selection_made": True,
            "image_generation_scope": state.image_generation_scope,
            "overlay_mode": state.overlay_mode,
            "image_mode": state.image_mode,
            "current_learning_step_index": state.current_learning_step_index,
            "current_scene_index": state.current_scene_index,
            "checkpoint_history": state.checkpoint_history,
        }

    def _convert_scene_number_to_selection(
        self, scene_num: int, learning_steps: List[Dict[str, Any]]
    ) -> SceneSelection:
        """Convert a 1-based scene number to SceneSelection object."""
        current_count = 0
        for ls_idx, ls in enumerate(learning_steps):
            scenes = ls.get("scenes", [])
            for s_idx, scene in enumerate(scenes):
                current_count += 1
                if current_count == scene_num:
                    return SceneSelection(
                        ls_index=ls_idx,
                        scene_index=s_idx,
                        scene_id=scene.get("scene_id", f"S{s_idx + 1}"),
                        scene_goal=scene.get("scene_goal", ""),
                    )
        # Fallback to first scene
        return SceneSelection(ls_index=0, scene_index=0, scene_id="S1", scene_goal="")

    def _node_image_check(self, state: PipelineState) -> Dict[str, Any]:
        """
        Ask user if they want to generate images.

        When TEST_MODE=True: Shows interactive prompt.
        When TEST_MODE=False: Automatically proceeds with image generation.

        Args:
            state: Current pipeline state

        Returns:
            State updates with generate_images flag
        """
        print("\n" + "=" * 50)
        print("  Scene Generation Complete!")
        print(
            f"  Selected scenes: {len(state.selected_scenes) if state.scene_selection_made else 'All'}"
        )
        print("=" * 50)

        # PRODUCTION MODE: Auto-proceed to image generation
        if not state.test_mode:
            print(
                "\n[CHECKPOINT] Production Mode - Auto-proceeding to image generation"
            )
            generate_images = True

            # Set indices to start from selected scenes
            if state.scene_selection_made and state.selected_scenes:
                first_sel = state.selected_scenes[0]
                state.current_learning_step_index = first_sel.ls_index
                state.current_scene_index = first_sel.scene_index
            else:
                state.current_learning_step_index = 0
                state.current_scene_index = 0

            state.checkpoint_history.append("Image Generation (AUTO): Yes")

            return {
                "generate_images": generate_images,
                "checkpoint_history": state.checkpoint_history,
            }

        # TEST_MODE: Show interactive prompt
        print("\nProceed to image generation?")
        print("  y - Yes, generate images")
        print("  n - No, skip image generation")

        response = input("\nEnter choice (y/n): ").strip().lower()

        if response == "y":
            generate_images = True
            print("\n✓ Proceeding to image generation...")
        else:
            generate_images = False
            print("\n✗ Skipping image generation.")
            print("Pipeline will end here. No PPT will be generated.")

        if generate_images:
            # Set indices to start from selected scenes
            if state.scene_selection_made and state.selected_scenes:
                first_sel = state.selected_scenes[0]
                state.current_learning_step_index = first_sel.ls_index
                state.current_scene_index = first_sel.scene_index
            else:
                state.current_learning_step_index = 0
                state.current_scene_index = 0

        # Log checkpoint decision
        state.checkpoint_history.append(
            f"Image Generation: {'Yes' if generate_images else 'No'}"
        )

        return {
            "generate_images": generate_images,
            "checkpoint_history": state.checkpoint_history,
        }

    def _node_ppt_check(self, state: PipelineState) -> Dict[str, Any]:
        """
        Ask user if they want to generate PPT.

        Args:
            state: Current pipeline state

        Returns:
            State updates with generate_ppt flag
        """
        print("\n" + "=" * 50)
        print("  Image Generation Complete!")
        print(f"  Generated {len(state.image_paths)} images")
        print("=" * 50)

        response = input("\nDo you want to generate PPT? (y/n): ").strip().lower()
        generate_ppt = response in ["y", "yes"]

        if generate_ppt:
            print("\nProceeding to PPT generation...")
        else:
            print("\nSkipping PPT generation.")
            print("Pipeline will end here.")

        return {"generate_ppt": generate_ppt}

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

        print(f"[DEBUG] Active LS count: {len(state.learning_steps_list)}")

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
        ls_key = f"LS{current_index + 1}"

        print(f"\n{'=' * 60}")
        print(
            f"  SCENE PLANNING: {ls_id} ({current_index + 1}/{len(state.learning_steps_list)})"
        )
        print(f"{'=' * 60}")

        run_folder = Path(state.run_folder)

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

        plan_prompt = f"""
You are generating a SCENE PLAN for a learning step.

----------------------------------------
STORY CONTEXT:
Title: {story_context.get("title", "")}
Premise: {story_context.get("core_premise", "")}
Characters: {json.dumps(story_context.get("characters", []))}

PREVIOUS LEARNING STEP LAST SCENE:
{json.dumps(previous_step_last_scene) if previous_step_last_scene else "None (this is the first step)"}

CURRENT LEARNING STEP:
- ID: {ls_id}
- Title: {learning_step.get("title", "")}
- Concepts: {json.dumps(learning_step.get("concepts_introduced", []))}
- Narrative: {learning_step.get("narrative_moment", "")}

----------------------------------------
SCENE PLAN RULES:

1. Generate between 6-15 scenes
2. Each scene must have a PURPOSE:
   - HOOK: Grab attention
   - SETUP: Introduce situation
   - DISCOVERY: Reveal something
   - CONFUSION: Create tension/mystery
   - GUIDANCE: Show direction
   - MICRO_LEARN: Teach micro concept
   - VALIDATION: Confirm understanding
   - APPLICATION: Real-world use
   - TWIST: Surprise element
   - ESCALATION: Increase stakes
   - PAYOFF: Satisfying resolution
   - REFLECTION: Personal insight
   - TRANSITION: Bridge to next step
   - CLIFFHANGER: Leave wanting more

3. STRICT REQUIREMENTS:
   - First scene MUST be HOOK
   - DO NOT repeat same type consecutively
   - Use tension/confusion every 2-3 scenes
   - Delay full explanations (build curiosity first)
   - Include at least one APPLICATION scene
   - Final scene should have PAYOFF or set up next step

4. Scene plan format:
   - scene_id: "S1", "S2", etc.
   - phase: scene type (HOOK, SETUP, etc.)
   - summary: what happens (2-3 sentences)
   - concept_focus: what concept is taught

----------------------------------------
STRICT SCENE COUNT RULE:

You MUST generate:

* Minimum 6 scenes
* Maximum 15 scenes

If fewer than 6 scenes are generated:
REGENERATE the output.

----------------------------------------
OUTPUT JSON:

{{
  "scene_plan": [
    {{
      "scene_id": "S1",
      "phase": "HOOK",
      "summary": "...",
      "concept_focus": "..."
    }},
    ...
  ]
}}

Generate 6-15 scenes following the rules above.
"""
        # Retry logic for scene count validation
        max_retries = 3
        retry_count = 0
        scene_plan = []

        while retry_count < max_retries:
            result = self.llm_service.invoke(
                plan_prompt, temperature=0.4, max_tokens=1500
            )
            response = result["content"]

            try:
                parsed = safe_parse(response)
                scene_plan = parsed.get("scene_plan", [])

                # Validate scene count
                if len(scene_plan) < 6:
                    print(
                        f"[VALIDATION] Only {len(scene_plan)} scenes generated (minimum: 6). Retrying..."
                    )
                    retry_count += 1
                    continue

                print(f"[SCENE PLAN] Generated {len(scene_plan)} scenes for {ls_key}")
                break

            except Exception as e:
                print(f"[WARNING] Failed to parse scene plan: {e}")
                scene_plan = []
                retry_count += 1

        # Final validation
        if len(scene_plan) < 6:
            print(
                f"[WARNING] Scene plan still has only {len(scene_plan)} scenes. Using default plan."
            )
            scene_plan = [
                {
                    "scene_id": f"S{i + 1}",
                    "phase": "MICRO_LEARN",
                    "summary": f"Scene {i + 1}",
                    "concept_focus": "",
                }
                for i in range(6)
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
            "current_scene_index": 0,
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

        print(f"[DEBUG] Active LS count: {len(state.learning_steps_list)}")

        if not state.learning_steps_list:
            print("[PIPELINE ERROR] No learning steps.")
            return {"learning_steps_list": state.learning_steps_list}

        if current_ls_index >= len(state.learning_steps_list):
            print(f"\n[PROMPT3B] Completed all learning steps")
            return {
                "learning_steps_list": state.learning_steps_list,
                "current_learning_step_index": current_ls_index + 1,
            }

        learning_step = state.learning_steps_list[current_ls_index]
        ls_id = learning_step.get("learning_step_id", f"LS{current_ls_index + 1}")
        ls_key = f"LS{current_ls_index + 1}"

        scene_plan = state.scene_plans.get(ls_key, [])

        print(f"[DEBUG] Scene plan count: {len(scene_plan)}")
        print(f"[DEBUG] Generating scenes for LS: {ls_id}")

        if not scene_plan:
            print(f"[WARNING] No scene plan for {ls_key}, generating default plan")
            scene_plan = [
                {
                    "scene_id": f"S{i + 1}",
                    "phase": "MICRO_LEARN",
                    "summary": "Generate scene",
                    "concept_focus": "",
                }
                for i in range(6)
            ]
            state.scene_plans[ls_key] = scene_plan

        if current_scene_index >= len(scene_plan):
            print(f"\n[PROMPT3B] Completed all scenes for {ls_key}")
            return {
                "learning_steps_list": state.learning_steps_list,
                "current_learning_step_index": current_ls_index + 1,
                "current_scene_index": 0,
                "scenes": state.scenes,
            }

        current_plan = scene_plan[current_scene_index]
        scene_id = current_plan.get("scene_id", f"S{current_scene_index + 1}")

        print(
            f"\n  Generating {ls_key}_{scene_id} ({current_scene_index + 1}/{len(scene_plan)})"
        )

        run_folder = Path(state.run_folder)

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
            prev_ls_key = f"LS{current_ls_index}"
            prev_scenes = state.scenes.get(prev_ls_key, [])
            if prev_scenes:
                previous_step_last_scene = prev_scenes[-1]

        scene_prompt = f"""
You are generating a CINEMATIC, VIRAL learning scene.

----------------------------------------
SCENE PLAN:
- Scene ID: {scene_id}
- Phase: {current_plan.get("phase", "MICRO_LEARN")}
- Summary: {current_plan.get("summary", "")}
- Concept Focus: {current_plan.get("concept_focus", "")}

----------------------------------------
STORY CONTEXT:
Title: {story_context.get("title", "")}
Premise: {story_context.get("core_premise", "")}
Characters: {json.dumps(story_context.get("characters", []))}

----------------------------------------
LEARNING STEP:
- ID: {ls_id}
- Title: {learning_step.get("title", "")}
- Concepts: {json.dumps(learning_step.get("concepts_introduced", []))}

----------------------------------------
PREVIOUS SCENE (for continuity):
{json.dumps(previous_scene) if previous_scene else "This is the first scene."}

----------------------------------------
SCENE GENERATION RULES:

1. Based on the scene plan, generate a full scene
2. Phase: {current_plan.get("phase", "MICRO_LEARN")} - follow its purpose
3. Setting: Create a vivid, engaging location
4. Characters: Use story characters naturally
5. Action: Show, don't tell
6. Dialogue: 2-4 lines, realistic and sharp
7. Learning: Teach the concept subtly within the narrative
8. Continuity: Connect naturally to previous scene

----------------------------------------
SCENE COMPLETENESS RULE:

This scene is part of a sequence of {len(scene_plan)} scenes.
Ensure the story is not prematurely concluded.

- DO NOT rush to a final resolution in early scenes
- Build tension and curiosity progressively
- Leave room for the story to develop
- Each scene should set up the next

----------------------------------------
11. HOOK SCENE RULE (CRITICAL):

* If phase == HOOK:

  * DO NOT explain any concept
  * DO NOT define arithmetic progression
  * Only show confusion, frustration, or curiosity
  * End scene with a question or hint, not an answer

12. DISCOVERY PACING RULE:

* Discovery must feel gradual, not instant
* Characters should:
  observe → doubt → test → realize
* Avoid immediate correct conclusions

13. DIALOGUE NATURALNESS RULE:

* Avoid perfect or teacher-like dialogue
* Add hesitation, partial thoughts, interruptions
* Use phrases like:
  "wait...", "maybe...", "that means...", "hold on..."

14. EXPLANATION DELAY RULE:

* Do NOT fully explain concepts in early scenes
* Spread explanation across:
  S3 → S6 gradually
* Each scene should reveal only 1 small idea

15. SCENE VARIETY RULE:

* Avoid repeating same structure:
  explanation → confirmation
* Mix:
  confusion scenes
  silent realization moments
  visual thinking (drawing, observing)

16. MICRO-TENSION RULE:

* Each scene must include:

  * a question OR
  * a doubt OR
  * a small problem
* Never allow smooth uninterrupted understanding

17. STRICT HOOK ENFORCEMENT:

* If phase contains "HOOK" (case-insensitive):

  * Absolutely NO explanation allowed
  * If any explanation appears, it is INVALID
  * Scene must end with unresolved curiosity

18. NO EARLY RESOLUTION RULE:

* The first 30–40% of scenes must NOT:

  * fully explain the concept
  * resolve the main idea
* If resolved too early → regenerate internally

----------------------------------------
OUTPUT JSON:

{{
  "scene_id": "{scene_id}",
  "phase": "{current_plan.get("phase", "MICRO_LEARN")}",
  "setting": "...",
  "characters": ["..."],
  "action": "...",
  "dialogue": ["...", "..."],
  "learning_moment": "...",
  "transition_hint": "..."
}}

Generate the complete scene now.
"""

        temp = 0.7 if current_plan.get("phase") == "HOOK" else 0.6

        result = self.llm_service.invoke(scene_prompt, temperature=temp, max_tokens=600)
        response = result["content"]

        try:
            parsed = safe_parse(response)
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
            }

        if ls_key not in state.scenes:
            state.scenes[ls_key] = []
        state.scenes[ls_key].append(scene)

        state.learning_steps_list[current_ls_index]["scenes"] = state.scenes[ls_key]

        import os

        scenes_dir = os.path.join(str(run_folder), "scenes")
        os.makedirs(scenes_dir, exist_ok=True)

        scene_filename = f"{ls_key}_{scene_id}.json"
        scene_path = os.path.join(scenes_dir, scene_filename)
        with open(scene_path, "w", encoding="utf-8") as f:
            json.dump(scene, f, indent=2, ensure_ascii=False)

        print(f"[SCENE GEN] {ls_key}_{scene_id} saved to scenes/{scene_filename}")

        next_scene_index = current_scene_index + 1

        return {
            "learning_steps_list": state.learning_steps_list,
            "scenes": state.scenes,
            "current_scene_index": next_scene_index,
        }

    def _node_execute_prompt3(self, state: PipelineState) -> Dict[str, Any]:
        """
        Execute Prompt 3 - Wrapper that calls 3A then 3B in sequence.
        Kept for backward compatibility.

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
        """
        Execute Prompt 4 - Scene Image Generation.

        Args:
            state: Current pipeline state

        Returns:
            State updates
        """
        import json

        if not state.generate_images:
            print("\n[PROMPT4] Image generation skipped by user")
            return {"image_paths": state.image_paths}

        run_folder = Path(state.run_folder)

        ls_index = state.current_learning_step_index
        scene_index = state.current_scene_index

        if ls_index >= len(state.learning_steps_list):
            print(f"\n[PROMPT4] Completed all learning steps")
            return {"image_paths": state.image_paths}

        current_ls = state.learning_steps_list[ls_index]
        scenes = current_ls.get("scenes", [])

        if scene_index >= len(scenes):
            next_ls = ls_index + 1
            if next_ls >= len(state.learning_steps_list):
                print(f"\n[PROMPT4] Completed all scenes")
                return {
                    "image_paths": state.image_paths,
                    "current_learning_step_index": next_ls,
                }
            return {
                "current_learning_step_index": next_ls,
                "current_scene_index": 0,
            }

        scene = scenes[scene_index]
        scene_id = scene.get("scene_id", f"LS{ls_index + 1}_S{scene_index + 1}")

        print(f"\n  [IMAGE] Generating for {scene_id}")

        prompt = f"""
Scene:
{json.dumps(scene)}

Generate a detailed image prompt.
Return only the text prompt.
"""

        result = self.llm_service.invoke(prompt)
        image_prompt = result["content"].strip()

        image_path = self.image_generator.generate(image_prompt)

        save_image(run_folder, ls_index, scene_index, image_path)

        state.image_paths.append(image_path)
        state.current_image_index += 1

        print(f"  ✓ Generated image {state.current_image_index}: {scene_id}")

        next_scene_index = scene_index + 1
        next_ls_index = ls_index

        if next_scene_index >= len(scenes):
            next_ls_index = ls_index + 1
            next_scene_index = 0
            print(f"  → Moving to LS{next_ls_index + 1}")

        return {
            "image_paths": state.image_paths,
            "current_scene_index": next_scene_index,
            "current_learning_step_index": next_ls_index,
        }

    def _node_check_continuation(self, state: PipelineState) -> str:
        """
        Check if we should continue loops or move to next stage.

        Args:
            state: Current pipeline state

        Returns:
            Next node name
        """
        current_prompt = state.current_prompt_id

        if current_prompt == "prompt3":
            # Check if more learning steps to process
            if state.current_learning_step_index < len(state.learning_steps_list):
                # Continue with next learning step - use new 3A/3B flow
                return "execute_prompt3a"
            else:
                # Move to image generation
                state.current_learning_step_index = 0
                state.current_scene_index = 0
                state.current_prompt_id = "prompt4"
                return "execute_prompt4"

        elif current_prompt == "prompt4":
            # Check if more scenes to process
            if not state.generate_images:
                return END

            ls_index = state.current_learning_step_index
            scene_index = state.current_scene_index

            if ls_index < len(state.learning_steps_list):
                current_ls = state.learning_steps_list[ls_index]
                scenes = current_ls.get("scenes", [])

                if scene_index < len(scenes):
                    # Continue with next scene
                    return "execute_prompt4"
                else:
                    # Move to next learning step
                    state.current_learning_step_index += 1
                    state.current_scene_index = 0

                    if state.current_learning_step_index < len(
                        state.learning_steps_list
                    ):
                        return "execute_prompt4"

            # All done
            return END

        return END

    def _node_generate_ppt(self, state: PipelineState) -> Dict[str, Any]:
        """
        Generate the final PowerPoint presentation.

        Args:
            state: Current pipeline state

        Returns:
            State updates
        """
        # Generate PPT
        output_path = self.ppt_generator.generate_ppt(
            state=state,
            learning_steps_dir=str(Path(state.run_folder) / "learning_steps"),
            output_filename="lesson_output.pptx",
        )

        state.ppt_output_path = output_path
        state.is_complete = True

        return {"ppt_output_path": output_path, "is_complete": True}

    def _parse_concepts(self, response: str) -> List[Dict[str, Any]]:
        """
        Parse the concept inventory response.

        Args:
            response: Raw LLM response

        Returns:
            List of concepts
        """
        # Try to parse as JSON
        try:
            response = response.strip()
            if response.startswith("```json"):
                response = response[7:]
            elif response.startswith("```"):
                response = response[3:]
            if response.endswith("```"):
                response = response[:-3]

            data = json.loads(response.strip())

            # Handle different JSON structures
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

        # If not JSON, return as text list
        return [{"raw_text": response}]

    def _parse_story_backbone(self, response: str) -> Dict[str, Any]:
        """
        Parse the story backbone response to extract selected story (JSON format).

        Args:
            response: Raw LLM response (JSON)

        Returns:
            Selected story dictionary
        """
        # Clean the response - remove markdown code blocks if present
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
            # Try to get selected_story first
            selected = data.get("selected_story", {})
            if selected:
                title = selected.get("title", "Selected Story")
                # Check both possible key names
                core_premise = selected.get(
                    "core_narrative_premise", ""
                ) or selected.get("core_premise", "")
                print(
                    f"  DEBUG: JSON Parsed - title: {title}, premise length: {len(core_premise)}"
                )
                return {
                    "title": title,
                    "core_premise": core_premise,
                    "raw_response": response,
                }

            # Fallback to first story in stories array
            stories = data.get("stories", [])
            if stories:
                first_story = stories[0]
                title = first_story.get("title", "Selected Story")
                core_premise = first_story.get(
                    "core_narrative_premise", ""
                ) or first_story.get("core_premise", "")
                print(
                    f"  DEBUG: JSON Parsed (fallback) - title: {title}, premise length: {len(core_premise)}"
                )
                return {
                    "title": title,
                    "core_premise": core_premise,
                    "raw_response": response,
                }

            print(f"  DEBUG: JSON Parsed - No selected_story or stories found")
            return {
                "title": "Selected Story",
                "core_premise": "",
                "raw_response": response,
            }

        except json.JSONDecodeError as e:
            print(f"  DEBUG: JSON parsing failed: {e}")
            # Fallback: parse text format
            print("  DEBUG: Trying text format fallback...")

            # Try to find story title - fix to remove prefixes like "Overview:", "Story Overview:"
            title = "Selected Story"
            title_match = re.search(
                r"(?:Title|Story)[:\s]+\*?(.+?)(?:\n|$|\*\*)", response, re.IGNORECASE
            )
            if title_match:
                title = title_match.group(1).strip()
                title = re.sub(r"^\*+|\*+$", "", title).strip()
                # Remove prefixes like "Overview:", "Story Overview:"
                title = re.sub(
                    r"^(?:Overview|Story Overview)[:\s]*",
                    "",
                    title,
                    flags=re.IGNORECASE,
                ).strip()

            # Try to find core premise - get FULL text, not truncated
            core_premise = ""
            # Look for "Core Narrative Premise:" or "Core Premise:" followed by content
            premise_match = re.search(
                r"(?:Core Narrative Premise|Core Premise)[:\s]*\n?(.+?)(?=\n\n|\n###|\n---|$)",
                response,
                re.DOTALL | re.IGNORECASE,
            )
            if premise_match:
                core_premise = premise_match.group(1).strip()
                # Don't truncate - get full story

            print(
                f"  DEBUG: Text fallback - title: {title}, premise length: {len(core_premise)}"
            )

            return {
                "title": title,
                "core_premise": core_premise,
                "raw_response": response,
            }

    def _parse_learning_steps(self, response: str) -> list:
        """
        Parse learning steps from prompt 2 output (JSON format).

        Args:
            response: Raw LLM response (JSON)

        Returns:
            List of learning step dictionaries
        """
        # Clean the response - remove markdown code blocks if present
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
            print(f"  DEBUG: Parsed {len(learning_steps)} learning steps from JSON")
            return learning_steps
        except json.JSONDecodeError as e:
            print(f"  DEBUG: JSON parsing failed: {e}")
            print("  DEBUG: Falling back to text learning-step extraction")

        # If we get here, JSON parsing failed - use text fallback
        # Add text fallback
        print("  DEBUG: JSON returned empty, trying text fallback...")

        # Parse text format - improved to extract more details
        learning_steps = []

        # Look for numbered learning steps with more context
        # Pattern: "1. Title" or "LS1 - Title" or "**Title**"
        ls_pattern = r"(?:\d+[.\s]+|LS\d+[.\s-]+)\*?([^\n]+)\*?"
        matches = list(re.finditer(ls_pattern, response, re.IGNORECASE))

        for i, match in enumerate(matches):
            title = match.group(1).strip()[:100]

            # Try to find narrative/description after the title
            # Look for text between this match and the next numbered item
            start_pos = match.end()
            next_pos = matches[i + 1].start() if i + 1 < len(matches) else len(response)
            between_text = response[start_pos:next_pos].strip()

            # Clean up the description - remove bullets, get first paragraph
            narrative = (
                between_text[:500]
                if between_text
                else f"Learning step {i + 1}: {title}"
            )
            # Remove bullet points and numbering
            narrative = re.sub(r"^[\s\d\.\-\*]+", "", narrative, flags=re.MULTILINE)
            narrative = narrative.split("\n\n")[0][:500]  # First paragraph only

            learning_steps.append(
                {
                    "learning_step_id": f"LS{i + 1}",
                    "title": title,
                    "concepts_introduced": [],  # Keep empty if not found
                    "narrative_moment": narrative,
                    "scenes": [],
                }
            )

        if learning_steps:
            print(f"  DEBUG: Text fallback found {len(learning_steps)} learning steps")
            for i, ls in enumerate(learning_steps[:3]):
                print(f"    LS{i + 1}: {ls.get('title', 'NO TITLE')[:50]}")
                print(f"    Narrative: {ls.get('narrative_moment', '')[:50]}...")

        return learning_steps

    def _parse_scenes_json(self, response: str) -> Dict[str, Any]:
        """
        Parse scenes JSON from prompt 3 response.

        Args:
            response: Raw LLM response

        Returns:
            Scenes dictionary
        """
        # Try to extract JSON
        response = response.strip()

        # Remove markdown code blocks if present
        if response.startswith("```json"):
            response = response[7:]
        elif response.startswith("```"):
            response = response[3:]

        if response.endswith("```"):
            response = response[:-3]

        response = response.strip()

        try:
            parsed_json = json.loads(response)

            # Normalize DeepSeek/OpenRouter wrapper responses
            if "response" in parsed_json:
                parsed_json = parsed_json["response"]
                print("[SCENE JSON NORMALIZED] Unwrapped 'response' field")

            if "data" in parsed_json:
                parsed_json = parsed_json["data"]
                print("[SCENE JSON NORMALIZED] Unwrapped 'data' field")

            print("[SCENE JSON NORMALIZED] Keys:", list(parsed_json.keys()))

            return parsed_json
        except json.JSONDecodeError:
            # If parsing fails, return a minimal structure
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
        test_mode: bool = False,
    ) -> PipelineState:
        """
        Run the complete pipeline.

        Args:
            chapter_name: Full name of the chapter (e.g., "Class 10 Maths Chapter 5 Arithmetic Progression")
            chapter_title: Short title (e.g., "Arithmetic Progression")
            class_level: Class level
            subject: Subject
            chapter_number: Chapter number
            medium: Language medium
            pdf_path: Path to PDF file (if already available)
            generation_mode: "full" or "ls1" for LS1-only generation
            text_model: Text model to use (currently only "deepseek" supported)
            image_model: Image model to use ("gpt-image-1.5", "fal-flux", or "fal-juggernaut")
            image_mode: "dialogue" or "overlay"
            test_mode: If True, enable human-in-the-loop checkpoints

        Returns:
            Final pipeline state
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

        # Set test_mode for human-in-the-loop checkpoints
        state.test_mode = test_mode
        if test_mode:
            print(f"[MODE] Test Mode: Human-in-the-loop checkpoints ENABLED")

        # Debug logs
        print(f"[MODEL] Text model: {text_model}")
        print(f"[MODEL] Image model: {image_model}")
        print(f"[MODE] Image rendering: {state.image_mode}")

        # Reinitialize LLM service with selected model
        self.llm_service = LLMService(model=text_model)

        # Reinitialize image generator with selected model and mode
        self.image_generator = ImageGeneratorService(
            model=image_model, image_mode=state.image_mode
        )

        # Set PDF path if provided
        if pdf_path:
            state.pdf_path = pdf_path
            state.pdf_source = "provided"

        # Create run folder
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

        # Run the graph
        config = {"configurable": {"thread_id": "storytelling-pipeline"}}

        final_state = None
        for state_update in self.graph.stream(state, config):
            final_state = state_update

        # Extract the actual state from the final state dict
        actual_state = (
            final_state.get("__root__", state)
            if isinstance(final_state, dict)
            else state
        )

        # Update metadata with learning steps count
        if actual_state.model_run_folder:
            model_run_path = Path(actual_state.model_run_folder)
            if model_run_path.exists():
                update_run_metadata(
                    model_run_path,
                    {"learning_steps": len(actual_state.learning_steps_list)},
                )

        return {
            "run_folder": actual_state.model_run_folder,
            "learning_steps_list": actual_state.learning_steps_list,
            "image_paths": actual_state.image_paths,
            "ppt_output_path": actual_state.ppt_output_path,
        }


def create_pipeline_graph() -> PipelineGraph:
    """Factory function to create PipelineGraph."""
    return PipelineGraph()
