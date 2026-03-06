"""
Image Repository - Manages a reusable library of generated images.

This module provides functionality to:
- Categorize images into characters, environments, objects, misc
- Generate unique descriptive filenames
- Prevent duplicate storage using MD5 hashing
- Store images in a centralized repository for future prompts
"""

import os
import hashlib
import shutil
import re
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any


def get_repository_base_dir() -> Path:
    """
    Get the base directory for the image repository.

    Returns:
        Path to assets/image_repository/
    """
    return Path("assets") / "image_repository"


def get_category_dir(category: str) -> Path:
    """
    Get the directory for a specific category.

    Args:
        category: One of 'characters', 'environments', 'objects', 'misc'

    Returns:
        Path to the category directory
    """
    valid_categories = ["characters", "environments", "objects", "misc"]
    category_lower = category.lower()

    if category_lower not in valid_categories:
        category_lower = "misc"

    repo_dir = get_repository_base_dir()
    category_dir = repo_dir / category_lower
    category_dir.mkdir(parents=True, exist_ok=True)

    return category_dir


def compute_image_hash(image_path: Path) -> str:
    """
    Compute MD5 hash of an image file.

    Args:
        image_path: Path to the image file

    Returns:
        MD5 hash string
    """
    md5_hash = hashlib.md5()

    with open(image_path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            md5_hash.update(chunk)

    return md5_hash.hexdigest()


def get_existing_hashes(category: str) -> set:
    """
    Get all existing image hashes in a category directory.

    Args:
        category: Category to check

    Returns:
        Set of existing MD5 hashes
    """
    category_dir = get_category_dir(category)
    hashes = set()

    if not category_dir.exists():
        return hashes

    hash_file = category_dir / ".hashes.txt"

    if hash_file.exists():
        with open(hash_file, "r") as f:
            for line in f:
                hashes.add(line.strip())

    return hashes


def save_hash(category: str, image_hash: str, filename: str) -> None:
    """
    Save a hash to the category's hash tracking file.

    Args:
        category: Category name
        image_hash: MD5 hash of the image
        filename: Filename that was stored
    """
    category_dir = get_category_dir(category)
    hash_file = category_dir / ".hashes.txt"

    with open(hash_file, "a") as f:
        f.write(f"{image_hash} | {filename}\n")


def extract_main_subject(prompt: str, scene_data: Dict[str, Any]) -> str:
    """
    Extract the main subject from prompt or scene data.

    Args:
        prompt: Image generation prompt
        scene_data: Scene data dictionary

    Returns:
        Main subject identifier (lowercase, no spaces)
    """
    subject = "unknown"

    dialogues = scene_data.get("dialogue", [])
    if dialogues and isinstance(dialogues, list):
        for d in dialogues:
            if isinstance(d, dict):
                speaker = d.get("speaker", "").lower()
                if speaker and speaker not in ["teacher", "narrator"]:
                    subject = speaker
                    break

    if subject == "unknown":
        visual = scene_data.get("visual_setting", {})
        environment = visual.get("environment", "").lower()

        char_patterns = ["boy", "girl", "student", "teacher", "man", "woman", "child"]
        for pattern in char_patterns:
            if pattern in environment or pattern in prompt.lower():
                subject = pattern
                break

    subject = re.sub(r"[^a-z0-9]", "", subject.lower())
    return subject if subject else "subject"


def detect_category(prompt: str, scene_data: Dict[str, Any]) -> str:
    """
    Automatically detect the category for an image based on prompt and scene data.

    Args:
        prompt: Image generation prompt
        scene_data: Scene data dictionary

    Returns:
        Category: 'characters', 'environments', 'objects', or 'misc'
    """
    prompt_lower = prompt.lower()
    scene_str = str(scene_data).lower()

    character_keywords = [
        "character",
        "boy",
        "girl",
        "student",
        "teacher",
        "man",
        "woman",
        "child",
        "person",
        "people",
        "protagonist",
        "mentor",
        "guide",
        "friend",
        "expert",
        "narrator",
        "driver",
        "cyclist",
        "named",
    ]

    environment_keywords = [
        "classroom",
        "school",
        "street",
        "forest",
        "garden",
        "park",
        "room",
        "house",
        "home",
        "building",
        "road",
        "path",
        "beach",
        "mountain",
        "river",
        "village",
        "city",
        "market",
        "library",
        "laboratory",
        "kitchen",
        "office",
        "background",
        "setting",
        "scene",
        "environment",
        "outside",
        "inside",
    ]

    object_keywords = [
        "book",
        "table",
        "chair",
        "desk",
        "board",
        "chalkboard",
        "whiteboard",
        "computer",
        "phone",
        "bicycle",
        "wheel",
        "pen",
        "pencil",
        "notebook",
        "paper",
        "ball",
        "toy",
        "tool",
        "machine",
        "device",
        "apparatus",
        "instrument",
        "vehicle",
        "car",
        "bus",
        "train",
        "bike",
        "motorcycle",
        "bookshelf",
    ]

    for keyword in character_keywords:
        if keyword in prompt_lower or keyword in scene_str:
            return "characters"

    for keyword in environment_keywords:
        if keyword in prompt_lower or keyword in scene_str:
            return "environments"

    for keyword in object_keywords:
        if keyword in prompt_lower or keyword in scene_str:
            return "objects"

    return "misc"


def generate_unique_filename(
    main_subject: str,
    environment: str,
    scene_id: str,
    category: str,
    extension: str = "png",
) -> str:
    """
    Generate a unique descriptive filename for the image.

    Format: {main_subject}_{environment}_{scene_id}_{timestamp}.{ext}

    Args:
        main_subject: Main subject (e.g., 'aarav', 'student')
        environment: Environment (e.g., 'classroom', 'street')
        scene_id: Scene ID (e.g., 'S1', 'LS1_S1')
        category: Category for uniqueness
        extension: File extension (default: png)

    Returns:
        Unique filename
    """
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")

    subject_clean = re.sub(r"[^a-z0-9]", "", main_subject.lower())
    env_clean = re.sub(r"[^a-z0-9]", "", environment.lower())

    scene_clean = scene_id.replace("LS", "").replace("_", "")

    if not subject_clean:
        subject_clean = category

    if not env_clean:
        env_clean = "scene"

    filename = f"{subject_clean}_{env_clean}_{scene_clean}_{timestamp}.{extension}"

    return filename


def store_image_repository(
    image_path: str, prompt: str, scene_data: Dict[str, Any], scene_id: str = "S1"
) -> Optional[str]:
    """
    Store an image in the repository with categorization and deduplication.

    This function:
    1. Computes MD5 hash of the image
    2. Detects category from prompt/scene data
    3. Checks for duplicates
    4. Generates unique filename
    5. Copies to appropriate category directory

    Args:
        image_path: Path to the generated image
        prompt: The prompt used to generate the image
        scene_data: Scene data dictionary
        scene_id: Scene identifier (e.g., 'S1', 'LS1_S1')

    Returns:
        Path to the stored image in repository, or None if duplicate/skipped
    """
    image_path = Path(image_path)

    if not image_path.exists():
        print(f"  [Repository] Image not found: {image_path}")
        return None

    image_hash = compute_image_hash(image_path)

    category = detect_category(prompt, scene_data)
    category_dir = get_category_dir(category)

    existing_hashes = get_existing_hashes(category)

    if image_hash in existing_hashes:
        print(
            f"  [Repository] Duplicate detected, skipping copy (hash: {image_hash[:8]}...)"
        )
        return None

    visual = scene_data.get("visual_setting", {})
    environment = visual.get("environment", "scene")

    main_subject = extract_main_subject(prompt, scene_data)

    filename = generate_unique_filename(
        main_subject=main_subject,
        environment=environment,
        scene_id=scene_id,
        category=category,
        extension=image_path.suffix.lstrip("."),
    )

    dest_path = category_dir / filename

    try:
        shutil.copy2(image_path, dest_path)
        save_hash(category, image_hash, filename)
        print(f"  [Repository] Stored: {category}/{filename}")
        return str(dest_path)
    except Exception as e:
        print(f"  [Repository] Error storing image: {e}")
        return None


def get_repository_stats() -> Dict[str, Any]:
    """
    Get statistics about the image repository.

    Returns:
        Dictionary with repository statistics
    """
    repo_dir = get_repository_base_dir()

    stats = {"total_images": 0, "categories": {}}

    for category in ["characters", "environments", "objects", "misc"]:
        category_dir = repo_dir / category
        if category_dir.exists():
            image_files = list(category_dir.glob("*.png")) + list(
                category_dir.glob("*.jpg")
            )
            count = len([f for f in image_files if f.name != ".hashes.txt"])
            stats["categories"][category] = count
            stats["total_images"] += count

    return stats


def list_repository_images(category: Optional[str] = None) -> list:
    """
    List all images in the repository.

    Args:
        category: Optional category filter

    Returns:
        List of image paths
    """
    repo_dir = get_repository_base_dir()

    if category:
        category_dir = repo_dir / category
        if category_dir.exists():
            return list(category_dir.glob("*.png")) + list(category_dir.glob("*.jpg"))
        return []

    all_images = []
    for cat in ["characters", "environments", "objects", "misc"]:
        cat_dir = repo_dir / cat
        if cat_dir.exists():
            images = [f for f in cat_dir.glob("*") if f.suffix in [".png", ".jpg"]]
            all_images.extend(images)

    return all_images
