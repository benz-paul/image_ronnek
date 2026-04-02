# Frontend Complete Architecture & Analysis

## Purpose
This document provides a comprehensive analysis of the current frontend implementation for the Storytelling Pipeline. It explains how the frontend displays pipeline outputs, the API calls made, data flow.

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

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/auth/login` | POST | Authenticate user with username/password |
| `/api/auth/register` | POST | Register new user |

### Run/Pipeline APIs

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/runs` | GET | List all available pipeline runs (sorted newest first) |
| `/api/runs/latest` | GET | Get the most recent run summary |
| `/api/runs/{run_id}` | GET | Get full run data: config, scenes grouped by LS, audio manifest, story backbone |
| `/api/runs/{run_id}/scenes` | GET | Get scenes grouped by LS for a run |
| `/api/runs/{run_id}/config` | GET | Get config.json for a run |

### Avatar APIs

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/avatar/generate` | POST | Generate avatar from uploaded photos (uses FAL.ai) |
| `/api/avatar/{username}` | GET | Get user's avatar JSON |
| `/api/avatar/{username}/base_face.png` | GET | Get avatar base face image |
| `/api/avatar/{username}/expressions/{expression}.png` | GET | Get specific expression image |

### Static File Serving

| Endpoint | Purpose |
|----------|---------|
| `/static/{run_id}/images/{ls_id}/{scene_id}.png` | Serve scene images |
| `/static/{run_id}/audio/{ls_id}/{scene_id}/narrator.mp3` | Serve narrator audio |
| `/static/{run_id}/audio/{ls_id}/{scene_id}/dialogue_{n}.mp3` | Serve character dialogues |
| `/static/{run_id}/audio/{ls_id}/{scene_id}.mp3` | Serve combined audio |

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
  learning_steps: [ ... ],   # Learning steps array
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

The `load_scenes_for_run()` function in `backend/server.py` (lines 181-230) tries multiple sources in priority order:
1. `parsed/scenes_full.json`
2. `parsed/scenes_LS*.json` merged
3. Individual `scenes/LS*/*.json` files merged

---

## 6. Audio Manifest Structure

### Location
`outputs/run_20260324_173734/audio/manifest.json`

### Audio Manifest JSON

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

In `backend/server.py` (`get_run` endpoint, lines 351-435):

1. Backend loads the audio manifest
2. For each scene, it creates `audio` object with URLs:
   - **combined_url**: Single MP3 combining all audio (narrator + dialogues)
   - **narrator_url**: Individual narrator MP3
   - **dialogue_urls**: Array of dialogue URLs with timing info:
     - `url`: Path to dialogue MP3
     - `speaker`: Character ID
     - `duration_ms`: Duration in milliseconds
     - `start_ms`: Start time in combined audio

3. Frontend receives these URLs and uses them for playback

---

## 7. How Audio Playback Works in Frontend

### Hook: `useAudioPlayer.ts` (`frontend/hooks/useAudioPlayer.ts`)

The audio player provides:
- **play(url)**: Play single audio file
- **playQueue(items)**: Play multiple audio files in sequence
- **pause()**, **resume()**, **stop()**: Playback controls
- **state**: Current state (idle, loading, playing, paused, ended, error)

### Scene Audio Logic (Player Page)

```typescript
// From frontend/app/player/[runId]/page.tsx

// When scene loads (useEffect, line 96-146):
const audio = scene.audio;

if (audio?.combined_url) {
  // Play combined audio
  play(audio.combined_url);
  
  // If dialogues have start_ms timing, reveal them at correct times
  dlgs.forEach((d, i) => {
    const dt = setTimeout(() => {
      setShowDialogue(true);
      setActiveDialogueIndex(i);
    }, d.start_ms);
  });
} else if (audio?.narrator_url || audio?.dialogue_urls?.length > 0) {
  // Build queue: narrator first, then each dialogue
  const q = [
    { url: audio.narrator_url, speaker: "narrator", duration_ms: ... },
    { url: dialogue1.url, speaker: "leosharma", duration_ms: ... },
    { url: dialogue2.url, speaker: "mayachen", duration_ms: ... }
  ];
  playQueue(q);
}
```

### Audio Auto-Advance
- When audio ends, scene automatically advances after 2.5 seconds
- If scene has `student_interaction`, shows interaction overlay instead

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
```typescript
// From player/page.tsx line 243-248
{cs.image_url ? (
  <img 
    src={cs.image_url} 
    alt={cs.scene_id}
    onLoad={() => { setImageLoaded(true); setDisplayedImageUrl(cs.image_url); }}
    className="absolute inset-0 w-full h-full object-cover kenburns transition-opacity duration-700"
  />
) : (
  <div>Image generating...</div>
)}
```

### Preloading
```typescript
// From player/page.tsx line 149-155
useEffect(() => {
  const next = flatScenes[currentIndex + 1];
  if (next?.image_url) {
    const img = new window.Image();
    img.src = next.image_url;  // Preload next scene's image
  }
}, [currentIndex, flatScenes]);
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

### Avatar JSON Structure

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

### Avatar API Endpoints

| Endpoint | Purpose |
|----------|---------|
| `GET /api/avatar/{username}` | Get avatar JSON |
| `GET /api/avatar/{username}/base_face.png` | Get base face image |
| `GET /api/avatar/{username}/expressions/{expression}.png` | Get expression image |
| `POST /api/avatar/generate` | Generate new avatar |

### Avatar Expression Switching (Frontend)

```typescript
// From AvatarPageInner.tsx

const expressions = [
  { key: "neutral", icon: "sentiment_neutral" },
  { key: "happy", icon: "sentiment_very_satisfied" },
  { key: "sad", icon: "sentiment_dissatisfied" },
  { key: "angry", icon: "mood_bad" },
  { key: "surprised", icon: "sentiment_excited" },
  { key: "talking_open", icon: "record_voice_over" },
];

// Get current expression image
const imgUrl = avatar.visual.expressions[activeExpr] || avatar.visual.base_face;
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

### Auth Hook (`useAuth.ts`)

```typescript
// Provides:
// - user: current logged-in user
// - loading: auth check loading state
// - login(username, password): login function
// - logout(): logout function

const { user, loading, login, logout } = useAuth();

// Login stores to localStorage:
// localStorage.setItem("academy_user", JSON.stringify(user))
```

### Protected Routes
- `/dashboard`, `/player`, `/avatar`, `/profile` all check for user
- If no user, redirect to `/` (login page)

---

## 11. Key Files Summary

### Frontend Key Files

| File | Purpose |
|------|---------|
| `frontend/app/page.tsx` | Login page |
| `frontend/app/dashboard/page.tsx` | Run listing dashboard |
| `frontend/app/player/[runId]/page.tsx` | Scene player with audio |
| `frontend/app/avatar/page.tsx` | Avatar creation page |
| `frontend/app/avatar/AvatarPageInner.tsx` | Avatar generation logic |
| `frontend/hooks/useAuth.ts` | Authentication hook |
| `frontend/hooks/useAudioPlayer.ts` | Audio playback hook |

### Backend Key Files

| File | Purpose |
|------|---------|
| `backend/server.py` | FastAPI server with all endpoints |

### Key Data Directories

| Directory | Contents |
|-----------|----------|
| `outputs/run_*/` | Pipeline run outputs (scenes, images, audio) |
| `data/avatars/{username}/` | Generated avatars |
| `data/users.json` | Registered users |

---

## 12. Summary for New Frontend Developers

### To Display a Run's Scenes:
1. Call `GET /api/runs/{run_id}`
2. Get `scenes` object containing scenes grouped by LS
3. Each scene has `image_url` for display and `audio` for playback

### To Play Audio:
1. Use `useAudioPlayer` hook
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

## 13. Environment Setup for Development

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