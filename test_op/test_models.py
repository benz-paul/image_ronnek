"""
Model Comparison Test — Generates scenes using the real pipeline prompts (3A → 3B → 4),
then runs image generation using Flux 2 Pro in dialogue-in mode.
Also generates audio (Polly TTS) and tracks per-run token/cost metrics.

Usage:
    python test_op/test_models.py                  # all scenes
    python test_op/test_models.py --scenes 3       # limit to 3 scenes (save credits)
    python test_op/test_models.py --no-audio       # skip audio generation
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv

# ── Project root on sys.path so we can import pipeline modules ──────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
load_dotenv(PROJECT_ROOT / ".env", override=True)  # override=True so .env wins over terminal `set` commands

from brain.services.prompt_builder import PromptBuilder
from brain.services.image_generator import ImageGeneratorService
from brain.services.audio_generator import AudioGeneratorService
from utils.json_utils import safe_parse, safe_parse_with_retry
from utils.run_cost_tracker import RunCostTracker

# ── Constants ───────────────────────────────────────────────────────────────
IMAGE_MODELS = ["fal-flux2pro"]
IMAGE_MODES = ["dialogue_in"]

BASE_DIR = Path(__file__).parent
OUTPUTS_DIR = BASE_DIR / "outputs"

# ── Hardcoded test data ────────────────────────────────────────────────────

LEARNING_STEP = {
    "learning_step_id": "LS1",
    "title": "The Mysterious Numbers Appear",
    "concepts_introduced": ["Patterns in sequences", "Identifying AP from list"],
    "narrative_moment": (
        "Maya notices a strange sequence of numbers written in chalk on the school "
        "courtyard: 3, 7, 11, 15, 19. She sketches them in her notebook, feeling "
        "both puzzled and intrigued. The numbers seem deliberate but she can't "
        "decipher their meaning. When she shows the pattern to Mr. Chen during his "
        "office hours, his eyes light up with excitement. He points out how each "
        "number increases by the same amount. Leo joins them, skeptical at first, "
        "but pulls out his tablet to record the sequence. Mr. Chen asks them what "
        "they notice about the differences between consecutive numbers, planting "
        "the first seed of recognizing a mathematical pattern in their mysterious "
        "discovery."
    ),
}

STORY_BACKBONE = {
    "title": "The Sequence Sprint",
    "core_premise": (
        "Two students, Leo and Maya, discover the power of Arithmetic Progressions "
        "while training for a relay race, using AP concepts to strategize, track "
        "progress, and overcome challenges with the help of their math teacher."
    ),
    "characters": [
        {
            "name": "Leo",
            "role": "High school student and track team member",
            "personality": "Analytical, determined, and a bit of a math enthusiast. Loves finding patterns.",
            "visual_description": "16-year-old with curly brown hair, wearing glasses, athletic build, track shorts and school t-shirt.",
            "gender": "male",
            "voice_id": "Joey",
        },
        {
            "name": "Maya",
            "role": "High school student and track team co-captain",
            "personality": "Energetic, encouraging, practical. Competitive but believes in teamwork.",
            "visual_description": "16-year-old with a ponytail, warm smile, track team hoodie and running shoes, stopwatch around neck.",
            "gender": "female",
            "voice_id": "Joanna",
        },
        {
            "name": "Mr. Chen",
            "role": "Math teacher and informal mentor",
            "personality": "Wise, patient, methodical. Uses stories and examples to teach concepts.",
            "visual_description": "Mid-40s, kind face, button-up shirt with chalk-stained sleeves, reading glasses on a lanyard.",
            "gender": "male",
            "voice_id": "Brian",
        },
    ],
}

# Custom character set: Doraemon & Nobita
DORAEMON_STORY_BACKBONE = {
    "title": "Doraemon's Number Machine",
    "core_premise": (
        "Nobita is struggling with his math homework on Arithmetic Progressions. "
        "Doraemon pulls out the 'Sequence Visualizer' gadget from his pocket, which "
        "brings number patterns to life as physical objects. Together they discover "
        "how AP works by watching patterns materialize around them."
    ),
    "characters": [
        {
            "name": "Doraemon",
            "role": "Robot cat from the future, gadget inventor and patient teacher",
            "personality": "Helpful, patient, clever, always has the right gadget. Explains things with enthusiasm.",
            "visual_description": "Round blue robot cat with white belly and face, large round eyes, red nose, yellow bell on blue collar around neck, no ears, short stubby limbs, standing upright.",
            "gender": "male",
            "voice_id": "Matthew",
        },
        {
            "name": "Nobita",
            "role": "Lazy but curious schoolboy who struggles with math",
            "personality": "Lazy at first, easily confused, but genuinely curious when interested. Relatable, makes mistakes, asks basic questions.",
            "visual_description": "10-year-old Japanese boy with large round glasses, messy black hair, wearing blue shorts, yellow shirt, white sneakers.",
            "gender": "male",
            "voice_id": "Kevin",
        },
    ],
}

# Map of available character sets
CHARACTER_SETS = {
    "default": STORY_BACKBONE,
    "doraemon": DORAEMON_STORY_BACKBONE,
}


# ═══════════════════════════════════════════════════════════════════════════
#  LLM Service (copied from pipeline_graph.py to avoid heavy import)
# ═══════════════════════════════════════════════════════════════════════════

class LLMService:
    """Lightweight DeepSeek V3.2 client via OpenRouter."""

    def __init__(self):
        import requests as _r  # noqa: F401
        self._api_key = os.getenv("OPENROUTER_API_KEY")
        if not self._api_key:
            raise ValueError("OPENROUTER_API_KEY not set in .env")

    def invoke(
        self,
        prompt: str,
        temperature: float = 0.65,
        max_tokens: int = 4096,
    ) -> Dict[str, Any]:
        import requests

        messages = [
            {"role": "system", "content": "You must respond in valid JSON format. Always return JSON."},
            {"role": "user", "content": prompt},
        ]

        payload = {
            "model": "deepseek/deepseek-v3.2",
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        for attempt in range(3):
            try:
                resp = requests.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self._api_key}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                    timeout=120,
                )
                break
            except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
                if attempt < 2:
                    print(f"  [RETRY] LLM network error, attempt {attempt + 1}/3")
                    time.sleep(5)
                else:
                    raise Exception(f"LLM request failed after 3 attempts: {e}")

        if resp.status_code != 200:
            raise Exception(f"LLM API error {resp.status_code}: {resp.text[:300]}")

        content = resp.json()["choices"][0]["message"].get("content", "")
        usage = resp.json().get("usage", {})
        return {"content": content, "usage": usage}


# ═══════════════════════════════════════════════════════════════════════════
#  Helpers
# ═══════════════════════════════════════════════════════════════════════════


def build_character_details(story: Dict, scene: Dict) -> List[Dict]:
    """Merge character visual descriptions from story backbone into scene character list."""
    char_lookup = {c["name"].lower(): c for c in story["characters"]}
    details = []
    for char_name in scene.get("characters", []):
        info = char_lookup.get(char_name.lower(), {})
        details.append({
            "name": char_name,
            "visual_description": info.get("visual_description", ""),
            "gender": info.get("gender", ""),
        })
    return details


def save_json(data: Any, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def save_text(text: str, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


# ═══════════════════════════════════════════════════════════════════════════
#  Pipeline Steps
# ═══════════════════════════════════════════════════════════════════════════

def run_prompt3a(
    llm: LLMService,
    prompt_builder: PromptBuilder,
    run_folder: Path,
    cost_tracker: RunCostTracker,
) -> List[Dict]:
    """Run Prompt 3A — Scene Planning. Returns scene_plan list."""
    print("\n  [3A] Generating scene plan...")

    prompt3a = prompt_builder.get_prompt(
        "prompt3a",
        STORY_TITLE=STORY_BACKBONE["title"],
        STORY_PREMISE=STORY_BACKBONE["core_premise"],
        CHARACTER_REGISTRY=json.dumps(STORY_BACKBONE["characters"], indent=2),
        PREVIOUS_STEP_LAST_SCENE="None",
        LS_ID=LEARNING_STEP["learning_step_id"],
        LS_TITLE=LEARNING_STEP["title"],
        LS_CONCEPTS=json.dumps(LEARNING_STEP["concepts_introduced"]),
        LS_NARRATIVE=LEARNING_STEP["narrative_moment"],
    )

    save_text(prompt3a, run_folder / "prompts" / "prompt3a.txt")

    # Retry up to 3 times for valid scene plan with >= 8 scenes
    scene_plan = None
    for attempt in range(3):
        result = llm.invoke(prompt3a, temperature=0.4, max_tokens=3000)
        cost_tracker.add_llm_usage(result.get("usage", {}), label="prompt_3a")
        parsed = safe_parse(result["content"], prompt_type="scene_plan")

        if "_error" in parsed:
            print(f"    [RETRY] Parse failed (attempt {attempt + 1}/3)")
            continue

        plan = parsed.get("scene_plan", [])
        if len(plan) >= 8:
            scene_plan = plan
            break
        else:
            print(f"    [RETRY] Only {len(plan)} scenes (need >= 8), attempt {attempt + 1}/3")

    if not scene_plan:
        raise RuntimeError("Failed to generate valid scene plan after 3 attempts")

    save_json({"scene_plan": scene_plan}, run_folder / "parsed" / "scene_plan.json")
    print(f"  [3A] {len(scene_plan)} scenes planned")
    return scene_plan


def run_prompt3b(
    llm: LLMService,
    prompt_builder: PromptBuilder,
    scene_plan: List[Dict],
    run_folder: Path,
    cost_tracker: RunCostTracker,
    max_scenes: Optional[int] = None,
) -> List[Dict]:
    """Run Prompt 3B for each scene. Returns list of scene JSONs."""
    scenes = []
    story_summary_parts = []  # rolling window of last 8 scene summaries
    prev_scene_json = "None"

    effective_plan = scene_plan[:max_scenes] if max_scenes else scene_plan
    total = len(effective_plan)

    print(f"\n  [3B] Generating {total} scenes...")

    for i, plan_entry in enumerate(effective_plan):
        scene_id = plan_entry.get("scene_id", f"S{i+1}")
        phase = plan_entry.get("phase", "MICRO_LEARN")
        print(f"    [{scene_id}] ({i+1}/{total}) — {phase}")

        story_summary = " | ".join(story_summary_parts[-8:]) if story_summary_parts else "None — this is the first scene."

        prompt3b = prompt_builder.get_prompt(
            "prompt3b",
            SCENE_ID=scene_id,
            SCENE_PHASE=phase,
            SCENE_SUMMARY=plan_entry.get("summary", ""),
            CONCEPT_FOCUS=plan_entry.get("concept_focus", ""),
            STORY_TITLE=STORY_BACKBONE["title"],
            STORY_PREMISE=STORY_BACKBONE["core_premise"],
            CHARACTER_REGISTRY=json.dumps(STORY_BACKBONE["characters"], indent=2),
            LS_ID=LEARNING_STEP["learning_step_id"],
            LS_TITLE=LEARNING_STEP["title"],
            LS_CONCEPTS=json.dumps(LEARNING_STEP["concepts_introduced"]),
            TOTAL_SCENES=str(len(scene_plan)),
            STORY_SUMMARY=story_summary,
            PREVIOUS_SCENE=prev_scene_json,
        )

        save_text(prompt3b, run_folder / "prompts" / f"prompt3b_{scene_id}.txt")

        temp = 0.7 if phase == "HOOK" else 0.6
        scene = None
        for attempt in range(3):
            result = llm.invoke(prompt3b, temperature=temp, max_tokens=1500)
            cost_tracker.add_llm_usage(result.get("usage", {}), label=f"prompt_3b_{scene_id}")
            parsed = safe_parse(result["content"], prompt_type="scene")
            if "_error" not in parsed:
                scene = parsed
                break
            print(f"      [RETRY] Parse failed, attempt {attempt + 1}/3")

        if not scene:
            print(f"      [SKIP] Could not parse scene {scene_id}")
            continue

        # Inject IDs
        scene["scene_id"] = scene_id
        scene["phase"] = phase

        # Save
        save_json(scene, run_folder / "scenes" / f"LS1_{scene_id}.json")
        scenes.append(scene)

        # Update rolling summary
        action_summary = scene.get("action", "")[:100]
        story_summary_parts.append(f"{scene_id}: {action_summary}")
        prev_scene_json = json.dumps(scene, indent=2)

    print(f"  [3B] {len(scenes)} scenes generated successfully")
    return scenes


def run_prompt4(
    llm: LLMService,
    prompt_builder: PromptBuilder,
    scenes: List[Dict],
    run_folder: Path,
    cost_tracker: RunCostTracker,
) -> Dict[str, Dict[str, str]]:
    """
    Run Prompt 4 for each scene in dialogue_in mode only.
    Returns: {"dialogue_in": {"S1": prompt, ...}}
    """
    prompts = {"dialogue_in": {}}

    print(f"\n  [P4] Generating visual prompts for {len(scenes)} scenes...")

    # Character visual anchor — injected into every Prompt 4 call for consistency
    char_anchor_lines = []
    for c in STORY_BACKBONE["characters"]:
        char_anchor_lines.append(
            f"  - {c['name']}: {c['visual_description']}"
        )
    char_anchor = (
        "\n\nCHARACTER LOCK — use EXACT same appearance in every scene:\n"
        + "\n".join(char_anchor_lines)
    )

    for scene in scenes:
        scene_id = scene["scene_id"]

        # Build scene_data for Prompt 4 (matches main pipeline logic)
        character_details = build_character_details(STORY_BACKBONE, scene)
        dialogue_list = scene.get("dialogue", [])
        dialogue_text = "\n".join(dialogue_list) if dialogue_list else "(no dialogue)"

        scene_data = {
            "scene_id": scene_id,
            "setting": scene.get("setting", ""),
            "action": scene.get("action", ""),
            "characters": character_details,
            "dialogue": dialogue_list,
            "learning": scene.get("learning_moment", ""),
            "concepts": LEARNING_STEP["concepts_introduced"],
        }

        dialogue_instruction = (
            "DIALOGUE MODE - Include speech bubbles with EXACT text:\n"
            f"Use EXACT dialogue below in speech bubbles:\n{dialogue_text}\n\n"
            "Speech bubbles must be clearly readable with correct English text.\n"
            "Keep dialogue SHORT — each bubble must match the exact text provided."
            + char_anchor
        )

        prompt4 = prompt_builder.get_prompt(
            "prompt4",
            SCENE_DATA=json.dumps(scene_data, indent=2),
            DIALOGUE_INSTRUCTION=dialogue_instruction,
        )

        save_text(prompt4, run_folder / "prompts" / f"prompt4_{scene_id}_dialogue_in.txt")

        result = llm.invoke(prompt4)
        cost_tracker.add_llm_usage(result.get("usage", {}), label=f"prompt_4_{scene_id}")
        parsed, _, success = safe_parse_with_retry(
            result["content"], max_retries=2, prompt_type="prompt4"
        )

        if success:
            visual_prompt = (
                parsed.get("visual_prompt")
                or parsed.get("prompt")
                or result["content"]
            )
        else:
            visual_prompt = result["content"]

        prompts["dialogue_in"][scene_id] = visual_prompt
        print(f"    [{scene_id}] dialogue_in: {len(visual_prompt)} chars")

    return prompts


def run_image_generation(
    visual_prompts: Dict[str, Dict[str, str]],
    scenes: List[Dict],
    run_folder: Path,
    cost_tracker: RunCostTracker,
) -> Dict[str, Dict[str, Dict[str, Any]]]:
    """
    Generate images for each mode x model combination.
    Returns nested dict: results[mode][model][scene_id] = {"path": ..., "time": ..., "success": ...}
    """
    results = {}

    for mode in IMAGE_MODES:
        results[mode] = {}
        mode_prompts = visual_prompts[mode]

        for model_name in IMAGE_MODELS:
            print(f"\n  [IMG] {mode} / {model_name}")
            results[mode][model_name] = {}

            # Each model gets its own subfolder
            model_folder = run_folder / mode / model_name
            model_folder.mkdir(parents=True, exist_ok=True)

            gen = ImageGeneratorService(
                model=model_name,
                quality="low",
                image_mode="overlay" if mode == "overlay" else "dialogue",
                run_folder=str(model_folder),
            )

            for scene_id, visual_prompt in mode_prompts.items():
                start = time.time()
                print(f"    [{scene_id}] generating...", end="", flush=True)

                try:
                    path = gen.generate(
                        prompt=visual_prompt,
                        learning_step_id="LS1",
                        scene_id=scene_id,
                    )
                    elapsed = time.time() - start
                    success = path is not None
                    results[mode][model_name][scene_id] = {
                        "path": path,
                        "time": elapsed,
                        "success": success,
                    }
                    if success:
                        cost_tracker.add_image_generation(model_name, attempted=1, success=1)
                    else:
                        cost_tracker.add_image_generation(model_name, attempted=1, success=0)
                    status = "OK" if success else "FAIL"
                    print(f" {status} ({elapsed:.1f}s)")
                except Exception as e:
                    elapsed = time.time() - start
                    results[mode][model_name][scene_id] = {
                        "path": None,
                        "time": elapsed,
                        "success": False,
                        "error": str(e),
                    }
                    cost_tracker.add_image_generation(model_name, attempted=1, success=0)
                    print(f" ERROR ({e})")

    return results




def run_audio_generation(
    scenes: List[Dict],
    run_folder: Path,
    cost_tracker: RunCostTracker,
) -> Dict[str, Any]:
    """
    Generate TTS audio for all scenes using Amazon Polly.
    Audio saved to run_folder/audio/LS1/{scene_id}/narrator.mp3 + dialogue_NN.mp3

    Returns:
        Stats dict: {total, success, failed, narrator_chars, dialogue_chars}
    """
    print(f"\n  [AUDIO] Generating TTS for {len(scenes)} scenes...")

    stats = {"total": len(scenes), "success": 0, "failed": 0,
             "narrator_chars": 0, "dialogue_chars": 0}

    try:
        audio_service = AudioGeneratorService(run_folder=str(run_folder))
    except ValueError as e:
        print(f"  [AUDIO] Skipped — {e}")
        return stats

    for scene in scenes:
        scene_id = scene.get("scene_id", "unknown")
        full_scene_id = f"LS1_{scene_id}" if not scene_id.startswith("LS1") else scene_id

        narrator_text = scene.get("narrator_audio_text", "")
        char_dialogues = scene.get("character_dialogues", [])

        # Track characters for cost
        if narrator_text:
            cost_tracker.add_polly_synthesis(narrator_text, engine="neural")
            stats["narrator_chars"] += len(narrator_text)
        for cd in char_dialogues:
            text = cd.get("audio_text", cd.get("dialogue", ""))
            if text:
                # Determine engine from CHARACTER_VOICE_MAP
                char_id = cd.get("character_id", "").lower()
                from brain.services.audio_generator import CHARACTER_VOICE_MAP
                engine = CHARACTER_VOICE_MAP.get(char_id, {}).get("engine", "standard")
                cost_tracker.add_polly_synthesis(text, engine=engine)
                stats["dialogue_chars"] += len(text)

        try:
            result = audio_service.generate_audio_for_scene(
                scene=scene,
                ls_id="LS1",
                ls_index=0,
            )
            has_audio = bool(result.get("narrator") or result.get("characters"))
            if has_audio:
                stats["success"] += 1
            else:
                stats["failed"] += 1
        except Exception as e:
            print(f"    [{full_scene_id}] Audio failed: {e}")
            stats["failed"] += 1

    # Save manifest
    manifest_path = run_folder / "audio" / "manifest.json"
    print(f"  [AUDIO] Done: {stats['success']}/{stats['total']} scenes, "
          f"narrator={stats['narrator_chars']} chars, "
          f"dialogue={stats['dialogue_chars']} chars")
    return stats


def print_summary(
    img_results: Dict,
    audio_stats: Dict,
    cost_tracker: RunCostTracker,
    run_folder: Path,
    duration: float,
) -> None:
    """Print and save comparison summary with audio stats and cost report."""
    summary: Dict[str, Any] = {
        "run_folder": str(run_folder),
        "duration_seconds": round(duration, 1),
        "models": {},
        "audio": audio_stats,
    }

    print("\n" + "=" * 70)
    print("  MODEL COMPARISON SUMMARY")
    print("=" * 70)

    for mode in IMAGE_MODES:
        print(f"\n  -- {mode.upper()} --")
        for model_name in IMAGE_MODELS:
            model_results = img_results.get(mode, {}).get(model_name, {})
            total = len(model_results)
            success = sum(1 for r in model_results.values() if r.get("success"))
            failed = total - success
            avg_time = (
                sum(r.get("time", 0) for r in model_results.values()) / max(total, 1)
            )

            key = f"{mode}/{model_name}"
            summary["models"][key] = {
                "total": total,
                "success": success,
                "failed": failed,
                "avg_time_seconds": round(avg_time, 1),
            }

            bar = "#" * success + "-" * failed
            print(f"    {model_name:<20} {bar} {success}/{total}  avg {avg_time:.1f}s")

    # Audio summary
    print(f"\n  -- AUDIO (Polly TTS) --")
    a = audio_stats
    print(f"    Scenes: {a.get('success', 0)}/{a.get('total', 0)} success")
    print(f"    Narrator chars: {a.get('narrator_chars', 0)}")
    print(f"    Dialogue chars: {a.get('dialogue_chars', 0)}")

    # Cost summary
    cost = cost_tracker.compute_total()
    print(f"\n  -- ESTIMATED COSTS --")
    print(f"    LLM (DeepSeek):  ${cost['llm']['total_cost']:.4f}  ({cost['llm']['total_tokens']} tokens)")
    print(f"    Images (FAL):    ${cost['images']['total_cost']:.4f}")
    print(f"    Audio (Polly):   ${cost['audio_polly']['total_cost']:.4f}")
    print(f"    TOTAL:           ${cost['grand_total_usd']:.4f}")

    print(f"\n  Duration: {duration/60:.1f} min")
    print(f"  Output:   {run_folder}")
    print("=" * 70)

    # Save files
    save_json(summary, run_folder / "summary.json")
    cost_tracker.save(run_folder / "metrics")


# ═══════════════════════════════════════════════════════════════════════════
#  Main
# ═══════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="Model comparison test")
    parser.add_argument(
        "--scenes", type=int, default=None,
        help="Limit number of scenes (default: all from Prompt 3A)",
    )
    parser.add_argument(
        "--no-audio", action="store_true",
        help="Skip audio generation (saves AWS Polly costs)",
    )
    parser.add_argument(
        "--characters", type=str, default="default",
        choices=list(CHARACTER_SETS.keys()),
        help="Character set to use (default: Leo/Maya/Mr.Chen, doraemon: Doraemon/Nobita)",
    )
    args = parser.parse_args()

    # ── Select character set ──
    # Replace the global STORY_BACKBONE with the selected character set
    global STORY_BACKBONE
    STORY_BACKBONE = CHARACTER_SETS[args.characters]

    # ── Setup ──
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_folder = OUTPUTS_DIR / f"run_{run_id}"
    run_folder.mkdir(parents=True, exist_ok=True)

    print("=" * 70)
    print("  MODEL COMPARISON TEST")
    print("  Flux 2 Pro — dialogue-in mode")
    print("=" * 70)
    print(f"  Run folder: {run_folder}")
    print(f"  Characters: {args.characters} ({STORY_BACKBONE['title']})")
    if args.scenes:
        print(f"  Scene limit: {args.scenes}")
    if args.no_audio:
        print("  Audio: DISABLED")
    print()

    start_time = time.time()
    cost_tracker = RunCostTracker()

    llm = LLMService()
    prompt_builder = PromptBuilder()

    # ── Step 1: Scene Plan (Prompt 3A) ──
    scene_plan = run_prompt3a(llm, prompt_builder, run_folder, cost_tracker)

    # ── Step 2: Scene Generation (Prompt 3B) ──
    scenes = run_prompt3b(llm, prompt_builder, scene_plan, run_folder, cost_tracker, max_scenes=args.scenes)

    if not scenes:
        print("\n  [ERROR] No scenes generated. Aborting.")
        return

    # ── Step 3: Visual Prompts (Prompt 4 x 2 modes) ──
    visual_prompts = run_prompt4(llm, prompt_builder, scenes, run_folder, cost_tracker)

    # ── Step 4: Image Generation (3 models x 2 modes) ──
    img_results = run_image_generation(visual_prompts, scenes, run_folder, cost_tracker)

    # ── Step 5: Audio Generation ──
    if args.no_audio:
        audio_stats: Dict[str, Any] = {"total": len(scenes), "success": 0, "failed": 0,
                                        "narrator_chars": 0, "dialogue_chars": 0, "skipped": True}
    else:
        audio_stats = run_audio_generation(scenes, run_folder, cost_tracker)

    # ── Step 7: Summary + Metrics ──
    duration = time.time() - start_time
    print_summary(img_results, audio_stats, cost_tracker, run_folder, duration)


if __name__ == "__main__":
    main()
