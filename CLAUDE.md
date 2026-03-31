# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

# Agent Instructions

You're working inside the **WAT framework** (Workflows, Agents, Tools). This architecture separates concerns so that probabilistic AI handles reasoning while deterministic code handles execution. That separation is what makes this system reliable.

## The WAT Architecture

**Layer 1: Workflows (The Instructions)**
- Markdown SOPs stored in `workflows/`
- Each workflow defines the objective, required inputs, which tools to use, expected outputs, and how to handle edge cases
- Written in plain language, the same way you'd brief someone on your team

**Layer 2: Agents (The Decision-Maker)**
- This is your role. You're responsible for intelligent coordination.
- Read the relevant workflow, run tools in the correct sequence, handle failures gracefully, and ask clarifying questions when needed
- You connect intent to execution without trying to do everything yourself
- Example: If you need to pull data from a website, don't attempt it directly. Read `workflows/scrape_website.md`, figure out the required inputs, then execute `tools/scrape_single_site.py`

**Layer 3: Tools (The Execution)**
- Python scripts in `tools/` that do the actual work
- API calls, data transformations, file operations, database queries
- Credentials and API keys are stored in `.env`
- These scripts are consistent, testable, and fast

**Why this matters:** When AI tries to handle every step directly, accuracy drops fast. If each step is 90% accurate, you're down to 59% success after just five steps. By offloading execution to deterministic scripts, you stay focused on orchestration and decision-making where you excel.

## How to Operate

**1. Look for existing tools first**
Before building anything new, check `tools/` based on what your workflow requires. Only create new scripts when nothing exists for that task.

**2. Learn and adapt when things fail**
When you hit an error:
- Read the full error message and trace
- Fix the script and retest (if it uses paid API calls or credits, check with me before running again)
- Document what you learned in the workflow (rate limits, timing quirks, unexpected behavior)
- Example: You get rate-limited on an API, so you dig into the docs, discover a batch endpoint, refactor the tool to use it, verify it works, then update the workflow so this never happens again

**3. Keep workflows current**
Workflows should evolve as you learn. When you find better methods, discover constraints, or encounter recurring issues, update the workflow. That said, don't create or overwrite workflows without asking unless I explicitly tell you to. These are your instructions and need to be preserved and refined, not tossed after one use.

## The Self-Improvement Loop

Every failure is a chance to make the system stronger:
1. Identify what broke
2. Fix the tool
3. Verify the fix works
4. Update the workflow with the new approach
5. Move on with a more robust system

## File Structure

**What goes where:**
- **Deliverables**: Final outputs go to cloud services (Google Sheets, Slides, etc.) where I can access them directly
- **Intermediates**: Temporary processing files that can be regenerated

**Directory layout:**
```
assets/
  knowledge/      # Source PDFs (NCERT chapters)
  prompts/        # MASTER_PROMPTS.txt — all LLM prompts in one file
backend/          # FastAPI server (server.py) for React frontend
brain/
  agents/         # Individual pipeline step agents
  pipeline/       # LangGraph orchestration (pipeline_graph.py + state/)
  prompt_engine/  # Legacy prompt core (llm_client, state_manager, etc.)
  services/       # image_generator, audio_generator, ppt_generator, prompt_builder, dialogue_overlay
core/             # (legacy) logger, llm_client, prompt_loader, state_manager, pipeline_controller
frontend/         # Next.js React app for viewing pipeline runs
outputs/          # Run outputs (run_{YYYYMMDD_HHMMSS}/ per execution)
tools/            # Deterministic Python execution scripts
utils/            # json_utils, model_output_manager, pipeline_logger, image_repository
workflows/        # Markdown SOPs
.env              # API keys — NEVER store secrets anywhere else
```

**Core principle:** Local files are just for processing. Anything I need to see or use lives in cloud services. Everything in `.tmp/` is disposable.

---

## Running the Pipeline

```bash
# Activate venv first
source venv/Scripts/activate  # Windows bash
# or: venv\Scripts\activate.bat

# Run the interactive pipeline (TEST_MODE=True by default in brain/main.py)
cd brain && python main.py

# Run the LS1-only pipeline variant
python run_ls1_pipeline.py

# Start the backend API server (serves outputs to the React frontend)
uvicorn backend.server:app --port 8000 --reload

# Start the frontend
cd frontend && npm install && npm run dev
```

**Required environment variables in `.env`:**
- `OPENAI_API_KEY` — for GPT-image-1.5 image generation
- `FAL_KEY` — for fal.ai image models (Flux 2 Pro, Juggernaut)
- `DEEPSEEK_API_KEY` — for text generation (hardcoded as `text_model = "deepseek"`)
- AWS credentials — for Amazon Polly TTS audio generation

---

## Architecture: How the Pipeline Works

The pipeline is a **5-prompt sequential LangGraph graph** defined in [brain/pipeline/pipeline_graph.py](brain/pipeline/pipeline_graph.py). Each run creates a timestamped folder under `outputs/run_{YYYYMMDD_HHMMSS}/`.

**Pipeline stages (in order):**
1. **Prompt 0 — Concept Inventory**: Extracts key concepts from the chapter PDF
2. **Prompt 1 — Story Backbone**: Generates narrative story structure possibilities
3. **Prompt 2 — Learning Steps**: Decomposes chapter into ordered learning steps (LS1, LS2, ...)
4. **Prompt 3A/3B — Scene Generation**: For each learning step, generates a scene plan then individual scenes
5. **Prompt 4 — Image Generation**: Generates images per scene using the selected image model

**Key files to understand the pipeline:**
- [brain/pipeline/pipeline_graph.py](brain/pipeline/pipeline_graph.py) — LangGraph nodes, edges, and the `.run()` method; also holds `DEBUG_MODE` and `DEBUG_MAX_LS` flags
- [brain/pipeline/state/pipeline_state.py](brain/pipeline/state/pipeline_state.py) — `PipelineState` TypedDict that flows through LangGraph
- [brain/services/prompt_builder.py](brain/services/prompt_builder.py) — Loads `assets/prompts/MASTER_PROMPTS.txt`, parses sections by `## Prompt N:` headers, fills `[PLACEHOLDER]` variables
- [utils/model_output_manager.py](utils/model_output_manager.py) — All file I/O for run folders; `create_run_folder()`, `save_scenes()`, `save_image()`, etc.
- [utils/json_utils.py](utils/json_utils.py) — `safe_parse()` and `safe_parse_with_retry()` for LLM JSON output cleaning
- [utils/pipeline_logger.py](utils/pipeline_logger.py) — `log()` / `debug()` with verbosity control via `set_verbose()`

**Image generation models** (selected interactively at runtime):
- `gpt-image-1.5` — OpenAI (default)
- `fal-flux2pro` — fal.ai Flux 2 Pro
- `fal-juggernaut` — fal.ai Juggernaut

**Image modes:**
- `dialogue` — AI renders character dialogue text inside the scene image
- `overlay` — Speech bubbles are composited onto the image after generation (via [brain/services/dialogue_overlay.py](brain/services/dialogue_overlay.py))

**Output folder structure per run:**
```
outputs/run_{timestamp}/
  inputs/config.json          # chapter metadata, model choices
  prompts/                    # injected prompts sent to LLM (prompt0.txt ... prompt4_LS1_S1.txt)
  raw_outputs/                # raw LLM responses before JSON parsing
  parsed/                     # concept_inventory.json, story_backbone.json, learning_steps.json, scenes_*.json
  scenes/LS1/LS1_S1.json      # individual scene JSON files
  images/LS1/LS1_S1.png       # generated scene images
  audio/LS1/LS1_S1/           # Polly TTS audio per scene
  ppt/lesson.pptx             # final PowerPoint output
  summary.json                # run stats
```

---

## Modifying Prompts

All LLM prompts live in a single file: [assets/prompts/MASTER_PROMPTS.txt](assets/prompts/MASTER_PROMPTS.txt).

Sections are delimited by `----` and identified by headers like `## Prompt 3B: Scene Generation`. Placeholders use `[VARIABLE_NAME]` syntax. `PromptBuilder` in [brain/services/prompt_builder.py](brain/services/prompt_builder.py) parses and fills these at runtime.

---

## Controlling Debug/Test Behavior

- `TEST_MODE = True` at the top of [brain/main.py](brain/main.py) — enables interactive topic/LS/scene selection menus
- `DEBUG_MODE = True` and `DEBUG_MAX_LS = 1` at the top of [brain/pipeline/pipeline_graph.py](brain/pipeline/pipeline_graph.py) — limits pipeline to 1 learning step and saves intermediate debug JSONs to `outputs/debug_run/`
- Verbosity is set interactively via `ask_verbosity()` which calls `set_verbose()` in `utils/pipeline_logger.py`

---

## Backend API (FastAPI)

The [backend/server.py](backend/server.py) serves run data to the React frontend:
- `GET /api/runs` — list all available runs
- `GET /api/runs/{run_id}` — metadata + scenes + audio manifest
- `GET /static/{run_id}/images/...` — serve image files
- `GET /static/{run_id}/audio/...` — serve audio files

CORS is configured for `localhost:3000`.

## Bottom Line

You sit between what I want (workflows) and what actually gets done (tools). Your job is to read instructions, make smart decisions, call the right tools, recover from errors, and keep improving the system as you go.

Stay pragmatic. Stay reliable. Keep learning.
