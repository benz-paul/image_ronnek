"""
Main entry point for the Storytelling Pipeline - Agentic Version.

This version uses LangGraph, LangChain, and LangSmith for orchestration.
The knowledge folder logic and PDF download logic are PRESERVED from the original.
"""

from dotenv import load_dotenv

load_dotenv(override=True)

import sys
import os
import time
from pathlib import Path

TEST_MODE = True

sys.path.insert(0, str(Path(__file__).parent.parent))

from brain.pipeline.pipeline_graph import create_pipeline_graph, DEBUG_MODE
from brain.pipeline.state.pipeline_state import PipelineState
from utils.pipeline_logger import set_verbose


def get_available_topics():
    """
    Scan the knowledge folder for available PDF topics.

    Returns:
        List of topic dicts with index, display_name, and chapter_info
    """
    knowledge_dir = Path(__file__).parent.parent / "assets" / "knowledge"
    topics = []

    if not knowledge_dir.exists():
        return topics

    pdf_files = sorted(knowledge_dir.glob("*.pdf"))

    topic_presets = {
        "Chapter 10 – Circles": {
            "subject": "Mathematics",
            "chapter_number": "10",
            "title": "Circles",
        },
        "Chapter 11-Electricity": {
            "subject": "Physics",
            "chapter_number": "11",
            "title": "Electricity",
        },
        "Chapter 5 Arithmetic Progression Maths": {
            "subject": "Mathematics",
            "chapter_number": "5",
            "title": "Arithmetic Progression",
        },
        "Introduction to Trigonometry": {
            "subject": "Mathematics",
            "chapter_number": "0",
            "title": "Introduction to Trigonometry",
        },
        "Magnetic Effects of Electric Current": {
            "subject": "Physics",
            "chapter_number": "13",
            "title": "Magnetic Effects of Electric Current",
        },
    }

    for idx, pdf_path in enumerate(pdf_files, 1):
        filename = pdf_path.stem

        if filename in topic_presets:
            info = topic_presets[filename]
        else:
            info = {"subject": "Unknown", "chapter_number": "1", "title": filename}

        display_name = (
            f"{info['subject']} - Chapter {info['chapter_number']}: {info['title']}"
        )

        topics.append(
            {
                "index": idx,
                "display_name": display_name,
                "filename": pdf_path.name,
                "chapter_number": info["chapter_number"],
                "subject": info["subject"],
                "chapter_title": info["title"],
                "pdf_path": str(pdf_path),
            }
        )

    return topics

    pdf_files = sorted(knowledge_dir.glob("*.pdf"))

    for idx, pdf_path in enumerate(pdf_files, 1):
        filename = pdf_path.stem

        name_parts = (
            filename.replace("Chapter ", "")
            .replace(" – ", " ")
            .replace("-", " ")
            .split()
        )

        if len(name_parts) >= 3:
            chapter_number = name_parts[1] if name_parts[1].isdigit() else name_parts[0]
            subject = (
                name_parts[0]
                if not name_parts[0].isdigit()
                else name_parts[2]
                if len(name_parts) > 2
                else "Unknown"
            )
            chapter_title = (
                " ".join(name_parts[2:])
                if len(name_parts) > 2
                else " ".join(name_parts)
            )
        else:
            chapter_number = "1"
            subject = "Unknown"
            chapter_title = filename

        display_name = f"{subject} - Chapter {chapter_number}: {chapter_title}"

        topics.append(
            {
                "index": idx,
                "display_name": display_name,
                "filename": pdf_path.name,
                "chapter_number": chapter_number,
                "subject": subject,
                "chapter_title": chapter_title,
                "pdf_path": str(pdf_path),
            }
        )

    return topics


def select_topic():
    """
    Interactive topic selection for TEST_MODE.

    Returns:
        Selected topic dict
    """
    topics = get_available_topics()

    print("\n" + "=" * 60)
    print("  Available Topics")
    print("=" * 60)

    for topic in topics:
        print(f"  {topic['index']}. {topic['display_name']}")

    print("-" * 60)

    while True:
        try:
            choice = int(input("Select topic number: ").strip())
            selected = next((t for t in topics if t["index"] == choice), None)
            if selected:
                print(f"  ✓ Selected: {selected['display_name']}")
                return selected
            else:
                print("  Invalid selection. Please enter a valid number.")
        except ValueError:
            print("  Please enter a number.")


def display_learning_steps(learning_steps):
    """
    Display available learning steps from pipeline result.

    Args:
        learning_steps: List of learning steps
    """
    print("\n" + "-" * 40)
    print("  Available Learning Steps")
    print("-" * 40)

    for idx, ls in enumerate(learning_steps, 1):
        title = ls.get("title", ls.get("learning_step_title", f"Step {idx}"))
        print(f"  {idx}. {title}")


def select_learning_step(learning_steps):
    """
    Interactive learning step selection for TEST_MODE.

    Args:
        learning_steps: List of learning steps

    Returns:
        Selected learning step index (1-based) or None for all
    """
    display_learning_steps(learning_steps)

    print("-" * 40)
    print("  Enter step number to generate scenes for")
    print("  Or press Enter to generate scenes for ALL steps")
    print("-" * 40)

    while True:
        choice = input("Selection: ").strip()

        if not choice:
            return None

        try:
            idx = int(choice)
            if 1 <= idx <= len(learning_steps):
                return idx
            else:
                print(f"  Please enter a number between 1 and {len(learning_steps)}")
        except ValueError:
            print("  Please enter a number or press Enter.")


def ask_scene_generation_mode():
    """
    Ask user how many scenes to generate in TEST_MODE.

    Returns:
        "single" or "all"
    """
    print("\n" + "-" * 40)
    print("  Scene Generation Options")
    print("-" * 40)
    print("  1. Generate only ONE scene (for testing)")
    print("  2. Generate ALL scenes")
    print("-" * 40)

    while True:
        choice = input("Enter choice (1/2): ").strip()
        if choice == "1":
            return "single"
        elif choice == "2":
            return "all"
        else:
            print("  Invalid choice. Please enter 1 or 2.")



def get_user_input() -> dict:
    """
    Get chapter information from user input.

    Returns:
        Dictionary with class, subject, chapter_number, chapter_title, medium
    """
    print("\n" + "=" * 60)
    print("  Storytelling Pipeline - Agentic Version")
    print("  (Powered by LangGraph + LangChain + LangSmith)")
    print("=" * 60 + "\n")

    class_level = input("Class: ").strip()
    subject = input("Subject: ").strip()
    chapter_number = input("Chapter Number: ").strip()
    chapter_title = input("Chapter Title: ").strip()
    medium = input("Medium (English/Hindi): ").strip()

    if not medium:
        medium = "English"

    return {
        "class_level": class_level,
        "subject": subject,
        "chapter_number": chapter_number,
        "chapter_title": chapter_title,
        "medium": medium,
    }


def select_image_model() -> str:
    """
    Allow user to select image generation model.

    Returns:
        Model name: "gpt-image-1.5", "fal-flux2pro", or "fal-juggernaut"
    """
    print("\n" + "-" * 40)
    print("Select image generation model:")
    print("  1 - GPT-image-1.5 (OpenAI)")
    print("  2 - Flux 2 Pro (fal.ai)  ← recommended")
    print("  3 - Juggernaut (fal.ai)")

    while True:
        choice = input("Enter choice (1/2/3): ").strip()
        if choice == "1":
            return "gpt-image-1.5"
        elif choice == "2":
            return "fal-flux2pro"
        elif choice == "3":
            return "fal-juggernaut"
        else:
            print("  Invalid choice. Please enter 1, 2, or 3.")


def ask_generate_audio() -> bool:
    """
    Ask user whether to generate audio (calls Amazon Polly).

    Returns:
        True if user wants to generate audio
    """
    print("\n" + "-" * 40)
    print("  Generate Audio?")
    print("-" * 40)
    print("  Generates narrator + character voices via Amazon Polly.")
    print("  Select 'n' to skip (faster test runs).")
    print("-" * 40)
    response = input("Generate audio? (y/n): ").strip().lower()
    if response in ["y", "yes"]:
        print("  ✓ Audio will be generated")
        return True
    print("  ✓ Skipping audio generation")
    return False


def get_generation_mode() -> str:
    """
    Ask user for generation mode.

    Returns:
        "full" or "ls1"
    """
    print("\n" + "-" * 40)
    print("Select generation mode:")
    print("  1 - Full chapter (all learning steps)")
    print("  2 - Only LS1 (fast preview)")

    while True:
        choice = input("Enter choice (1/2): ").strip()
        if choice == "1":
            return "full"
        elif choice == "2":
            return "ls1"
        else:
            print("Invalid choice. Please enter 1 or 2.")


def ask_generate_images() -> bool:
    """
    Ask user whether to generate images (calls image model API).

    Returns:
        True if user wants to generate images
    """
    print("\n" + "-" * 40)
    print("  Generate Images?")
    print("-" * 40)
    print("  Call the image model API to generate scene images.")
    print("  Select 'n' to skip image generation (saves API credits).")
    print("-" * 40)
    response = input("Generate images? (y/n): ").strip().lower()
    if response in ["y", "yes"]:
        print("  ✓ Images will be generated")
        return True
    print("  ✓ Skipping image generation")
    return False


def ask_verbosity() -> bool:
    """
    Ask user whether to show verbose debug logs.

    Returns:
        True = show all debug output, False = show only milestones (recommended)
    """
    print("\n" + "-" * 40)
    print("  Log Verbosity")
    print("-" * 40)
    print("  n = clean output (scene progress, image status, errors only)")
    print("  y = verbose (fal.ai polling, JSON validation, scene storage, etc.)")
    print("-" * 40)
    response = input("Verbose logs? (y/n): ").strip().lower()
    if response in ["y", "yes"]:
        print("  ✓ Verbose mode on")
        return True
    print("  ✓ Clean output mode")
    return False


def check_and_get_pdf(
    class_level: str,
    subject: str,
    chapter_number: str,
    chapter_title: str,
    medium: str,
    pdf_path: str = None,
) -> tuple:
    """
    Check for PDF, use provided path or download if not found.
    This logic is PRESERVED from the original implementation.

    Args:
        class_level: Class level (e.g., "10")
        subject: Subject name
        chapter_number: Chapter number
        chapter_title: Chapter title
        medium: Language medium
        pdf_path: Pre-selected PDF path (for TEST_MODE)

    Returns:
        Tuple of (pdf_path, pdf_source)
    """
    if pdf_path and Path(pdf_path).exists():
        return pdf_path, "knowledge_folder"

    from brain.agents.pdf_agent import PDFAgent
    from brain.prompt_engine.core.state_manager import get_state_manager

    state_manager = get_state_manager()
    state_manager.create_chapter(
        class_level=class_level,
        subject=subject,
        chapter_number=chapter_number,
        chapter_title=chapter_title,
        medium=medium,
    )

    state = state_manager.get_current()
    pdf_agent = PDFAgent()

    try:
        pdf_path = pdf_agent.run()
        return pdf_path, "downloaded"
    except Exception as e:
        print(f"Warning: Could not get PDF: {e}")
        return None, "none"


def _print_summary(result: dict, elapsed_seconds: float) -> None:
    """Print the detailed per-LS pipeline summary box."""
    run_folder = result.get("run_folder", "unknown")
    ls_list = result.get("learning_steps_list", [])
    image_paths = result.get("image_paths", [])

    width = 56
    border = "═" * width

    def row(text: str) -> str:
        return f"  ║  {text:<{width - 4}}║"

    def divider() -> str:
        return f"  ╠{border}╣"

    mins, secs = divmod(int(elapsed_seconds), 60)
    duration_str = f"{mins}m {secs:02d}s" if mins else f"{secs}s"

    lines = [f"  ╔{border}╗", row("Pipeline Complete"), divider()]

    for ls in ls_list:
        ls_id = ls.get("learning_step_id", "?")
        ls_title = ls.get("title", "")
        scenes = ls.get("scenes", [])
        scene_count = len(scenes)

        # Count actual saved .png images for this LS
        images_saved = 0
        if run_folder and run_folder != "unknown":
            ls_images_dir = Path(run_folder) / "images" / ls_id
            if ls_images_dir.exists():
                images_saved = len(list(ls_images_dir.glob("*.png")))
        images_failed = scene_count - images_saved if scene_count > 0 else 0

        header = f"{ls_id} — {ls_title}"
        lines.append(row(header[:width - 4]))
        lines.append(row(f"  Scenes : {scene_count}"))
        if result.get("generate_images", True) or image_paths:
            lines.append(row(f"  Images : {images_saved} saved / {images_failed} failed"))

        # Audio stats
        if result.get("generate_audio", True) and run_folder and run_folder != "unknown":
            ls_audio_dir = Path(run_folder) / "audio" / ls_id
            combined_count = len(list(ls_audio_dir.glob("*.mp3"))) if ls_audio_dir.exists() else 0
            if combined_count:
                lines.append(row(f"  Audio  : {combined_count} combined MP3(s)"))

    lines.append(divider())
    lines.append(row(f"Duration : {duration_str}"))
    lines.append(row(f"Output   : {run_folder}"))
    if result.get("ppt_output_path"):
        lines.append(row(f"PPT      : {result.get('ppt_output_path')}"))
    lines.append(f"  ╚{border}╝")

    print()
    for line in lines:
        print(line)
    print()


def run_test_mode():
    """
    Run pipeline in TEST_MODE with interactive debugging.
    DEBUG_MODE in pipeline_graph.py controls whether we cap at 1 LS.
    """
    print("\n" + "=" * 60)
    print("  TEST MODE - Interactive Debugging")
    if DEBUG_MODE:
        print("  DEBUG MODE ON — limited to 1 learning step")
    print("=" * 60)

    # Hardcoded text model
    text_model = "deepseek"
    image_model = select_image_model()

    selected_topic = select_topic()

    class_level = "10"
    subject = selected_topic["subject"]
    chapter_number = selected_topic["chapter_number"]
    chapter_title = selected_topic["chapter_title"]
    medium = "English"
    pdf_path = selected_topic["pdf_path"]

    print(f"\n[TEST MODE] Topic: {subject} - {chapter_title}")

    print("\n[1/5] Getting PDF...")
    pdf_path, pdf_source = check_and_get_pdf(
        class_level=class_level,
        subject=subject,
        chapter_number=chapter_number,
        chapter_title=chapter_title,
        medium=medium,
        pdf_path=pdf_path,
    )
    print(f"  ✓ PDF source: {pdf_source}")

    print("\n[2/5] Initializing Pipeline...")
    pipeline = create_pipeline_graph()

    chapter_name = (
        f"Class {class_level} {subject} Chapter {chapter_number} {chapter_title}"
    )

    # When DEBUG_MODE is on, always run ls1 — skip the question entirely
    if DEBUG_MODE:
        generation_mode = "ls1"
        print("  Mode: 1 Learning Step (DEBUG_MODE)")
    else:
        generation_mode = get_generation_mode()
        if generation_mode == "ls1":
            print("  Mode: LS1 Only (fast preview)")
        else:
            print("  Mode: Full chapter")

    # Dialogue-in mode only (overlay removed)
    image_mode = "dialogue"

    # Ask how many scenes to generate per LS
    scene_mode = ask_scene_generation_mode()
    scene_generation_scope = "single" if scene_mode == "single" else "multiple"

    # Ask whether to call the image model API
    generate_images = ask_generate_images()

    # Ask whether to generate audio
    generate_audio = ask_generate_audio()

    # Ask verbosity preference and set global logger level
    verbose = ask_verbosity()
    set_verbose(verbose)

    steps = 5
    print(f"\n[3/{steps}] Running Pipeline...")
    print("  - Prompt 0: Concept Inventory")
    print("  - Prompt 1: Story Backbone")
    print("  - Prompt 2: Learning Steps")
    print("  - Prompt 3: Scene Generation (per learning step)")
    print("  - Prompt 4: Image Generation (per scene)" if generate_images else "  - Prompt 4: Image Prompts (skipped — generate_images=False)")
    if generate_audio:
        print("  - Audio: Narrator + dialogue voices via Polly")

    _start_time = time.time()

    result = pipeline.run(
        chapter_name=chapter_name,
        chapter_title=chapter_title,
        class_level=class_level,
        subject=subject,
        chapter_number=chapter_number,
        medium=medium,
        pdf_path=pdf_path,
        generation_mode=generation_mode,
        text_model=text_model,
        image_model=image_model,
        image_mode=image_mode,
        generate_images=generate_images,
        generate_audio=generate_audio,
        test_mode=True,
        scene_generation_scope=scene_generation_scope,
    )

    elapsed = time.time() - _start_time
    result["generate_images"] = generate_images
    result["generate_audio"] = generate_audio
    _print_summary(result, elapsed)

    return result


def run_production_mode():
    """
    Run pipeline in production mode with full automation.
    """
    try:
        user_input = get_user_input()

        # Hardcoded text model
        text_model = "deepseek"
        image_model = select_image_model()

        print("\n[1/4] Getting PDF (checking knowledge folder first...)")

        pdf_path, pdf_source = check_and_get_pdf(
            class_level=user_input["class_level"],
            subject=user_input["subject"],
            chapter_number=user_input["chapter_number"],
            chapter_title=user_input["chapter_title"],
            medium=user_input["medium"],
        )

        if pdf_path:
            print(f"  ✓ PDF available: {pdf_source}")
        else:
            print("  ⚠ PDF not available - proceeding without PDF")

        print("\n[2/4] Initializing Agentic Pipeline...")

        pipeline = create_pipeline_graph()

        chapter_name = f"Class {user_input['class_level']} {user_input['subject']} Chapter {user_input['chapter_number']} {user_input['chapter_title']}"
        chapter_title = user_input["chapter_title"]

        generation_mode = get_generation_mode()

        if generation_mode == "ls1":
            print("  Mode: LS1 Only (fast preview)")
        else:
            print("  Mode: Full chapter")

        # Dialogue-in mode only (overlay removed)
        image_mode = "dialogue"

        # Ask whether to actually call the image model API
        generate_images = ask_generate_images()

        # Ask whether to generate audio
        generate_audio = ask_generate_audio()

        print("\n[3/4] Running Pipeline (this may take a while...)")
        print("  - Prompt 0: Concept Inventory")
        print("  - Prompt 1: Story Backbone")
        print("  - Prompt 2: Learning Steps")
        print("  - Prompt 3: Scene Generation (per learning step)")
        print("  - Prompt 4: Image Generation (per scene)" if generate_images else "  - Prompt 4: Image Prompts (skipped — generate_images=False)")
        if generate_audio:
            print("  - Audio: Narrator + dialogue voices via Polly")

        print("\n" + "=" * 40)
        print("MODEL CONFIGURATION")
        print("=" * 40)
        print(f"Text Model: {text_model}")
        print(f"Image Model: {image_model}")
        print(f"Image Mode: {image_mode}")
        print(f"Generate Images: {generate_images}")
        print(f"Generate Audio: {generate_audio}")
        print("=" * 40 + "\n")

        result = pipeline.run(
            chapter_name=chapter_name,
            chapter_title=chapter_title,
            class_level=user_input["class_level"],
            subject=user_input["subject"],
            chapter_number=user_input["chapter_number"],
            medium=user_input["medium"],
            pdf_path=pdf_path,
            generation_mode=generation_mode,
            text_model=text_model,
            image_model=image_model,
            image_mode=image_mode,
            generate_images=generate_images,
            generate_audio=generate_audio,
            test_mode=False,
        )

        print("\n[4/4] Generating PowerPoint...")

        print("\n" + "=" * 60)
        print("  Pipeline execution completed successfully!")
        print("=" * 60)

        if result:
            print(f"\nOutput Location: {result.get('run_folder', 'unknown')}")
            print(f"Learning Steps: {len(result.get('learning_steps_list', []))}")
            print(f"Images Generated: {len(result.get('image_paths', []))}")
            if result.get("ppt_output_path"):
                print(f"PPT: {result.get('ppt_output_path')}")

    except KeyboardInterrupt:
        print("\n\nPipeline cancelled by user.")
        sys.exit(1)

    except Exception as e:
        print(f"\n\nError: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


def main() -> None:
    """
    Main entry point for the agentic pipeline.
    """
    if TEST_MODE:
        run_test_mode()
    else:
        run_production_mode()


if __name__ == "__main__":
    main()
