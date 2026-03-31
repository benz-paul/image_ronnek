# Pipeline Flow — Step-by-Step Execution Trace

> This document traces every step of the pipeline from the moment `python brain/main.py` is run to the final output. Every function called, every file touched, every decision made.

---

## Table of Contents

1. [Visual Overview](#1-visual-overview)
2. [Phase 0 — Startup & User Input](#2-phase-0--startup--user-input)
3. [Phase 1 — PDF Retrieval](#3-phase-1--pdf-retrieval)
4. [Phase 2 — Prompt 0: Concept Extraction](#4-phase-2--prompt-0-concept-extraction)
5. [Phase 3 — Prompt 1: Story Backbone](#5-phase-3--prompt-1-story-backbone)
6. [Phase 4 — Prompt 2: Learning Steps](#6-phase-4--prompt-2-learning-steps)
7. [Phase 5 — Prompt 3A: Scene Plans (Loop)](#7-phase-5--prompt-3a-scene-plans-loop)
8. [Phase 6 — Prompt 3B: Full Scenes (Loop)](#8-phase-6--prompt-3b-full-scenes-loop)
9. [Phase 7 — Prompt 4: Image Prompts (Loop)](#9-phase-7--prompt-4-image-prompts-loop)
10. [Phase 8 — Image Generation](#10-phase-8--image-generation)
11. [Phase 9 — Audio Generation](#11-phase-9--audio-generation)
12. [Phase 10 — PPT Generation](#12-phase-10--ppt-generation)
13. [Phase 11 — Output & Summary](#13-phase-11--output--summary)
14. [Phase 12 — Frontend Playback](#14-phase-12--frontend-playback)
15. [State at Every Stage](#15-state-at-every-stage)
16. [Full Call Graph](#16-full-call-graph)
17. [File Timeline](#17-file-timeline)
18. [LLM Calls Summary](#18-llm-calls-summary)

---

## 1. Visual Overview

```
python brain/main.py
        │
        ▼
┌─────────────────────────────────────────────────────────────────────┐
│  PHASE 0: Startup                                                    │
│  main.py → ask_verbosity() → select_topic() → select_image_model()  │
│  → create_run_folder() → pipeline.run()                             │
└─────────────────────────────┬───────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│  PHASE 1: PDF                                                        │
│  pdf_agent → check knowledge/ → scrape NCERT if missing             │
└─────────────────────────────┬───────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│  PHASE 2: Prompt 0                                                   │
│  concept_agent → LLM (Pass A) → LLM (Pass B) → merge concepts       │
└─────────────────────────────┬───────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│  PHASE 3: Prompt 1                                                   │
│  backbone_agent → LLM → select best story → extract characters      │
└─────────────────────────────┬───────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│  PHASE 4: Prompt 2                                                   │
│  learning_steps_agent → LLM → parse 10-15 learning steps            │
└─────────────────────────────┬───────────────────────────────────────┘
                              │
                    ┌─────────▼──────────┐
                    │  FOR EACH LS (1..N) │
                    └─────────┬──────────┘
                              │
┌─────────────────────────────▼───────────────────────────────────────┐
│  PHASE 5: Prompt 3A (per LS)                                         │
│  scene_generator_agent → LLM → scene plan (12-15 scenes)            │
└─────────────────────────────┬───────────────────────────────────────┘
                              │
                    ┌─────────▼──────────────┐
                    │  FOR EACH SCENE in plan │
                    └─────────┬──────────────┘
                              │
┌─────────────────────────────▼───────────────────────────────────────┐
│  PHASE 6: Prompt 3B (per scene)                                      │
│  scene_generator_agent → LLM → full scene JSON                      │
│  → update story_summary → save LS{N}_S{M}.json                      │
└─────────────────────────────┬───────────────────────────────────────┘
                              │ (after all scenes for this LS)
┌─────────────────────────────▼───────────────────────────────────────┐
│  PHASE 7: Prompt 4 (per scene)                                       │
│  image_prompt_agent → LLM → image generation prompt                 │
│  → append GLOBAL_VISUAL_STYLE                                        │
└─────────────────────────────┬───────────────────────────────────────┘
                              │ (if generate_images=True)
┌─────────────────────────────▼───────────────────────────────────────┐
│  PHASE 8: Image Generation (per scene)                               │
│  image_generator → OpenAI or fal.ai → save PNG                      │
└─────────────────────────────┬───────────────────────────────────────┘
                              │ (if generate_audio=True)
┌─────────────────────────────▼───────────────────────────────────────┐
│  PHASE 9: Audio Generation (per scene)                               │
│  audio_generator → Amazon Polly → save narrator.mp3 + dialogue_*.mp3│
│  → merge to combined.mp3 → build audio manifest                     │
└─────────────────────────────┬───────────────────────────────────────┘
                              │ (next LS? → back to Phase 5)
                              │ (all LS done → continue)
┌─────────────────────────────▼───────────────────────────────────────┐
│  PHASE 10: PPT Generation                                            │
│  ppt_generator → python-pptx → lesson.pptx                          │
└─────────────────────────────┬───────────────────────────────────────┘
                              │
┌─────────────────────────────▼───────────────────────────────────────┐
│  PHASE 11: Summary                                                   │
│  write summary.json → print stats box → return result dict          │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 2. Phase 0 — Startup & User Input

### Entry point: `brain/main.py`

**`TEST_MODE = True`** (default) — runs interactive menus.

---

#### Step 0.1 — Load environment

```python
from dotenv import load_dotenv
load_dotenv()  # loads .env → OPENAI_API_KEY, FAL_KEY, AWS_*, etc.
```

---

#### Step 0.2 — `ask_verbosity()`

Prompts: `"Show verbose debug output? (y/n)"`

Calls `set_verbose(bool)` in `utils/pipeline_logger.py`. This sets a module-level flag that controls whether `debug()` calls print anything.

---

#### Step 0.3 — `get_available_topics()`

Scans `assets/knowledge/` for `*.pdf` files. For each PDF:
- Extracts filename metadata (chapter number, subject inferred from filename)
- Returns list of topic dicts: `{filename, chapter_name, inferred_subject, inferred_class}`

---

#### Step 0.4 — `select_topic(topics)`

Shows numbered menu if `TEST_MODE=True`. User picks a number. Returns selected topic dict.

If `TEST_MODE=False` (production): user types chapter name, number, subject, class level free-form.

---

#### Step 0.5 — `select_image_model()`

Menu:
```
1. gpt-image-1.5   (OpenAI)
2. fal-flux2pro    (fal.ai Flux 2 Pro)
3. fal-juggernaut  (fal.ai Juggernaut XL)
```
Returns model string that flows into `pipeline.run()`.

---

#### Step 0.6 — `ask_scene_generation_mode()`

```
Generate all learning steps? (y) or just one? (n)
```
If "one": `select_learning_step()` — user picks an LS number. This sets `DEBUG_MAX_LS` in state.

---

#### Step 0.7 — `ask_generate_images()` / `ask_generate_audio()`

Simple y/n prompts. Set `generate_images=bool`, `generate_audio=bool` in pipeline config.

---

#### Step 0.8 — `check_and_get_pdf()`

Checks `assets/knowledge/` for the selected chapter's PDF. Returns `(pdf_path, "local")` if found, triggers `pdf_agent` if not (see Phase 1).

---

#### Step 0.9 — `create_run_folder()`

In `utils/model_output_manager.py`:
```python
run_id = f"run_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
run_folder = outputs_dir / run_id
```

Creates full directory tree:
```
outputs/run_{timestamp}/
  inputs/
  prompts/
  raw_outputs/
  parsed/
  scenes/
  images/
  audio/
  ppt/
  logs/
```

Saves `inputs/config.json` with chapter metadata and all config flags.

---

#### Step 0.10 — Build `UserInputs` and call `pipeline.run()`

```python
user_inputs = UserInputs(
    chapter_name="Arithmetic Progressions",
    chapter_title="Chapter 5",
    chapter_number=5,
    class_level="Grade 10",
    subject="Mathematics",
    medium="English"
)

result = pipeline.run(
    user_inputs=user_inputs,
    image_model="gpt-image-1.5",
    image_mode="dialogue",
    generate_images=True,
    generate_audio=True,
    verbose=False,
    run_folder=run_folder
)
```

---

## 3. Phase 1 — PDF Retrieval

### `brain/agents/pdf_agent.py` → `PDFAgent.get_pdf()`

---

#### Step 1.1 — `_search_local(chapter_name)`

Iterates `assets/knowledge/*.pdf`. Does a case-insensitive partial match on filename vs `chapter_name`. Returns path if found, `None` if not.

---

#### Step 1.2 — If not local: `_download_from_ncert()`

Constructs NCERT URL from chapter metadata:
```
https://ncert.nic.in/textbook/pdf/{subject_code}{class_code}{chapter_num:02d}.pdf
```

Downloads with `requests.get(url, timeout=30)`. On SSL error or timeout: retries with exponential backoff (1s, 2s, 4s). After 3 failures: raises `PDFDownloadError`.

Saves to `assets/knowledge/{chapter_name}.pdf`.

---

#### Step 1.3 — Extract text

Uses `pypdf.PdfReader(pdf_path)`:
```python
reader = PdfReader(pdf_path)
text = "\n".join([page.extract_text() for page in reader.pages])
```

Saves extracted text to `inputs/chapter_text.txt` in run folder.

Sets `state.pdf_path` and `state.pdf_source`.

---

## 4. Phase 2 — Prompt 0: Concept Extraction

### `brain/agents/concept_agent.py` → `ConceptAgent.extract_concepts()`

---

#### Step 2.1 — Load Prompt 0A from `MASTER_PROMPTS.txt`

```python
prompt_builder = PromptBuilder("assets/prompts/MASTER_PROMPTS.txt")
prompt_0a = prompt_builder.get_prompt("0A",
    CHAPTER_NAME=user_inputs.chapter_name,
    CHAPTER_TEXT=extracted_pdf_text[:8000]   # first 8K chars
)
```

Saves filled prompt to `prompts/prompt0a.txt`.

---

#### Step 2.2 — LLM Call (Pass A)

```python
llm_client = create_llm_client(model="deepseek", temperature=0.3)
raw_response_a = llm_client.call(prompt_0a)
```

Saves raw response to `raw_outputs/prompt0a_raw.txt`.

---

#### Step 2.3 — Parse Pass A response

```python
parsed_a = safe_parse(raw_response_a)
# Expected: {"concepts": ["arithmetic sequence", "common difference", ...]}
concepts_a = parsed_a["concepts"]
```

---

#### Step 2.4 — Load and call Prompt 0B (Gap Detection)

```python
prompt_0b = prompt_builder.get_prompt("0B",
    CHAPTER_NAME=user_inputs.chapter_name,
    CHAPTER_TEXT=extracted_pdf_text[8000:16000],   # next 8K chars
    EXISTING_CONCEPTS=json.dumps(concepts_a)
)
raw_response_b = llm_client.call(prompt_0b)
concepts_b = safe_parse(raw_response_b)["concept_titles"]
```

---

#### Step 2.5 — `_merge_and_deduplicate(concepts_a, concepts_b)`

Combines both lists. Lowercases and strips all entries. Removes duplicates. Sorts alphabetically. Returns final `list[str]`.

---

#### Step 2.6 — Save and update state

```python
concept_inventory = {"concepts": merged_concepts}
save_parsed(run_folder, "concept_inventory", concept_inventory)
state["prompt0_output"] = concept_inventory
```

**File written:** `parsed/concept_inventory.json`

**Log output:**
```
✓ Concept extraction complete — 23 concepts found
```

---

## 5. Phase 3 — Prompt 1: Story Backbone

### `brain/agents/backbone_agent.py` → `BackboneAgent.generate_backbone()`

---

#### Step 3.1 — Load and fill Prompt 1

```python
prompt_1 = prompt_builder.get_prompt("1",
    CHAPTER_NAME=user_inputs.chapter_name,
    CLASS_LEVEL=user_inputs.class_level,
    SUBJECT=user_inputs.subject,
    CONCEPTS=json.dumps(concept_inventory["concepts"])
)
```

Saves to `prompts/prompt1.txt`.

---

#### Step 3.2 — LLM Call

```python
raw_response = llm_client.call(prompt_1)
```

Saves raw to `raw_outputs/prompt1_raw.txt`.

The LLM typically returns 2–3 story options with title, premise, characters, coverage%, pedagogical%.

---

#### Step 3.3 — `_select_best_story(raw_response)`

Parses response. If multiple story options:
```python
# Extracts coverage_% and pedagogical_% from each using regex
# Score = coverage_% + pedagogical_%
# Returns story dict with highest combined score
best_story = max(stories, key=lambda s: s["coverage_%"] + s["pedagogical_%"])
```

---

#### Step 3.4 — `_extract_characters(story_dict)`

Pulls `story_dict["characters"]` — list of character dicts. Validates each has: `character_id`, `name`, `visual_description`, `gender`, `voice_id`.

---

#### Step 3.5 — Save and update state

```python
save_parsed(run_folder, "story_backbone", best_story)
state["prompt1_output"] = best_story
state["character_registry"] = best_story["characters"]
state["art_style"] = "Studio Ghibli inspired 2D illustration, clean lines, warm palette, educational comic style"
state["story_bible"] = {
    "academic_context": concept_inventory,
    "art_style": state["art_style"],
    "character_registry": state["character_registry"],
    "story_backbone": best_story
}
```

**File written:** `parsed/story_backbone.json`

**Log output:**
```
✓ Story backbone selected: "The Pattern Detective"
  Characters: Maya (Ivy), Leo (Kevin), Professor Chen (Matthew)
  Coverage: 94%  Pedagogical strength: 91%
```

---

## 6. Phase 4 — Prompt 2: Learning Steps

### `brain/agents/learning_steps_agent.py` → `LearningStepsAgent.generate_learning_steps()`

---

#### Step 4.1 — Build `[CHARACTER_REGISTRY]` string

```python
registry_str = format_character_registry_for_prompt(state)
# → "Maya: Black shoulder-length hair with red streak, amber eyes, navy tracksuit...\nLeo: ..."
```

---

#### Step 4.2 — Load and fill Prompt 2

```python
prompt_2 = prompt_builder.get_prompt("2",
    CHAPTER_NAME=user_inputs.chapter_name,
    CONCEPTS=json.dumps(concept_inventory["concepts"]),
    STORY_BACKBONE=json.dumps(best_story),
    CHARACTER_REGISTRY=registry_str
)
```

Saves to `prompts/prompt2.txt`.

---

#### Step 4.3 — LLM Call

```python
raw_response = llm_client.call(prompt_2)
```

Saves raw to `raw_outputs/prompt2_raw.txt`.

---

#### Step 4.4 — `_parse_learning_steps(raw_response)`

```python
parsed = safe_parse(raw_response)
learning_steps = parsed["learning_steps"]
# Each: {learning_step_id, title, concepts_introduced, narrative_moment}
```

Validates: step IDs are sequential (LS1, LS2, ...), `concepts_introduced` is non-empty, `narrative_moment` is at least 3 sentences.

---

#### Step 4.5 — Apply DEBUG_MAX_LS

If `DEBUG_MODE=True`:
```python
learning_steps = learning_steps[:DEBUG_MAX_LS]  # typically [:1]
```

---

#### Step 4.6 — Save and update state

```python
save_parsed(run_folder, "learning_steps", {"learning_steps": learning_steps})
state["learning_steps_list"] = learning_steps
state["current_ls_index"] = 0
state["story_summary"] = ""
```

**File written:** `parsed/learning_steps.json`

**Log output:**
```
✓ Learning steps generated: 12 steps
  LS1: The Broken Pattern
  LS2: Naming the Gap
  ...
```

LangGraph now enters the **PROMPT3_LOOP** — iterating over each learning step.

---

## 7. Phase 5 — Prompt 3A: Scene Plans (Loop)

### Per learning step. `brain/agents/scene_generator_agent.py` → `_generate_scene_plan(ls_dict, state)`

---

#### Step 5.1 — Get current LS

```python
ls = get_current_learning_step(state)
# e.g.: {learning_step_id: "LS1", title: "The Broken Pattern", concepts_introduced: [...], narrative_moment: "..."}
```

---

#### Step 5.2 — Build context for Prompt 3A

```python
registry_str = format_character_registry_for_prompt(state)
prompt_3a = prompt_builder.get_prompt("3A",
    LEARNING_STEP_TITLE=ls["title"],
    LS_CONCEPTS=json.dumps(ls["concepts_introduced"]),
    NARRATIVE_MOMENT=ls["narrative_moment"],
    CHARACTER_REGISTRY=registry_str,
    STORY_SUMMARY=state["story_summary"]
)
```

Saves to `prompts/prompt3a_{ls_id}.txt`.

---

#### Step 5.3 — LLM Call

```python
raw_response = llm_client.call(prompt_3a)
```

Saves raw to `raw_outputs/prompt3a_{ls_id}_raw.txt`.

---

#### Step 5.4 — Parse scene plan

```python
parsed = safe_parse(raw_response)
scene_plan = parsed["scene_plan"]
# Each item: {scene_id: "LS1_S1", phase: "HOOK", summary: "...", concept_focus: null}
```

Validates:
- First scene phase is `HOOK`
- Second scene phase is `SETUP`
- No two consecutive same phases
- Last or second-to-last scene is `PAYOFF`

**Log output:**
```
✓ Scene plan for LS1: 14 scenes
  S1:HOOK  S2:SETUP  S3:DISCOVERY  S4:CONFUSION  ...  S14:PAYOFF
```

---

## 8. Phase 6 — Prompt 3B: Full Scenes (Loop)

### Per scene in current LS. `brain/agents/scene_generator_agent.py` → `_generate_single_scene()`

---

#### Step 6.1 — Build full context

For each scene in `scene_plan`:

```python
previous_scene = scenes[-1] if scenes else None
prompt_3b = prompt_builder.get_prompt("3B",
    LEARNING_STEP_TITLE=ls["title"],
    LS_CONCEPTS=json.dumps(ls["concepts_introduced"]),
    SCENE_PLAN_ITEM=json.dumps(scene_plan_item),
    CHARACTER_REGISTRY=registry_str,
    STORY_SUMMARY=state["story_summary"],
    PREVIOUS_SCENE=json.dumps(previous_scene) if previous_scene else "None (first scene)",
    STORY_BACKBONE=json.dumps(state["prompt1_output"]),
    SCENE_PHASE=scene_plan_item["phase"]
)
```

Saves to `prompts/prompt3b_{scene_id}.txt`.

---

#### Step 6.2 — LLM Call

```python
raw_response = llm_client.call(prompt_3b)
```

Saves raw to `raw_outputs/prompt3b_{scene_id}_raw.txt`.

---

#### Step 6.3 — Parse full scene JSON

```python
scene = safe_parse(raw_response)
```

Expected scene structure:
```json
{
  "scene_id": "LS1_S3",
  "phase": "DISCOVERY",
  "setting": "...",
  "characters": [{"character_id": "maya", "position": "left", "emotion": "curious"}],
  "character_dialogues": [
    {
      "character_id": "maya",
      "dialogue": "Every gap is the same.",
      "emotion": "curious",
      "audio_text": "Every gap is the same."
    }
  ],
  "narrator_audio_text": "Maya erased the board and started again.",
  "learning_moment": "Recognizing the constant difference",
  "concept_taught": "common difference",
  "visual_setting": "Close-up on whiteboard with +3 arrows"
}
```

---

#### Step 6.4 — `_update_story_summary(state, scene)`

```python
summary_line = f"{scene['scene_id']}: {scene['phase']} — {scene['learning_moment'] or scene['setting'][:60]}"
state["story_summary"] += f"\n{summary_line}"
```

This accumulating string is injected into every subsequent Prompt 3B call as `[STORY_SUMMARY]`.

---

#### Step 6.5 — Save scene

```python
save_scenes(run_folder, ls_id, [scene])
# → writes scenes/LS1/LS1_S3.json
```

Also appends to in-memory `state["scenes"]["LS1"]` list.

**Log output:**
```
  ✓ LS1_S3 [DISCOVERY] generated
```

---

#### Step 6.6 — After all scenes for current LS

```python
# Save combined LS scenes file
save_parsed(run_folder, f"scenes_{ls_id}", {"scenes": scenes_for_ls})

# Advance LS index
state["current_ls_index"] += 1

# flow_tracker: should_continue_learning_step_loop?
if current_ls_index < len(learning_steps_list):
    # → loop back to Phase 5 with next LS
else:
    # → proceed to Phase 7 (image prompts)
```

**File written per LS:** `parsed/scenes_LS1.json`, `parsed/scenes_LS2.json`, ...

---

## 9. Phase 7 — Prompt 4: Image Prompts (Loop)

### Per scene. `brain/agents/image_prompt_agent.py` → `generate_image_prompts()`

---

#### Step 7.1 — For each scene across all learning steps

Iterates `state["scenes"]` flattened: LS1_S1, LS1_S2, ..., LS2_S1, ...

---

#### Step 7.2 — Build Prompt 4

```python
prompt_4 = prompt_builder.get_prompt("4",
    SCENE_JSON=json.dumps(scene),
    CHARACTER_REGISTRY=registry_str,
    IMAGE_MODE=state["image_mode"],     # "dialogue" or "overlay"
    CHAPTER_NAME=user_inputs.chapter_name,
    CLASS_LEVEL=user_inputs.class_level
)
```

Saves to `prompts/prompt4_{scene_id}.txt`.

---

#### Step 7.3 — LLM Call

```python
raw_response = llm_client.call(prompt_4)
```

---

#### Step 7.4 — Parse image prompt

```python
parsed = safe_parse(raw_response)
image_prompt = parsed["image_prompt"]
```

---

#### Step 7.5 — Append `GLOBAL_VISUAL_STYLE`

```python
GLOBAL_VISUAL_STYLE = (
    "Studio Ghibli-inspired 2D illustration. Clean black outlines, "
    "warm color temperature, soft ambient lighting. Characters are "
    "anime-proportioned, expressive faces. Background has 2-3 depth layers. "
    "Educational comic panel style. No text in image unless specified. "
    "Aspect ratio 4:3, landscape orientation."
)

final_prompt = f"{image_prompt}\n\nVisual Style: {GLOBAL_VISUAL_STYLE}"
```

---

#### Step 7.6 — Save

```python
image_prompts[scene_id] = final_prompt
```

After all scenes: `save_parsed(run_folder, "image_prompts", image_prompts)`

**File written:** `parsed/image_prompts.json`

---

## 10. Phase 8 — Image Generation

### Conditional: only if `generate_images=True`

### `brain/services/image_generator.py` → `ImageGeneratorService.generate_image()`

---

#### Step 8.1 — Per scene, retrieve prompt

```python
prompt = image_prompts[scene_id]
image_path = _get_image_path(run_folder, scene_id)
# → "outputs/run_{ts}/images/LS1/LS1_S1.png"
```

Ensures parent directory `images/LS1/` exists (`Path.mkdir(parents=True, exist_ok=True)`).

---

#### Step 8.2a — OpenAI (`gpt-image-1.5`)

```python
response = openai_client.images.generate(
    model="gpt-image-1.5",
    prompt=prompt,
    size="1024x1024",
    n=1
)
image_url = response.data[0].url
image_bytes = requests.get(image_url).content
```

---

#### Step 8.2b — fal.ai (Flux 2 Pro or Juggernaut)

```python
# Submit job
request_id = fal.queue.submit(
    model_id,  # "fal-ai/flux-pro/v1.1" or "fal-ai/juggernaut-xl"
    arguments={"prompt": prompt, "image_size": "landscape_4_3", "num_images": 1}
)

# Poll for completion
while True:
    status = fal.queue.status(request_id)
    if status.status == "COMPLETED":
        break
    elif status.status == "FAILED":
        raise FalGenerationError(status.error)
    time.sleep(3)

# Download result
result = fal.queue.result(request_id)
image_url = result["images"][0]["url"]
image_bytes = requests.get(image_url).content
```

**On 5xx errors (3 consecutive):**
```python
if consecutive_failures >= 3 and model != fallback_model:
    log(f"⚠ Switching to fallback model: {fallback_model}")
    model = fallback_model
    consecutive_failures = 0
```

---

#### Step 8.3 — Save image

```python
_save_image(image_bytes, image_path)
state["image_paths"][scene_id] = image_path
```

**File written:** `images/LS1/LS1_S1.png`

**Log output:**
```
  ✓ Image generated: LS1_S1.png (1024×1024, 387KB)
```

---

#### Step 8.4 — `dialogue_overlay.py` (if `image_mode="overlay"`)

```python
from brain.services.dialogue_overlay import DialogueOverlay
overlay = DialogueOverlay(fonts_dir="assets/fonts/")
overlay.apply(
    image_path=image_path,
    character_dialogues=scene["character_dialogues"],
    character_positions={c["character_id"]: c["position"] for c in scene["characters"]}
)
```

Uses `PIL.Image.open()` → `PIL.ImageDraw.Draw()` → draw rounded rectangles + text with `ComicNeue-Bold.ttf` → `image.save(image_path)` (overwrites original).

---

## 11. Phase 9 — Audio Generation

### Conditional: only if `generate_audio=True`

### `brain/services/audio_generator.py` → `AudioGeneratorService.generate_scene_audio()`

---

#### Step 9.1 — Per scene, build audio file paths

```python
audio_dir = run_folder / "audio" / ls_id / scene_id
audio_dir.mkdir(parents=True, exist_ok=True)
narrator_path = audio_dir / "narrator.mp3"
```

---

#### Step 9.2 — Synthesize narrator audio

```python
narrator_text = scene["narrator_audio_text"]
voice_config = CHARACTER_VOICE_MAP["narrator"]
# → {"voice_id": "Gregory", "engine": "neural"}

ssml = _build_ssml(narrator_text, voice_id="Gregory", emotion="neutral")
narrator_bytes = _synthesize(ssml, voice_id="Gregory", engine="neural")
narrator_path.write_bytes(narrator_bytes)
```

**`_synthesize()`:**
```python
response = polly_client.synthesize_speech(
    Text=ssml,
    TextType="ssml",
    OutputFormat="mp3",
    VoiceId=voice_id,
    Engine=engine
)
return response["AudioStream"].read()
```

---

#### Step 9.3 — Build narrator SSML

```python
def _build_ssml(text, voice_id, emotion):
    if voice_id == "Matthew":
        # Supports amazon:emotion
        return f"""<speak><amazon:emotion name="{emotion_name}" intensity="{intensity}">
{text}
</amazon:emotion></speak>"""
    elif voice_id in ("Kevin", "Ivy"):
        # Kids voices: prosody only (no amazon:emotion, no pitch change)
        rate, volume = EMOTION_PROSODY_MAP[emotion]
        return f"""<speak><prosody rate="{rate}" volume="{volume}">
{text}
</prosody></speak>"""
    else:
        return f"<speak>{text}</speak>"
```

---

#### Step 9.4 — Synthesize each dialogue line

```python
dialogue_paths = []
for i, dialogue in enumerate(scene["character_dialogues"]):
    char_id = dialogue["character_id"]
    voice_config = CHARACTER_VOICE_MAP.get(char_id, CHARACTER_VOICE_MAP["default_male"])
    ssml = _build_ssml(dialogue["audio_text"], voice_config["voice_id"], dialogue["emotion"])
    audio_bytes = _synthesize(ssml, voice_config["voice_id"], voice_config["engine"])
    path = audio_dir / f"dialogue_{i+1:02d}.mp3"
    path.write_bytes(audio_bytes)
    dialogue_paths.append(path)
```

---

#### Step 9.5 — `merge_scene_audio(narrator_path, dialogue_paths, output_path)`

```python
from pydub import AudioSegment

merged = AudioSegment.from_mp3(narrator_path)
silence = AudioSegment.silent(duration=300)   # 300ms gap

for dlg_path in dialogue_paths:
    dlg_audio = AudioSegment.from_mp3(dlg_path)
    merged = merged + silence + dlg_audio

merged.export(audio_dir / "combined.mp3", format="mp3")
```

---

#### Step 9.6 — Get durations

```python
from mutagen.mp3 import MP3

def _get_audio_duration(path) -> int:
    audio = MP3(path)
    return int(audio.info.length * 1000)   # convert seconds → ms
```

---

#### Step 9.7 — Build manifest entry

```python
current_offset = narrator_duration_ms + 300

manifest[scene_id] = {
    "narrator": {
        "text": narrator_text,
        "voice_id": "Gregory",
        "audio_file": f"audio/{ls_id}/{scene_id}/narrator.mp3",
        "duration_ms": narrator_duration_ms
    },
    "dialogues": [
        {
            "character_id": dlg["character_id"],
            "voice_id": voice_config["voice_id"],
            "text": dlg["audio_text"],
            "audio_file": f"audio/{ls_id}/{scene_id}/dialogue_{i+1:02d}.mp3",
            "start_ms": current_offset,
            "duration_ms": dlg_duration_ms
        }
        for i, (dlg, dlg_duration_ms) in enumerate(zip(dialogues, durations))
    ],
    "combined": {
        "audio_file": f"audio/{ls_id}/{scene_id}/combined.mp3",
        "total_duration_ms": total_ms
    }
}
```

---

#### Step 9.8 — Save manifest

After all scenes: write `audio/manifest.json`.

**Files written per scene:**
```
audio/LS1/LS1_S1/narrator.mp3
audio/LS1/LS1_S1/dialogue_01.mp3
audio/LS1/LS1_S1/dialogue_02.mp3
audio/LS1/LS1_S1/combined.mp3
```

---

## 12. Phase 10 — PPT Generation

### `brain/services/ppt_generator.py` → `PPTGeneratorService.generate_ppt()`

---

#### Step 10.1 — Create presentation

```python
from pptx import Presentation
from pptx.util import Inches, Pt

prs = Presentation()
prs.slide_width = Inches(10)
prs.slide_height = Inches(7.5)
```

---

#### Step 10.2 — Title slide

```python
add_title_slide(prs, chapter_metadata)
# → blank layout + text box centered
# Line 1: chapter_name (40pt bold)
# Line 2: subject + class_level (24pt)
```

---

#### Step 10.3 — For each learning step: LS slide

```python
add_learning_step_slide(prs, ls_dict)
# → title box: ls["title"]
# → bullet box: top 5 concepts from ls["concepts_introduced"]
```

---

#### Step 10.4 — For each scene: scene slide

```python
add_scene_slide(prs, scene, image_path)
# → header strip (top 0.8 inches): scene phase + scene_goal
# → image below header: full width/height fitted
```

Image placement:
```python
slide.shapes.add_picture(
    image_path,
    left=Inches(0),
    top=Inches(0.8),
    width=Inches(10),
    height=Inches(6.7)
)
```

If `image_path` doesn't exist:
```python
# Draw grey rectangle placeholder
shape = slide.shapes.add_shape(MSO_SHAPE_TYPE.RECTANGLE, ...)
shape.fill.fore_color.rgb = RGBColor(180, 180, 180)
tf = shape.text_frame
tf.text = f"[Image not found: {image_path}]"
```

---

#### Step 10.5 — Save

```python
pptx_path = run_folder / "ppt" / "lesson.pptx"
prs.save(pptx_path)
state["ppt_output_path"] = str(pptx_path)
```

**File written:** `ppt/lesson.pptx`

---

## 13. Phase 11 — Output & Summary

### Back in `brain/main.py` → `_print_summary(result)`

---

#### Step 11.1 — Build summary dict

```python
summary = {
    "run_id": run_id,
    "chapter": user_inputs.chapter_name,
    "subject": user_inputs.subject,
    "class_level": user_inputs.class_level,
    "ls_count": len(learning_steps_list),
    "scene_count": total_scenes,
    "image_count": len(image_paths),
    "audio_count": len(audio_manifest),
    "has_ppt": ppt_output_path is not None,
    "completed_at": datetime.now().isoformat(),
    "duration_seconds": int(time.time() - start_time)
}
update_run_metadata(run_folder, summary)
```

---

#### Step 11.2 — Print stats box

```
┌─────────────────────────────────────────────────┐
│  ✓ Pipeline Complete                             │
│  Chapter:  Arithmetic Progressions (Grade 10)   │
│  Run ID:   run_20250331_120000                   │
│  ───────────────────────────────────────────    │
│  Learning Steps:  12                            │
│  Scenes:         168                            │
│  Images:         168                            │
│  Audio:          168                            │
│  PPT:            lesson.pptx                    │
│  Duration:       1h 43m                         │
└─────────────────────────────────────────────────┘
```

---

#### Step 11.3 — Save combined scenes file

```python
save_parsed(run_folder, "scenes_full", {"scenes": all_scenes_flat})
```

**File written:** `parsed/scenes_full.json`

---

## 14. Phase 12 — Frontend Playback

The pipeline run is complete. Now the user can view it in the browser.

---

#### Step 12.1 — Backend loads the run

`GET /api/runs/{run_id}` in `backend/server.py`:

```python
run_folder = OUTPUTS_DIR / run_id
config = load_json(run_folder / "inputs/config.json")
learning_steps = load_json(run_folder / "parsed/learning_steps.json")
scenes = load_scenes_for_run(run_folder)
audio_manifest = load_json(run_folder / "audio/manifest.json")
```

**`load_scenes_for_run()`** tries these paths in order:
1. `parsed/scenes_full.json` (if exists → use it)
2. `parsed/scenes_LS1.json`, `parsed/scenes_LS2.json`, ... (merge them)
3. `scenes/LS1/LS1_S1.json`, `scenes/LS1/LS1_S2.json`, ... (walk directory)

For each scene, injects computed URLs:
```python
scene["image_url"] = f"/static/{run_id}/images/{ls_id}/{scene_id}.png"
scene["audio"] = {
    "combined_url": f"/static/{run_id}/audio/{ls_id}/{scene_id}/combined.mp3",
    "combined_duration_ms": manifest_entry["combined"]["total_duration_ms"],
    ...
}
```

---

#### Step 12.2 — Frontend fetches and renders

`frontend/app/player/[runId]/page.tsx`:

```typescript
// On mount
const data = await fetch(`/api/runs/${runId}`).then(r => r.json())
const allScenes = Object.values(data.scenes).flat()   // LS1 + LS2 + ... → 1D array

// Display current scene
setCurrentScene(allScenes[currentIndex])

// Preload next image
const preload = new Image()
preload.src = allScenes[currentIndex + 1]?.image_url
```

---

#### Step 12.3 — Audio playback

```typescript
// If combined.mp3 exists
audioRef.current.src = scene.audio.combined_url
audioRef.current.play()

// Timed dialogue bubbles
scene.audio.dialogues.forEach(dlg => {
    setTimeout(() => showBubble(dlg), dlg.start_ms)
    setTimeout(() => hideBubble(dlg), dlg.start_ms + dlg.duration_ms)
})
```

---

#### Step 12.4 — Scene navigation

```typescript
// Keyboard handler
document.addEventListener('keydown', (e) => {
    if (e.key === 'ArrowRight' || e.key === 'l') nextScene()
    if (e.key === 'ArrowLeft'  || e.key === 'j') prevScene()
    if (e.key === ' ')                            toggleAudio()
    if (e.key === 'Escape')                       router.push('/dashboard')
})
```

---

## 15. State at Every Stage

The `PipelineState` grows as the pipeline progresses:

| After Phase | New state fields populated |
|---|---|
| Phase 0 | `user_inputs`, `run_folder`, `image_model`, `image_mode`, `generate_images`, `generate_audio`, `verbose` |
| Phase 1 | `pdf_path`, `pdf_source` |
| Phase 2 | `prompt0_output` → concept inventory |
| Phase 3 | `prompt1_output` → story backbone, `character_registry`, `art_style`, `story_bible` |
| Phase 4 | `prompt2_output` → learning steps, `learning_steps_list`, `current_ls_index=0`, `story_summary=""` |
| Phase 5 | `scene_plan` for current LS (local, not stored in state long-term) |
| Phase 6 | `scenes[ls_id]` grows per scene; `story_summary` grows per scene |
| Phase 7 | `image_prompts` dict populated |
| Phase 8 | `image_paths[scene_id]` populated per image |
| Phase 9 | `audio_manifest[scene_id]` populated per scene |
| Phase 10 | `ppt_output_path` |
| Phase 11 | run folder has complete `summary.json` |

---

## 16. Full Call Graph

```
main.py
├── load_dotenv()
├── ask_verbosity() → pipeline_logger.set_verbose()
├── get_available_topics() → reads assets/knowledge/*.pdf
├── select_topic()
├── select_image_model()
├── ask_scene_generation_mode()
├── ask_generate_images()
├── ask_generate_audio()
├── check_and_get_pdf()
│   └── pdf_agent.get_pdf()
│       ├── _search_local() → reads assets/knowledge/
│       └── _download_from_ncert() → requests.get()
│           └── pypdf.PdfReader() → extract text
├── model_output_manager.create_run_folder() → creates directory tree
└── pipeline.run()                            [brain/pipeline/pipeline_graph.py]
    │
    ├── [NODE: extract_concepts]
    │   └── concept_agent.extract_concepts()
    │       ├── prompt_builder.get_prompt("0A") → fills [CHAPTER_NAME], [CHAPTER_TEXT]
    │       ├── llm_client.call(prompt_0a) → DeepSeek via OpenRouter
    │       ├── json_utils.safe_parse(response)
    │       ├── prompt_builder.get_prompt("0B") → fills [EXISTING_CONCEPTS]
    │       ├── llm_client.call(prompt_0b)
    │       ├── safe_parse(response)
    │       ├── _merge_and_deduplicate()
    │       └── model_output_manager.save_parsed("concept_inventory")
    │
    ├── [NODE: generate_backbone]
    │   └── backbone_agent.generate_backbone()
    │       ├── format_character_registry_for_prompt() → ""  (empty at this stage)
    │       ├── prompt_builder.get_prompt("1")
    │       ├── llm_client.call(prompt_1)
    │       ├── llm_json_parser.parse(response)
    │       ├── _select_best_story() → regex scoring
    │       ├── _extract_characters()
    │       └── save_parsed("story_backbone")
    │
    ├── [NODE: generate_learning_steps]
    │   └── learning_steps_agent.generate_learning_steps()
    │       ├── format_character_registry_for_prompt()
    │       ├── prompt_builder.get_prompt("2")
    │       ├── llm_client.call(prompt_2)
    │       ├── safe_parse()
    │       ├── _parse_learning_steps()
    │       └── save_parsed("learning_steps")
    │
    └── [LOOP: for each learning step]
        │
        ├── [NODE: generate_scene_plan]
        │   └── scene_generator_agent._generate_scene_plan()
        │       ├── prompt_builder.get_prompt("3A")
        │       ├── llm_client.call(prompt_3a)
        │       └── safe_parse()
        │
        └── [LOOP: for each scene in plan]
            │
            ├── [NODE: generate_scenes]
            │   └── scene_generator_agent._generate_single_scene()
            │       ├── prompt_builder.get_prompt("3B")  [with PREVIOUS_SCENE, STORY_SUMMARY]
            │       ├── llm_client.call(prompt_3b)
            │       ├── safe_parse()
            │       ├── _update_story_summary() → appends to state.story_summary
            │       └── save_scenes(ls_id, scene)  → scenes/LS1/LS1_S3.json
            │
            ├── [NODE: generate_image_prompts]
            │   └── image_prompt_agent._build_prompt()
            │       ├── prompt_builder.get_prompt("4")
            │       ├── llm_client.call(prompt_4)
            │       ├── safe_parse()
            │       └── _append_global_style()
            │
            ├── [NODE: generate_images] (if generate_images=True)
            │   └── image_generator_service.generate_image()
            │       ├── [gpt-image-1.5] → openai.images.generate() → requests.get(url)
            │       └── [fal] → fal.queue.submit() → poll status → fal.queue.result()
            │           └── [on 5xx×3] → switch fallback model
            │       ├── pillow.Image.open() → validate
            │       ├── save PNG → images/LS1/LS1_S1.png
            │       └── [if overlay mode] → dialogue_overlay.apply()
            │           └── PIL.ImageDraw → draw speech bubbles + ComicNeue-Bold.ttf
            │
            └── [NODE: generate_audio] (if generate_audio=True)
                └── audio_generator_service.generate_scene_audio()
                    ├── _build_ssml(narrator_text, "Gregory", "neutral")
                    ├── boto3.polly.synthesize_speech() → narrator.mp3
                    ├── for each dialogue:
                    │   ├── _build_ssml(text, voice_id, emotion)
                    │   └── polly.synthesize_speech() → dialogue_N.mp3
                    ├── pydub.AudioSegment → merge → combined.mp3
                    ├── mutagen.mp3.MP3 → get durations
                    └── build manifest entry
    │
    ├── [NODE: generate_ppt]
    │   └── ppt_generator_service.generate_ppt()
    │       ├── pptx.Presentation() → slide_width=10in, height=7.5in
    │       ├── add_title_slide()
    │       ├── for each LS: add_learning_step_slide()
    │       ├── for each scene: add_scene_slide()
    │       │   ├── shapes.add_picture(image_path, ...)
    │       │   └── [if missing] → add_shape(grey_rect) + text
    │       └── prs.save("ppt/lesson.pptx")
    │
    └── [NODE: complete]
        ├── save_parsed("scenes_full", all_scenes)
        ├── write summary.json
        └── return result dict
```

---

## 17. File Timeline

In the order files are written during a run:

```
T+0s    outputs/run_{ts}/inputs/config.json          ← run config
T+0s    outputs/run_{ts}/inputs/chapter_text.txt      ← PDF text

T+10s   prompts/prompt0a.txt                          ← filled Prompt 0A
T+15s   raw_outputs/prompt0a_raw.txt                  ← LLM response
T+20s   prompts/prompt0b.txt
T+25s   raw_outputs/prompt0b_raw.txt
T+25s   parsed/concept_inventory.json                 ← 23 concepts

T+35s   prompts/prompt1.txt
T+60s   raw_outputs/prompt1_raw.txt
T+60s   parsed/story_backbone.json                    ← story + characters

T+75s   prompts/prompt2.txt
T+100s  raw_outputs/prompt2_raw.txt
T+100s  parsed/learning_steps.json                    ← 12 LS

[LS1 LOOP]
T+110s  prompts/prompt3a_LS1.txt
T+125s  raw_outputs/prompt3a_LS1_raw.txt

T+130s  prompts/prompt3b_LS1_S1.txt
T+145s  raw_outputs/prompt3b_LS1_S1_raw.txt
T+145s  scenes/LS1/LS1_S1.json                        ← scene JSON

T+150s  prompts/prompt4_LS1_S1.txt
T+160s  raw_outputs/prompt4_LS1_S1_raw.txt

T+165s  images/LS1/LS1_S1.png                         ← generated image

T+175s  audio/LS1/LS1_S1/narrator.mp3
T+178s  audio/LS1/LS1_S1/dialogue_01.mp3
T+180s  audio/LS1/LS1_S1/dialogue_02.mp3
T+182s  audio/LS1/LS1_S1/combined.mp3

... [repeats for LS1_S2 ... LS1_S14] ...

T+30m   parsed/scenes_LS1.json                        ← all LS1 scenes merged

[LS2..LS12 follow same pattern]

T+110m  ppt/lesson.pptx                               ← PowerPoint
T+110m  parsed/scenes_full.json                       ← all scenes flat
T+110m  audio/manifest.json                           ← audio timing
T+110m  summary.json                                  ← run stats
```

---

## 18. LLM Calls Summary

For a full run (12 LS × 14 scenes average = 168 scenes):

| Stage | Prompt | Calls | Model | Typical tokens per call |
|---|---|---|---|---|
| Concept extraction | Prompt 0A | 1 | DeepSeek | ~2,000 in / 500 out |
| Gap detection | Prompt 0B | 1 | DeepSeek | ~2,000 in / 300 out |
| Story backbone | Prompt 1 | 1 | DeepSeek | ~1,500 in / 1,200 out |
| Learning steps | Prompt 2 | 1 | DeepSeek | ~2,000 in / 2,500 out |
| Scene plans | Prompt 3A | 12 (1 per LS) | DeepSeek | ~1,500 in / 800 out |
| Scene generation | Prompt 3B | 168 (1 per scene) | DeepSeek | ~3,000 in / 1,500 out |
| Image prompts | Prompt 4 | 168 (1 per scene) | DeepSeek | ~1,200 in / 400 out |
| **Total LLM calls** | | **~352** | DeepSeek | ~1.1M total tokens |

| Stage | API | Calls | Cost estimate |
|---|---|---|---|
| Image generation | OpenAI / fal.ai | 168 | ~$1.68–$5.04 |
| Audio synthesis | Amazon Polly | ~504 (3 per scene) | ~$0.50 |
| Text generation | DeepSeek (OpenRouter) | ~352 | ~$0.30 |
| **Total run cost** | | | **~$2.50–$6.00** |
