"""
Pipeline State Model - Centralized state for LangGraph workflow.
"""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class UserInputs(BaseModel):
    """User-provided chapter information."""

    chapter_name: str = (
        ""  # Full name like "Class 10 Maths Chapter 5 Arithmetic Progression"
    )
    chapter_title: str = ""  # Just "Arithmetic Progression"
    chapter_number: str = ""
    class_level: str = ""
    subject: str = ""
    medium: str = "English"


class SceneSelection(BaseModel):
    """Represents a selected scene with its learning step and scene indices."""

    ls_index: int = 0
    scene_index: int = 0
    scene_id: str = ""
    scene_goal: str = ""


class PipelineState(BaseModel):
    """
    Centralized pipeline state that persists across all LangGraph nodes.
    This state tracks the entire pipeline execution.
    """

    # User inputs
    user_inputs: UserInputs = Field(default_factory=UserInputs)

    # Current execution state
    current_prompt_id: str = "prompt0"  # prompt0, prompt1, prompt2, prompt3, prompt4
    current_learning_step_index: int = 0
    current_scene_index: int = 0

    # Prompt outputs storage (parsed JSON)
    prompt0_output: Optional[Dict[str, Any]] = None
    prompt1_output: Optional[Dict[str, Any]] = None
    prompt2_output: Optional[Dict[str, Any]] = None

    # Learning steps
    learning_steps_list: List[Dict[str, Any]] = Field(default_factory=list)
    learning_step_json_paths: List[str] = Field(default_factory=list)

    # Structured scenes mapping: {"LS1": [scene1, scene2], "LS2": [...], ...}
    scenes: Dict[str, List[Dict[str, Any]]] = Field(default_factory=dict)

    # Scene planning (Prompt 3A)
    scene_plans: Dict[str, List[Dict[str, Any]]] = Field(default_factory=dict)
    current_scene_index: int = 0

    # Human-in-the-loop: Learning Step Selection
    ls_selection_made: bool = False
    selected_learning_steps: List[int] = Field(
        default_factory=list
    )  # List of LS indices (0-based)

    # Human-in-the-loop: Scene Selection
    scene_selection_made: bool = False
    selected_scenes: List[SceneSelection] = Field(default_factory=list)

    # Scene images
    image_paths: List[str] = Field(default_factory=list)
    current_image_index: int = 0  # Dedicated counter for image generation

    # User decision for image generation
    generate_images: bool = False
    generate_ppt: bool = False
    generation_mode: str = "full"  # "full" or "ls1"

    # Image mode: "single" or "multiple" scenes
    image_generation_scope: str = "single"

    # Overlay mode: "overlay" (speech bubbles) or "dialogue_in_image" (text in image)
    overlay_mode: str = "overlay"

    # PDF handling (preserved from original)
    pdf_path: Optional[str] = None
    pdf_source: str = "local"  # "local" or "downloaded"

    # Output paths
    ppt_output_path: Optional[str] = None
    run_folder: str = ""
    model_run_folder: Optional[str] = None  # Model-based output folder

    # Image quality setting
    image_quality: str = "low"

    # Text model selection - currently only deepseek is supported
    text_model: str = "deepseek"  # "deepseek" (via OpenRouter)

    # Image model selection
    image_model: str = (
        "gpt-image-1.5"  # "gpt-image-1.5", "fal-flux", or "fal-juggernaut"
    )

    # Image mode selection (dialogue inside image vs overlay)
    image_mode: str = "dialogue"  # "dialogue" or "overlay"

    # Test mode flag - enables human-in-the-loop checkpoints
    test_mode: bool = False

    # Execution tracking
    is_complete: bool = False
    error_message: Optional[str] = None

    # Story backbone (selected)
    selected_story: Optional[Dict[str, Any]] = None

    # Checkpoint tracking for logging
    checkpoint_history: List[str] = Field(default_factory=list)

    class Config:
        arbitrary_types_allowed = True


def create_initial_state(
    chapter_name: str,
    class_level: str,
    subject: str,
    chapter_number: str = "",
    chapter_title: str = "",
    medium: str = "English",
) -> PipelineState:
    """
    Create initial pipeline state with user inputs.

    Args:
        chapter_name: Full name of the chapter (e.g., "Class 10 Maths Chapter 5 Arithmetic Progression")
        chapter_title: Short title (e.g., "Arithmetic Progression")
        class_level: Class (e.g., "10")
        subject: Subject (e.g., "Physics")
        chapter_number: Chapter number
        medium: Language medium

    Returns:
        Initialized PipelineState
    """
    user_inputs = UserInputs(
        chapter_name=chapter_name,
        chapter_title=chapter_title,
        chapter_number=chapter_number,
        class_level=class_level,
        subject=subject,
        medium=medium,
    )

    return PipelineState(user_inputs=user_inputs, current_prompt_id="prompt0")


def get_learning_step(state: PipelineState, index: int) -> Optional[Dict[str, Any]]:
    """Get a learning step by index."""
    if 0 <= index < len(state.learning_steps_list):
        return state.learning_steps_list[index]
    return None


def get_current_learning_step(state: PipelineState) -> Optional[Dict[str, Any]]:
    """Get the current learning step being processed."""
    return get_learning_step(state, state.current_learning_step_index)


def get_next_learning_step(state: PipelineState) -> Optional[Dict[str, Any]]:
    """Get the next learning step for transition."""
    return get_learning_step(state, state.current_learning_step_index + 1)


def get_previous_learning_step(state: PipelineState) -> Optional[Dict[str, Any]]:
    """Get the previous learning step for continuity."""
    if state.current_learning_step_index > 0:
        return get_learning_step(state, state.current_learning_step_index - 1)
    return None


def get_scenes_for_current_learning_step(state: PipelineState) -> List[Dict[str, Any]]:
    """Get scenes from current learning step JSON."""
    current_ls = get_current_learning_step(state)
    if current_ls and "scenes" in current_ls:
        return current_ls["scenes"]
    return []


def get_current_scene(state: PipelineState) -> Optional[Dict[str, Any]]:
    """Get the current scene being processed."""
    scenes = get_scenes_for_current_learning_step(state)
    if 0 <= state.current_scene_index < len(scenes):
        return scenes[state.current_scene_index]
    return None


def get_selected_learning_steps(state: PipelineState) -> List[Dict[str, Any]]:
    """Get the list of selected learning steps from the full list."""
    if not state.selected_learning_steps:
        return []
    return [
        state.learning_steps_list[i]
        for i in state.selected_learning_steps
        if i < len(state.learning_steps_list)
    ]


def is_learning_step_selected(state: PipelineState, ls_index: int) -> bool:
    """Check if a learning step is selected."""
    if not state.ls_selection_made:
        return True  # If no selection made, all are selected
    return ls_index in state.selected_learning_steps


def is_scene_selected(state: PipelineState, ls_index: int, scene_index: int) -> bool:
    """Check if a scene is selected."""
    if not state.scene_selection_made:
        return True  # If no selection made, all are selected
    for sel in state.selected_scenes:
        if sel.ls_index == ls_index and sel.scene_index == scene_index:
            return True
    return False
