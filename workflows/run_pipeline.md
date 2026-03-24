# Workflow: Run Storytelling Pipeline

## Objective
Generate a complete storytelling presentation (scenes + images + PPT) from an NCERT chapter PDF.

## Inputs Required
- `class_level` — e.g., "10"
- `subject` — e.g., "Physics", "Mathematics"
- `chapter_number` — e.g., "11"
- `chapter_title` — e.g., "Electricity"
- `medium` — "English" or "Hindi"
- `pdf_path` — Path to chapter PDF (from `assets/knowledge/`) or downloaded
- `text_model` — Currently hardcoded to "deepseek"
- `image_model` — "gpt-image-1.5", "fal-flux2pro", or "fal-juggernaut"
- `image_mode` — "dialogue" (text inside image) or "overlay" (speech bubbles after)
- `generation_mode` — "full" (all learning steps) or "ls1" (fast preview)
- `scene_generation_scope` — "single" (one scene, for testing) or "multiple" (all scenes)

## Pipeline Steps

### Step 0 — PDF Retrieval
- **Tool**: `brain/agents/pdf_agent.py`
- Check `assets/knowledge/` for a pre-loaded PDF first
- If not found, download from NCERT using the PDF agent
- Output: `pdf_path`

### Step 1 — Concept Inventory (Prompt 0)
- **Tool**: `brain/agents/concept_agent.py`
- Extracts key concepts from the chapter PDF
- Output: `concept_inventory.json`

### Step 2 — Story Backbone (Prompt 1)
- **Tool**: `brain/agents/backbone_agent.py`
- Generates story backbone possibilities linking concepts to a narrative
- Output: `story_backbone.json`

### Step 3 — Learning Steps (Prompt 2)
- **Tool**: `brain/agents/learning_steps_agent.py`
- Decomposes chapter into ordered learning steps
- Output: `learning_steps.json`

### Step 4 — Scene Generation (Prompt 3)
- **Tool**: `brain/agents/scene_generator_agent.py`
- Generates scenes for each learning step (one or all depending on `scene_generation_scope`)
- Output: `scenes_LS{n}.json` and `scenes_full.json`

### Step 5 — Image Prompts (Prompt 4)
- **Tool**: `brain/agents/image_prompt_agent.py`
- Generates image prompts for each scene
- Output: `image_prompts.json`

### Step 6 — Image Generation
- **Tool**: `brain/services/image_generator.py`
- Calls OpenAI or fal.ai based on `image_model`
- Output: PNG files in `outputs/{run_folder}/images/`

### Step 7 — PPT Generation
- **Tool**: `brain/services/ppt_generator.py`
- Assembles scenes and images into a PowerPoint
- Output: `.pptx` file in `outputs/{run_folder}/`

## Entry Point
```bash
cd brain
python main.py
```

## Output Structure
```
outputs/{class}_{subject}_{chapter}/
├── images/
├── scenes_full.json
├── learning_steps.json
├── concept_inventory.json
├── story_backbone.json
├── image_prompts.json
└── presentation.pptx
```

## Edge Cases & Known Issues
- **PDF not found**: Pipeline proceeds without PDF — quality degrades significantly. Always pre-load PDFs to `assets/knowledge/`.
- **Rate limits**: DeepSeek and fal.ai have rate limits. On 429 errors, wait 60s before retrying. Do not retry automatically.
- **JSON parse failures**: LLM may return malformed JSON. The `utils/json_utils.py` handles repair — check logs if output is empty.
- **Image generation cost**: Each image call costs credits. Always confirm with user before re-running image generation steps.
- **`scene_generation_scope="single"`**: Only generates scenes for the first learning step. Use for fast validation before full runs.

## Environment Variables (`.env`)
```
OPENAI_API_KEY=...
DEEPSEEK_API_KEY=...
FAL_KEY=...
LANGSMITH_API_KEY=...
LANGCHAIN_TRACING_V2=true
LANGCHAIN_PROJECT=...
```
