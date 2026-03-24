"""
Model Output Manager - Handles run-based output directory management.

outputs/
  run_{YYYYMMDD_HHMMSS}/
    inputs/
      config.json              ← chapter metadata, model choices, flags
      chapter_text.txt         ← extracted PDF text (for debugging)
    prompts/
      prompt0.txt              ← injected prompt sent to LLM
      prompt1.txt
      prompt2.txt
      prompt3a_LS1.txt         ← scene plan prompt per LS
      prompt3b_LS1_S1.txt      ← individual scene gen prompt per scene
      prompt4_LS1_S1.txt       ← image prompt per scene
      ...
    raw_outputs/
      prompt0.txt              ← raw LLM response (before JSON parsing)
      prompt1.txt
      prompt3b_LS1_S1.txt
      ...
    parsed/
      concept_inventory.json   ← parsed Prompt 0 output
      story_backbone.json      ← parsed Prompt 1 output
      learning_steps.json      ← parsed Prompt 2 output
      scene_plan_LS1.json      ← parsed Prompt 3A output per LS
      scenes_LS1.json          ← all scenes for LS1 (combined)
      scenes_full.json         ← all scenes across all LS (master)
      image_prompts.json       ← all image prompts (Prompt 4)
    scenes/
      LS1/
        LS1_S1.json            ← individual scene JSON (includes narrator_audio_text)
        LS1_S2.json
      LS2/
        LS2_S1.json
        ...
    images/
      LS1/
        LS1_S1.png             ← generated scene image
        LS1_S2.png
      LS2/
        LS2_S1.png
        ...
    audio/
      LS1/
        LS1_S1/
          narrator.mp3         ← Polly TTS for narrator_audio_text
          char_arjun.mp3       ← Polly TTS per character dialogue
          char_priya.mp3
        LS1_S2/
          ...
      LS2/
        ...
      manifest.json            ← maps scene_id → { narrator: path, characters: {id: path} }
    ppt/
      lesson.pptx              ← final PowerPoint
    logs/
      pipeline.log             ← all console + debug output for this run
    summary.json               ← run stats: LS count, scene count, image count, audio count, duration
"""

import os
import json
import shutil
from pathlib import Path
from typing import Optional, Dict, Any, List
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
    """Create a new timestamped run folder under outputs/ with full subdirectory layout."""
    base_dir = get_base_output_dir()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_folder = base_dir / f"run_{timestamp}"
    run_folder.mkdir(parents=True, exist_ok=True)

    # Create all subdirectories
    for subdir in [
        "inputs",
        "prompts",
        "raw_outputs",
        "parsed",
        "scenes",
        "images",
        "audio",
        "ppt",
        "logs",
    ]:
        (run_folder / subdir).mkdir(exist_ok=True)

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
    with open(run_folder / "inputs" / "config.json", "w") as f:
        json.dump(config, f, indent=2)

    return run_folder


def save_chapter_text(run_folder: Path, text: str) -> None:
    """Save extracted PDF chapter text to inputs/ for debugging."""
    inputs_dir = run_folder / "inputs"
    inputs_dir.mkdir(parents=True, exist_ok=True)
    (inputs_dir / "chapter_text.txt").write_text(text, encoding="utf-8")


def save_prompt(
    run_folder: Path,
    prompt_num: int,
    content: str,
    ls_index: int = None,
    scene_index: int = None,
    prompt_variant: str = None,
) -> None:
    """
    Save injected prompt to prompts/ folder.

    Naming scheme:
      prompt0.txt
      prompt1.txt
      prompt2.txt
      prompt3a_LS1.txt         (3A scene plan, ls_index given)
      prompt3b_LS1_S1.txt      (3B single scene, ls_index + scene_index given)
      prompt4_LS1_S1.txt       (4 image prompt, ls_index + scene_index given)
    """
    prompts_dir = run_folder / "prompts"
    prompts_dir.mkdir(parents=True, exist_ok=True)

    if prompt_num == 3 and prompt_variant == "a" and ls_index is not None:
        filename = f"prompt3a_LS{ls_index + 1}.txt"
    elif prompt_num == 3 and prompt_variant == "b" and ls_index is not None and scene_index is not None:
        filename = f"prompt3b_LS{ls_index + 1}_S{scene_index + 1}.txt"
    elif prompt_num == 3 and ls_index is not None:
        # Legacy fallback
        filename = f"prompt3_LS{ls_index + 1}.txt"
    elif prompt_num == 4 and ls_index is not None and scene_index is not None:
        filename = f"prompt4_LS{ls_index + 1}_S{scene_index + 1}.txt"
    else:
        filename = f"prompt{prompt_num}.txt"

    (prompts_dir / filename).write_text(content, encoding="utf-8")


def save_raw_output(
    run_folder: Path,
    prompt_num: int,
    content: str,
    ls_index: int = None,
    scene_index: int = None,
    prompt_variant: str = None,
) -> None:
    """
    Save raw LLM output to raw_outputs/ folder.
    Uses the same naming scheme as save_prompt().
    """
    raw_output_dir = run_folder / "raw_outputs"
    raw_output_dir.mkdir(parents=True, exist_ok=True)

    if prompt_num == 3 and prompt_variant == "a" and ls_index is not None:
        filename = f"prompt3a_LS{ls_index + 1}.txt"
    elif prompt_num == 3 and prompt_variant == "b" and ls_index is not None and scene_index is not None:
        filename = f"prompt3b_LS{ls_index + 1}_S{scene_index + 1}.txt"
    elif prompt_num == 3 and ls_index is not None:
        filename = f"prompt3_LS{ls_index + 1}.txt"
    elif prompt_num == 4 and ls_index is not None and scene_index is not None:
        filename = f"prompt4_LS{ls_index + 1}_S{scene_index + 1}.txt"
    else:
        filename = f"prompt{prompt_num}.txt"

    (raw_output_dir / filename).write_text(content, encoding="utf-8")


def save_parsed(run_folder: Path, data_type: str, data: Any) -> None:
    """
    Save parsed JSON data to parsed/ folder.

    data_type examples:
      "concept_inventory", "story_backbone", "learning_steps",
      "scene_plan_LS1", "scenes_LS1", "scenes_full", "image_prompts"
    """
    parsed_dir = run_folder / "parsed"
    parsed_dir.mkdir(parents=True, exist_ok=True)
    with open(parsed_dir / f"{data_type}.json", "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def save_scenes(run_folder: Path, ls_index: int, scenes_data: Any) -> None:
    """
    Save scenes for a learning step.

    Each scene gets its own file under scenes/LS{n}/.
    Also saves the combined LS scenes to parsed/scenes_LS{n}.json.
    """
    ls_key = f"LS{ls_index + 1}"

    # Per-scene files under scenes/LS{n}/
    ls_scenes_dir = run_folder / "scenes" / ls_key
    ls_scenes_dir.mkdir(parents=True, exist_ok=True)

    scenes = (
        scenes_data.get("scenes", []) if isinstance(scenes_data, dict) else scenes_data
    )

    for i, scene in enumerate(scenes):
        scene_id = scene.get("scene_id", f"S{i + 1}")
        # Normalise scene_id to have LS prefix if missing
        if not scene_id.startswith(ls_key):
            scene_id = f"{ls_key}_{scene_id}"
        scene_filename = f"{scene_id}.json"
        with open(ls_scenes_dir / scene_filename, "w", encoding="utf-8") as f:
            json.dump(scene, f, indent=2, ensure_ascii=False)
        print(f"[SCENE STORAGE] {scene_id} saved to scenes/{ls_key}/{scene_filename}")

    # Combined LS scenes in parsed/
    save_parsed(run_folder, f"scenes_{ls_key}", scenes)


def save_image(
    run_folder: Path,
    ls_index: int,
    scene_index: int,
    source_image_path: str,
    image_prompt: str = None,
) -> str:
    """
    Copy a generated image into images/LS{n}/ for this run.

    Args:
        run_folder:        Path to the run folder
        ls_index:          0-based learning step index
        scene_index:       0-based scene index
        source_image_path: Path returned by image_generator.generate()
        image_prompt:      Optional prompt text — saved as a companion .txt file

    Returns:
        Path to the saved image in images/LS{n}/
    """
    ls_key = f"LS{ls_index + 1}"
    images_ls_dir = run_folder / "images" / ls_key
    images_ls_dir.mkdir(parents=True, exist_ok=True)

    image_filename = f"LS{ls_index + 1}_S{scene_index + 1}.png"
    image_filepath = images_ls_dir / image_filename

    src = Path(source_image_path)
    if src.exists():
        shutil.copy2(src, image_filepath)
    else:
        print(f"[WARNING] save_image: source not found: {source_image_path}")

    if image_prompt:
        prompt_filepath = images_ls_dir / f"LS{ls_index + 1}_S{scene_index + 1}.txt"
        prompt_filepath.write_text(image_prompt, encoding="utf-8")

    print(f"[IMAGE] Saved {ls_key}_S{scene_index + 1}.png → images/{ls_key}/")
    return str(image_filepath)


def save_audio(
    run_folder: Path,
    ls_index: int,
    scene_id: str,
    audio_data: bytes,
    audio_type: str,
    char_id: str = None,
) -> str:
    """
    Save a Polly-generated audio file to audio/LS{n}/{scene_id}/.

    Args:
        run_folder:  Path to the run folder
        ls_index:    0-based learning step index
        scene_id:    Scene ID string (e.g. "LS1_S1")
        audio_data:  Raw MP3 bytes from Polly AudioStream
        audio_type:  "narrator" or "character"
        char_id:     Character ID (required when audio_type == "character")

    Returns:
        Path to the saved .mp3 file
    """
    ls_key = f"LS{ls_index + 1}"
    audio_scene_dir = run_folder / "audio" / ls_key / scene_id
    audio_scene_dir.mkdir(parents=True, exist_ok=True)

    if audio_type == "narrator":
        filename = "narrator.mp3"
    elif audio_type == "character" and char_id:
        safe_id = char_id.lower().replace(" ", "_")
        filename = f"char_{safe_id}.mp3"
    else:
        filename = f"{audio_type}.mp3"

    filepath = audio_scene_dir / filename
    filepath.write_bytes(audio_data)
    print(f"[AUDIO] Saved {audio_type} audio → audio/{ls_key}/{scene_id}/{filename}")
    return str(filepath)


def save_audio_manifest(run_folder: Path, manifest: Dict[str, Any]) -> None:
    """Save the audio manifest mapping scene_id → audio file paths."""
    audio_dir = run_folder / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)
    with open(audio_dir / "manifest.json", "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)
    print(f"[AUDIO] Manifest saved → audio/manifest.json")


def save_ppt(run_folder: Path, ppt_path: str) -> None:
    """Copy generated PowerPoint into ppt/ subfolder."""
    ppt_dir = run_folder / "ppt"
    ppt_dir.mkdir(exist_ok=True)
    if Path(ppt_path).exists():
        shutil.copy2(ppt_path, ppt_dir / "lesson.pptx")


def save_summary(run_folder: Path, summary: Dict[str, Any]) -> None:
    """Save run summary statistics to summary.json."""
    with open(run_folder / "summary.json", "w") as f:
        json.dump(summary, f, indent=2)


def update_run_metadata(run_folder: Path, updates: Dict[str, Any]) -> None:
    """Update config.json with new values."""
    config_path = run_folder / "inputs" / "config.json"
    config = {}
    if config_path.exists():
        with open(config_path) as f:
            config = json.load(f)
    config.update(updates)
    with open(config_path, "w") as f:
        json.dump(config, f, indent=2)


def get_images_for_run(run_folder: Path) -> List[str]:
    """Return sorted list of all image paths in images/ for this run."""
    images_dir = run_folder / "images"
    if not images_dir.exists():
        return []
    paths = []
    for ls_dir in sorted(images_dir.iterdir()):
        if ls_dir.is_dir():
            for img in sorted(ls_dir.glob("*.png")):
                paths.append(str(img))
    return paths


def get_audio_manifest(run_folder: Path) -> Optional[Dict]:
    """Load and return the audio manifest for this run, or None if not generated yet."""
    manifest_path = run_folder / "audio" / "manifest.json"
    if not manifest_path.exists():
        return None
    with open(manifest_path, encoding="utf-8") as f:
        return json.load(f)


# ============================================================================
# LEGACY / COMPATIBILITY FUNCTIONS
# Keep these intact so existing callers don't break.
# ============================================================================


def get_base_output_dir() -> Path:
    """Get the base output directory."""
    return Path("outputs")


def get_model_output_dir(model_name: str) -> Path:
    return get_base_output_dir()


def get_image_quality_folder(model_name: str, quality: str = "low") -> Path:
    return get_base_output_dir() / "images"


def get_current_run_folder(model_name: str = None) -> Optional[Path]:
    """Return the most recent run_ folder."""
    base_dir = get_base_output_dir()
    if not base_dir.exists():
        return None
    run_folders = sorted(
        [d for d in base_dir.iterdir() if d.is_dir() and d.name.startswith("run_")],
        key=lambda x: x.name,
        reverse=True,
    )
    return run_folders[0] if run_folders else None


def get_images_dir(run_folder: Path) -> Path:
    """Legacy: returns images/ root. New code should use images/LS{n}/ subfolders."""
    return run_folder / "images"


def get_model_type(model_name: str) -> str:
    return "text_models"


def sanitize_folder_name(name: str) -> str:
    return name.replace("/", "_").replace(".", "_").replace(" ", "_").lower()


def get_existing_run_numbers(model_name: str) -> list:
    return []


def get_model_run_folder(model_name: str) -> Path:
    return get_base_output_dir()
