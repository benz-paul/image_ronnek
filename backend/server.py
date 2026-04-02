"""
backend/server.py
-----------------
FastAPI backend that serves pipeline run data to the React frontend.

Startup:
    uvicorn backend.server:app --port 8000 --reload

Endpoints:
    POST /api/auth/login                    → authenticate user
    POST /api/auth/register                 → register new user
    GET  /api/runs                          → list all available runs
    GET  /api/runs/latest                   → redirect to latest run
    GET  /api/runs/{run_id}                 → run metadata + scenes + audio manifest
    GET  /api/runs/{run_id}/scenes          → scenes grouped by LS
    GET  /api/runs/{run_id}/config          → run config.json
    POST /api/avatar/generate               → generate face-consistent avatar via PuLID
    GET  /api/avatar/{username}             → get user's avatar JSON
    GET  /static/{run_id}/images/...        → serve image files
    GET  /static/{run_id}/audio/...         → serve audio files
    GET  /static/avatars/...               → serve avatar files
"""

import asyncio
import base64
import hashlib
import json
import os
import re
import shutil
import tempfile
import traceback
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from dotenv import load_dotenv
load_dotenv()

from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------

app = FastAPI(title="Storytelling Pipeline API", version="1.0.0")


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Catch-all: always return JSON so the frontend can parse the error."""
    print(f"[SERVER ERROR] Unhandled exception on {request.url.path}:\n{traceback.format_exc()}")
    return JSONResponse(
        status_code=500,
        content={"detail": str(exc) or "Internal server error", "type": type(exc).__name__},
    )

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Outputs directory — anchored to project root regardless of where uvicorn is launched from
OUTPUTS_DIR = Path(__file__).parent.parent / "outputs"

# User data + avatar storage
DATA_DIR   = Path(__file__).parent.parent / "data"
USERS_FILE = DATA_DIR / "users.json"
AVATARS_DIR = DATA_DIR / "avatars"
OLD_AVATARS_DIR = DATA_DIR / "old_avatar_repo"
DATA_DIR.mkdir(exist_ok=True)
AVATARS_DIR.mkdir(exist_ok=True)
OLD_AVATARS_DIR.mkdir(exist_ok=True)

# FAL API key from environment
FAL_API_KEY = os.getenv("FAL_API_KEY") or os.getenv("FAL_KEY", "")


# ---------------------------------------------------------------------------
# User store helpers
# ---------------------------------------------------------------------------

def _load_users() -> Dict[str, Any]:
    if not USERS_FILE.exists():
        return {}
    with open(USERS_FILE, encoding="utf-8") as f:
        return json.load(f)

def _save_users(users: Dict[str, Any]) -> None:
    with open(USERS_FILE, "w", encoding="utf-8") as f:
        json.dump(users, f, indent=2)

def _hash_password(pw: str) -> str:
    return hashlib.sha256(pw.encode()).hexdigest()


# ---------------------------------------------------------------------------
# Avatar JSON template (per spec from product owner)
# ---------------------------------------------------------------------------

AVATAR_TEMPLATE: Dict[str, Any] = {
    "version": "1.0",
    "visual": {
        "expressions": {
            "neutral": None, "happy": None, "sad": None,
            "angry": None, "surprised": None,
            "talking_open": None, "talking_closed": None,
        },
        "style": {
            "type": "semi_realistic_anime",
            "consistency_rules": {
                "same_hairstyle": True,
                "same_outfit": True,
                "same_color_palette": True,
            },
        },
    },
    "voice": {
        "engine": "polly",
        "voice_id": "Matthew",
        "language_code": "en-US",
        "engine_type": "neural",
        "speech_style": {"rate": "medium", "pitch": "medium", "volume": "medium"},
    },
    "character": {
        "personality": "curious, friendly teacher",
        "tone": "simple, engaging, explanatory",
        "target_audience": "students",
        "communication_style": "storytelling",
    },
    "animation": {
        "lip_sync": {
            "enabled": True,
            "method": "frame_switch",
            "frames": ["talking_open", "talking_closed"],
        },
        "movement": {
            "idle_motion": True,
            "gesture_support": ["hand_up", "pointing"],
            "camera_effects": ["zoom_in", "zoom_out", "pan"],
        },
    },
}


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

    # Check PPT - pipeline saves to lesson_output.pptx in run root; also check legacy ppt/lesson.pptx
    ppt_path = run_folder / "lesson_output.pptx"
    if not ppt_path.exists():
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
# Auth — simple hardcoded credentials (extend with a DB if needed)
# ---------------------------------------------------------------------------

USERS = {
    "admin": {"password": "academy123", "displayName": "Admin Agent"},
    "student": {"password": "decoder2024", "displayName": "Agent 01"},
    "demo": {"password": "demo", "displayName": "Demo User"},
}


class LoginRequest(BaseModel):
    username: str
    password: str


class RegisterRequest(BaseModel):
    fullName: str
    username: str
    email: str
    password: str


@app.post("/api/auth/login")
def login(req: LoginRequest):
    uname = req.username.lower().strip()
    # Check hardcoded users first
    user = USERS.get(uname)
    if user and user["password"] == req.password:
        return {"user": {"username": uname, "displayName": user["displayName"]}}
    # Check registered users
    db = _load_users()
    db_user = db.get(uname)
    if db_user and db_user["password_hash"] == _hash_password(req.password):
        return {"user": {"username": uname, "displayName": db_user["full_name"]}}
    raise HTTPException(status_code=401, detail="Invalid credentials")


@app.post("/api/auth/register")
def register(req: RegisterRequest):
    uname = req.username.lower().strip()
    if uname in USERS:
        raise HTTPException(status_code=409, detail="Username already taken")
    db = _load_users()
    if uname in db:
        raise HTTPException(status_code=409, detail="Username already taken")
    db[uname] = {
        "full_name": req.fullName,
        "email": req.email,
        "password_hash": _hash_password(req.password),
        "created_at": datetime.utcnow().isoformat() + "Z",
        "has_avatar": False,
    }
    _save_users(db)
    return {"user": {"username": uname, "displayName": req.fullName}}


# ---------------------------------------------------------------------------
# API routes
# ---------------------------------------------------------------------------


@app.get("/api/runs/latest")
def get_latest_run():
    """Return the summary of the most recent run (newest first)."""
    folders = get_run_folders()
    if not folders:
        raise HTTPException(status_code=404, detail="No runs found")
    return run_summary(folders[0])


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
    # Pipeline saves as story.json; story_backbone.json is the legacy name
    story_backbone = (
        load_json(run_folder / "parsed" / "story_backbone.json")
        or load_json(run_folder / "parsed" / "story.json")
        or {}
    )
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

            # Attach audio URLs + timing (frontend fetches from /static/...)
            scene_audio = ls_audio.get(scene_id, {})
            scene_copy = dict(scene)

            # Narrator info
            narrator_info = scene_audio.get("narrator", {})
            has_narrator = bool(narrator_info.get("path") if isinstance(narrator_info, dict) else narrator_info)
            narrator_dur = narrator_info.get("duration_ms", 0) if isinstance(narrator_info, dict) else 0

            # Dialogue timing list (from new manifest format)
            manifest_dialogues = scene_audio.get("dialogues", [])
            char_count = len(scene_audio.get("characters", {}))

            # Build dialogue URL list with timing
            dialogue_urls = []
            for i in range(max(char_count, len(manifest_dialogues))):
                key = f"dialogue_{str(i+1).zfill(2)}"
                entry = {
                    "url": f"/static/{run_id}/audio/{ls_id}/{scene_id}/{key}.mp3",
                    "speaker": manifest_dialogues[i].get("speaker", "unknown") if i < len(manifest_dialogues) else "unknown",
                    "duration_ms": manifest_dialogues[i].get("duration_ms", 0) if i < len(manifest_dialogues) else 0,
                    "start_ms": manifest_dialogues[i].get("start_ms", 0) if i < len(manifest_dialogues) else 0,
                }
                dialogue_urls.append(entry)

            # Check if combined.mp3 exists in manifest
            combined_path = scene_audio.get("combined_path", "")
            has_combined = bool(combined_path)
            combined_dur = scene_audio.get("combined_duration_ms", 0)

            scene_copy["audio"] = {
                "combined_url": (
                    f"/static/{run_id}/audio/{ls_id}/{scene_id}.mp3"
                    if has_combined else None
                ),
                "combined_duration_ms": combined_dur,
                "narrator_url": (
                    f"/static/{run_id}/audio/{ls_id}/{scene_id}/narrator.mp3"
                    if has_narrator else None
                ),
                "narrator_duration_ms": narrator_dur,
                "dialogue_urls": dialogue_urls,
                "total_duration_ms": scene_audio.get("total_duration_ms", 0),
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
# Avatar generation + serving
# ---------------------------------------------------------------------------

def _backup_existing_avatar(uname: str, avatar_dir: Path) -> None:
    """
    If the user already has an avatar, copy it to old_avatar_repo/{uname}/avatar_{N}/
    before overwriting with a regenerated one. N auto-increments each time.
    Files backed up: expressions/*.png, base_face.png, avatar.json, uploads/*
    """
    expressions_dir = avatar_dir / "expressions"
    has_existing = (
        (avatar_dir / "avatar.json").exists() or
        (avatar_dir / "base_face.png").exists() or
        (expressions_dir.exists() and any(expressions_dir.glob("*.png")))
    )
    if not has_existing:
        return

    user_archive = OLD_AVATARS_DIR / uname
    user_archive.mkdir(parents=True, exist_ok=True)

    # Find next slot: avatar_1, avatar_2, ...
    existing = sorted(
        [d for d in user_archive.iterdir() if d.is_dir() and d.name.startswith("avatar_")],
        key=lambda d: int(d.name.split("_")[1]) if d.name.split("_")[1].isdigit() else 0,
    )
    next_n = (int(existing[-1].name.split("_")[1]) + 1) if existing else 1
    slot = user_archive / f"avatar_{next_n}"
    slot.mkdir()

    # Copy expressions
    if expressions_dir.exists():
        slot_expr = slot / "expressions"
        slot_expr.mkdir()
        for img in expressions_dir.glob("*.png"):
            shutil.copy2(img, slot_expr / img.name)

    # Copy base_face and avatar.json
    for fname in ("base_face.png", "avatar.json"):
        src = avatar_dir / fname
        if src.exists():
            shutil.copy2(src, slot / fname)

    # Copy uploads (reference photos)
    uploads_dir = avatar_dir / "uploads"
    if uploads_dir.exists():
        slot_up = slot / "uploads"
        slot_up.mkdir()
        for f in uploads_dir.iterdir():
            if f.is_file():
                shutil.copy2(f, slot_up / f.name)

    print(f"[AVATAR] Backed up old avatar → old_avatar_repo/{uname}/avatar_{next_n}/ "
          f"({len(list((slot / 'expressions').glob('*.png'))) if (slot / 'expressions').exists() else 0} expressions)")


def _upload_image_to_fal(path: Path) -> str:
    """
    Upload a local image file to fal.ai CDN and return the public URL.
    Uses fal.media/files/upload — raw binary POST, same as the official fal-client SDK.
    """
    import mimetypes, json as _json
    mime, _ = mimetypes.guess_type(str(path))
    if not mime:
        mime = "image/jpeg"

    with open(path, "rb") as f:
        file_bytes = f.read()

    req = urllib.request.Request(
        "https://fal.media/files/upload",
        data=file_bytes,
        headers={
            "Authorization": f"Key {FAL_API_KEY}",
            "Content-Type": mime,
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        result = _json.loads(resp.read())

    url = (result.get("access_url") or result.get("url") or
           result.get("file_url") or result.get("cdn_url"))
    if not url:
        raise ValueError(f"fal.ai upload returned no URL. Response keys: {list(result.keys())}")
    return url


def _fal_queue_call(model: str, payload: Dict[str, Any], timeout_s: int = 300) -> Dict[str, Any]:
    """
    Generic fal.ai queue API helper.
    Submits a job, polls until COMPLETED, fetches and returns the result dict.
    Works for any fal.ai model that supports the queue API.
    """
    import time, json as _json

    post_headers = {"Authorization": f"Key {FAL_API_KEY}", "Content-Type": "application/json"}
    get_headers  = {"Authorization": f"Key {FAL_API_KEY}"}

    # Submit
    req = urllib.request.Request(
        f"https://queue.fal.run/{model}",
        data=_json.dumps(payload).encode(),
        headers=post_headers, method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            queue_data = _json.loads(r.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        raise ValueError(f"[{model}] submit {e.code}: {body[:500]}")

    request_id   = queue_data.get("request_id")
    status_url   = queue_data.get("status_url")
    response_url = queue_data.get("response_url")
    if not request_id or not status_url:
        raise ValueError(f"[{model}] missing request_id/status_url — got: {list(queue_data.keys())}")

    # Poll
    for _ in range(timeout_s // 4):
        time.sleep(4)
        poll_req = urllib.request.Request(status_url, headers=get_headers, method="GET")
        with urllib.request.urlopen(poll_req, timeout=30) as pr:
            s = _json.loads(pr.read())
        st = s.get("status")
        if st == "COMPLETED":
            break
        elif st == "FAILED":
            raise ValueError(f"[{model}] FAILED: {s.get('error', s.get('detail', 'unknown'))}")
        elif st not in ("IN_QUEUE", "IN_PROGRESS"):
            raise ValueError(f"[{model}] unexpected status: {st}")
    else:
        raise TimeoutError(f"[{model}] timed out after {timeout_s}s")

    # Fetch result
    if not response_url:
        response_url = f"https://queue.fal.run/{model}/requests/{request_id}"
    fetch_req = urllib.request.Request(response_url, headers=get_headers, method="GET")
    try:
        with urllib.request.urlopen(fetch_req, timeout=30) as fr:
            return _json.loads(fr.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        raise ValueError(f"[{model}] result fetch {e.code}: {body[:500]}")


def _extract_fal_image_url(result: Dict[str, Any]) -> str:
    """Pull the first image URL out of a fal.ai result dict."""
    images = result.get("images") or []
    if not images:
        raise ValueError(f"No images in fal result. Keys: {list(result.keys())}")
    img = images[0]
    url = img.get("url") if isinstance(img, dict) else img
    if not url:
        raise ValueError(f"Image entry has no url field: {img}")
    return url


def _generate_base_avatar(reference_image_url: str, seed: int) -> Tuple[str, str]:
    """
    Step 1 of the avatar pipeline.
    Convert a real photo into a semi-realistic anime avatar using flux-kontext/dev.
    Preserves face shape, hair colour, and features closely while applying the anime style.

    Returns (with_bg_url, no_bg_url):
      - with_bg_url: dark gradient background — used as input for expression generation
      - no_bg_url:   transparent PNG (rembg) — saved as base_face.png and neutral.png
    """
    payload: Dict[str, Any] = {
        "image_url": reference_image_url,
        "prompt": (
            "Transform this person into a semi-realistic anime character. "
            "Preserve the exact face shape, hair colour, and facial features closely. "
            "Style: detailed anime portrait with soft cel shading, natural warm lighting, "
            "large expressive eyes with bright highlights and reflections, smooth clean skin, "
            "SAO/Re:Zero anime quality level. "
            "FRAMING: half-body shot — head FULLY visible with generous headroom above hair, "
            "visible from waist up (waist, torso, shoulders, neck, and full head all in frame), "
            "character centered horizontally, dark atmospheric gradient background. "
            "CRITICAL: do NOT crop the head — head and hair must be completely visible. "
            "Neutral calm expression."
        ),
        "seed": seed,
        "guidance_scale": 3.5,
        "num_inference_steps": 28,
        "image_size": "portrait_4_3",
    }
    print(f"[AVATAR] flux-kontext/dev: generating semi-realistic anime base (seed={seed})...")
    result = _fal_queue_call("fal-ai/flux-kontext/dev", payload)
    with_bg_url = _extract_fal_image_url(result)
    print("[AVATAR] Removing background from base avatar...")
    no_bg_url = _remove_background(with_bg_url)
    return with_bg_url, no_bg_url


def _remove_background(image_url: str) -> str:
    """Remove background using fal-ai/imageutils/rembg. Returns transparent PNG CDN URL."""
    result = _fal_queue_call("fal-ai/imageutils/rembg", {"image_url": image_url})
    img = result.get("image", {})
    if isinstance(img, dict):
        url = img.get("url", "")
    else:
        url = str(img) if img else ""
    if not url:
        raise ValueError(f"rembg returned no image URL. Keys: {list(result.keys())}")
    return url


def _generate_expression_from_base(ref_photo_url: str, expression_prompt: str, seed: int) -> str:
    """
    Step 2 of the avatar pipeline — Option B.
    Each expression is generated independently from the original reference photo,
    with the full anime style + expression baked into a single prompt.
    This guarantees distinct expressions because each generation is unconstrained.
    Returns the CDN URL of the transparent expression variant.
    """
    payload: Dict[str, Any] = {
        "image_url": ref_photo_url,
        "prompt": expression_prompt,
        "seed": seed,
        "guidance_scale": 3.5,
        "num_inference_steps": 28,
        "image_size": "portrait_4_3",
    }
    result = _fal_queue_call("fal-ai/flux-kontext/dev", payload)
    with_bg_url = _extract_fal_image_url(result)
    return _remove_background(with_bg_url)


def _download_image(url: str, dest: Path) -> None:
    """Download an image from a URL and save to dest."""
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        with open(dest, "wb") as f:
            f.write(resp.read())


# Expression prompts — Option B: each generates directly from the reference photo.
# Full anime style + expression in one prompt → each variant is independently generated
# → guarantees distinct expressions.
_ANIME_STYLE = (
    "Transform this person into a semi-realistic anime character. "
    "Preserve the face shape, hair colour, and facial features closely. "
    "Style: detailed anime portrait, soft cel shading, natural warm lighting, "
    "large expressive eyes with bright highlights, smooth clean skin, SAO/Re:Zero quality. "
    "FRAMING: half-body shot — head FULLY visible with generous headroom above hair, "
    "visible from waist up (waist, torso, shoulders, neck, and full head all in frame), "
    "character centered horizontally, dark atmospheric gradient background. "
    "CRITICAL: do NOT crop the head — head and hair must be completely visible. "
)
EXPRESSION_PROMPTS: Dict[str, str] = {
    "talking_open": (
        _ANIME_STYLE +
        "Expression: TALKING — mouth open mid-speech SHOWING TEETH in a natural speaking position, "
        "eyebrows in COMPLETELY RELAXED flat position (NOT raised), "
        "eyes are HALF-LIDDED and CALM with normal-sized pupils (NOT wide, NOT shocked), "
        "head tilted slightly forward in a conversational lean, "
        "body language: relaxed shoulders, leaning in with confidence — clearly speaking a sentence. "
        "ABSOLUTE NEGATIVE: NO raised eyebrows, NO wide eyes, NO shocked expression, "
        "NO O-shaped mouth — teeth must be visible. This is NOT surprised."
    ),
    "talking_mid": (
        _ANIME_STYLE +
        "Expression: mouth half-open forming a word, lips naturally parted, "
        "attentive conversational look, slight eyebrow raise."
    ),
    "talking_closed": (
        _ANIME_STYLE +
        "Expression: mouth closed with a gentle soft smile, serene calm eyes, "
        "relaxed thoughtful look."
    ),
    "happy": (
        _ANIME_STYLE +
        "Expression: big joyful anime smile showing teeth, eyes curved upward into happy crescents, "
        "cheeks flushed pink, eyebrows raised high in delight, radiant beaming happiness."
    ),
    "sad": (
        _ANIME_STYLE +
        "Expression: tears streaming down cheeks, downturned trembling lips, "
        "eyebrows deeply angled inward, eyes glistening wet, visibly crying and heartbroken."
    ),
    "angry": (
        _ANIME_STYLE +
        "Expression: sharp narrowed glaring eyes, deep furrowed brow with crease lines, "
        "clenched jaw, gritted teeth, intensely fierce angry anime expression."
    ),
    "surprised": (
        _ANIME_STYLE +
        "Expression: SHOCKED SURPRISE — eyes BLOWN MAXIMALLY WIDE, pupils tiny dots surrounded "
        "by large white sclera, eyebrows LAUNCHED as high as physically possible (touching forehead), "
        "mouth forms a PERFECT ROUND O-SHAPE with NO teeth visible — lips form a shocked circle, "
        "body recoiling BACKWARD with shoulders hunched up toward ears in startle reflex, "
        "hands raised palms-out beside face in shock gesture, "
        "face shows pure stunned disbelief — frozen mid-gasp, completely speechless. "
        "ABSOLUTE NEGATIVE: NO visible teeth, NO calm eyes, NO relaxed eyebrows — "
        "this is NOT talking. Maximum shock. Extreme exaggerated anime shock reaction."
    ),
}


async def _generate_expression_task(
    expr_name: str,
    base_avatar_url: str,
    expression_prompt: str,
    expressions_dir: Path,
    uname: str,
    result_map: Dict[str, str],
    seed: int,
    label: str = "AVATAR",
) -> None:
    """Async task: generate one expression variant and save it. Updates result_map in-place."""
    try:
        img_url = await asyncio.to_thread(
            _generate_expression_from_base, base_avatar_url, expression_prompt, seed
        )
        dest = expressions_dir / f"{expr_name}.png"
        await asyncio.to_thread(_download_image, img_url, dest)
        result_map[expr_name] = f"/api/avatar/{uname}/expressions/{expr_name}.png"
        print(f"[{label}] Generated {expr_name}")
    except Exception as e:
        print(f"[{label}] Failed {expr_name}: {e}")


def _update_avatar_json(avatar_json_path: Path, new_expressions: Dict[str, str]) -> None:
    """Merge newly generated expressions into the saved avatar.json."""
    try:
        with open(avatar_json_path, encoding="utf-8") as f:
            data = json.load(f)
        data["visual"]["expressions"].update(new_expressions)
        data["metadata"]["updated_at"] = datetime.utcnow().isoformat() + "Z"
        with open(avatar_json_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        print(f"[AVATAR BG] avatar.json updated with: {list(new_expressions)}")
    except Exception as e:
        print(f"[AVATAR BG] Failed to update avatar.json: {e}")


async def _generate_remaining_expressions_bg(
    uname: str,
    expressions_dir: Path,
    avatar_json_path: Path,
    base_avatar_local_path: Path,
    secondary: Dict[str, str],
    seed: int,
) -> None:
    """
    Background task: generate remaining expression variants concurrently.
    Re-uploads the base avatar from local disk (CDN URLs from the request phase may expire).
    All calls run concurrently via asyncio.gather for speed.
    """
    try:
        base_url = await asyncio.to_thread(_upload_image_to_fal, base_avatar_local_path)
        print(f"[AVATAR BG] Re-uploaded reference photo → {base_url[:60]}...")
    except Exception as e:
        print(f"[AVATAR BG] Failed to re-upload reference photo: {e}")
        return

    bg_expressions: Dict[str, str] = {}
    tasks = [
        _generate_expression_task(
            expr_name, base_url, prompt, expressions_dir, uname, bg_expressions, seed, label="AVATAR BG"
        )
        for expr_name, prompt in secondary.items()
    ]
    await asyncio.gather(*tasks)
    if bg_expressions:
        _update_avatar_json(avatar_json_path, bg_expressions)


@app.post("/api/avatar/generate")
async def generate_avatar(
    background_tasks: BackgroundTasks,
    username: str = Form(...),
    photos: List[UploadFile] = File(...),
):
    """
    4-step avatar pipeline:
      1. Real photo → semi-realistic anime base via flux-kontext/dev (with dark bg)
      2. Background removed via rembg → transparent neutral.png / base_face.png
      3. Base (with bg) → 7 expression variants via flux-kontext/dev (strong anime expressions)
      4. Background removed from each expression → transparent PNGs

    Returns immediately after neutral + talking_open + talking_mid are ready.
    Remaining 5 expressions are generated concurrently in the background.
    """
    if not FAL_API_KEY:
        raise HTTPException(status_code=500, detail="FAL_API_KEY not configured in .env")
    if not photos:
        raise HTTPException(status_code=400, detail="At least one photo required")

    uname = username.lower().strip()
    avatar_dir = AVATARS_DIR / uname
    avatar_dir.mkdir(parents=True, exist_ok=True)

    # Back up existing avatar before overwriting (for regeneration history)
    _backup_existing_avatar(uname, avatar_dir)

    uploads_dir = avatar_dir / "uploads"
    uploads_dir.mkdir(exist_ok=True)
    expressions_dir = avatar_dir / "expressions"
    expressions_dir.mkdir(exist_ok=True)

    # Save uploaded photos locally (use the first one as the style reference)
    saved_paths: List[Path] = []
    for i, photo in enumerate(photos):
        suffix = Path(photo.filename or "photo.jpg").suffix or ".jpg"
        dest = uploads_dir / f"ref_{i:02d}{suffix}"
        with open(dest, "wb") as f:
            f.write(await photo.read())
        saved_paths.append(dest)

    # Upload the first reference photo to fal.ai CDN
    try:
        ref_cdn_url = await asyncio.to_thread(_upload_image_to_fal, saved_paths[0])
        print(f"[AVATAR] Uploaded {saved_paths[0].name} → {ref_cdn_url[:60]}...")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to upload reference photo: {e}")

    # Stable seed per user — same seed every regeneration for reproducibility
    seed = int(hashlib.md5(uname.encode()).hexdigest()[:8], 16) % (2**31)

    # ── Step 1: Generate neutral base avatar (flux-kontext → rembg) ─────────
    try:
        base_avatar_url, no_bg_url = await asyncio.to_thread(_generate_base_avatar, ref_cdn_url, seed)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Base avatar generation failed: {e}")

    # Save with-background version → used as source for all expression generation
    neutral_bg_path = expressions_dir / "neutral_bg.png"
    await asyncio.to_thread(_download_image, base_avatar_url, neutral_bg_path)
    # Save transparent version → displayed in UI
    neutral_path = expressions_dir / "neutral.png"
    await asyncio.to_thread(_download_image, no_bg_url, neutral_path)
    await asyncio.to_thread(_download_image, no_bg_url, avatar_dir / "base_face.png")
    generated_expressions: Dict[str, str] = {
        "neutral": f"/api/avatar/{uname}/expressions/neutral.png",
    }
    print("[AVATAR] Generated neutral (base avatar)")

    # ── Step 2a: Generate critical expressions concurrently ──────────────────
    CRITICAL   = ["talking_open", "talking_mid"]
    secondary  = {k: v for k, v in EXPRESSION_PROMPTS.items() if k not in CRITICAL}

    # Option B: pass ref_cdn_url (original photo) — each expression generated independently
    await asyncio.gather(*[
        _generate_expression_task(
            k, ref_cdn_url, EXPRESSION_PROMPTS[k],
            expressions_dir, uname, generated_expressions, seed,
        )
        for k in CRITICAL
    ])

    if len(generated_expressions) < 2:
        raise HTTPException(status_code=500, detail="Avatar generation failed — no expression images produced")

    import copy
    avatar_json = copy.deepcopy(AVATAR_TEMPLATE)
    avatar_json["avatar_id"] = f"{uname}_001"
    avatar_json["name"] = uname.capitalize()
    avatar_json["visual"]["base_face"] = f"/api/avatar/{uname}/base_face.png"
    for expr, url in generated_expressions.items():
        avatar_json["visual"]["expressions"][expr] = url
    avatar_json["metadata"] = {
        "created_at": datetime.utcnow().isoformat() + "Z",
        "updated_at": datetime.utcnow().isoformat() + "Z",
        "created_by": uname,
        "status": "active",
    }

    avatar_json_path = avatar_dir / "avatar.json"
    with open(avatar_json_path, "w", encoding="utf-8") as f:
        json.dump(avatar_json, f, indent=2)

    db = _load_users()
    if uname in db:
        db[uname]["has_avatar"] = True
        _save_users(db)

    # ── Step 2b: Generate remaining 5 expressions concurrently in background ─
    # Option B: pass saved_paths[0] (original reference photo) — background task
    # re-uploads it and generates each expression directly from the real photo.
    background_tasks.add_task(
        _generate_remaining_expressions_bg,
        uname, expressions_dir, avatar_json_path, saved_paths[0], secondary, seed,
    )
    print(f"[AVATAR] Returning {list(generated_expressions)}; background will add {list(secondary)}")

    return {
        "ok": True,
        "avatar_id": avatar_json["avatar_id"],
        "base_face": avatar_json["visual"]["base_face"],
        "expressions": generated_expressions,
        "avatar_json": avatar_json,
    }


@app.get("/api/avatar/{username}")
def get_avatar(username: str) -> Dict[str, Any]:
    """Return the avatar JSON for a user."""
    uname = username.lower().strip()
    avatar_json_path = AVATARS_DIR / uname / "avatar.json"
    if not avatar_json_path.exists():
        raise HTTPException(status_code=404, detail="Avatar not found")
    with open(avatar_json_path, encoding="utf-8") as f:
        return json.load(f)


@app.get("/api/avatar/{username}/base_face.png")
def get_avatar_base(username: str):
    path = AVATARS_DIR / username.lower() / "base_face.png"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Image not found")
    return FileResponse(str(path), media_type="image/png")


@app.get("/api/avatar/{username}/expressions/{expression}.png")
def get_avatar_expression(username: str, expression: str):
    path = AVATARS_DIR / username.lower() / "expressions" / f"{expression}.png"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Expression image not found")
    return FileResponse(str(path), media_type="image/png")


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
