"""
backend/server.py
-----------------
FastAPI backend that serves pipeline run data to the React frontend.

Startup:
    uvicorn backend.server:app --port 8000 --reload

Endpoints:
    GET  /api/runs                          → list all available runs
    GET  /api/runs/{run_id}                 → run metadata + scenes + audio manifest
    GET  /api/runs/{run_id}/scenes          → scenes grouped by LS
    GET  /api/runs/{run_id}/config          → run config.json
    GET  /static/{run_id}/images/...        → serve image files
    GET  /static/{run_id}/audio/...         → serve audio files
"""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------

app = FastAPI(title="Storytelling Pipeline API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Outputs directory — relative to project root where uvicorn is launched from
OUTPUTS_DIR = Path("outputs")


# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------


def get_run_folders() -> List[Path]:
    """Return all run_* folders under outputs/, sorted newest first."""
    if not OUTPUTS_DIR.exists():
        return []
    folders = [
        d for d in OUTPUTS_DIR.iterdir()
        if d.is_dir() and d.name.startswith("run_")
    ]
    return sorted(folders, key=lambda x: x.name, reverse=True)


def load_json(path: Path) -> Optional[Any]:
    """Load JSON from a file, return None if missing or invalid."""
    if not path.exists():
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def load_scenes_for_run(run_folder: Path) -> Dict[str, List[Dict]]:
    """
    Load all scenes for a run.

    Priority:
    1. parsed/scenes_full.json
    2. parsed/scenes_LS*.json files merged
    3. Individual scenes/LS*/*.json files merged
    """
    # Option 1
    full = load_json(run_folder / "parsed" / "scenes_full.json")
    if full:
        if isinstance(full, dict) and any(k.startswith("LS") for k in full):
            return full
        # Try nested "scenes" key
        nested = full.get("scenes") if isinstance(full, dict) else None
        if nested:
            return nested

    # Option 2: per-LS parsed files
    parsed_dir = run_folder / "parsed"
    if parsed_dir.exists():
        ls_files = sorted(parsed_dir.glob("scenes_LS*.json"))
        if ls_files:
            result = {}
            for f in ls_files:
                ls_id = f.stem.replace("scenes_", "")
                data = load_json(f)
                if data is not None:
                    result[ls_id] = data if isinstance(data, list) else data.get("scenes", [])
            if result:
                return result

    # Option 3: individual scene JSON files
    scenes_dir = run_folder / "scenes"
    if scenes_dir.exists():
        result = {}
        for ls_dir in sorted(scenes_dir.iterdir()):
            if not ls_dir.is_dir():
                continue
            scenes = []
            for sf in sorted(ls_dir.glob("*.json")):
                data = load_json(sf)
                if data:
                    scenes.append(data)
            if scenes:
                result[ls_dir.name] = scenes
        return result

    return {}


def run_summary(run_folder: Path) -> Dict[str, Any]:
    """Build a summary dict for a run folder."""
    config = load_json(run_folder / "inputs" / "config.json") or {}
    summary = load_json(run_folder / "summary.json") or {}

    # Count images
    images_dir = run_folder / "images"
    image_count = 0
    if images_dir.exists():
        image_count = sum(1 for _ in images_dir.rglob("*.png"))

    # Count audio files
    audio_dir = run_folder / "audio"
    audio_count = 0
    has_audio = False
    if audio_dir.exists():
        audio_count = sum(1 for _ in audio_dir.rglob("*.mp3"))
        has_audio = audio_count > 0

    # Check PPT
    ppt_path = run_folder / "ppt" / "lesson.pptx"

    return {
        "run_id": run_folder.name,
        "timestamp": config.get("timestamp", run_folder.name.replace("run_", "")),
        "chapter": config.get("chapter", ""),
        "subject": config.get("subject", ""),
        "class_level": config.get("class_level", ""),
        "text_model": config.get("text_model", ""),
        "image_model": config.get("image_model", ""),
        "image_mode": config.get("image_mode", ""),
        "generation_mode": config.get("generation_mode", ""),
        "image_count": image_count,
        "audio_count": audio_count,
        "has_audio": has_audio,
        "has_ppt": ppt_path.exists(),
        **summary,
    }


# ---------------------------------------------------------------------------
# API routes
# ---------------------------------------------------------------------------


@app.get("/api/runs")
def list_runs() -> List[Dict[str, Any]]:
    """List all available pipeline runs, newest first."""
    folders = get_run_folders()
    return [run_summary(f) for f in folders]


@app.get("/api/runs/{run_id}")
def get_run(run_id: str) -> Dict[str, Any]:
    """
    Return full run data: config, scenes grouped by LS, audio manifest,
    and story backbone.
    """
    run_folder = OUTPUTS_DIR / run_id
    if not run_folder.exists():
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")

    config = load_json(run_folder / "inputs" / "config.json") or {}
    story_backbone = load_json(run_folder / "parsed" / "story_backbone.json") or {}
    learning_steps = load_json(run_folder / "parsed" / "learning_steps.json") or {}
    scenes_by_ls = load_scenes_for_run(run_folder)
    audio_manifest = load_json(run_folder / "audio" / "manifest.json") or {}

    # Build scene list with audio paths attached
    enriched_scenes: Dict[str, List[Dict]] = {}
    for ls_id, scenes in scenes_by_ls.items():
        enriched = []
        ls_audio = audio_manifest.get(ls_id, {})
        for scene in scenes:
            scene_id = scene.get("scene_id", "")
            if not scene_id.startswith(ls_id):
                scene_id = f"{ls_id}_{scene_id}"

            # Attach audio URLs (frontend fetches from /static/...)
            scene_audio = ls_audio.get(scene_id, {})
            scene_copy = dict(scene)
            scene_copy["audio"] = {
                "narrator_url": (
                    f"/static/{run_id}/audio/{ls_id}/{scene_id}/narrator.mp3"
                    if scene_audio.get("narrator") else None
                ),
                "characters": {
                    char_id: f"/static/{run_id}/audio/{ls_id}/{scene_id}/char_{char_id.lower().replace(' ', '_')}.mp3"
                    for char_id in scene_audio.get("characters", {})
                },
            }
            # Attach image URL
            scene_copy["image_url"] = (
                f"/static/{run_id}/images/{ls_id}/{scene_id}.png"
            )
            enriched.append(scene_copy)
        enriched_scenes[ls_id] = enriched

    return {
        "run_id": run_id,
        "config": config,
        "story_backbone": story_backbone,
        "learning_steps": learning_steps.get("learning_steps", []),
        "scenes": enriched_scenes,
        "has_audio": bool(audio_manifest),
    }


@app.get("/api/runs/{run_id}/scenes")
def get_scenes(run_id: str) -> Dict[str, Any]:
    """Return scenes grouped by LS for a run."""
    run_folder = OUTPUTS_DIR / run_id
    if not run_folder.exists():
        raise HTTPException(status_code=404, detail=f"Run '{run_id}' not found")
    return load_scenes_for_run(run_folder)


@app.get("/api/runs/{run_id}/config")
def get_config(run_id: str) -> Dict[str, Any]:
    """Return config.json for a run."""
    run_folder = OUTPUTS_DIR / run_id
    config_path = run_folder / "inputs" / "config.json"
    if not config_path.exists():
        raise HTTPException(status_code=404, detail="Config not found")
    return load_json(config_path)


# ---------------------------------------------------------------------------
# Static file serving — images and audio
# ---------------------------------------------------------------------------
# Mount the outputs directory so frontend can fetch:
#   /static/{run_id}/images/LS1/LS1_S1.png
#   /static/{run_id}/audio/LS1/LS1_S1/narrator.mp3


@app.get("/static/{run_id}/{rest_of_path:path}")
def serve_static(run_id: str, rest_of_path: str):
    """Serve static files (images, audio) from the outputs directory."""
    file_path = OUTPUTS_DIR / run_id / rest_of_path
    if not file_path.exists():
        raise HTTPException(status_code=404, detail=f"File not found: {file_path}")

    # Determine media type
    suffix = file_path.suffix.lower()
    media_types = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".mp3": "audio/mpeg",
        ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    }
    media_type = media_types.get(suffix, "application/octet-stream")
    return FileResponse(str(file_path), media_type=media_type)


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------


@app.get("/health")
def health():
    return {"status": "ok", "outputs_dir": str(OUTPUTS_DIR.resolve())}
