"""
Main entry point for the Storytelling Pipeline - Agentic Version.

This version uses LangGraph, LangChain, and LangSmith for orchestration.
The knowledge folder logic and PDF download logic are PRESERVED from the original.
"""
from dotenv import load_dotenv
load_dotenv()

import sys
import os
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from graph.pipeline_graph import create_pipeline_graph
from state.pipeline_state import PipelineState


# Import preserved PDF logic from original implementation
def check_and_get_pdf(
    class_level: str,
    subject: str,
    chapter_number: str,
    chapter_title: str,
    medium: str
) -> tuple:
    """
    Check knowledge folder for PDF, download if not found.
    This logic is PRESERVED from the original implementation.
    
    Args:
        class_level: Class level (e.g., "10")
        subject: Subject name
        chapter_number: Chapter number
        chapter_title: Chapter title
        medium: Language medium
        
    Returns:
        Tuple of (pdf_path, pdf_source)
    """
    from agents.pdf_agent import PDFAgent
    
    # Create a temporary state manager to use PDF agent
    from core.state_manager import get_state_manager
    
    # Create state for PDF download
    state_manager = get_state_manager()
    state_manager.create_chapter(
        class_level=class_level,
        subject=subject,
        chapter_number=chapter_number,
        chapter_title=chapter_title,
        medium=medium
    )
    
    state = state_manager.get_current()
    
    # Use PDF agent to get the PDF
    pdf_agent = PDFAgent()
    
    try:
        pdf_path = pdf_agent.run()
        return pdf_path, "downloaded"
    except Exception as e:
        print(f"Warning: Could not get PDF: {e}")
        return None, "none"


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
    Main entry point for the agentic pipeline.
    """
    try:
        user_input = get_user_input()

        print("\n[1/4] Getting PDF (checking knowledge folder first...)")
        
        # PRESERVED: Check knowledge folder and download if needed
        pdf_path, pdf_source = check_and_get_pdf(
            class_level=user_input["class_level"],
            subject=user_input["subject"],
            chapter_number=user_input["chapter_number"],
            chapter_title=user_input["chapter_title"],
            medium=user_input["medium"]
        )
        
        if pdf_path:
            print(f"  ✓ PDF available: {pdf_source}")
        else:
            print("  ⚠ PDF not available - proceeding without PDF")

        print("\n[2/4] Initializing Agentic Pipeline...")
        
        # Create the pipeline graph
        pipeline = create_pipeline_graph()
        
        # Build chapter name
        chapter_name = f"Class {user_input['class_level']} {user_input['subject']} Chapter {user_input['chapter_number']} {user_input['chapter_title']}"

        print("\n[3/4] Running Pipeline (this may take a while...)")
        print("  - Prompt 0: Concept Inventory")
        print("  - Prompt 1: Story Backbone")
        print("  - Prompt 2: Learning Steps")
        print("  - Prompt 3: Scene Generation (per learning step)")
        print("  - Prompt 4: Image Prompts (per scene)")
        
        # Run the pipeline
        result = pipeline.run(
            chapter_name=chapter_name,
            class_level=user_input["class_level"],
            subject=user_input["subject"],
            chapter_number=user_input["chapter_number"],
            medium=user_input["medium"],
            pdf_path=pdf_path
        )

        print("\n[4/4] Generating PowerPoint...")
        
        if ask_image_prompts():
            print("  Generating image prompts...")

        print("\n" + "=" * 60)
        print("  Pipeline execution completed successfully!")
        print("=" * 60)

        # Print output locations
        if result:
            print(f"\nOutput Location: {result.get('run_folder', 'unknown')}")
            print(f"Learning Steps: {len(result.get('learning_steps_list', []))}")
            print(f"Images Generated: {len(result.get('image_paths', []))}")
            if result.get('ppt_output_path'):
                print(f"PPT: {result['ppt_output_path']}")

    except KeyboardInterrupt:
        print("\n\nPipeline cancelled by user.")
        sys.exit(1)

    except Exception as e:
        print(f"\n\nError: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
