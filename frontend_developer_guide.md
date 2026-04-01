

## 2. Backend API - What You Get

The backend runs on **port 8000** and provides these APIs. All return JSON.

### 2.1 Authentication APIs

| Endpoint | Method | Request | Response |
|----------|--------|---------|-----------|
| `/api/auth/login` | POST | `{"username": "admin", "password": "academy123"}` | `{"user": {"username": "admin", "displayName": "Admin Agent"}}` |
| `/api/auth/register` | POST | `{"fullName": "John", "username": "john", "email": "john@test.com", "password": "pass123"}` | `{"user": {"username": "john", "displayName": "John"}}` |

**Hardcoded Test Users** (for testing):
- `admin` / `academy123`
- `student` / `decoder2024`
- `demo` / `demo`

### 2.2 Pipeline Run APIs

| Endpoint | Method | Response |
|----------|--------|----------|
| `/api/runs` | GET | Array of run summaries: `[{"run_id": "run_20260324_173734", "chapter": "Electricity", "subject": "Physics", "class_level": "10", "image_count": 13, "audio_count": 13, "has_audio": true}, ...]` |
| `/api/runs/latest` | GET | Single run summary (most recent) |
| `/api/runs/{run_id}` | GET | Full run data with scenes and audio |
| `/api/runs/{run_id}/scenes` | GET | Just scenes grouped by LS |
| `/api/runs/{run_id}/config` | GET | Just the config JSON |

### 2.3 Avatar APIs

| Endpoint | Method | Request | Response |
|----------|--------|---------|-----------|
| `/api/avatar/generate` | POST | FormData: `username`, `photos` (1+ image files) | `{"ok": true, "avatar_id": "...", "avatar_json": {...}}` |
| `/api/avatar/{username}` | GET | - | Full avatar JSON |
| `/api/avatar/{username}/base_face.png` | GET | - | PNG image |
| `/api/avatar/{username}/expressions/{expr}.png` | GET | - | PNG image (expr = neutral, happy, sad, angry, surprised, talking_open, talking_mid, talking_closed) |

### 2.4 Static Files

| URL Pattern | Serves |
|-------------|--------|
| `/static/{run_id}/images/{ls_id}/{scene_id}.png` | Scene images |
| `/static/{run_id}/audio/{ls_id}/{scene_id}/narrator.mp3` | Narrator audio |
| `/static/{run_id}/audio/{ls_id}/{scene_id}.mp3` | Combined audio |
| `/static/{run_id}/audio/{ls_id}/{scene_id}/dialogue_01.mp3` | Character dialogues |

---

## 3. Data Structures

### 3.1 Run Summary (from `/api/runs`)

```json
{
  "run_id": "run_20260324_173734",
  "timestamp": "20260324173734",
  "chapter": "Electricity",
  "subject": "Physics",
  "class_level": "10",
  "text_model": "gpt-4o-mini",
  "image_model": "flux-1-dev",
  "image_count": 13,
  "audio_count": 13,
  "has_audio": true,
  "has_ppt": true
}
```

### 3.2 Full Run Data (from `/api/runs/{run_id}`)

```json
{
  "run_id": "run_20260324_173734",
  "config": { "chapter": "Electricity", "subject": "Physics", "class_level": "10", ... },
  "story_backbone": { ... },
  "learning_steps": [
    { "learning_step_id": "LS1", "title": "Introduction to Electric Current" },
    { "learning_step_id": "LS2", "title": "Ohm's Law" }
  ],
  "scenes": {
    "LS1": [
      {
        "scene_id": "S1",
        "phase": "HOOK",
        "setting": "Classroom description...",
        "action": "Character actions...",
        "narrator_audio_text": "Narrator script...",
        "character_dialogues": [
          { "character_id": "teacher", "voice_id": "Matthew", "dialogue": "Hello class!", "audio_text": "Hello class!" }
        ],
        "image_url": "/static/run_20260324_173734/images/LS1/LS1_S1.png",
        "audio": {
          "combined_url": "/static/run_20260324_173734/audio/LS1/LS1_S1.mp3",
          "combined_duration_ms": 15000,
          "narrator_url": "/static/.../narrator.mp3",
          "narrator_duration_ms": 8000,
          "dialogue_urls": [
            { "url": "/static/.../dialogue_01.mp3", "speaker": "teacher", "duration_ms": 2000, "start_ms": 5000 }
          ],
          "total_duration_ms": 15000
        }
      },
      { "scene_id": "S2", ... }
    ],
    "LS2": [ ... ]
  },
  "has_audio": true
}
```

### 3.3 Avatar JSON (from `/api/avatar/{username}`)

```json
{
  "avatar_id": "john_001",
  "name": "John",
  "version": "1.0",
  "visual": {
    "base_face": "/api/avatar/john/base_face.png",
    "expressions": {
      "neutral": "/api/avatar/john/expressions/neutral.png",
      "happy": "/api/avatar/john/expressions/happy.png",
      "sad": "/api/avatar/john/expressions/sad.png",
      "angry": "/api/avatar/john/expressions/angry.png",
      "surprised": "/api/avatar/john/expressions/surprised.png",
      "talking_open": "/api/avatar/john/expressions/talking_open.png",
      "talking_mid": "/api/avatar/john/expressions/talking_mid.png",
      "talking_closed": "/api/avatar/john/expressions/talking_closed.png"
    },
    "style": { "type": "semi_realistic_anime" }
  },
  "voice": { "engine": "polly", "voice_id": "Matthew", "language_code": "en-US" },
  "character": { "personality": "curious, friendly teacher" },
  "animation": {
    "lip_sync": { "enabled": true, "method": "frame_switch", "frames": ["talking_open", "talking_closed"] },
    "movement": { "idle_motion": true }
  },
  "metadata": { "status": "active" }
}
```

---

## 4. Integration Guide

### 4.1 Authentication Flow

1. User enters credentials → POST `/api/auth/login`
2. On success → store user in localStorage/session
3. On protected routes → check if user exists, redirect to login if not

```typescript
// Example login
const response = await fetch('/api/auth/login', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ username, password })
});
const data = await response.json();
if (data.user) {
  localStorage.setItem('user', JSON.stringify(data.user));
  router.push('/dashboard');
}
```

### 4.2 Dashboard Flow

1. Fetch all runs → GET `/api/runs`
2. Display as grid/list
3. Click run → navigate to player with run_id

```typescript
const runs = await fetch('/api/runs').then(r => r.json());
// Render runs.map(run => <RunCard key={run.run_id} run={run} />)
```

### 4.3 Scene Player Flow

1. Fetch run data → GET `/api/runs/{run_id}`
2. Flatten scenes: combine all LS scenes into single array
3. Display current scene:
   - Show image at `scene.image_url`
   - Play audio at `scene.audio.combined_url` (or build queue from dialogue_urls)
   - Show dialogues based on timing (`start_ms`)
4. Navigate prev/next through scenes

```typescript
// Flatten scenes for easier navigation
const flatScenes = Object.entries(scenes).flatMap(([ls_id, sceneList]) =>
  sceneList.map((scene, i) => ({ ...scene, ls_id, scene_index: i }))
);

// Display current scene
const currentScene = flatScenes[currentIndex];
<img src={currentScene.image_url} />;
<audio src={currentScene.audio.combined_url} />;
```

### 4.4 Avatar Generation Flow

1. User uploads 1+ photos
2. POST to `/api/avatar/generate` with FormData
3. Show loading state (generation takes 2-3 minutes)
4. On success, display avatar with expression switcher

```typescript
const formData = new FormData();
formData.append('username', username);
photos.forEach(photo => formData.append('photos', photo));

const response = await fetch('/api/avatar/generate', { method: 'POST', body: formData });
const data = await response.json();
// data.avatar_json contains the full avatar
```

---

## 5. Technical Requirements

### 5.1 Environment

| Service | URL |
|---------|-----|
| Backend API | http://localhost:8000 |
| Backend Docs | http://localhost:8000/docs (Swagger UI - shows all APIs) |
| Frontend | http://localhost:3000 (you'll build this) |

### 5.2 Running the Project

```bash
# Terminal 1: Start backend
cd Automation_prompt_json_generator
uvicorn backend.server:app --port 8000 --reload

# Terminal 2: Start your new frontend
cd your-new-frontend
npm run dev
```

### 5.3 CORS

The backend allows requests from `localhost:3000` (CORS configured in `backend/server.py:63-69`). Your frontend will work out of the box.

### 5.4 Data Storage

| Data | Location |
|------|----------|
| Pipeline runs | `outputs/run_*/` |
| Avatars | `data/avatars/{username}/` |
| Users | `data/users.json` |

---

## 6. Features to Implement (Priority Order)

### P0 - Must Have
1. **Login/Register** - Auth flow with localStorage session
2. **Dashboard** - List all runs, click to enter
3. **Scene Player** - Navigate scenes, play audio, show images

### P1 - Should Have
4. **Avatar Generation** - Upload photos, generate avatar
5. **Profile Page** - View/edit user profile

### P2 - Nice to Have
6. **Search/Filter** - Search runs by chapter/subject
7. **Progress Tracking** - Show scene progress bar
8. **Avatar Expression Switcher** - Toggle between expressions

---

## 7. What the Backend Doesn't Provide (You Need to Build)

| Feature | Notes |
|---------|-------|
| **User Dashboard UI** | How runs are displayed is up to you |
| **Scene Player UI** | Design the player how you want |
| **Avatar Editor UI** | Expression switcher, regen flow |
| **State Management** | Use React/Redux/Zustand as you prefer |
| **Styling** | Use any CSS framework you want |

---

## 8. Key Constraints

1. **Audio Format**: MP3 only (from Polly TTS)
2. **Image Format**: PNG from Flux image generation
3. **Avatars**: 7 expressions must be supported (neutral, happy, sad, angry, surprised, talking_open, talking_closed)
4. **Scenes**: Always grouped by Learning Step (LS1, LS2, etc.)

---

## 9. Testing Your Integration

### Quick Test Checklist

- [ ] Login with `demo` / `demo` works
- [ ] Dashboard shows runs from `/api/runs`
- [ ] Clicking a run loads scenes from `/api/runs/{run_id}`
- [ ] Scene images load from `/static/{run_id}/images/...`
- [ ] Audio plays from `/static/{run_id}/audio/...`
- [ ] Avatar generation POST works (uploads photos, returns JSON)

### Test Commands

```bash
# Test login
curl -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"demo","password":"demo"}'

# Test runs list
curl http://localhost:8000/api/runs

# Test specific run
curl http://localhost:8000/api/runs/run_20260324_173734
```

---

## 10. File Locations Reference

### Backend (don't modify, just call)

| File | Purpose |
|------|----------|
| `backend/server.py` | All API endpoints (1016 lines) |

### Output Data (read-only - generated by pipeline)

| Directory | Contents |
|-----------|----------|
| `outputs/run_*/` | Scenes, images, audio for each run |
| `data/avatars/...` | Generated avatars |
| `data/users.json` | Registered users |

---

## 11. Questions? How to Get Help

1. **API Documentation**: Visit http://localhost:8000/docs - Swagger UI shows all endpoints with request/response formats
2. **Run Health Check**: http://localhost:8000/health - confirms backend is running
3. **Test Existing Data**: Use Postman or curl to test APIs before building UI

---

## 12. Quick Start Template

Here's a minimal starting point for your new frontend:

```typescript
// pages/index.tsx (Login)
export default function Login() {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');

  async function handleLogin() {
    const res = await fetch('/api/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password })
    });
    if (res.ok) {
      const data = await res.json();
      localStorage.setItem('user', JSON.stringify(data.user));
      router.push('/dashboard');
    }
  }

  return (
    <div>
      <input value={username} onChange={e => setUsername(e.target.value)} />
      <input type="password" value={password} onChange={e => setPassword(e.target.value)} />
      <button onClick={handleLogin}>Login</button>
    </div>
  );
}

// pages/dashboard.tsx
export default function Dashboard() {
  const [runs, setRuns] = useState([]);

  useEffect(() => {
    fetch('/api/runs').then(r => r.json()).then(setRuns);
  }, []);

  return (
    <div>
      {runs.map(run => (
        <div key={run.run_id} onClick={() => router.push(`/player/${run.run_id}`)}>
          {run.chapter} - {run.subject}
        </div>
      ))}
    </div>
  );
}

// pages/player/[runId].tsx
export default function Player({ params }) {
  const [runData, setRunData] = useState(null);

  useEffect(() => {
    fetch(`/api/runs/${params.runId}`).then(r => r.json()).then(setRunData);
  }, [params.runId]);

  if (!runData) return <div>Loading...</div>;

  const scenes = Object.values(runData.scenes).flat();
  // Now display scenes with images and audio...

  return <div>Player for {params.runId}</div>;
}
```

---

**You're ready to build! Start with login → dashboard → player, then add avatar features.**