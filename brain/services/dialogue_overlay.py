"""
Dialogue Overlay Service - Overlays speech bubbles with dialogue text onto generated images.

Uses Pillow for image manipulation to add speech bubbles with character dialogue
to scene images for educational storytelling content.
"""

import os
import json
from pathlib import Path
from typing import Dict, Any, List, Tuple

from PIL import Image, ImageDraw, ImageFont
import textwrap


class DialogueOverlayError(Exception):
    """Custom exception for dialogue overlay errors."""

    pass


def overlay_dialogue_on_image(
    base_image_path: str,
    scene_json: Dict[str, Any],
    output_path: str,
) -> Dict[str, Any]:
    """
    Overlay speech bubbles with dialogue text onto a generated scene image.

    Args:
        base_image_path: Path to the base generated image
        scene_json: Scene JSON containing dialogue information
        output_path: Path to save the overlay image

    Returns:
        Dictionary with overlay result information

    Raises:
        RuntimeError: If base image or dialogue is missing
    """
    # Step 1 — Validate inputs
    if not os.path.exists(base_image_path):
        raise RuntimeError(f"Base image missing for overlay: {base_image_path}")

    if "dialogue" not in scene_json or not scene_json.get("dialogue"):
        raise RuntimeError("Scene JSON missing dialogue section")

    # Step 2 — Load base image
    img = Image.open(base_image_path).convert("RGB")
    draw = ImageDraw.Draw(img)
    image_width, image_height = img.size

    # Step 3 — Font loading
    font = _load_font()

    # Step 4 — Extract dialogue list
    dialogues = scene_json.get("dialogue", [])
    formatted_dialogues = []

    for dialogue in dialogues:
        speaker = dialogue.get("speaker", "Character")
        text = dialogue.get("text", "")
        formatted_dialogues.append(f"{speaker}: {text}")

    # Step 5-9 — Create speech bubbles for each dialogue
    bubble_positions = _get_bubble_positions(
        len(formatted_dialogues), image_width, image_height
    )

    for idx, (dialogue_text, position) in enumerate(
        zip(formatted_dialogues, bubble_positions)
    ):
        # Step 5 — Text wrapping
        wrapped_text = textwrap.fill(dialogue_text, width=30)

        # Step 6 — Calculate bounding box
        bbox = draw.multiline_textbbox((0, 0), wrapped_text, font=font)
        bbox_width = bbox[2] - bbox[0]
        bbox_height = bbox[3] - bbox[1]

        padding = 20
        bubble_width = bbox_width + padding * 2
        bubble_height = bbox_height + padding * 2

        # Adjust bubble width to minimum size
        bubble_width = max(bubble_width, 200)

        x, y = position

        # Adjust position if bubble goes off-screen
        if x + bubble_width > image_width:
            x = image_width - bubble_width - 50
        if y + bubble_height > image_height:
            y = image_height - bubble_height - 50

        # Step 8 — Draw rounded rectangle bubble
        try:
            draw.rounded_rectangle(
                [x, y, x + bubble_width, y + bubble_height],
                radius=25,
                fill="white",
                outline="black",
                width=3,
            )
        except Exception:
            # Fallback for older Pillow versions
            draw.rectangle(
                [x, y, x + bubble_width, y + bubble_height],
                fill="white",
                outline="black",
                width=3,
            )

        # Step 9 — Draw dialogue text
        draw.multiline_text(
            (x + padding, y + padding),
            wrapped_text,
            fill="black",
            font=font,
        )

    # Step 10 — Save overlay image
    img.save(output_path)

    # Save dialogue JSON alongside overlay
    dialogue_json_path = output_path.replace(".png", "_dialogue.json")
    with open(dialogue_json_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "dialogues": dialogues,
                "overlay_applied": True,
                "base_image": os.path.basename(base_image_path),
            },
            f,
            indent=2,
            ensure_ascii=False,
        )

    return {
        "overlay_applied": True,
        "output_path": output_path,
        "dialogue_json_path": dialogue_json_path,
        "dialogues_count": len(dialogues),
    }


def _load_font() -> ImageFont.FreeTypeFont:
    """
    Load font for dialogue text.

    Tries system fonts first, falls back to default.

    Returns:
        ImageFont object
    """
    font_paths = [
        "arial.ttf",
        "Arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
        "C:/Windows/Fonts/arial.ttf",
        "C:/Windows/Fonts/Arial.ttf",
    ]

    for font_path in font_paths:
        try:
            return ImageFont.truetype(font_path, 32)
        except (OSError, IOError):
            continue

    # Fallback to default font
    return ImageFont.load_default()


def _get_bubble_positions(
    count: int, image_width: int, image_height: int
) -> List[Tuple[int, int]]:
    """
    Calculate deterministic bubble positions to avoid overlap.

    Positions bubbles in corners: top-left, top-right, bottom-left, bottom-right

    Args:
        count: Number of dialogue entries
        image_width: Width of the image
        image_height: Height of the image

    Returns:
        List of (x, y) coordinates for each bubble
    """
    positions = [
        (50, 50),  # top-left
        (image_width - 350, 50),  # top-right
        (50, image_height - 150),  # bottom-left
        (image_width - 350, image_height - 150),  # bottom-right
    ]

    # Return positions based on count, cycling through available positions
    return [positions[i % len(positions)] for i in range(count)]


def create_overlay_images(
    base_image_path: str,
    scene_json: Dict[str, Any],
    output_dir: str,
    scene_id: str,
) -> Dict[str, Any]:
    """
    Create overlay images for a scene with multiple output files.

    Creates:
    - scene_base.png (original)
    - scene_overlay.png (with dialogue bubbles)
    - scene_dialogue.json (dialogue data)

    Args:
        base_image_path: Path to the base generated image
        scene_json: Scene JSON containing dialogue
        output_dir: Directory to save outputs
        scene_id: ID for the scene

    Returns:
        Dictionary with paths to created files
    """
    os.makedirs(output_dir, exist_ok=True)

    base_path = os.path.join(output_dir, f"{scene_id}")
    base_image_output = f"{base_path}_base.png"
    overlay_output = f"{base_path}_overlay.png"
    dialogue_output = f"{base_path}_dialogue.json"

    # Copy base image
    if os.path.exists(base_image_path):
        import shutil

        shutil.copy(base_image_path, base_image_output)
    else:
        raise RuntimeError(f"Base image not found: {base_image_path}")

    # Create overlay
    overlay_result = overlay_dialogue_on_image(
        base_image_path=base_image_output,
        scene_json=scene_json,
        output_path=overlay_output,
    )

    # Save dialogue JSON
    with open(dialogue_output, "w", encoding="utf-8") as f:
        json.dump(
            {
                "scene_id": scene_id,
                "dialogues": scene_json.get("dialogue", []),
                "overlay_applied": True,
                "base_image": os.path.basename(base_image_output),
                "overlay_image": os.path.basename(overlay_output),
            },
            f,
            indent=2,
            ensure_ascii=False,
        )

    return {
        "base_image": base_image_output,
        "overlay_image": overlay_output,
        "dialogue_json": dialogue_output,
        "overlay_applied": True,
    }
