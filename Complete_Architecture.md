# Complete Architecture — AI Storytelling Pipeline

> This document covers the full system architecture: every layer, every file, every library, every design decision, and how everything fits together.

---

## Table of Contents

1. [Project Purpose](#1-project-purpose)
2. [WAT Framework](#2-wat-framework)
3. [Directory Structure](#3-directory-structure)
4. [Layer 1 — Pipeline Orchestration (LangGraph)](#4-layer-1--pipeline-orchestration-langgraph)
5. [Layer 2 — Agents](#5-layer-2--agents)
6. [Layer 3 — Services](#6-layer-3--services)
7. [Layer 4 — Prompt Engine (Legacy Core)](#7-layer-4--prompt-engine-legacy-core)
8. [Layer 5 — Utilities](#8-layer-5--utilities)
9. [Layer 6 — Backend API (FastAPI)](#9-layer-6--backend-api-fastapi)
10. [Layer 7 — Frontend (Next.js)](#10-layer-7--frontend-nextjs)
11. [Master Prompts File](#11-master-prompts-file)
12. [Libraries & Why Each One Exists](#12-libraries--why-each-one-exists)
13. [Design Patterns](#13-design-patterns)
14. [Data Structures](#14-data-structures)
15. [Environment Variables](#15-environment-variables)
16. [Critical Rules & Guardrails](#16-critical-rules--guardrails)
17. [Error Handling Strategy](#17-error-handling-strategy)
18. [Debug & Test Modes](#18-debug--test-modes)
19. [Deployment](#19-deployment)

---

## 1. Project Purpose

This system takes an **NCERT school chapter PDF** (Grades 9–12, any subject) and automatically produces:

- A **cinematic story** with original characters who learn the chapter's concepts through adventure/mystery/sports arcs
- **12–15 AI-generated scene images per learning step** (using OpenAI or fal.ai image models)
- **TTS audio narration + character dialogue** per scene (Amazon Polly, neural voices)
- A **PowerPoint presentation** (one slide per scene)
- A **React web player** that plays it all back like an animated lesson

The core insight: instead of AI explaining concepts directly, it hides concepts inside story beats. A detective figures out Arithmetic Progressions by cracking a code. Two friends discover Circles by building a racetrack. Learning happens through narrative immersion.

---

## 2. WAT Framework

The system is built on the **WAT** (Workflows, Agents, Tools) architecture:

```
┌──────────────────────────────────────────────────┐
│  WORKFLOWS  (Markdown SOPs in workflows/)        │
│  Plain-language instructions: what to do, when, │
│  what inputs/outputs, how to handle failures     │
└───────────────────┬──────────────────────────────┘
                    │ reads + follows
┌───────────────────▼──────────────────────────────┐
│  AGENTS  (brain/ — you are here)                 │
│  Intelligent coordination: read workflow,        │
│  call the right tools in the right order,        │
│  handle failures, make decisions                 │
└───────────────────┬──────────────────────────────┘
                    │ calls
┌───────────────────▼──────────────────────────────┐
│  TOOLS  (tools/ — Python scripts)                │
│  Deterministic execution: API calls, file I/O,   │
│  data transforms — consistent, testable, fast    │
└──────────────────────────────────────────────────┘
```

**Why WAT?** When AI handles everything end-to-end, each step has ~90% accuracy. Five steps = 59% success. By separating reasoning (agents) from execution (tools), the system stays reliable. AI only does what AI is good at — orchestration and language. Deterministic code handles everything else.

---

## 3. Directory Structure

```
project_root/
├── assets/
│   ├── characters/          # Character reference images
│   ├── environments/        # Environment reference images
│   ├── fonts/               # ComicNeue-Bold.ttf, ComicNeue-Regular.ttf
│   ├── image_repository/    # Cache of generated images (gitignored)
│   ├── knowledge/           # Source PDFs (NCERT chapters)
│   ├── objects/             # Prop reference images
│   └── prompts/
│       └── MASTER_PROMPTS.txt   # ALL LLM prompts in one file
│
├── backend/
│   └── server.py            # FastAPI server — serves data to frontend
│
├── brain/
│   ├── main.py              # Entry point — interactive pipeline runner
│   ├── agents/              # One agent class per pipeline stage
│   │   ├── pdf_agent.py
│   │   ├── concept_agent.py
│   │   ├── backbone_agent.py
│   │   ├── learning_steps_agent.py
│   │   ├── scene_generator_agent.py
│   │   ├── image_prompt_agent.py
│   │   ├── prompt_injector_agent.py
│   │   └── flow_tracker_agent.py
│   ├── pipeline/
│   │   ├── pipeline_graph.py        # LangGraph DAG definition + .run() method
│   │   └── state/
│   │       └── pipeline_state.py    # PipelineState TypedDict
│   ├── prompt_engine/       # Legacy LLM + prompt abstractions
│   │   ├── llm_client.py
│   │   ├── prompt_loader.py
│   │   └── state_manager.py
│   └── services/            # Non-LLM execution services
│       ├── audio_generator.py
│       ├── image_generator.py
│       ├── ppt_generator.py
│       ├── prompt_builder.py
│       ├── dialogue_overlay.py
│       └── regenerate_images.py
│
├── core/                    # Legacy utility layer
│   ├── llm_json_parser.py
│   ├── llm_usage_parser.py
│   ├── llm_response_extractor.py
│   └── metrics_logger.py
│
├── frontend/                # Next.js 14 React app
│   ├── app/
│   │   ├── layout.tsx
│   │   ├── globals.css
│   │   ├── page.tsx             # Login
│   │   ├── register/page.tsx
│   │   ├── dashboard/page.tsx
│   │   ├── player/[runId]/page.tsx
│   │   ├── profile/page.tsx
│   │   └── avatar/page.tsx
│   ├── components/
│   │   └── LatestRunButton.tsx
│   └── hooks/
│       └── useAuth.ts
│
├── outputs/                 # Run outputs — gitignored
│   └── run_{YYYYMMDD_HHMMSS}/
│       ├── inputs/config.json
│       ├── prompts/
│       ├── raw_outputs/
│       ├── parsed/
│       ├── scenes/LS1/LS1_S1.json
│       ├── images/LS1/LS1_S1.png
│       ├── audio/LS1/LS1_S1/narrator.mp3
│       ├── ppt/lesson.pptx
│       └── summary.json
│
├── tools/                   # Deterministic execution scripts
├── utils/                   # Shared utility modules
│   ├── pipeline_logger.py
│   ├── model_output_manager.py
│   ├── image_repository.py
│   ├── json_utils.py
│   └── run_cost_tracker.py
│
├── workflows/               # Markdown SOPs
├── CLAUDE.md                # Project instructions for Claude Code
├── AGENTS.md                # Agent framework instructions
├── requirements.txt
└── .env                     # API keys — never committed
```

---

## 4. Layer 1 — Pipeline Orchestration (LangGraph)

### `brain/pipeline/pipeline_graph.py`

**Role:** The central conductor. Defines the pipeline as a Directed Acyclic Graph (DAG) using LangGraph. Each stage is a node; edges define which node runs next.

**Key flags at the top of the file:**
```python
DEBUG_MODE = True       # Limits pipeline to 1 LS for fast testing
DEBUG_MAX_LS = 1        # Number of learning steps when debug mode is on
```

**Nodes (in execution order):**

| Node Name | What it does |
|---|---|
| `extract_concepts` | Calls ConceptAgent → Prompt 0 |
| `generate_backbone` | Calls BackboneAgent → Prompt 1 |
| `generate_learning_steps` | Calls LearningStepsAgent → Prompt 2 |
| `generate_scene_plan` | Calls SceneGeneratorAgent → Prompt 3A per LS |
| `generate_scenes` | Calls SceneGeneratorAgent → Prompt 3B per scene |
| `generate_image_prompts` | Calls ImagePromptAgent → Prompt 4 per scene |
| `generate_images` | Calls ImageGeneratorService per scene |
| `generate_audio` | Calls AudioGeneratorService per scene |
| `generate_ppt` | Calls PPTGeneratorService |

**Edge logic:**
- After `generate_learning_steps`: enter loop over all learning steps
- After `generate_scenes` for a LS: check if more LS → loop back or proceed to image prompts
- After `generate_image_prompts`: check if more scenes → loop or proceed
- Uses `FlowTrackerAgent` enum to route edges: `PROMPT3_LOOP`, `PROMPT4_LOOP`, `COMPLETE`, `ERROR`

**`.run()` method signature:**
```python
pipeline.run(
    user_inputs=UserInputs(...),
    image_model="gpt-image-1.5",
    image_mode="dialogue",
    generate_images=True,
    generate_audio=True,
    verbose=False,
    run_folder=None
)
```
Returns a dict: `{run_folder, learning_steps_list, image_paths, ppt_output_path, summary}`

**LangSmith tracing:** If `LANGSMITH_API_KEY` is set in `.env`, every LLM call is automatically traced with inputs/outputs for auditing and debugging.

---

### `brain/pipeline/state/pipeline_state.py`

**Role:** The single source of truth. A Pydantic `TypedDict` that flows through every LangGraph node unchanged unless a node explicitly mutates it.

**Key fields:**

```python
class UserInputs(TypedDict):
    chapter_name: str         # e.g. "Arithmetic Progressions"
    chapter_title: str        # e.g. "Chapter 5"
    chapter_number: int
    class_level: str          # e.g. "Grade 10"
    subject: str              # e.g. "Mathematics"
    medium: str               # e.g. "English"

class PipelineState(TypedDict):
    user_inputs: UserInputs
    run_folder: str                   # Absolute path to outputs/run_{timestamp}/
    pdf_path: str                     # Path to chapter PDF
    pdf_source: str                   # "local" or "downloaded"

    # LLM outputs (parsed JSON dicts)
    prompt0_output: dict              # Concept inventory
    prompt1_output: dict              # Story backbone
    prompt2_output: dict              # Learning steps
    
    # Pipeline state
    character_registry: list[dict]    # Extracted from Prompt 1; injected into all later prompts
    story_bible: dict                 # {academic_context, art_style, character_registry, story_backbone}
    art_style: str                    # Global visual anchor — injected into every Prompt 4
    learning_steps_list: list[dict]   # All LS dicts from Prompt 2
    current_ls_index: int             # Loop counter for LS iteration
    current_scene_index: int          # Loop counter for scene iteration
    scenes: dict[str, list[dict]]     # {LS_ID: [scene1, scene2, ...]}
    story_summary: str                # Accumulated 1-2 line summary per scene
    
    # Config flags
    image_model: str
    image_mode: str
    generate_images: bool
    generate_audio: bool
    verbose: bool
    
    # Outputs
    image_paths: dict[str, str]       # {scene_id: abs_path_to_png}
    audio_manifest: dict              # {scene_id: {narrator, dialogues, combined}}
    ppt_output_path: str
```

**Helper functions (module-level):**
- `get_current_learning_step(state)` → current LS dict based on `current_ls_index`
- `get_scenes_for_current_learning_step(state)` → scenes list for current LS
- `is_learning_step_selected(state, ls_id)` → bool (respects single-LS test mode)
- `is_scene_selected(state, scene_id)` → bool (respects single-scene test mode)
- `format_character_registry_for_prompt(state)` → formatted string for [CHARACTER_REGISTRY] injection

---

## 5. Layer 2 — Agents

Each agent handles exactly one pipeline stage. All agents share the same pattern: receive state, call LLMClient with a filled prompt, parse the response, return updated state fields.

---

### `brain/agents/pdf_agent.py` — `PDFAgent`

**Role:** Gets the chapter PDF onto disk.

**Logic:**
1. Check `assets/knowledge/` folder for a file matching the chapter name (case-insensitive, partial match)
2. If found → return `(path, "local")`
3. If not found → scrape NCERT website, construct download URL from chapter metadata
4. Download with `requests.get()` using exponential backoff on SSL/timeout errors (3 retries)
5. Save to `assets/knowledge/{chapter_name}.pdf`
6. Return `(path, "downloaded")`

**Key methods:**
- `get_pdf(chapter_name, chapter_number, class_level, subject)` → `(str, str)`
- `_search_local(chapter_name)` → `str | None`
- `_download_from_ncert(chapter_number, class_level, subject)` → `str`

---

### `brain/agents/concept_agent.py` — `ConceptAgent`

**Role:** Prompt 0 — Extracts the concept inventory from the PDF.

**Two-pass approach:**
- **Pass A (Section Pass):** Reads the PDF and extracts concept titles section by section. Filters out examples, case studies, problems — only definitions, formulas, properties survive.
- **Pass B (Gap Detection Pass):** Given Pass A's output, re-reads the PDF looking for concepts that were missed. Returns additional concepts.

Final output merges both passes, deduplicates, returns `{concepts: [string, ...]}`

**Key methods:**
- `extract_concepts(pdf_path, chapter_metadata)` → `dict`
- `_run_pass_a(pdf_text, metadata)` → `list[str]`
- `_run_pass_b(pdf_text, existing_concepts)` → `list[str]`
- `_merge_and_deduplicate(pass_a, pass_b)` → `list[str]`

---

### `brain/agents/backbone_agent.py` — `BackboneAgent`

**Role:** Prompt 1 — Generates the story backbone with characters.

**What it generates:**
- Story title, core premise
- 2–4 characters, each with: `name, role, personality, visual_description, gender, voice_id`
- `visual_description` must include: hair color + style, eye color, skin tone, outfit colors, height/build, 1 distinctive feature (anime/Ghibli style)
- `voice_id` must be from approved palette: Kevin, Ivy, Matthew, Joanna, Brian, Emma (not Gregory — reserved for narrator)
- `coverage_%` — how much of the chapter's concepts this story covers
- `pedagogical_%` — how strong the learning design is

**Selection logic:** If multiple story options are generated, picks the one with the highest `coverage% + pedagogical%` combined score using regex extraction.

**Critical constraint enforced in prompt:** Story archetype must be DETECTIVE/MYSTERY, GAMING/ADVENTURE, SPORTS CHALLENGE, or SCI-FI DISCOVERY. Never a generic school classroom story.

**Key methods:**
- `generate_backbone(concept_inventory, chapter_metadata)` → `dict`
- `_select_best_story(raw_stories)` → `dict`
- `_extract_characters(story_dict)` → `list[dict]`

---

### `brain/agents/learning_steps_agent.py` — `LearningStepsAgent`

**Role:** Prompt 2 — Breaks the story into ordered learning steps.

**Output structure per LS:**
```json
{
  "learning_step_id": "LS1",
  "title": "The Broken Pattern",
  "concepts_introduced": ["arithmetic sequence", "common difference"],
  "narrative_moment": "Maya notices the stadium lights flickering in a pattern. She counts: 2, 5, 8... but the 7th light is wrong. She and Leo spend 5 minutes arguing about whether it's a glitch before realizing the gap between each light is always 3. That gap has a name."
}
```

**`narrative_moment` rules (enforced in prompt):**
- 5–8 sentences
- 3-act arc: encounter → exploration → breakthrough
- Must include a physical/environmental anchor (the lights, the scoreboard, the map)
- Must include an emotional journey (confusion → frustration → realization)

Generates 10–15 learning steps. Each LS corresponds to a cluster of related concepts taught through one narrative beat.

**Key methods:**
- `generate_learning_steps(backbone, concepts, chapter_metadata)` → `dict`
- `_parse_learning_steps(raw_response)` → `list[dict]`

---

### `brain/agents/scene_generator_agent.py` — `SceneGeneratorAgent`

**Role:** Prompts 3A and 3B — The most complex agent. Generates all scenes for all learning steps.

**Two-stage generation per LS:**

**Stage 3A (Scene Plan):** Given a learning step's `narrative_moment` and `concepts_introduced`, generates a plan of 12–15 scenes. Each scene in the plan:
```json
{
  "scene_id": "LS1_S1",
  "phase": "HOOK",
  "summary": "Stadium lights flicker. Maya stares at the pattern in silence.",
  "concept_focus": null
}
```

Scene phase types and their order rules:
- `HOOK` — always S1, environment only, no characters, no concepts
- `SETUP` — always S2, character enters, no concept definitions
- `DISCOVERY` — character notices something interesting
- `CONFUSION` — tries and fails
- `GUIDANCE` — mentor/peer offers a clue
- `MICRO_LEARN` — tiny insight lands
- `VALIDATION` — tests the insight
- `APPLICATION` — applies it to a new problem
- `TWIST` — unexpected complication
- `ESCALATION` — stakes rise
- `PAYOFF` — concept fully revealed and named
- `REFLECTION` — whiteboard/diagram moment
- `TRANSITION` — bridge to next LS
- `CLIFFHANGER` — emotional hook for next LS

No two consecutive scenes can have the same phase. PAYOFF is always the final scene (or near-final).

**Stage 3B (Full Scene Generation):** For each planned scene, generates a complete scene JSON:
```json
{
  "scene_id": "LS1_S1",
  "phase": "HOOK",
  "setting": "A deserted stadium at night. Row 7 of the scoreboards is lit — except bulb 7 flickers on and off every 3 seconds.",
  "characters": [],
  "character_dialogues": [
    {
      "character_id": "maya",
      "dialogue": "Wait... 2, 5, 8... why does 17 feel wrong?",
      "emotion": "confused",
      "audio_text": "Wait... two, five, eight... why does seventeen feel wrong?"
    }
  ],
  "narrator_audio_text": "The scoreboard has been flickering for six minutes. No one has called maintenance.",
  "learning_moment": null,
  "concept_taught": null,
  "visual_setting": "Wide shot, stadium floodlights, deep shadows, single flickering bulb in row 7"
}
```

**Context injected into every 3B call:**
- `[CHARACTER_REGISTRY]` — full character descriptions so visuals stay consistent
- `[STORY_SUMMARY]` — accumulated 1–2 line summary of all previous scenes so dialogue references past events
- `[PREVIOUS_SCENE]` — full JSON of the immediately prior scene so continuity is maintained (exact numbers, same location details)

**Key methods:**
- `generate_scenes_for_ls(ls_dict, state)` → `list[dict]`
- `_generate_scene_plan(ls_dict, state)` → `list[dict]`
- `_generate_single_scene(scene_plan_item, ls_dict, state)` → `dict`
- `_update_story_summary(state, new_scene)` → `str`

---

### `brain/agents/image_prompt_agent.py` — `ImagePromptAgent`

**Role:** Prompt 4 — Converts scene JSON into an image generation prompt.

**Two image modes:**
- `dialogue` mode: Prompt instructs the image model to **render speech bubble text inside the image**. The generated PNG contains the dialogue visually.
- `overlay` mode: Prompt explicitly tells the image model to **leave space** for text that will be composited later. Dialogue is then added by `dialogue_overlay.py`.

**GLOBAL_VISUAL_STYLE suffix:** After every Prompt 4 response, a fixed style string is appended. This string defines: art style (anime/Ghibli 2D), line weight, color palette temperature, background complexity, character proportions. Same suffix = visual consistency across all scenes regardless of which image model runs.

**Key methods:**
- `generate_image_prompts(scenes, state)` → `dict[str, str]`
- `_build_prompt(scene, image_mode)` → `str`
- `_append_global_style(prompt)` → `str`

---

### `brain/agents/prompt_injector_agent.py` — `PromptInjectorAgent`

**Role:** Utility agent for automatic placeholder injection using LLM.

**When used:** When a prompt has complex content blocks that can't be filled by simple variable substitution. For example, `[STORY_SUMMARY_NARRATIVE]` might need to be written in story tone — a simple string replacement won't work. This agent calls the LLM to fill it intelligently.

**Validation:** After injection, scans the filled prompt for remaining `[PLACEHOLDER]` patterns. If any found, raises `ValueError` with the list. This prevents partially-filled prompts from reaching the main LLM calls.

**Key methods:**
- `inject(prompt_template, available_context, state)` → `str`
- `_fill_simple_placeholders(template, context)` → `str`
- `_fill_complex_placeholders(template, state)` → `str`
- `_validate_no_remaining_placeholders(filled_prompt)` → `None`

---

### `brain/agents/flow_tracker_agent.py` — `FlowTrackerAgent`

**Role:** Enum-based state machine that tells LangGraph which node to run next.

**Stages enum:**
```python
class PipelineStage(Enum):
    START = "start"
    PROMPT0 = "prompt0"
    PROMPT1 = "prompt1"
    PROMPT2 = "prompt2"
    PROMPT3_LOOP = "prompt3_loop"
    PROMPT4_LOOP = "prompt4_loop"
    PPT_GENERATION = "ppt_generation"
    COMPLETE = "complete"
    ERROR = "error"
```

**Key methods:**
- `get_current_stage()` → `PipelineStage`
- `advance()` → moves to next stage
- `determine_next_action(state)` → returns routing string for LangGraph conditional edge
- `should_continue_learning_step_loop(state)` → bool (more LS to process?)
- `should_continue_scene_loop(state)` → bool (more scenes in current LS?)

---

## 6. Layer 3 — Services

Services handle **execution** — they call external APIs or do I/O. They receive structured data from agents and produce files/artifacts.

---

### `brain/services/image_generator.py` — `ImageGeneratorService`

**Role:** Takes an image prompt string and produces a PNG file.

**Supported models:**

| Model ID | API | Cost tier | Style |
|---|---|---|---|
| `gpt-image-1.5` | OpenAI `/v1/images/generations` | High | Clean, detailed, follows prompts precisely |
| `fal-flux2pro` | fal.ai Flux 2 Pro | Medium | Photorealistic, cinematic |
| `fal-juggernaut` | fal.ai Juggernaut XL | Medium | High detail, anime-capable |

**OpenAI flow:**
1. Call `openai.images.generate(prompt=..., model="gpt-image-1.5", size="1024x1024")`
2. Download image from returned URL
3. Save bytes to `images/LS{N}/LS{N}_S{M}.png`

**fal.ai flow (async):**
1. Submit job to `fal.queue.submit(model_id, arguments={prompt, ...})`
2. Poll `fal.queue.status(request_id)` every 3 seconds
3. On completion: `fal.queue.result(request_id)` → download image URL
4. On persistent 5xx errors (3 consecutive): switch to fallback model (`fal-flux2pro` if primary was `fal-juggernaut`)
5. Save downloaded bytes to canonical path

**Fallback chain:** `fal-juggernaut` → `fal-flux2pro` → skip + save placeholder text file

**Key methods:**
- `generate_image(prompt, scene_id, run_folder, model, mode)` → `str` (image path)
- `_generate_openai_image(prompt)` → `bytes`
- `_generate_fal_image(prompt, model_id)` → `bytes`
- `_get_image_path(run_folder, scene_id)` → `str`
- `_save_image(bytes, path)` → `str`

---

### `brain/services/audio_generator.py` — `AudioGeneratorService`

**Role:** Generates MP3 audio files using Amazon Polly neural TTS. One file per narrator passage, one per dialogue line, then merges all into `combined.mp3`.

**Character → Voice mapping:**
```python
CHARACTER_VOICE_MAP = {
    "leo":      {"voice_id": "Kevin",   "engine": "neural"},
    "maya":     {"voice_id": "Ivy",     "engine": "neural"},
    "professor":{"voice_id": "Matthew", "engine": "neural"},
    "narrator": {"voice_id": "Gregory", "engine": "neural"},
    "default_male":   {"voice_id": "Kevin",   "engine": "neural"},
    "default_female": {"voice_id": "Ivy",     "engine": "neural"},
}
```

**SSML emotion wrapping:** Different voices support different SSML features:
- `Matthew` (adult male, neural): Supports `<amazon:emotion name="excited" intensity="high">` tags
- `Kevin`, `Ivy` (teen neural): Do NOT support `<amazon:emotion>`. Instead use `<prosody rate="+10%" pitch="+5%">` for energy, `<prosody rate="-15%" pitch="-8%">` for sadness
- `Gregory` (narrator): Neutral, no emotion tags — uses slight `<prosody rate="-5%">` for gravitas

**EMOTION_SSML dict:** Maps `(voice_id, emotion)` tuples to SSML wrapping templates. Emotions supported: `excited`, `curious`, `confused`, `sad`, `angry`, `happy`, `whisper`, `neutral`.

**Merge logic:**
1. Synthesize `narrator.mp3`
2. Synthesize `dialogue_01.mp3`, `dialogue_02.mp3`, ... per character line (in order of `character_dialogues` array)
3. Use `pydub.AudioSegment` to concatenate: narrator → short silence → dialogue 1 → dialogue 2 → ...
4. Export merged file as `combined.mp3`
5. Record durations using `mutagen.mp3.MP3` for frontend timing

**Audio manifest structure saved per scene:**
```json
{
  "LS1_S1": {
    "narrator": {
      "text": "...",
      "voice_id": "Gregory",
      "audio_file": "audio/LS1/LS1_S1/narrator.mp3",
      "duration_ms": 4200
    },
    "dialogues": [
      {
        "character_id": "maya",
        "voice_id": "Ivy",
        "text": "...",
        "audio_file": "audio/LS1/LS1_S1/dialogue_01.mp3",
        "start_ms": 4400,
        "duration_ms": 2800
      }
    ],
    "combined": {
      "audio_file": "audio/LS1/LS1_S1/combined.mp3",
      "total_duration_ms": 9800
    }
  }
}
```

**Key methods:**
- `generate_scene_audio(scene, run_folder)` → `dict`
- `_synthesize(text, voice_id, engine, emotion)` → `bytes`
- `_build_ssml(text, voice_id, emotion)` → `str`
- `merge_scene_audio(narrator_path, dialogue_paths, output_path)` → `str`
- `_get_audio_duration(mp3_path)` → `int` (ms)

---

### `brain/services/ppt_generator.py` — `PPTGeneratorService`

**Role:** Generates a PowerPoint file from all scenes and their images.

**Slide structure:**
1. **Title slide:** Chapter name, subject, class level, center-aligned
2. **Learning step slide:** LS title + top 5 concepts as bullet points (one per LS)
3. **Scene slides:** Full-screen image below a header strip; header text = `scene_goal` or scene phase

**Technical:** Uses `python-pptx`. Slide size is `Inches(10, 7.5)` (widescreen). Images are fitted to fill the content area with aspect ratio preserved. If an image is missing, a grey placeholder rectangle is drawn with `[Image not found: {path}]` text.

**Key methods:**
- `generate_ppt(run_folder, learning_steps, scenes, image_paths)` → `str` (pptx path)
- `create_presentation()` → `pptx.Presentation`
- `add_title_slide(prs, chapter_metadata)` → `None`
- `add_learning_step_slide(prs, ls_dict)` → `None`
- `add_scene_slide(prs, scene, image_path)` → `None`

---

### `brain/services/prompt_builder.py` — `PromptBuilder`

**Role:** Loads all prompts from `MASTER_PROMPTS.txt` and fills `[PLACEHOLDER]` variables at runtime.

**Parsing:** The file is split by `----` delimiter lines. Each block starts with a `## Prompt N:` header. The PromptBuilder builds a dict: `{prompt_id: template_string}` on initialization.

**Placeholder filling:** Uses Python's `str.replace()` for each `{key: value}` pair passed to `get_prompt()`. After all replacements, validates that no `[...]` patterns remain.

**Key methods:**
- `__init__(prompts_file_path)` → loads and parses all prompts
- `get_prompt(prompt_id, **variables)` → `str`
- `available_prompts()` → `list[str]`
- `_parse_sections(raw_text)` → `dict[str, str]`
- `_validate_filled(filled_prompt)` → raises `ValueError` if placeholders remain

---

### `brain/services/dialogue_overlay.py`

**Role:** When `image_mode="overlay"`, composites speech bubbles onto the scene image after generation.

**Process:**
1. Read `character_dialogues` from scene JSON
2. For each dialogue, determine bubble position based on which character is speaking (stored in scene's `characters` array with `position` field)
3. Draw rounded-rectangle speech bubble with `PIL.ImageDraw`
4. Render text using `ComicNeue-Bold.ttf` from `assets/fonts/`
5. Tail drawn pointing toward character's screen position
6. Save composited image over original

---

### `brain/services/regenerate_images.py`

**Role:** Standalone utility script for regenerating images for an existing run without re-running the full pipeline.

**Usage:** Run directly: `python brain/services/regenerate_images.py --run-id run_20250331_120000 --model fal-flux2pro`

Reads existing `parsed/image_prompts.json`, calls `ImageGeneratorService` for each scene, overwrites `images/` folder.

---

## 7. Layer 4 — Prompt Engine (Legacy Core)

These modules pre-date the current LangGraph architecture. Still used internally by some agents.

---

### `brain/prompt_engine/llm_client.py` — `LLMClient`

**Role:** Thin wrapper around `langchain_openai.ChatOpenAI`.

**Why a wrapper?** Centralizes model config (temperature, max tokens, model ID), adds retry logic, and normalizes the response interface so agents don't need to know which provider is in use.

**Key methods:**
- `call(prompt: str, attachments: list = [])` → `str`
- `call_with_json_output(prompt)` → `dict`
- Factory: `create_llm_client(model, temperature, max_tokens)` → `LLMClient`

Text model is hardcoded in `brain/main.py` as `text_model = "deepseek"`, which routes through OpenRouter using `OPENROUTER_API_KEY`.

---

### `brain/prompt_engine/prompt_loader.py` — `PromptLoader`

**Role:** Alternate prompt loading mechanism. Parses `MASTER_PROMPTS.txt` by splitting on `Prompt N:` headers.

**Key methods:**
- `get_prompt(prompt_num: int)` → `str`
- `get_pdf_prompt()` → `str`
- `inject_values(template, **values)` → `str`
- Static: `normalize_subject(subject)` → canonical subject name
- Static: `slugify(text)` → filesystem-safe slug

---

### `brain/prompt_engine/state_manager.py` — `StateManager` + `ChapterState`

**Role:** Legacy per-chapter state management and file I/O (before `ModelOutputManager` was built).

**`ChapterState`** creates a run folder under `runs/{class}_{subject}_{chapter}/` with subdirs: `prompts/`, `outputs/`, `raw/`, `json/`, `image_prompts/`.

**Methods:**
- `save_prompt(prompt_num, text)` → saves injected prompt to file
- `save_raw_response(prompt_num, text)` → saves raw LLM response
- `save_output(prompt_num, data)` → saves parsed output
- `save_json(name, data)` → saves arbitrary JSON

**`StateManager`:** Singleton that manages all `ChapterState` instances.
- `get_state_manager()` → singleton instance
- `get_or_create_state(chapter_id)` → `ChapterState`

---

## 8. Layer 5 — Utilities

---

### `utils/pipeline_logger.py`

**Role:** Two-level logging for the pipeline.

```python
log("✓ Scene LS1_S3 generated")          # Always printed
debug("Raw LLM response: {...}")          # Only if verbose=True
set_verbose(True)                         # Toggle debug output
```

Used to give users a clean progress view (milestones only) unless they opt into verbose mode.

---

### `utils/model_output_manager.py`

**Role:** All file I/O for the `outputs/run_{timestamp}/` folder. Single point of truth for where things get saved.

**Creates this structure on `create_run_folder()`:**
```
run_{timestamp}/
  inputs/
    config.json         ← chapter metadata, model choices, flags
    chapter_text.txt    ← extracted PDF text
  prompts/
    prompt0.txt         ← filled Prompt 0 text sent to LLM
    prompt1.txt
    prompt3a_LS1.txt
    prompt3b_LS1_S1.txt ← one file per (LS, scene) for Prompt 3B
    prompt4_LS1_S1.txt
  raw_outputs/
    prompt0_raw.txt     ← raw LLM response before JSON parsing
    prompt1_raw.txt
    ...
  parsed/
    concept_inventory.json
    story_backbone.json
    learning_steps.json
    scenes_LS1.json
    scenes_full.json    ← all scenes merged
    image_prompts.json
  scenes/
    LS1/
      LS1_S1.json
      LS1_S2.json
      ...
  images/
    LS1/
      LS1_S1.png
      LS1_S2.png
  audio/
    LS1/
      LS1_S1/
        narrator.mp3
        dialogue_01.mp3
        dialogue_02.mp3
        combined.mp3
    manifest.json
  ppt/
    lesson.pptx
  logs/
    pipeline.log
  summary.json
```

**Key functions:**
- `create_run_folder()` → `str` (abs path)
- `save_prompt(run_folder, prompt_id, text)` → `None`
- `save_raw_output(run_folder, prompt_id, text)` → `None`
- `save_parsed(run_folder, name, data)` → `None`
- `save_scenes(run_folder, ls_id, scenes)` → `None`
- `save_image(run_folder, scene_id, image_bytes)` → `str` (saved path)
- `save_ppt(run_folder, pptx_bytes)` → `str`
- `update_run_metadata(run_folder, updates)` → `None`

---

### `utils/json_utils.py`

**Role:** Handles the messy reality that LLMs sometimes return malformed JSON.

**`safe_parse(raw_text, default=None)`** — tries 7 strategies in order:
1. Direct `json.loads()`
2. Strip markdown code block (` ```json ... ``` `)
3. Extract substring between first `{` and last `}`
4. Replace single quotes with double quotes
5. Remove trailing commas before `}` and `]`
6. Handle multiple JSON objects (take the largest valid one)
7. If all fail and `default` is provided, return default

**`safe_parse_with_retry(raw_text, llm_client, original_prompt)`** — if parsing fails, sends the raw text back to the LLM with a "please fix this JSON" prompt, then tries `safe_parse` again.

---

### `utils/image_repository.py`

**Role:** Image cache — stores generated images with metadata to avoid re-generating identical prompts.

**`store_image_repository(prompt, image_bytes, model, metadata)`:**
- Hashes the prompt (SHA256)
- Saves image to `assets/image_repository/{hash}.png`
- Saves metadata JSON: `{prompt, model, timestamp, hash, scene_id, ...}`

**`lookup_image(prompt, model)`:**
- Hash prompt, check if `{hash}.png` exists
- If yes, return cached bytes + metadata

---

### `utils/run_cost_tracker.py`

**Role:** Tracks API spending per run.

**Tracks:**
- OpenAI image generation: cost per image × count
- fal.ai: cost per second of compute × count
- Amazon Polly: cost per character × character count
- DeepSeek/OpenRouter text: cost per 1K tokens × token count

**Key functions:**
- `track_usage(api, units, unit_cost)` → cumulative log entry
- `estimate_cost(run_folder)` → `float` (total USD)
- `get_total_cost()` → `float`

---

### `core/llm_json_parser.py`

**Role:** Universal JSON parser for LLM output. More aggressive than `json_utils.safe_parse` — uses regex to find JSON-like structures in heavily wrapped LLM responses.

**Strategies (in order):**
1. Direct `json.loads()`
2. Markdown code block extraction
3. JSON between `{` and `}` (greedy)
4. Single → double quote normalization
5. Trailing comma removal via regex
6. Find all valid JSON objects, return the largest
7. Return default if provided, else raise

Used by: `BackboneAgent._select_best_story()`, `LearningStepsAgent._parse_learning_steps()`, and any agent where the LLM might wrap JSON in extra prose.

---

## 9. Layer 6 — Backend API (FastAPI)

### `backend/server.py`

**Role:** REST API that serves the React frontend. Reads from `outputs/` folder and serves JSON + static files.

**Port:** 8000  
**CORS:** Allows `http://localhost:3000`

---

#### Auth Endpoints

**`POST /api/auth/login`**
```
Request:  {username: str, password: str}
Response: {user: {username, displayName, email}}
```
- Checks hardcoded USERS dict first (dev accounts: `admin / academy123`)
- Falls back to `data/users.json` for registered users
- Password hashing: SHA256 hex digest
- No JWT tokens — session is managed client-side in localStorage

**`POST /api/auth/register`**
```
Request:  {fullName: str, username: str, email: str, password: str}
Response: {user: {username, displayName, email}}
```
- Checks `data/users.json` for existing username/email
- Hashes password, appends new user, saves back to file
- Auto-logs in after successful registration

---

#### Run Endpoints

**`GET /api/runs`**
- Scans `outputs/` for `run_*` folders
- Returns list of `RunSummary` dicts sorted newest-first
- Each summary: `{run_id, chapter, subject, class_level, timestamp, scene_count, image_count, has_audio, has_ppt}`

**`GET /api/runs/latest`**
- Returns the single most recent `RunSummary`
- Used by `LatestRunButton` to navigate directly to newest content

**`GET /api/runs/{run_id}`**
- Full run data: config + learning_steps + all scenes + audio manifest
- Scene loading tries multiple fallback paths:
  1. `parsed/scenes_full.json` (preferred — single merged file)
  2. `parsed/scenes_LS1.json`, `parsed/scenes_LS2.json`, ... (per-LS files)
  3. Individual `scenes/LS1/LS1_S1.json` files (fallback)
- Injects `image_url` and audio URLs into each scene dict

---

#### Avatar Endpoints

**`GET /api/avatar/{username}`** → Returns avatar JSON for that user  
**`POST /api/avatar/generate`** → Triggers PuLID avatar generation in background  
Avatars stored at: `data/avatars/{username}/avatar.json` + `base_face.png`

---

#### Static Files

```
GET /static/{run_id}/images/LS1/LS1_S1.png  → serves image file
GET /static/{run_id}/audio/LS1/LS1_S1/combined.mp3  → serves audio
GET /static/avatars/{username}/base_face.png  → serves avatar image
```

---

#### Helper Functions

- `get_run_folders()` → sorted `list[Path]` of all run dirs
- `load_json(path)` → `dict | None` (never crashes)
- `load_scenes_for_run(run_folder)` → `dict[str, list[dict]]` (tries all fallback paths)
- `run_summary(run_folder)` → `RunSummary` dict

---

## 10. Layer 7 — Frontend (Next.js)

**Stack:** Next.js 14, React 18, TypeScript, Tailwind CSS 3.3, Material Design 3 color system

---

### `frontend/app/page.tsx` — Login

- Username + password form
- Dev credentials shown: `admin / academy123`
- Calls `POST /api/auth/login`
- On success: saves user object to `localStorage["academy_user"]`, redirects to `/dashboard`

---

### `frontend/app/register/page.tsx` — Registration

3-step wizard:
1. **Account:** full name, username, email, password, confirm password (min 6 chars, match validation)
2. **Upload photos:** drag-and-drop or file picker (for avatar generation)
3. **Generate avatar:** triggers PuLID avatar generation

On success: auto-login → redirect to `/avatar`

---

### `frontend/app/dashboard/page.tsx` — Dashboard

- Fetches `GET /api/runs` on mount
- Grid of run cards, each showing: chapter thumbnail, chapter name, subject, class, timestamp, scene count, badges (Audio, PPT)
- Search bar filters by chapter name, subject, or run ID
- Left sidebar: profile card with avatar, navigation items, progress widget
- Click any card → navigate to `/player/{run_id}`
- `LatestRunButton` floats bottom-right → one click to newest run

---

### `frontend/app/player/[runId]/page.tsx` — Player

The most complex frontend component. Full-screen scene viewer.

**On load:**
1. Fetch `GET /api/runs/{runId}`
2. Flatten `{LS1: [scenes], LS2: [scenes]}` into 1D array `allScenes[]`
3. Preload first image + next image

**Image display:**
- `<img src={image_url}>` for current scene
- Preloads next scene's image in background `<img style="display:none">`
- On scene change: instant swap (image was already loaded) → no visible flash
- Ken Burns zoom animation on each new scene (CSS keyframe, 6s, auto-resets on scene change)

**Audio playback:**
- If `combined.mp3` exists: plays full combined audio for scene duration
- If no combined: plays `narrator.mp3` first, then queues `dialogue_*.mp3` in order based on `start_ms` timing
- Audio level slider controls volume
- Toggle button: mute/unmute

**Dialogue overlays:**
- If `image_mode="overlay"`: renders `DialogueBubble` components on top of image
- If `image_mode="dialogue"`: no overlay (dialogue is in the image itself)
- Bubbles timed to show/hide based on audio `start_ms` + `duration_ms`

**Keyboard shortcuts:**
| Key | Action |
|---|---|
| `→` or `l` | Next scene |
| `←` or `j` | Previous scene |
| `Space` | Pause / resume audio |
| `Esc` | Back to dashboard |

**Right sidebar:**
- Learning step list with expand/collapse
- Scene list within current LS (scroll-synced)
- Progress bar (% of total scenes)
- Audio visualization

---

### `frontend/app/profile/page.tsx` — Profile

- Shows avatar (`base_face.png` or expression variants)
- Expression tabs: neutral, happy, sad, surprised, angry
- Stats: missions completed (= total run count), avatar ID, activation date
- Buttons: Enter Academy → `/dashboard`, Edit Avatar → `/avatar/edit`

---

### `frontend/app/avatar/page.tsx` — Avatar Creator

- Multi-step interface for PuLID avatar generation
- Upload 3–5 face photos
- Select character traits (personality type, color scheme)
- Submit → backend generates avatar async
- Shows progress indicator, then displays result

---

### `frontend/hooks/useAuth.ts`

```typescript
interface AuthUser {
  username: string;
  displayName: string;
  email: string;
}

function useAuth(): {
  user: AuthUser | null;
  loading: boolean;
  login: (username: string, password: string) => Promise<boolean>;
  logout: () => void;
}
```

- localStorage key: `"academy_user"`
- `loading=true` on first render while checking localStorage
- `login()` calls `POST /api/auth/login`, stores user on success
- `logout()` clears localStorage, redirects to `/`
- All pages check `user === null && !loading` → redirect to `/`

---

### `frontend/components/LatestRunButton.tsx`

- Floating action button, fixed bottom-right
- On mount: fetches `GET /api/runs/latest`
- Shows run ID as tooltip on hover
- Click → `router.push("/player/{run_id}")`
- Only renders if a run exists

---

## 11. Master Prompts File

### `assets/prompts/MASTER_PROMPTS.txt`

All LLM prompts live here. Zero prompts are hardcoded in Python files. This means:
- Prompt changes require no code changes
- Non-technical team members can edit prompts
- Full prompt audit trail in git

**Format:**
```
## Prompt 0A: Concept Extraction — Section Pass
----
[prompt text with [VARIABLE] placeholders]
----

## Prompt 1: Story Backbone Generation
----
[prompt text]
----
```

**Prompts defined:**

| ID | Stage | Purpose |
|---|---|---|
| `0A` | ConceptAgent | Extract concept titles from PDF sections |
| `0B` | ConceptAgent | Gap detection — find missed concepts |
| `1` | BackboneAgent | Generate story + characters |
| `2` | LearningStepsAgent | Break story into learning steps |
| `3A` | SceneGeneratorAgent | Generate scene plan (12–15 scene IDs + phases) |
| `3B` | SceneGeneratorAgent | Generate full scene JSON |
| `4` | ImagePromptAgent | Generate image generation prompt |

**Placeholders used:**

| Placeholder | Filled by | Used in |
|---|---|---|
| `[CHAPTER_NAME]` | user_inputs | 0A, 0B, 1, 2 |
| `[CONCEPTS]` | Prompt 0 output | 1, 2 |
| `[STORY_BACKBONE]` | Prompt 1 output | 2, 3A, 3B |
| `[CHARACTER_REGISTRY]` | state.character_registry | 3A, 3B, 4 |
| `[LEARNING_STEP_TITLE]` | current LS | 3A, 3B |
| `[LS_CONCEPTS]` | current LS | 3A, 3B |
| `[SCENE_PLAN]` | Prompt 3A output | 3B |
| `[PREVIOUS_SCENE]` | last scene JSON | 3B |
| `[STORY_SUMMARY]` | accumulated summary | 3B, 4 |
| `[IMAGE_MODE]` | user choice | 4 |
| `[SCENE_JSON]` | current scene | 4 |

---

## 12. Libraries & Why Each One Exists

### LLM Orchestration

| Library | Version | Why it's here |
|---|---|---|
| `langchain` | ≥0.1.0 | Abstracts LLM calls — same agent code works with OpenAI, DeepSeek, Anthropic |
| `langgraph` | ≥0.0.20 | Defines the pipeline as a proper DAG with state. Without it, pipeline is just sequential function calls with no branching, retry, or checkpointing |
| `langsmith` | latest | Logs every LLM call (inputs + outputs + latency + cost) to Langsmith dashboard. Critical for debugging prompt quality |
| `langchain-openai` | latest | LangChain integration for OpenAI models |
| `langchain-deepseek` | latest | LangChain integration for DeepSeek via OpenRouter |
| `openai` | ≥1.0.0 | Direct OpenAI SDK — used by ImageGeneratorService for `gpt-image-1.5` (not through LangChain, because image generation uses a different API endpoint) |

### Data & Validation

| Library | Why |
|---|---|
| `pydantic` ≥2.0 | Validates `PipelineState` TypedDict fields at runtime. Catches bugs where a node returns the wrong type for a state field |
| `python-dotenv` | Loads `.env` into `os.environ`. Without this, every API key would need to be an OS env var set manually |

### PDF Processing

| Library | Why |
|---|---|
| `pypdf` ≥3.0 | Extracts text from NCERT chapter PDFs. Handles multi-column layouts and scanned text via built-in OCR fallback |
| `beautifulsoup4` | Parses NCERT website HTML to find the correct PDF download URL. Used only in `pdf_agent.py` fallback path |
| `requests` | HTTP library for downloading PDFs from NCERT and polling fal.ai status endpoints |

### Audio

| Library | Why |
|---|---|
| `boto3` ≥1.34 | AWS SDK — calls Amazon Polly `synthesize_speech()`. Polly was chosen because: (1) neural voices sound natural, (2) SSML support for emotion, (3) per-character voice assignment, (4) cheap at scale |
| `mutagen` ≥1.47 | Reads MP3 metadata — specifically `INFO.length` to get duration in seconds. Used to build the audio timing manifest for the frontend |
| `pydub` ≥0.25 | Merges narrator.mp3 + dialogue files into combined.mp3. Uses ffmpeg under the hood (hence `bin/ffmpeg.exe` in the repo) |

### Presentation

| Library | Why |
|---|---|
| `python-pptx` ≥0.6.23 | Creates `.pptx` files programmatically. Slide dimensions, image placement, text boxes all controlled precisely |

### Image Processing

| Library | Why |
|---|---|
| `pillow` ≥10.0 | PIL fork — used by `dialogue_overlay.py` to composite speech bubbles onto images. Also used to validate downloaded image bytes before saving |

### Web Backend

| Library | Why |
|---|---|
| `fastapi` ≥0.110 | Modern async Python web framework. Auto-generates OpenAPI docs. Chosen over Flask for: async support, type-checked request/response models, built-in file serving |
| `uvicorn` ≥0.29 | ASGI server for FastAPI. Production-grade but also great for `--reload` dev mode |
| `python-multipart` | FastAPI dependency for `multipart/form-data` (file uploads for avatar) |

### Frontend

| Library | Why |
|---|---|
| `Next.js 14` | React meta-framework. File-based routing, server components, `next/image` optimization. Dynamic routes (`[runId]`) for the player page |
| `React 18` | UI library. Used for component composition and hooks |
| `TypeScript` | Type safety across all frontend code. Catches mismatched API response shapes at compile time |
| `Tailwind CSS 3.3` | Utility CSS. Entire UI built with utility classes — no separate CSS files for components |
| `Playwright` | Browser automation — used for e2e testing and the `frontend/.stitch/` design exploration files |

---

## 13. Design Patterns

### 1. Character Registry Injection

**Problem:** Image models don't maintain visual memory between calls. Scene 1 generates Maya with blue hair; Scene 10 generates her with black hair.

**Solution:** Extract the `characters` array from Prompt 1 output once, store as `state.character_registry`. Serialize to string and inject as `[CHARACTER_REGISTRY]` into every subsequent prompt (3A, 3B, 4). The image model sees "Maya: black shoulder-length hair, amber eyes, navy tracksuit, 165cm" on every single call.

### 2. Story Summary Accumulation

**Problem:** Prompt 3B generates each scene independently. Scene 10's dialogue might contradict what Scene 3 established.

**Solution:** After each `generate_scenes` node call, append a 1–2 line summary to `state.story_summary`. Each new 3B call receives the full accumulated summary as `[STORY_SUMMARY]`. The LLM has continuity context.

### 3. Art Style Anchor

**Problem:** Image generation models can drift style between calls (especially on long runs).

**Solution:** A fixed `GLOBAL_VISUAL_STYLE` string is appended to every Prompt 4 output before calling the image model. This string defines art style, line weight, color temperature, background complexity, and character proportion rules. Never changes within a run.

### 4. Two-Level Logging

**Problem:** Pipeline generates hundreds of log lines. Verbose output overwhelms users; silent output hides bugs.

**Solution:** `log()` (always shown) vs `debug()` (verbose only), toggled by `set_verbose()`. User chooses verbosity interactively at startup.

### 5. Fallback Model Chain

**Problem:** fal.ai models return 5xx errors occasionally due to queue overload.

**Solution:** After 3 consecutive 5xx errors, `ImageGeneratorService` automatically switches to the fallback model. Error is logged but execution continues. Prevents a single flaky API from halting a 2-hour pipeline run.

### 6. Output Manager as Single I/O Layer

**Problem:** Multiple agents and services need to save files. If each does its own path logic, folder structure becomes inconsistent.

**Solution:** All file I/O goes through `ModelOutputManager`. It owns the canonical path for every artifact type. No agent or service constructs paths independently.

### 7. Prompt-as-Config (MASTER_PROMPTS.txt)

**Problem:** Prompts scattered across agent files are hard to audit, compare, and iterate.

**Solution:** Single file, section delimiters, `[PLACEHOLDER]` convention. The file is the spec for what the LLM is being asked to do. `PromptBuilder` is a dumb interpolation engine. Prompts can be improved without touching Python.

---

## 14. Data Structures

### Scene JSON (canonical format)

```json
{
  "scene_id": "LS1_S3",
  "phase": "DISCOVERY",
  "setting": "Stadium corridor, buzzing fluorescent lights. A whiteboard with numbers.",
  "characters": [
    {"character_id": "maya", "position": "left", "emotion": "curious"},
    {"character_id": "leo", "position": "right", "emotion": "skeptical"}
  ],
  "character_dialogues": [
    {
      "character_id": "maya",
      "dialogue": "Every gap is the same. Look — 3, then 3, then 3.",
      "emotion": "curious",
      "audio_text": "Every gap is the same. Look. Three, then three, then three."
    }
  ],
  "narrator_audio_text": "Maya erased the board and started again. This time she wrote only the differences.",
  "learning_moment": "Recognizing the constant difference in an arithmetic sequence",
  "concept_taught": "common difference",
  "visual_setting": "Close-up on whiteboard: 2, 5, 8, 11 with arrows showing +3 gaps"
}
```

### Character Registry Entry

```json
{
  "character_id": "maya",
  "name": "Maya",
  "role": "protagonist",
  "personality": "analytical, impatient, driven",
  "visual_description": "Black shoulder-length hair with a single red streak, amber eyes, medium brown skin, navy tracksuit with white stripe, 165cm, always has a pencil behind her ear",
  "gender": "female",
  "voice_id": "Ivy"
}
```

### Run Config (inputs/config.json)

```json
{
  "run_id": "run_20250331_120000",
  "chapter_name": "Arithmetic Progressions",
  "chapter_number": 5,
  "class_level": "Grade 10",
  "subject": "Mathematics",
  "medium": "English",
  "image_model": "gpt-image-1.5",
  "image_mode": "dialogue",
  "generate_images": true,
  "generate_audio": true,
  "text_model": "deepseek",
  "pdf_source": "local",
  "started_at": "2025-03-31T12:00:00",
  "completed_at": "2025-03-31T14:22:33",
  "ls_count": 12,
  "scene_count": 156,
  "image_count": 156,
  "audio_count": 156
}
```

---

## 15. Environment Variables

All stored in `.env` at project root. Never committed to git.

| Variable | Used by | Purpose |
|---|---|---|
| `OPENAI_API_KEY` | `image_generator.py`, `llm_client.py` | OpenAI image generation + GPT fallback |
| `OPENROUTER_API_KEY` | `llm_client.py` | DeepSeek text generation via OpenRouter |
| `DEEPSEEK_API_KEY` | `llm_client.py` | Direct DeepSeek API (alternative) |
| `FAL_KEY` | `image_generator.py` | fal.ai Flux 2 Pro + Juggernaut image generation |
| `AWS_ACCESS_KEY_ID` | `audio_generator.py` | Amazon Polly TTS access |
| `AWS_SECRET_ACCESS_KEY` | `audio_generator.py` | Amazon Polly TTS secret |
| `AWS_REGION` | `audio_generator.py` | Polly region (e.g. `us-east-1`) |
| `LANGSMITH_API_KEY` | `pipeline_graph.py` | LangSmith tracing (optional) |
| `LANGSMITH_PROJECT` | `pipeline_graph.py` | LangSmith project name (optional) |
| `FIRECRAWL_API_KEY` | `pdf_agent.py` | Web scraping fallback for PDF download |
| `STITCH_API_KEY` | frontend tools | Stitch design tool API |

---

## 16. Critical Rules & Guardrails

These are rules enforced via prompts that determine output quality. Breaking them produces bad educational content.

### Character Rules
- Every character must have: hair color+style, eye color, skin tone, outfit colors, height, 1 distinctive feature
- Voice IDs must be from approved palette. No two characters share a voice
- Narrator is always Gregory — never any other voice
- Visual descriptions are injected into every image prompt to prevent drift

### Scene Rules
- HOOK (S1): Zero concepts, zero explanations. Environment only. End with a question or unsettling detail
- SETUP (S2): Characters enter but NO concept definitions. Plain language observation only
- Concepts are only named formally starting at DISCOVERY phase
- Every concept listed in `[LS_CONCEPTS]` must be spoken aloud in dialogue by the end of the LS
- 2–3 failed attempts required before breakthrough (cognitive struggle)
- Dialogue must feel natural: hesitations, half-thoughts, interruptions
- No two consecutive scenes with the same phase
- First 30–40% of scenes must NOT resolve or explain — maintain tension

### Image Rules
- `GLOBAL_VISUAL_STYLE` appended to every image prompt without exception
- Character registry injected into every Prompt 4 call
- Fallback model used on persistent API errors (never halt pipeline)

### Audio Rules
- Gregory for narrator always
- Emotion SSML applied per voice type (not generically)
- `amazon:emotion` only for Matthew; `prosody` for Kevin/Ivy
- Neural voices don't support pitch in prosody — strip pitch tags for Kevin/Ivy narrator
- Always merge into combined.mp3 even if only narrator exists

---

## 17. Error Handling Strategy

| Failure | Recovery |
|---|---|
| PDF not found locally | Scrape NCERT website, retry 3× with backoff |
| LLM returns malformed JSON | `safe_parse` with 7 strategies; retry with fix prompt if all fail |
| Image generation 5xx error | Retry 3×; switch to fallback model; save placeholder if exhausted |
| Audio synthesis failure | Skip that character's line; log warning; continue |
| Missing scene image in PPT | Draw grey placeholder rectangle with file path text |
| Unfilled prompt placeholder | Raise ValueError immediately — never send partial prompts to LLM |
| fal.ai job timeout | Poll for up to 5 minutes; cancel and fallback if not complete |

---

## 18. Debug & Test Modes

### `DEBUG_MODE` (`pipeline_graph.py`)

```python
DEBUG_MODE = True
DEBUG_MAX_LS = 1
```

- Limits pipeline to 1 learning step
- All scenes within that LS still generated (not scene-limited)
- Saves intermediate debug JSONs to `outputs/debug_run/`
- Enables fast iteration during prompt development

### `TEST_MODE` (`brain/main.py`)

```python
TEST_MODE = True
```

- Shows interactive menus: topic selection, LS selection, single vs all scenes
- User can select image model, audio on/off, verbosity
- Lets developer test specific chapters/LS without running the full pipeline

### Verbose Logging

- User is asked at startup: "Show verbose output? (y/n)"
- `set_verbose(True)` → all `debug()` calls print
- `set_verbose(False)` → only `log()` milestone calls print

---

## 19. Deployment

### Running the Full Stack

```bash
# 1. Activate Python virtual environment
source venv/Scripts/activate        # Windows bash
# venv\Scripts\activate.bat         # Windows cmd

# 2. Start the backend API server
uvicorn backend.server:app --port 8000 --reload

# 3. Start the frontend (separate terminal)
cd frontend
npm install
npm run dev
# → http://localhost:3000

# 4. Run the pipeline (separate terminal)
cd brain
python main.py
```

### Running a Pipeline with Debug Mode

```bash
# In brain/pipeline/pipeline_graph.py, set:
DEBUG_MODE = True
DEBUG_MAX_LS = 1

python brain/main.py
# → Runs only LS1, fast for testing
```

### Regenerating Images for an Existing Run

```bash
python brain/services/regenerate_images.py \
  --run-id run_20250331_120000 \
  --model fal-flux2pro
```

### Environment Setup

All API keys in `.env` at project root:
```
OPENAI_API_KEY=sk-proj-...
OPENROUTER_API_KEY=sk-or-...
FAL_KEY=...
AWS_ACCESS_KEY_ID=...
AWS_SECRET_ACCESS_KEY=...
AWS_REGION=us-east-1
LANGSMITH_API_KEY=...
LANGSMITH_PROJECT=storytelling-pipeline
```
