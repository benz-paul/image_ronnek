# Frontend Complete Architecture & Analysis

## Purpose
This document provides a comprehensive analysis of the current frontend implementation for the Storytelling Pipeline. It explains how the frontend displays pipeline outputs, the API calls made, data flow, and integration details so that new frontend developers can understand and extend the system.

---

## 1. Frontend Technologies & Stack

### Core Stack
| Technology | Version | Purpose |
|------------|---------|---------|
| **Next.js** | 14.2.3 | React framework with file-based routing |
| **React** | 18 | UI library |
| **TypeScript** | 5 | Type safety |
| **TailwindCSS** | 3.3.0 | Styling |
| **PostCSS** | 8 | CSS processing |

### Additional Libraries
- **Material Symbols** (Google Fonts): Icon library used throughout UI
- **Playwright** (1.58.2): End-to-end testing

### Frontend Port
- Default: `http://localhost:3000`
- Communicates with backend at `http://localhost:8000`

---

## 2. Project File Structure

```
frontend/
├── app/                          # Next.js App Router
│   ├── page.tsx                  # Login page (root)
│   ├── layout.tsx                # Root layout
│   ├── globals.css               # Global styles
│   ├── dashboard/
│   │   └── page.tsx              # Dashboard - lists all runs
│   ├── player/
│   │   └── [runId]/
│   │       └── page.tsx          # Scene player - plays scenes with audio
│   ├── avatar/
│   │   ├── page.tsx              # Avatar creation page
│   │   ├── AvatarPageInner.tsx   # Avatar page logic & UI
│   │   └── edit/
│   │       └── page.tsx          # Avatar edit page
│   ├── register/
│   │   └── page.tsx              # User registration
│   └── profile/
│       └── page.tsx              # User profile
├── components/
│   ├── LatestRunButton.tsx       # Navigate to latest run
│   ├── DialogueBubble.tsx       # Character dialogue display
│   ├── InteractionOverlay.tsx   # Student interaction overlays
│   └── ProgressBar.tsx           # Progress indicators
├── hooks/
│   ├── useAuth.ts               # Authentication hook (localStorage-based)
│   └── useAudioPlayer.ts        # Audio playback hook for scenes
├── package.json
├── tailwind.config.js
├── tsconfig.json
└── next.config.js
```

---

## 3. Backend API Endpoints

All API endpoints are served by **FastAPI** at `http://localhost:8000`. The frontend proxies to these endpoints directly.

### Authentication APIs

| Endpoint | Method | Purpose | Backend Code Location |
|----------|--------|---------|----------------------|
| `/api/auth/login` | POST | Authenticate user with username/password | `backend/server.py:296-308` |
| `/api/auth/register` | POST | Register new user | `backend/server.py:311-327` |

### Run/Pipeline APIs

| Endpoint | Method | Purpose | Backend Code Location |
|----------|--------|---------|----------------------|
| `/api/runs` | GET | List all available pipeline runs (sorted newest first) | `backend/server.py:344-348` |
| `/api/runs/latest` | GET | Get the most recent run summary | `backend/server.py:335-341` |
| `/api/runs/{run_id}` | GET | Get full run data: config, scenes grouped by LS, audio manifest, story backbone | `backend/server.py:351-435` |
| `/api/runs/{run_id}/scenes` | GET | Get scenes grouped by LS for a run | `backend/server.py:438-444` |
| `/api/runs/{run_id}/config` | GET | Get config.json for a run | `backend/server.py:447-454` |

### Avatar APIs

| Endpoint | Method | Purpose | Backend Code Location |
|----------|--------|---------|----------------------|
| `/api/avatar/generate` | POST | Generate avatar from uploaded photos (uses FAL.ai) | `backend/server.py:827-951` |
| `/api/avatar/{username}` | GET | Get user's avatar JSON | `backend/server.py:954-962` |
| `/api/avatar/{username}/base_face.png` | GET | Get avatar base face image | `backend/server.py:965-970` |
| `/api/avatar/{username}/expressions/{expression}.png` | GET | Get specific expression image | `backend/server.py:973-978` |

### Static File Serving

| Endpoint | Purpose | Backend Code Location |
|----------|---------|----------------------|
| `/static/{run_id}/images/{ls_id}/{scene_id}.png` | Serve scene images | `backend/server.py:989-1006` |
| `/static/{run_id}/audio/{ls_id}/{scene_id}/narrator.mp3` | Serve narrator audio | `backend/server.py:989-1006` |
| `/static/{run_id}/audio/{ls_id}/{scene_id}/dialogue_{n}.mp3` | Serve character dialogues | `backend/server.py:989-1006` |
| `/static/{run_id}/audio/{ls_id}/{scene_id}.mp3` | Serve combined audio | `backend/server.py:989-1006` |

---

## 4. Data Flow: How Outputs Are Displayed in Frontend

### 4.1 Dashboard - Run Listing Flow

```
User visits /dashboard
       ↓
Dashboard calls GET /api/runs
       ↓
Backend scans outputs/ directory for run_* folders
       ↓
Backend returns array of run summaries:
[
  {
    run_id: "run_20260324_173734",
    timestamp: "20260324173734",
    chapter: "Arithmetic Progression",
    subject: "Mathematics",
    class_level: "10",
    image_count: 13,
    audio_count: 13,
    has_audio: true,
    has_ppt: true
  },
  ...
]
       ↓
Frontend displays grid of run cards
       ↓
User clicks a run card → navigates to /player/{run_id}
```

**Frontend Code Location**: `frontend/app/dashboard/page.tsx:42-47`
```typescript
useEffect(() => {
  fetch("/api/runs")
    .then((r) => r.json())
    .then((d) => { setRuns(d); setFetching(false); })
    .catch(() => { setFetchError("Cannot reach backend..."); setFetching(false); });
}, []);
```

### 4.2 Player Page - Scene Display Flow

```
User navigates to /player/run_20260324_173734
       ↓
Player calls GET /api/runs/{run_id}
       ↓
Backend returns:
{
  run_id: "run_20260324_173734",
  config: { ... },           # Config JSON
  story_backbone: { ... },   # Story backbone
  learning_steps: [ ... ],  # Learning steps array
  scenes: {
    "LS1": [ scene1, scene2, ... ],
    "LS2": [ ... ],
    ...
  },
  has_audio: true
}
       ↓
Each scene object is ENRICHED with audio URLs:
{
  scene_id: "S1",
  phase: "HOOK",
  setting: "...",
  action: "...",
  narrator_audio_text: "...",
  character_dialogues: [...],
  image_url: "/static/run_20260324_173734/images/LS1/LS1_S1.png",
  audio: {
    combined_url: "/static/run_20260324_173734/audio/LS1/LS1_S1.mp3",
    combined_duration_ms: 15000,
    narrator_url: "/static/run_20260324_173734/audio/LS1/LS1_S1/narrator.mp3",
    narrator_duration_ms: 8000,
    dialogue_urls: [
      { url: "/static/.../dialogue_01.mp3", speaker: "leosharma", duration_ms: 2000, start_ms: 5000 },
      { url: "/static/.../dialogue_02.mp3", speaker: "mayachen", duration_ms: 3000, start_ms: 9000 }
    ],
    total_duration_ms: 15000
  }
}
       ↓
Frontend flattens scenes by LS:
flatScenes = [
  { ls_id: "LS1", scene_index: 0, ... },
  { ls_id: "LS1", scene_index: 1, ... },
  { ls_id: "LS2", scene_index: 0, ... },
  ...
]
       ↓
User navigates scenes with prev/next buttons
Image is preloaded for next scene (to avoid flash)
Audio plays via useAudioPlayer hook
```

**Frontend Code Location**: `frontend/app/player/[runId]/page.tsx:85-91`
```typescript
useEffect(() => {
  if (!runId) return;
  fetch(`/api/runs/${runId}`)
    .then((r) => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json(); })
    .then((d: RunData) => { setRunData(d); setFlatScenes(flattenScenes(d.scenes)); setLoading(false); })
    .catch((e) => { setError(e.message); setLoading(false); });
}, [runId]);
```

---

## 5. Scene JSON Structure

### Location in Backend
Scenes are stored in multiple formats in the run folder:

```
outputs/run_20260324_173734/
├── scenes/
│   └── LS1/
│       ├── LS1_S1.json
│       ├── LS1_S2.json
│       └── ...
├── parsed/
│   ├── scenes_full.json         # Combined scenes
│   ├── scenes_LS1.json          # LS1 scenes
│   └── scenes_LS2.json          # LS2 scenes
└── ...
```

### Scene JSON Fields (from `outputs/run_20260324_173734/scenes/LS1/LS1_S1.json`)

**File**: `outputs/run_20260324_173734/scenes/LS1/LS1_S1.json` (entire file - 30 lines)

```json
{
  "scene_id": "S1",
  "phase": "HOOK",
  "setting": "The crowded main hallway...",
  "characters": ["Leo Sharma"],
  "action": "Leo's fingers are tapping...",
  "dialogue": [
    "(muttered to himself) What sequence?",
    "(still to himself, voice barely audible) Begins at three what?"
  ],
  "learning_moment": "Leo encounters a mysterious...",
  "transition_hint": "Leo will stare at the note...",
  "narrator_audio_text": "The hallway buzzed...",
  "character_dialogues": [
    {
      "character_id": "leosharma",
      "voice_id": "Joey",
      "dialogue": "What sequence?",
      "audio_text": "What sequence?"
    },
    {
      "character_id": "leosharma",
      "voice_id": "Joey",
      "dialogue": "Begins at three what? ...",
      "audio_text": "Begins at three what? ..."
    }
  ]
}
```

### How Scenes Are Loaded (Backend `server.py`)

**Backend Code Location**: `backend/server.py:181-230`

```python
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
```

---

## 6. Audio Manifest Structure

### Location
`outputs/run_20260324_173734/audio/manifest.json` (entire file - 399 lines)

### Audio Manifest JSON

**File**: `outputs/run_20260324_173734/audio/manifest.json`

```json
{
  "run_id": "run_20260324_173734",
  "narrator_voice_id": "Matthew",
  "scenes": {
    "LS1_S1": {
      "narrator": {
        "text": "The hallway buzzed...",
        "voice_id": "Matthew",
        "audio_file": "audio/LS1/LS1_S1/narrator.mp3"
      },
      "characters": [
        {
          "character_id": "leosharma",
          "voice_id": "Joey",
          "text": "What sequence?",
          "audio_file": "audio/LS1/LS1_S1/char_leosharma.mp3"
        },
        ...
      ]
    },
    ...
  }
}
```

### Audio File Storage Structure

```
outputs/run_20260324_173734/audio/
├── manifest.json
└── LS1/
    ├── LS1_S1/
    │   ├── narrator.mp3           # Narrator audio
    │   ├── char_leosharma.mp3     # Character 1 dialogue
    │   └── char_mayachen.mp3      # Character 2 dialogue
    ├── LS1_S2/
    │   ├── narrator.mp3
    │   ├── char_leosharma.mp3
    │   └── char_mayachen.mp3
    └── ...
```

### How Audio Is Combined with Scenes (Backend)

**Backend Code Location**: `backend/server.py:351-435`

```python
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
```

---

## 7. How Audio Playback Works in Frontend

### Hook: `useAudioPlayer.ts`

**File**: `frontend/hooks/useAudioPlayer.ts` (entire file - 144 lines)

The audio player provides:
- **play(url)**: Play single audio file (line 90-98)
- **playQueue(items)**: Play multiple audio files in sequence (line 101-109)
- **pause()**: Pause playback (line 112-116)
- **resume()**: Resume playback (line 118-121)
- **stop()**: Stop and reset (line 123-132)
- **state**: Current state (line 25, 140)

**Code Reference**: `frontend/hooks/useAudioPlayer.ts:19-144`

```typescript
export function useAudioPlayer({
  onEnded,
  onSegmentStart,
  onQueueEnd,
}: UseAudioPlayerOptions = {}) {
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const [state, setState] = useState<AudioState>("idle");
  const [currentUrl, setCurrentUrl] = useState<string | null>(null);
  const queueRef = useRef<QueueItem[]>([]);
  const queueIndexRef = useRef(-1);
  const isPausedRef = useRef(false);
  // ... implementation
}
```

### Scene Audio Logic (Player Page)

**Frontend Code Location**: `frontend/app/player/[runId]/page.tsx:96-146`

```typescript
useEffect(() => {
  const scene = flatScenes[currentIndex];
  if (!scene) return;
  setImageLoaded(false); setShowDialogue(false); setActiveDialogueIndex(-1); setShowInteraction(false);
  clearDialogueTimers();
  const t = setTimeout(() => {
    if (isPaused || audioMode === "off") {
      if (audioMode === "off" && !isPaused) {
        const a = setTimeout(() => advanceScene(), 5000);
        dialogueTimersRef.current.push(a);
      }
      return;
    }
    const audio = scene.audio;
    if (audio?.combined_url) {
      play(audio.combined_url);
      const dlgs = audio.dialogue_urls ?? [];
      const hasStartMs = dlgs.length > 0 && dlgs.some((d) => (d.start_ms ?? 0) > 0);
      if (hasStartMs) {
        // Reveal each dialogue bubble at its exact start time within the combined audio
        dlgs.forEach((d, i) => {
          const dt = setTimeout(() => {
            setShowDialogue(true);
            setActiveDialogueIndex(i);
          }, Math.max(200, d.start_ms ?? 0));
          dialogueTimersRef.current.push(dt);
        });
      } else {
        // Fallback: show all dialogues at 55% of total duration
        const dur = audio.combined_duration_ms ?? 5000;
        const dt = setTimeout(() => { setShowDialogue(true); setActiveDialogueIndex(999); }, Math.max(500, dur * 0.55));
        dialogueTimersRef.current.push(dt);
      }
    } else if (audio?.narrator_url || (audio?.dialogue_urls?.length ?? 0) > 0) {
      const q: QueueItem[] = [];
      if (audio?.narrator_url)
        q.push({ url: audio.narrator_url, speaker: "narrator", duration_ms: audio.narrator_duration_ms ?? 0 });
      for (const d of audio?.dialogue_urls ?? [])
        q.push({ url: d.url, speaker: d.speaker, duration_ms: d.duration_ms ?? 0 });
      playQueue(q);
      const dt = setTimeout(() => setShowDialogue(true), Math.max(500, (audio?.narrator_duration_ms ?? 3000) * 0.55));
      dialogueTimersRef.current.push(dt);
    } else {
      setShowDialogue(true); setActiveDialogueIndex(999);
      const dt = setTimeout(() => advanceScene(), 5000);
      dialogueTimersRef.current.push(dt);
    }
  }, 350);
  return () => { clearTimeout(t); clearDialogueTimers(); };
}, [currentIndex]);
```

### Audio Auto-Advance

**Frontend Code Location**: `frontend/app/player/[runId]/page.tsx:74-80`

```typescript
const handleQueueEnd = useCallback(() => {
  if (isPaused) return;
  const scene = flatScenes[currentIndex];
  const inter = scene?.student_interaction;
  if (inter?.type && inter.type !== "none") setTimeout(() => setShowInteraction(true), 500);
  else setTimeout(() => advanceScene(), 2500);
}, [isPaused, advanceScene, flatScenes, currentIndex]);
```

---

## 8. Image Pathways

### Scene Images

| Frontend Access | Actual File Location |
|-----------------|---------------------|
| `/static/{run_id}/images/{ls_id}/{scene_id}.png` | `outputs/{run_id}/images/{ls_id}/{scene_id}.png` |

### Example
- **Frontend URL**: `/static/run_20260324_173734/images/LS1/LS1_S1.png`
- **Actual path**: `outputs/run_20260324_173734/images/LS1/LS1_S1.png`

### Image Display in Player

**Frontend Code Location**: `frontend/app/player/[runId]/page.tsx:243-256`

```typescript
{cs.image_url ? (
  // eslint-disable-next-line @next/next/no-img-element
  <img 
    key={cs.scene_id} 
    src={cs.image_url} 
    alt={cs.scene_id}
    onLoad={() => { setImageLoaded(true); setDisplayedImageUrl(cs.image_url ?? null); }}
    onError={() => { setImageLoaded(true); setDisplayedImageUrl(cs.image_url ?? null); }}
    className={"absolute inset-0 w-full h-full object-cover kenburns transition-opacity duration-700 " + (imageLoaded ? "opacity-100" : "opacity-0")} 
  />
) : (
  <div className="absolute inset-0 w-full h-full flex items-center justify-center digital-grid">
    <div className="text-center text-on-surface-variant/30">
      <span className="material-symbols-outlined text-6xl mb-2 block">image</span>
      <p className="font-label text-xs tracking-widest uppercase">Image generating...</p>
    </div>
  </div>
)}
```

### Image Preloading

**Frontend Code Location**: `frontend/app/player/[runId]/page.tsx:149-155`

```typescript
// Preload next scene image to eliminate flash on transition
useEffect(() => {
  const next = flatScenes[currentIndex + 1];
  if (next?.image_url) {
    const img = new window.Image();
    img.src = next.image_url;
  }
}, [currentIndex, flatScenes]);
```

### Static File Serving (Backend)

**Backend Code Location**: `backend/server.py:989-1006`

```python
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
```

---

## 9. Avatar System in Frontend

### Avatar Generation Flow

```
User navigates to /avatar
       ↓
User uploads 1+ reference photos
       ↓
User clicks "Generate My Avatar"
       ↓
Frontend sends POST /api/avatar/generate with FormData:
   - username: "username"
   - photos: [image files]
       ↓
Backend processes:
   1. Upload photo to FAL.ai CDN
   2. Generate base avatar (flux-kontext/dev)
   3. Remove background (rembg)
   4. Generate 7 expressions (talking_open, talking_mid, talking_closed, happy, sad, angry, surprised)
   5. Remove background from each expression
   6. Save to data/avatars/{username}/
       ↓
Backend returns avatar JSON + expression URLs
       ↓
Frontend displays avatar with expression switcher
```

### Avatar Generation API (Backend)

**Backend Code Location**: `backend/server.py:827-951`

```python
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
    # ... implementation
```

### Avatar JSON Structure

**File**: `data/avatars/1234/avatar.json`

```json
{
  "avatar_id": "1234_001",
  "name": "1234",
  "version": "1.0",
  "visual": {
    "base_face": "/api/avatar/1234/base_face.png",
    "expressions": {
      "neutral": "/api/avatar/1234/expressions/neutral.png",
      "happy": "/api/avatar/1234/expressions/happy.png",
      "sad": "/api/avatar/1234/expressions/sad.png",
      "angry": "/api/avatar/1234/expressions/angry.png",
      "surprised": "/api/avatar/1234/expressions/surprised.png",
      "talking_open": "/api/avatar/1234/expressions/talking_open.png",
      "talking_mid": "/api/avatar/1234/expressions/talking_mid.png",
      "talking_closed": "/api/avatar/1234/expressions/talking_closed.png"
    },
    "style": {
      "type": "semi_realistic_anime",
      "consistency_rules": {
        "same_hairstyle": true,
        "same_outfit": true,
        "same_color_palette": true
      }
    }
  },
  "voice": {
    "engine": "polly",
    "voice_id": "Matthew",
    "language_code": "en-US",
    "engine_type": "neural",
    "speech_style": {
      "rate": "medium",
      "pitch": "medium",
      "volume": "medium"
    }
  },
  "character": {
    "personality": "curious, friendly teacher",
    "tone": "simple, engaging, explanatory",
    "target_audience": "students",
    "communication_style": "storytelling"
  },
  "animation": {
    "lip_sync": {
      "enabled": true,
      "method": "frame_switch",
      "frames": ["talking_open", "talking_closed"]
    },
    "movement": {
      "idle_motion": true,
      "gesture_support": ["hand_up", "pointing"],
      "camera_effects": ["zoom_in", "zoom_out", "pan"]
    }
  },
  "metadata": {
    "created_at": "2026-03-24T17:00:00Z",
    "updated_at": "2026-03-24T17:00:00Z",
    "created_by": "1234",
    "status": "active"
  }
}
```

### Avatar Storage Location

```
data/avatars/{username}/
├── avatar.json              # Full avatar JSON
├── base_face.png            # Base face (transparent)
├── expressions/
│   ├── neutral.png
│   ├── happy.png
│   ├── sad.png
│   ├── angry.png
│   ├── surprised.png
│   ├── talking_open.png
│   ├── talking_mid.png
│   └── talking_closed.png
└── uploads/
    ├── ref_00.jpeg          # Original uploaded photos
    └── ref_01.jpeg
```

**File Path Example**: `data/avatars/1234/avatar.json`

### Avatar API Endpoints

| Endpoint | Method | Purpose | Backend Code Location |
|----------|--------|---------|----------------------|
| `GET /api/avatar/{username}` | Get avatar JSON | `backend/server.py:954-962` |
| `GET /api/avatar/{username}/base_face.png` | Get base face image | `backend/server.py:965-970` |
| `GET /api/avatar/{username}/expressions/{expression}.png` | Get expression image | `backend/server.py:973-978` |
| `POST /api/avatar/generate` | Generate new avatar | `backend/server.py:827-951` |

### Avatar Expression Switching (Frontend)

**Frontend Code Location**: `frontend/app/avatar/AvatarPageInner.tsx:111-196`

```typescript
function AvatarPreview({
  avatar, activeExpr, onExprChange,
}: {
  avatar: AvatarJson; activeExpr: ExpressionKey; onExprChange: (e: ExpressionKey) => void;
}) {
  const expressions: { key: ExpressionKey; icon: string; label: string }[] = [
    { key: "neutral",  icon: "sentiment_neutral",    label: "Neutral"  },
    { key: "happy",    icon: "sentiment_very_satisfied", label: "Happy"  },
    { key: "sad",      icon: "sentiment_dissatisfied", label: "Sad"     },
    { key: "angry",    icon: "mood_bad",              label: "Angry"   },
    { key: "surprised",icon: "sentiment_excited",     label: "Surprised"},
    { key: "talking_open", icon: "record_voice_over", label: "Talking" },
  ];

  const imgUrl = avatar.visual.expressions[activeExpr] || avatar.visual.base_face;
  // ...
}
```

### Avatar Generation Call (Frontend)

**Frontend Code Location**: `frontend/app/avatar/AvatarPageInner.tsx:236-260`

```typescript
async function handleGenerate() {
  if (!hasEnoughPhotos) return;
  setStep("generating");
  setGenError("");
  setProgress(["Uploading reference photos..."]);

  const formData = new FormData();
  formData.append("username", usernameParam);
  allFiles.forEach((f) => formData.append("photos", f));

  try {
    setProgress((p) => [...p, "Generating semi-realistic anime avatar with Flux Kontext..."]);
    const res = await fetch("/api/avatar/generate", { method: "POST", body: formData });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Generation failed");

    setProgress((p) => [...p, "Generating expressions: neutral, talking...", "Polishing remaining expressions in background...", "Finalising avatar..."]);
    setAvatar(data.avatar_json);
    setStep("done");
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : "Unknown error";
    setGenError(message);
    setStep("upload");
  }
}
```

---

## 10. Authentication Flow

### Login Process

```
User enters credentials on / page
       ↓
Frontend calls POST /api/auth/login
       ↓
Backend validates against:
   - Hardcoded users (admin/academy123, student/decoder2024, demo/demo)
   - Registered users from data/users.json
       ↓
Backend returns: { user: { username, displayName } }
       ↓
Frontend stores user in localStorage (key: "academy_user")
       ↓
User is redirected to /dashboard
```

### Login API (Backend)

**Backend Code Location**: `backend/server.py:296-308`

```python
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
```

### Hardcoded Users

**Backend Code Location**: `backend/server.py:277-281`

```python
USERS = {
    "admin": {"password": "academy123", "displayName": "Admin Agent"},
    "student": {"password": "decoder2024", "displayName": "Agent 01"},
    "demo": {"password": "demo", "displayName": "Demo User"},
}
```

### Auth Hook (`useAuth.ts`)

**Frontend Code Location**: `frontend/hooks/useAuth.ts` (entire file - 59 lines)

```typescript
export function useAuth() {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    try {
      const stored = localStorage.getItem(STORAGE_KEY);
      if (stored) setUser(JSON.parse(stored));
    } catch {
      // ignore
    }
    setLoading(false);
  }, []);

  const login = useCallback(
    async (username: string, password: string): Promise<{ ok: boolean; error?: string }> => {
      try {
        const res = await fetch("/api/auth/login", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ username, password }),
        });
        const data = await res.json();
        if (res.ok && data.user) {
          setUser(data.user);
          localStorage.setItem(STORAGE_KEY, JSON.stringify(data.user));
          return { ok: true };
        }
        return { ok: false, error: data.detail || "Invalid credentials" };
      } catch {
        return { ok: false, error: "Backend offline — run: uvicorn backend.server:app --port 8000 --reload" };
      }
    },
    []
  );

  const logout = useCallback(() => {
    setUser(null);
    localStorage.removeItem(STORAGE_KEY);
  }, []);

  return { user, loading, login, logout };
}
```

### Protected Routes

**Frontend Code Location**: `frontend/app/player/[runId]/page.tsx:60`

```typescript
useEffect(() => { if (!authLoading && !user) router.replace("/"); }, [authLoading, user, router]);
```

Similar protection exists in:
- `frontend/app/dashboard/page.tsx:38-40`
- `frontend/app/avatar/page.tsx:6-14`
- `frontend/app/profile/page.tsx` (not examined but similar pattern)

---

## 11. CORS Configuration (Backend)

**Backend Code Location**: `backend/server.py:63-69`

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

This tells the browser that it's okay for the frontend running on port 3000 to make requests to the backend on port 8000.

---

## 12. Key Files Summary with Line Numbers

### Frontend Key Files

| File | Purpose | Key Lines |
|------|---------|-----------|
| `frontend/app/page.tsx` | Login page | Entire file (Login form, auth call) |
| `frontend/app/dashboard/page.tsx` | Run listing dashboard | Lines 38-47 (fetch runs), 236-298 (render cards) |
| `frontend/app/player/[runId]/page.tsx` | Scene player with audio | Lines 85-91 (fetch run), 96-146 (audio logic), 243-256 (image display) |
| `frontend/app/avatar/page.tsx` | Avatar creation page | Lines 1-16 (wrapper component) |
| `frontend/app/avatar/AvatarPageInner.tsx` | Avatar generation logic | Lines 236-260 (handleGenerate), 111-196 (AvatarPreview) |
| `frontend/hooks/useAuth.ts` | Authentication hook | Lines 31-50 (login), 53-56 (logout) |
| `frontend/hooks/useAudioPlayer.ts` | Audio playback hook | Lines 90-109 (play, playQueue), 112-132 (pause, resume, stop) |

### Backend Key Files

| File | Purpose | Key Lines |
|------|---------|-----------|
| `backend/server.py` | FastAPI server with all endpoints | Entire file (1016 lines) |
| `backend/server.py:296-308` | Login endpoint | Login logic |
| `backend/server.py:311-327` | Register endpoint | Registration logic |
| `backend/server.py:335-341` | Get latest run | Returns most recent run |
| `backend/server.py:344-348` | List all runs | Returns all runs |
| `backend/server.py:351-435` | Get full run data | Returns scenes + audio + config |
| `backend/server.py:438-444` | Get scenes only | Returns scenes by LS |
| `backend/server.py:447-454` | Get config only | Returns config.json |
| `backend/server.py:827-951` | Avatar generation | 4-step avatar pipeline |
| `backend/server.py:954-962` | Get avatar JSON | Returns avatar JSON |
| `backend/server.py:989-1006` | Static file serving | Serves images/audio |

### Key Data Directories

| Directory | Contents |
|-----------|----------|
| `outputs/run_*/` | Pipeline run outputs (scenes, images, audio) |
| `data/avatars/{username}/` | Generated avatars |
| `data/users.json` | Registered users |

---

## 13. Summary for New Frontend Developers

### To Display a Run's Scenes:
1. Call `GET /api/runs/{run_id}` (backend endpoint at `server.py:351`)
2. Get `scenes` object containing scenes grouped by LS
3. Each scene has `image_url` for display and `audio` for playback

### To Play Audio:
1. Use `useAudioPlayer` hook (`frontend/hooks/useAudioPlayer.ts`)
2. Call `play(combined_url)` for single audio
3. Or build queue with `playQueue([{url, speaker, duration_ms}, ...])`

### To Work with Avatars:
1. Upload photos via `POST /api/avatar/generate`
2. Fetch avatar with `GET /api/avatar/{username}`
3. Switch expressions by updating `activeExpr` state

### Key Paths to Remember:
- Backend runs on port 8000
- Frontend runs on port 3000
- Static files served via `/static/{run_id}/...`
- Avatar files served via `/api/avatar/{username}/...`

---

## 14. Environment Setup for Development

### Running Backend
```bash
cd Automation_prompt_json_generator
uvicorn backend.server:app --port 8000 --reload
```

### Running Frontend
```bash
cd frontend
npm run dev
```

### Access Points
- Frontend: http://localhost:3000
- Backend API: http://localhost:8000
- Backend Docs: http://localhost:8000/docs
- Health Check: http://localhost:8000/health

---

## 15. WebSocket Support (Future Enhancement)

If real-time updates are needed (like progress bars for avatar generation), WebSockets can be added. Example implementation:

### Backend (to be added in `server.py`)
```python
from fastapi import WebSocket

@app.websocket("/ws/avatar/{username}")
async def avatar_progress(websocket: WebSocket, username: str):
    await websocket.accept()
    # Send progress updates as avatar generates
    await websocket.send_json({"status": "generating", "step": 1})
    await websocket.send_json({"status": "done"})
```

### Frontend (to use)
```typescript
const ws = new WebSocket('ws://localhost:8000/ws/avatar/username');
ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  updateProgress(data.step);
};
```

Currently, the system uses polling via `useEffect` for progress updates (see `AvatarPageInner.tsx:236-260` for the generation flow).