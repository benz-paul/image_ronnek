"""
Image Regeneration Script
Generates images for all existing scenes using updated settings.
Uses 1536x1024 size for better PPT compatibility.
"""

import json
from pathlib import Path
from brain.services.image_generator import ImageGeneratorService


def regenerate_all_images():
    """Regenerate all images with new settings."""

    # Use new settings
    generator = ImageGeneratorService(
        quality="low",
        size="1792x1024",  # Landscape for better PPT (wider than 1536)
    )

    output_dir = Path("outputs/10_maths_arithmetic_progression")
    scenes_dir = output_dir / "scenes"
    learning_steps_dir = output_dir / "learning_steps"

    ls_files = sorted(learning_steps_dir.glob("LS*.json"))

    total_scenes = 0
    total_generated = 0

    print("=" * 60)
    print("Image Regeneration Started")
    print("Size: 1536x1024 (Landscape)")
    print("Quality: Low")
    print("=" * 60)

    for ls_file in sorted(ls_files):
        ls_id = ls_file.stem

        scene_file = scenes_dir / f"{ls_id}_scenes.json"
        if not scene_file.exists():
            print(f"Skipping {ls_id} - no scenes file")
            continue

        with open(scene_file, "r", encoding="utf-8") as f:
            scene_data = json.load(f)

        scenes = scene_data.get("scenes", [])
        if not scenes:
            # Try nested structure
            for key in scene_data:
                if isinstance(scene_data[key], list):
                    for item in scene_data[key]:
                        if isinstance(item, dict) and "scenes" in item:
                            scenes.extend(item["scenes"])

        total_scenes += len(scenes)
        print(f"\n{ls_id}: {len(scenes)} scenes")

        for scene in scenes:
            scene_id = scene.get("scene_id", "S1")

            # Check if image already exists
            if ls_id == "LS1":
                img_name = f"LS1_{scene_id}.png"
            else:
                img_name = f"{ls_id}_{scene_id}.png"

            img_path = output_dir / "images" / img_name

            if img_path.exists():
                print(f"  - {scene_id}: Already exists, skipping")
                continue

            print(f"  - {scene_id}: Generating...")

            try:
                result = generator.generate_image(
                    scene_data=scene,
                    learning_step_id=ls_id,
                    scene_id=scene_id,
                    run_folder=str(output_dir),
                )

                if result.get("image_path"):
                    total_generated += 1
                    print(f"    -> Saved: {result['image_path']}")
                else:
                    print(f"    -> FAILED: No image returned")

            except Exception as e:
                print(f"    -> ERROR: {str(e)}")

    print("\n" + "=" * 60)
    print(f"Total scenes: {total_scenes}")
    print(f"Images generated: {total_generated}")
    print("=" * 60)


if __name__ == "__main__":
    regenerate_all_images()
