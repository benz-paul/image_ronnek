"""
Pipeline State Model - Centralized state for LangGraph workflow.
"""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class UserInputs(BaseModel):
    """User-provided chapter information."""
    chapter_name: str = ""
    chapter_number: str = ""
    class_level: str = ""
    subject: str = ""
    medium: str = "English"


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
    
    # Prompt outputs storage
    prompt0_output: Optional[str] = None
    prompt1_output: Optional[str] = None
    prompt2_output: Optional[str] = None
    
    # Learning steps
    learning_steps_list: List[Dict[str, Any]] = Field(default_factory=list)
    learning_step_json_paths: List[str] = Field(default_factory=list)
    
    # Scene images
    image_paths: List[str] = Field(default_factory=list)
    
    # PDF handling (preserved from original)
    pdf_path: Optional[str] = None
    pdf_source: str = "local"  # "local" or "downloaded"
    
    # Output paths
    ppt_output_path: Optional[str] = None
    run_folder: str = ""
    
    # Execution tracking
    is_complete: bool = False
    error_message: Optional[str] = None
    
    # Story backbone (selected)
    selected_story: Optional[Dict[str, Any]] = None
    
    class Config:
        arbitrary_types_allowed = True


def create_initial_state(
    chapter_name: str,
    class_level: str,
    subject: str,
    chapter_number: str = "",
    medium: str = "English"
) -> PipelineState:
    """
    Create initial pipeline state with user inputs.
    
    Args:
        chapter_name: Name of the chapter
        class_level: Class (e.g., "10")
        subject: Subject (e.g., "Physics")
        chapter_number: Chapter number
        medium: Language medium
    
    Returns:
        Initialized PipelineState
    """
    user_inputs = UserInputs(
        chapter_name=chapter_name,
        chapter_number=chapter_number,
        class_level=class_level,
        subject=subject,
        medium=medium
    )
    
    return PipelineState(
        user_inputs=user_inputs,
        current_prompt_id="prompt0"
    )


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
