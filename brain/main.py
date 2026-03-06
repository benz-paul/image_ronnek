"""
Main entry point for the Storytelling Pipeline - Agentic Version.

This version uses LangGraph, LangChain, and LangSmith for orchestration.
The knowledge folder logic and PDF download logic are PRESERVED from the original.
"""

from dotenv import load_dotenv

load_dotenv(override=True)

import sys
import os
from pathlib import Path

TEST_MODE = True

sys.path.insert(0, str(Path(__file__).parent.parent))

from brain.pipeline.pipeline_graph import create_pipeline_graph
from brain.pipeline.state.pipeline_state import PipelineState


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


def ask_image_generation_mode():
    """
    Ask user for image generation mode in TEST_MODE.

    Returns:
        "dialogue" or "overlay"
    """
    print("\n" + "-" * 40)
    print("  Image Generation Mode")
    print("-" * 40)
    print("  1. Dialogue INSIDE image (AI renders text in scene)")
    print("  2. Dialogue OVERLAY (add speech bubbles after generation)")
    print("-" * 40)

    while True:
        choice = input("Enter choice (1/2): ").strip()
        if choice == "1":
            print("  ✓ Mode: Dialogue inside image")
            return "dialogue"
        elif choice == "2":
            print("  ✓ Mode: Dialogue overlay")
            return "overlay"
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
        Model name: "gpt-image-1.5", "fal-flux", or "fal-juggernaut"
    """
    print("\n" + "-" * 40)
    print("Select image generation model:")
    print("  1 - GPT-image-1.5 (OpenAI)")
    print("  2 - Flux Pro (fal.ai)")
    print("  3 - Juggernaut (fal.ai)")

    while True:
        choice = input("Enter choice (1/2/3): ").strip()
        if choice == "1":
            return "gpt-image-1.5"
        elif choice == "2":
            return "fal-flux"
        elif choice == "3":
            return "fal-juggernaut"
        else:
            print("  Invalid choice. Please enter 1, 2, or 3.")


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


def ask_image_prompts() -> bool:
    """
    Ask user whether to generate image prompts.

    Returns:
        True if user wants to generate image prompts
    """
    print("\n" + "-" * 40)
    response = input("Generate image prompts now? (y/n): ").strip().lower()
    return response in ["y", "yes"]


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


def run_test_mode():
    """
    Run pipeline in TEST_MODE with interactive debugging.
    """
    print("\n" + "=" * 60)
    print("  TEST MODE - Interactive Debugging")
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
    print(f"[TEST MODE] PDF: {pdf_path}")

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

    print("\n[2/5] Initializing Agentic Pipeline...")
    pipeline = create_pipeline_graph()

    chapter_name = (
        f"Class {class_level} {subject} Chapter {chapter_number} {chapter_title}"
    )

    generation_mode = get_generation_mode()

    if generation_mode == "ls1":
        print("  Mode: LS1 Only (fast preview)")
    else:
        print("  Mode: Full chapter")

    # Ask for image generation mode BEFORE running pipeline
    image_mode = ask_image_generation_mode()

    print("\n[3/5] Running Pipeline...")
    print("  - Prompt 0: Concept Inventory")
    print("  - Prompt 1: Story Backbone")
    print("  - Prompt 2: Learning Steps")
    print("  - Prompt 3: Scene Generation (per learning step)")
    print("  - Prompt 4: Image Prompts (per scene)")

    print("\n" + "=" * 40)
    print("MODEL CONFIGURATION")
    print("=" * 40)
    print(f"Text Model: {text_model}")
    print(f"Image Model: {image_model}")
    print(f"Image Mode: {image_mode}")
    print("=" * 40 + "\n")

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
        test_mode=True,
    )

    print("\n[4/5] Processing Results...")

    learning_steps = result.get("learning_steps_list", [])

    if learning_steps:
        display_learning_steps(learning_steps)

        selected_ls = select_learning_step(learning_steps)

        scene_mode = ask_scene_generation_mode()

        if selected_ls:
            print(f"\n[TEST MODE] Generating scenes for Learning Step {selected_ls}")
        else:
            print(
                f"\n[TEST MODE] Generating scenes for ALL {len(learning_steps)} learning steps"
            )

        if scene_mode == "single":
            print("[TEST MODE] Generating ONE scene for testing")
        else:
            print(f"[TEST MODE] Generating ALL scenes")

    print("\n" + "=" * 60)
    print("  Pipeline execution completed successfully!")
    print("=" * 60)

    print(f"\nOutput Location: {result.get('run_folder', 'unknown')}")
    print(f"Learning Steps: {len(result.get('learning_steps_list', []))}")
    print(f"Images Generated: {len(result.get('image_paths', []))}")
    if result.get("ppt_output_path"):
        print(f"PPT: {result.get('ppt_output_path')}")

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

        # Ask for image generation mode
        image_mode = ask_image_generation_mode()

        print("\n[3/4] Running Pipeline (this may take a while...)")
        print("  - Prompt 0: Concept Inventory")
        print("  - Prompt 1: Story Backbone")
        print("  - Prompt 2: Learning Steps")
        print("  - Prompt 3: Scene Generation (per learning step)")
        print("  - Prompt 4: Image Prompts (per scene)")

        print("\n" + "=" * 40)
        print("MODEL CONFIGURATION")
        print("=" * 40)
        print(f"Text Model: {text_model}")
        print(f"Image Model: {image_model}")
        print(f"Image Mode: {image_mode}")
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
