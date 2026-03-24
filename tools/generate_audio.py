"""
tools/generate_audio.py
-----------------------
Post-processing script: reads scenes_full.json from a completed pipeline run
and generates Amazon Polly audio files for every scene.

Usage:
    python tools/generate_audio.py --run outputs/run_20240101_120000

Options:
    --run      Path to the run folder (required)
    --narrator Polly VoiceId for narrator (default: Matthew)
    --ls       Only process a specific learning step, e.g. --ls LS1
    --dry-run  Print what would be generated without calling Polly

Examples:
    python tools/generate_audio.py --run outputs/run_20240101_120000
    python tools/generate_audio.py --run outputs/run_20240101_120000 --ls LS1
    python tools/generate_audio.py --run outputs/run_20240101_120000 --dry-run
"""

import argparse
import json
import sys
from pathlib import Path

# Add project root to sys.path so local imports work
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv

load_dotenv()

from brain.services.audio_generator import AudioGeneratorService


def load_scenes(run_folder: Path) -> dict:
    """
    Load scenes from the run folder.

    Tries in order:
    1. parsed/scenes_full.json  (all LS combined)
    2. parsed/scenes_LS*.json   (per-LS files, merged)
    3. scenes/LS*/LS*_S*.json   (individual scene files, merged)

    Returns dict: {ls_id: [scene, ...]}
    """
    # Option 1: parsed/scenes_full.json
    full_path = run_folder / "parsed" / "scenes_full.json"
    if full_path.exists():
        print(f"[LOAD] Loading from {full_path}")
        with open(full_path, encoding="utf-8") as f:
            data = json.load(f)
        # scenes_full.json may be {"LS1": [...]} or {"scenes": {"LS1": [...]}}
        if isinstance(data, dict) and not any(k.startswith("LS") for k in data):
            # Try nested "scenes" key
            data = data.get("scenes", data)
        return data

    # Option 2: parsed/scenes_LS*.json files
    parsed_dir = run_folder / "parsed"
    ls_files = sorted(parsed_dir.glob("scenes_LS*.json")) if parsed_dir.exists() else []
    if ls_files:
        print(f"[LOAD] Loading from {len(ls_files)} per-LS parsed files")
        scenes_by_ls = {}
        for f in ls_files:
            ls_id = f.stem.replace("scenes_", "")  # e.g. "LS1"
            with open(f, encoding="utf-8") as fh:
                data = json.load(fh)
            scenes_by_ls[ls_id] = data if isinstance(data, list) else data.get("scenes", [])
        return scenes_by_ls

    # Option 3: individual scene files under scenes/LS*/
    scenes_dir = run_folder / "scenes"
    if scenes_dir.exists():
        print(f"[LOAD] Loading from individual scene files under {scenes_dir}")
        scenes_by_ls = {}
        for ls_dir in sorted(scenes_dir.iterdir()):
            if not ls_dir.is_dir():
                continue
            ls_id = ls_dir.name
            scenes = []
            for scene_file in sorted(ls_dir.glob("*.json")):
                with open(scene_file, encoding="utf-8") as f:
                    scenes.append(json.load(f))
            if scenes:
                scenes_by_ls[ls_id] = scenes
        return scenes_by_ls

    print("[ERROR] No scenes data found in run folder.")
    return {}


def dry_run_summary(scenes_by_ls: dict, narrator_voice: str) -> None:
    """Print a summary of what would be generated without calling Polly."""
    total_narrators = 0
    total_chars = 0

    for ls_id, scenes in scenes_by_ls.items():
        print(f"\n  {ls_id}: {len(scenes)} scenes")
        for scene in scenes:
            scene_id = scene.get("scene_id", "?")
            narrator_text = scene.get("narrator_audio_text", "")
            char_dialogues = scene.get("character_dialogues", [])

            narrator_status = f"✓ ({len(narrator_text)} chars)" if narrator_text else "✗ (missing)"
            print(f"    {scene_id}  narrator={narrator_status}  chars={len(char_dialogues)}")
            total_narrators += 1 if narrator_text else 0
            total_chars += len(char_dialogues)

    print(f"\n  Would generate: {total_narrators} narrator files, {total_chars} character files")
    print(f"  Narrator voice: {narrator_voice}")
    print("\n  (dry-run: no Polly calls made)")


def main():
    parser = argparse.ArgumentParser(
        description="Generate Amazon Polly audio for a completed pipeline run."
    )
    parser.add_argument(
        "--run",
        required=True,
        help="Path to the run folder (e.g. outputs/run_20240101_120000)",
    )
    parser.add_argument(
        "--narrator",
        default="Matthew",
        help="Polly VoiceId for narrator (default: Matthew)",
    )
    parser.add_argument(
        "--ls",
        default=None,
        help="Only process a specific learning step (e.g. LS1)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be generated without calling Polly",
    )
    args = parser.parse_args()

    run_folder = Path(args.run)
    if not run_folder.exists():
        print(f"[ERROR] Run folder not found: {run_folder}")
        sys.exit(1)

    print(f"[AUDIO] Run folder: {run_folder}")

    # Load scenes
    scenes_by_ls = load_scenes(run_folder)
    if not scenes_by_ls:
        print("[ERROR] No scenes found. Cannot generate audio.")
        sys.exit(1)

    # Filter to specific LS if requested
    if args.ls:
        if args.ls not in scenes_by_ls:
            print(f"[ERROR] Learning step '{args.ls}' not found. Available: {list(scenes_by_ls.keys())}")
            sys.exit(1)
        scenes_by_ls = {args.ls: scenes_by_ls[args.ls]}

    total = sum(len(s) for s in scenes_by_ls.values())
    print(f"[AUDIO] Found {total} scenes across {len(scenes_by_ls)} learning step(s)")

    if args.dry_run:
        print("\n[DRY RUN] Would generate audio for:")
        dry_run_summary(scenes_by_ls, args.narrator)
        return

    # Generate audio
    service = AudioGeneratorService(run_folder=str(run_folder))
    manifest = service.generate_audio_for_all_scenes(
        scenes_by_ls=scenes_by_ls,
        narrator_voice_id=args.narrator,
    )

    # Print summary
    total_narrators = sum(
        1 for ls_data in manifest.values()
        for scene_data in ls_data.values()
        if scene_data.get("narrator")
    )
    total_chars = sum(
        len(scene_data.get("characters", {}))
        for ls_data in manifest.values()
        for scene_data in ls_data.values()
    )

    print(f"\n[AUDIO] Complete!")
    print(f"  Narrator files: {total_narrators}")
    print(f"  Character files: {total_chars}")
    print(f"  Manifest: {run_folder}/audio/manifest.json")


if __name__ == "__main__":
    main()
