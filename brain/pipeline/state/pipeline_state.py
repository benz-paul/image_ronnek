"""
Pipeline State Model - Centralized state for LangGraph workflow.
"""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class UserInputs(BaseModel):
    """User-provided chapter information."""

    chapter_name: str = ""
    chapter_title: str = ""
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
    """

    # User inputs
    user_inputs: UserInputs = Field(default_factory=UserInputs)

    # Current execution state
    current_prompt_id: str = "prompt0"
    current_learning_step_index: int = 0
    current_scene_index: int = 0

    # Prompt outputs storage (parsed JSON)
    prompt0_output: Optional[Dict[str, Any]] = None
    prompt1_output: Optional[Dict[str, Any]] = None
    prompt2_output: Optional[Dict[str, Any]] = None

    # Story backbone (selected from Prompt 1 output)
    selected_story: Optional[Dict[str, Any]] = None

    # -------------------------------------------------------------------------
    # CHARACTER REGISTRY — ROOT FIX FOR CHARACTER DRIFT
    # Extracted from Prompt 1's characters[] array and stored here.
    # Injected as [CHARACTER_REGISTRY] into Prompt 2, Prompt 3A, Prompt 3B,
    # and Prompt 4 on every call so the image model always gets locked
    # visual_description strings and never drifts between scenes.
    # Format: list of dicts, each with:
    #   name, role, personality, visual_description, gender, voice_id
    # -------------------------------------------------------------------------
    character_registry: List[Dict[str, Any]] = Field(default_factory=list)

    # -------------------------------------------------------------------------
    # NARRATOR VOICE — Amazon Polly voice ID for the scene narrator
    # Always "Matthew" (neutral US English male).
    # Injected into Prompt 3B so narrator_audio_text always references the
    # same Polly voice across all scenes.
    # -------------------------------------------------------------------------
    narrator_voice_id: str = "Matthew"

    # -------------------------------------------------------------------------
    # ART STYLE ANCHOR — ROOT FIX FOR STYLE INCONSISTENCY
    # Set once after Prompt 1, appended to every Prompt 4 image call.
    # Never changes during a run so image model always picks the same style.
    # -------------------------------------------------------------------------
    art_style: str = (
        "Studio Ghibli inspired 2D illustration, warm color palette, "
        "clean anime line art, consistent character designs, "
        "soft lighting, educational comic style"
    )

    # -------------------------------------------------------------------------
    # STORY SUMMARY — ROLLING CONTEXT ACCUMULATOR
    # Grows by one bullet point per scene as scenes are generated.
    # Passed as [STORY_SUMMARY] into each Prompt 3B call so every scene
    # knows what has already happened in the story.
    # -------------------------------------------------------------------------
    story_summary: str = ""

    # Learning steps
    learning_steps_list: List[Dict[str, Any]] = Field(default_factory=list)
    active_learning_steps: List[Dict[str, Any]] = Field(default_factory=list)
    learning_step_json_paths: List[str] = Field(default_factory=list)

    # Structured scenes mapping: {"LS1": [scene1, scene2], ...}
    scenes: Dict[str, List[Dict[str, Any]]] = Field(default_factory=dict)

    # Scene planning (Prompt 3A)
    scene_plans: Dict[str, List[Dict[str, Any]]] = Field(default_factory=dict)

    # Human-in-the-loop: Learning Step Selection
    ls_selection_made: bool = False
    selected_learning_steps: List[int] = Field(default_factory=list)

    # Human-in-the-loop: Scene Selection
    scene_selection_made: bool = False
    selected_scenes: List[SceneSelection] = Field(default_factory=list)

    # Scene images
    image_paths: List[str] = Field(default_factory=list)
    current_image_index: int = 0
    prompt4_iterations: int = 0

    # generate_images defaults to False.
    # ONLY set to True when the user answers "y" in main.py ask_generate_images().
    # Never overridden inside the graph nodes.
    generate_images: bool = False
    # generate_audio controls Polly TTS — set from main.py ask_generate_audio()
    generate_audio: bool = True
    generate_ppt: bool = False
    generation_mode: str = "full"

    image_generation_scope: str = "single"
    scene_generation_scope: str = "multiple"
    total_images: int = 0
    overlay_mode: str = "overlay"

    # PDF handling
    pdf_path: Optional[str] = None
    pdf_source: str = "local"

    # Output paths
    ppt_output_path: Optional[str] = None
    run_folder: str = ""
    model_run_folder: Optional[str] = None

    # Model settings
    image_quality: str = "low"
    text_model: str = "deepseek"
    image_model: str = "gpt-image-1.5"

    # image_mode is always "dialogue" — overlay was removed.
    # Dialogue text is rendered directly inside the scene image by the model.
    image_mode: str = "dialogue"

    # Execution control
    test_mode: bool = False
    is_complete: bool = False
    single_scene_done: bool = False
    error_message: Optional[str] = None

    # Checkpoint tracking
    checkpoint_history: List[str] = Field(default_factory=list)

    # -------------------------------------------------------------------------
    # AUDIO MANIFEST — Built at end of pipeline (no actual audio generation)
    # Maps scene_id → { narrator: {text, voice_id, audio_file}, characters: [...] }
    # Written to run_folder/audio/audio_manifest.json after all scenes are done.
    # Used by tools/generate_audio.py to produce Polly MP3 files.
    # -------------------------------------------------------------------------
    audio_manifest: Dict[str, Any] = Field(default_factory=dict)

    # -------------------------------------------------------------------------
    # STORY BIBLE — Set after Prompt 1, available to all downstream nodes
    # Contains: academic_context, art_style, character_registry, story_backbone
    # -------------------------------------------------------------------------
    story_bible: Dict[str, Any] = Field(default_factory=dict)

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
    """Create initial pipeline state with user inputs."""
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
    if 0 <= index < len(state.learning_steps_list):
        return state.learning_steps_list[index]
    return None


def get_current_learning_step(state: PipelineState) -> Optional[Dict[str, Any]]:
    return get_learning_step(state, state.current_learning_step_index)


def get_next_learning_step(state: PipelineState) -> Optional[Dict[str, Any]]:
    return get_learning_step(state, state.current_learning_step_index + 1)


def get_previous_learning_step(state: PipelineState) -> Optional[Dict[str, Any]]:
    if state.current_learning_step_index > 0:
        return get_learning_step(state, state.current_learning_step_index - 1)
    return None


def get_scenes_for_current_learning_step(state: PipelineState) -> List[Dict[str, Any]]:
    current_ls = get_current_learning_step(state)
    if current_ls and "scenes" in current_ls:
        return current_ls["scenes"]
    return []


def get_current_scene(state: PipelineState) -> Optional[Dict[str, Any]]:
    scenes = get_scenes_for_current_learning_step(state)
    if 0 <= state.current_scene_index < len(scenes):
        return scenes[state.current_scene_index]
    return None


def get_selected_learning_steps(state: PipelineState) -> List[Dict[str, Any]]:
    if not state.selected_learning_steps:
        return []
    return [
        state.learning_steps_list[i]
        for i in state.selected_learning_steps
        if i < len(state.learning_steps_list)
    ]


def is_learning_step_selected(state: PipelineState, ls_index: int) -> bool:
    if not state.ls_selection_made:
        return True
    return ls_index in state.selected_learning_steps


def is_scene_selected(state: PipelineState, ls_index: int, scene_index: int) -> bool:
    if not state.scene_selection_made:
        return True
    for sel in state.selected_scenes:
        if sel.ls_index == ls_index and sel.scene_index == scene_index:
            return True
    return False


def format_character_registry_for_prompt(character_registry: List[Dict[str, Any]]) -> str:
    """
    Format the character registry list as a compact JSON block for prompt injection.
    Called from every node that needs to pass [CHARACTER_REGISTRY] to the LLM.
    Returns "[]" when registry is empty so prompts never receive a blank placeholder.
    """
    if not character_registry:
        return "[]"
    import json
    return json.dumps(character_registry, indent=2, ensure_ascii=False)