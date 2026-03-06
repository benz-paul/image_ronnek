"""
Model Output Manager - Handles run-based output directory management.

New simplified structure:
outputs/
run_{timestamp}/
  inputs/
    config.json       # Model used, generation mode, user choices
  prompts/
    prompt0.txt     # Concept extraction
    prompt1.txt     # Story backbone
    prompt2.txt     # Learning steps
    prompt3_LS1.txt # Scenes for LS1
    prompt3_LS2.txt # Scenes for LS2, etc.
  raw_outputs/
    prompt0.txt     # Raw LLM response
    prompt1.txt
    prompt2.txt
  parsed/
    concepts.json    # Parsed concept inventory
    story.json       # Parsed story backbone
    learning_steps.json  # Parsed learning steps
  scenes/
    LS1.json        # Scenes for Learning Step 1
    LS2.json
    ...
  images/
    LS1_S1.png      # Generated images
    LS1_S2.png
    ...
  ppt/
    lesson.pptx     # Generated PowerPoint
  summary.json     # Run statistics
"""

import os
import json
from pathlib import Path
from typing import Optional, Dict, Any
from datetime import datetime


def get_base_output_dir() -> Path:
    """Get the base output directory."""
    return Path("outputs")


def create_run_folder(
    model_name: str = "",
    chapter: str = "",
    class_level: str = "",
    subject: str = "",
    generation_mode: str = "full",
    generate_images: bool = False,
    text_model: str = "",
    image_model: str = "",
    image_mode: str = "dialogue",
) -> Path:
    """
    Create a new run folder with timestamp.

    Creates: outputs/run_YYYYMMDD_HHMMSS/

    Args:
        model_name: Name of the model
        chapter: Chapter name
        class_level: Class level
        subject: Subject
        generation_mode: "ls1" or "full"
        generate_images: Whether images were generated
        text_model: Text model used
        image_model: Image model used
        image_mode: Image mode ("dialogue" or "overlay")

    Returns:
        Path to the newly created run folder
    """
    base_dir = get_base_output_dir()

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_folder_name = f"run_{timestamp}"
    run_folder = base_dir / run_folder_name

    # Create main run folder
    run_folder.mkdir(parents=True, exist_ok=True)

    # Create subdirectories
    subdirs = ["inputs", "prompts", "raw_outputs", "parsed", "scenes", "images", "ppt"]
    for subdir in subdirs:
        (run_folder / subdir).mkdir(exist_ok=True)

    # Save configuration
    config = {
        "timestamp": timestamp,
        "chapter": chapter,
        "class_level": class_level,
        "subject": subject,
        "generation_mode": generation_mode,
        "generate_images": generate_images,
        "text_model": text_model,
        "image_model": image_model,
        "image_mode": image_mode,
    }

    config_path = run_folder / "inputs" / "config.json"
    with open(config_path, "w") as f:
        json.dump(config, f, indent=2)

    return run_folder


def save_prompt(
    run_folder: Path, prompt_num: int, content: str, ls_index: int = None
) -> None:
    """
    Save injected prompt to prompts folder.

    Args:
        run_folder: Path to run folder
        prompt_num: Prompt number (0-4)
        content: Prompt content
        ls_index: For prompt3, the learning step index
    """
    prompts_dir = run_folder / "prompts"

    if prompt_num == 3 and ls_index is not None:
        filename = f"prompt3_LS{ls_index + 1}.txt"
    else:
        filename = f"prompt{prompt_num}.txt"

    filepath = prompts_dir / filename
    filepath.write_text(content, encoding="utf-8")


def save_raw_output(run_folder: Path, prompt_num: int, content: str) -> None:
    """
    Save raw LLM output to raw_outputs folder.

    Args:
        run_folder: Path to run folder
        prompt_num: Prompt number (0-4)
        content: Raw LLM response
    """
    raw_dir = run_folder / "raw_outputs"
    filepath = raw_dir / f"prompt{prompt_num}.txt"
    filepath.write_text(content, encoding="utf-8")


def save_parsed(run_folder: Path, data_type: str, data: Any) -> None:
    """
    Save parsed data to parsed folder.

    Args:
        run_folder: Path to run folder
        data_type: Type of data ("concepts", "story", "learning_steps")
        data: Parsed data (dict or list)
    """
    parsed_dir = run_folder / "parsed"
    filepath = parsed_dir / f"{data_type}.json"

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def save_scenes(run_folder: Path, ls_index: int, scenes_data: Any) -> None:
    """
    Save scenes for a learning step with per-scene files.

    Structure:
    scenes/LS1_S1.json
    scenes/LS1_S2.json
    ...

    Args:
        run_folder: Path to run folder
        ls_index: Learning step index (0-based)
        scenes_data: Scenes data (dict with "scenes" key or list)
    """
    import os

    scenes_dir = run_folder / "scenes"
    scenes_dir.mkdir(parents=True, exist_ok=True)

    # Handle both dict and list formats
    if isinstance(scenes_data, dict):
        scenes = scenes_data.get("scenes", [])
    else:
        scenes = scenes_data

    ls_key = f"LS{ls_index + 1}"
    for i, scene in enumerate(scenes):
        scene_id = scene.get("scene_id", f"S{i + 1}")
        scene_filename = f"{ls_key}_{scene_id}.json"
        scene_filepath = scenes_dir / scene_filename

        with open(scene_filepath, "w", encoding="utf-8") as f:
            json.dump(scene, f, indent=2, ensure_ascii=False)

        print(f"[SCENE STORAGE] {ls_key}_{scene_id} saved to scenes/{scene_filename}")


def save_image(
    run_folder: Path,
    ls_index: int,
    scene_index: int,
    image_data: bytes = None,
    image_path: str = None,
    image_prompt: str = None,
) -> str:
    """
    Save generated image.

    Args:
        run_folder: Path to run folder
        ls_index: Learning step index (0-based)
        scene_index: Scene index (0-based)
        image_data: Image binary data (if generating)
        image_path: Path to existing image (if copying)
        image_prompt: Prompt used for generation

    Returns:
        Path to saved image
    """
    images_dir = run_folder / "images"
    image_filename = f"LS{ls_index + 1}_S{scene_index + 1}.png"
    image_filepath = images_dir / image_filename

    if image_data:
        image_filepath.write_bytes(image_data)
    elif image_path and Path(image_path).exists():
        import shutil

        shutil.copy(image_path, image_filepath)

    # Save image prompt
    if image_prompt:
        prompt_filepath = images_dir / f"LS{ls_index + 1}_S{scene_index + 1}.txt"
        prompt_filepath.write_text(image_prompt, encoding="utf-8")

    print(f"[IMAGE] Saved LS{ls_index + 1}_S{scene_index + 1}.png")

    return str(image_filepath)


def save_ppt(run_folder: Path, ppt_path: str) -> None:
    """
    Save generated PowerPoint.

    Args:
        run_folder: Path to run folder
        ppt_path: Path to PPT file
    """
    import shutil

    ppt_dir = run_folder / "ppt"
    output_path = ppt_dir / "lesson.pptx"

    if Path(ppt_path).exists():
        shutil.copy(ppt_path, output_path)


def save_summary(run_folder: Path, summary: Dict[str, Any]) -> None:
    """
    Save run summary statistics.

    Args:
        run_folder: Path to run folder
        summary: Summary data
    """
    summary_path = run_folder / "summary.json"

    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)


def update_run_metadata(run_folder: Path, updates: Dict[str, Any]) -> None:
    """
    Update config.json with new values.

    Args:
        run_folder: Path to run folder
        updates: Dictionary of fields to update
    """
    config_path = run_folder / "inputs" / "config.json"

    if config_path.exists():
        with open(config_path, "r") as f:
            config = json.load(f)
    else:
        config = {}

    config.update(updates)

    with open(config_path, "w") as f:
        json.dump(config, f, indent=2)


# ============================================================================
# LEGACY FUNCTIONS - For backward compatibility
# ============================================================================


def get_model_output_dir(model_name: str) -> Path:
    """Legacy function - returns base output dir."""
    return get_base_output_dir()


def get_image_quality_folder(model_name: str, quality: str = "low") -> Path:
    """Legacy function - returns images folder."""
    return get_base_output_dir() / "images"


def get_current_run_folder(model_name: str = None) -> Optional[Path]:
    """Get the most recent run folder."""
    base_dir = get_base_output_dir()

    if not base_dir.exists():
        return None

    run_folders = []
    for item in base_dir.iterdir():
        if item.is_dir() and item.name.startswith("run_"):
            run_folders.append(item)

    if not run_folders:
        return None

    # Sort by name (timestamp)
    run_folders.sort(key=lambda x: x.name, reverse=True)
    return run_folders[0]


def get_images_dir(run_folder: Path) -> Path:
    """Get images directory."""
    return run_folder / "images"


def get_model_type(model_name: str) -> str:
    """Legacy function."""
    return "text_models"


def sanitize_folder_name(name: str) -> str:
    """Legacy function."""
    return name.replace("/", "_").replace(".", "_").replace(" ", "_").lower()


def get_existing_run_numbers(model_name: str) -> list:
    """Legacy function."""
    return []


def get_model_run_folder(model_name: str) -> Path:
    """Legacy function - returns base output dir."""
    return get_base_output_dir()
