"""
Main entry point for the storytelling pipeline automation system.
"""

import sys
from typing import Optional

from core.logger import logger
from core.pipeline_controller import create_pipeline_controller
from core.state_manager import get_state_manager


def get_user_input() -> dict:
    """
    Get chapter information from user input.

    Returns:
        Dictionary with class, subject, chapter_number, chapter_title, medium
    """
    print("\n" + "=" * 60)
    print("  Storytelling Pipeline - Chapter Configuration")
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


def ask_image_prompts() -> bool:
    """
    Ask user whether to generate image prompts.

    Returns:
        True if user wants to generate image prompts
    """
    print("\n" + "-" * 40)
    response = input("Generate image prompts now? (y/n): ").strip().lower()
    return response in ["y", "yes"]


def main() -> None:
    """
    Main entry point for the pipeline.
    """
    try:
        user_input = get_user_input()

        controller = create_pipeline_controller()

        logger.info("Starting pipeline execution...")

        results = controller.run(
            class_level=user_input["class_level"],
            subject=user_input["subject"],
            chapter_number=user_input["chapter_number"],
            chapter_title=user_input["chapter_title"],
            medium=user_input["medium"],
            generate_image_prompts=False,
        )

        if ask_image_prompts():
            logger.info("Generating image prompts...")
            image_results = controller.run_image_prompts_only()
            logger.info(f"Generated {image_results.get('successful', 0)} image prompts")

        print("\n" + "=" * 60)
        print("  Pipeline execution completed successfully!")
        print("=" * 60)

        state = get_state_manager().get_current()
        if state:
            print(f"\nOutput location: {state.run_folder}")

    except KeyboardInterrupt:
        logger.warning("Pipeline interrupted by user")
        print("\n\nPipeline cancelled by user.")
        sys.exit(1)

    except Exception as e:
        logger.error(f"Pipeline failed: {e}", exc_info=True)
        print(f"\n\nError: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
