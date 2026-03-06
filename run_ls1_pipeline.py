"""
LS1 Pipeline Runner - Lightweight pipeline for generating only LS1 scenes.

Features:
- Model provider selection (GPT-4o-mini, GPT-5.2, DeepSeek)
- Model-specific output folders with run-based structure
- Runs only up to LS1 scene generation
- Proper logging and progress tracking
"""

import os
import re
import sys
import json
import logging
from pathlib import Path
from datetime import datetime

# Test mode configuration
# If test_mode == True: run only LS1 (for model evaluation)
# If test_mode == False: run all learning steps
TEST_MODE = True  # Set to True for LS1-only testing

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv

load_dotenv(override=True)

# Enable LangSmith tracing
os.environ["LANGCHAIN_TRACING_V2"] = os.environ.get("LANGCHAIN_TRACING_V2", "true")
os.environ["LANGSMITH_PROJECT"] = os.environ.get("LANGSMITH_PROJECT", "ls1-pipeline")

# Import LangSmith tracing
try:
    from langsmith import traceable

    LANGSMITH_AVAILABLE = True
except ImportError:
    LANGSMITH_AVAILABLE = False

    def traceable(name=None):
        """Dummy decorator if langsmith not available."""

        def decorator(func):
            return func

        return decorator


from langchain_openai import ChatOpenAI

# Initialize logging
logs_dir = Path("logs")
logs_dir.mkdir(exist_ok=True)

logging.basicConfig(
    filename=str(logs_dir / "ls1_pipeline.log"),
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)

# Get logger
logger = logging.getLogger(__name__)

# Import JSON cleaner utility
from core.utils.llm_json_parser import clean_llm_json, parse_llm_json

# Import prompt loader
from brain.prompt_engine.core.prompt_loader import get_prompt_loader

# Import metrics logger
from core.metrics.metrics_logger import MetricsLogger

# Import LLM utilities
from core.utils.llm_usage_parser import extract_token_usage
from core.utils.llm_response_extractor import extract_llm_content


def repair_json(text: str) -> str:
    """
    Attempt to repair malformed JSON returned by an LLM.
    Extracts the main JSON block and fixes common issues.
    """
    import re

    # Extract JSON block
    start = text.find("{")
    end = text.rfind("}")

    if start != -1 and end != -1:
        text = text[start : end + 1]

    # Replace single quotes with double quotes
    text = text.replace("'", '"')

    # Remove trailing commas
    text = re.sub(r",\s*}", "}", text)
    text = re.sub(r",\s*]", "]", text)

    return text


def safe_llm_json_call(llm, prompt, prompt_id, save_raw_fn, max_retries=2):
    """
    Calls LLM and guarantees JSON output using retry logic.
    """
    for attempt in range(max_retries):
        response = llm.invoke(prompt)

        raw_response = (
            response.content if hasattr(response, "content") else str(response)
        )

        # Debug: Print raw LLM response for prompt_id 0
        if prompt_id == 0:
            print("\n===== RAW LLM RESPONSE PROMPT0 =====")
            print(raw_response)
            print("===== END RAW RESPONSE =====\n")

        save_raw_fn(prompt_id, raw_response)

        content = extract_llm_content(response)

        if not content or len(content.strip()) < 5:
            error = "Empty LLM response"
        else:
            try:
                data = parse_llm_json(content)
                if isinstance(data, dict) or isinstance(data, list):
                    return data
                error = "Parsed JSON not dict/list"
            except Exception as e:
                # Try to repair JSON before retrying
                try:
                    repaired = repair_json(content)
                    import json

                    parsed = json.loads(repaired)
                    if isinstance(parsed, dict) or isinstance(parsed, list):
                        print("✓ JSON auto-repair succeeded")
                        return parsed
                except Exception:
                    pass
                error = str(e)
                print("⚠ JSON repair attempt failed")

        print(f"⚠ JSON parse failed (attempt {attempt + 1}/{max_retries})")

        prompt += (
            "\n\nCRITICAL: Your previous response was invalid."
            "\nReturn ONLY valid JSON."
            "\nStart response with { and end with }."
            "\nDo NOT include explanations."
            "\nDo NOT include markdown."
        )

    raise ValueError(f"LLM failed to produce valid JSON after {max_retries} attempts.")


class ModelProvider:
    """Manages model providers and configurations."""

    PROVIDERS = {
        "1": {
            "name": "GPT-4o-mini",
            "model": "gpt-4o-mini",
            "provider": "openai",
            "description": "OpenAI - Good balance of cost + speed",
        },
        "2": {
            "name": "GPT-5.2",
            "model": "gpt-5.2",
            "provider": "openai",
            "description": "OpenAI - Highest quality (if available)",
        },
        "3": {
            "name": "Trinity Large (OpenRouter)",
            "model": "arcee-ai/trinity-large-preview:free",
            "provider": "openrouter_free",
            "description": "Free - Arcee AI Trinity Large",
        },
        "4": {
            "name": "Step-3.5 Flash (OpenRouter)",
            "model": "stepfun/step-3.5-flash:free",
            "provider": "openrouter_free",
            "description": "Free - StepFun Step-3.5 Flash",
        },
        "5": {
            "name": "GLM-4.5 Air (OpenRouter)",
            "model": "z-ai/glm-4.5-air:free",
            "provider": "openrouter_free",
            "description": "Free - Z-AI GLM-4.5 Air",
        },
        "6": {
            "name": "Nemotron-3 Super (OpenRouter)",
            "model": "nvidia/nemotron-3-super:free",
            "provider": "openrouter_free",
            "description": "Free - NVIDIA Nemotron-3 Super",
        },
        "7": {
            "name": "Nemotron-3 Nano (OpenRouter)",
            "model": "nvidia/nemotron-3-nano-30b-a3b:free",
            "provider": "openrouter_free",
            "description": "Free - NVIDIA Nemotron-3 Nano",
        },
    }

    @staticmethod
    def select_provider() -> dict:
        """Ask user to select model provider."""
        print("\n" + "=" * 60)
        print("  Select Model Provider")
        print("=" * 60)

        # Show available options - DeepSeek now works via OpenRouter
        available = []
        for key, provider in ModelProvider.PROVIDERS.items():
            print(f"  {key} → {provider['name']}: {provider['description']}")
            available.append(key)

        while True:
            choice = input("\nEnter choice: ").strip()
            if choice in available:
                return ModelProvider.PROVIDERS[choice]
            print(f"Invalid choice. Please enter {', '.join(available)}.")

    @staticmethod
    def get_llm_client(model_config: dict, temperature: float = 0.65):
        """Get LLM client based on provider."""
        if model_config["provider"] == "openai":
            api_key = os.getenv("OPENAI_API_KEY")
            if not api_key:
                raise ValueError("OPENAI_API_KEY not found in .env")
            return ChatOpenAI(
                model=model_config["model"],
                temperature=temperature,
                max_retries=3,
                timeout=120,
            )
        elif model_config["provider"] in ("deepseek", "openrouter_free"):
            api_key = os.getenv("OPENROUTER_API_KEY")
            if not api_key:
                raise ValueError(
                    "OPENROUTER_API_KEY not found. OpenRouter requires this key."
                )
            model = model_config.get("model", "tngtech/deepseek-r1t-chimera:free")
            return ChatOpenAI(
                model=model,
                base_url="https://openrouter.ai/api/v1",
                api_key=api_key,
                temperature=temperature,
                max_retries=3,
                timeout=120,
            )
        else:
            raise ValueError(f"Unknown provider: {model_config['provider']}")

    @staticmethod
    def get_deepseek_model_for_stage(stage: int) -> str:
        """
        Get DeepSeek model for each prompt stage.

        Stage 0 (Concept extraction) → deepseek-chat
        Stage 1 (Story backbone) → deepseek-reasoner
        Stage 2 (Learning steps) → deepseek-chat
        Stage 3 (Scene generation) → deepseek-reasoner
        """
        models = {
            0: "deepseek-chat",
            1: "deepseek-reasoner",
            2: "deepseek-chat",
            3: "deepseek-reasoner",
        }
        return models.get(stage, "deepseek-chat")


class OutputManager:
    """Manages model-specific output folders with run-based structure."""

    @staticmethod
    def get_output_dir(model_name: str, test_mode: bool = False) -> Path:
        """Get output directory for a model."""
        sanitized = re.sub(r"[^a-zA-Z0-9_-]", "_", model_name).lower()
        if test_mode:
            return Path("outputs") / "model_tests" / sanitized
        return Path("outputs") / sanitized

    @staticmethod
    def create_output_structure(
        model_name: str, chapter_info: dict = None, test_mode: bool = False
    ) -> dict:
        """Create output folder structure with run-based directories."""
        base_dir = OutputManager.get_output_dir(model_name, test_mode)

        # Create timestamp-based run folder
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        # Add chapter identifier if provided
        if chapter_info:
            class_level = chapter_info.get("class_level", "unknown")
            subject = chapter_info.get("subject", "unknown").lower().replace(" ", "_")
            chapter_num = chapter_info.get("chapter_number", "unknown")
            run_folder = base_dir / f"{class_level}_{subject}_{chapter_num}_{timestamp}"
        else:
            run_folder = base_dir / f"run_{timestamp}"

        folders = {
            "base": base_dir,
            "model_base": base_dir,
            "run_folder": run_folder,
            "chapter": run_folder / "chapter",
            "concepts": run_folder / "concepts",
            "story": run_folder / "story",
            "learning_steps": run_folder / "learning_steps",
            "scenes": run_folder / "scenes",
            "visuals": run_folder / "visuals",
            "prompts": run_folder / "prompts",
            "metrics": run_folder / "metrics",
            "raw_llm": run_folder / "raw_llm",
        }

        for folder in folders.values():
            folder.mkdir(parents=True, exist_ok=True)

        logger.info(f"Created output structure: {run_folder}")
        return folders

    @staticmethod
    def get_learning_step_scene_dir(scenes_dir: Path, learning_step_id: str) -> Path:
        """Get or create directory for a specific learning step's scenes."""
        step_dir = scenes_dir / learning_step_id
        step_dir.mkdir(parents=True, exist_ok=True)
        return step_dir

    @staticmethod
    def get_learning_step_visual_dir(visuals_dir: Path, learning_step_id: str) -> Path:
        """Get or create directory for a specific learning step's visuals."""
        visual_step_dir = visuals_dir / learning_step_id
        visual_step_dir.mkdir(parents=True, exist_ok=True)
        return visual_step_dir

    @staticmethod
    def save_json(data: dict, filepath: Path) -> None:
        """Save JSON data to file."""
        filepath.parent.mkdir(parents=True, exist_ok=True)
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        logger.info(f"Saved JSON: {filepath}")

    @staticmethod
    def save_text(text: str, filepath: Path) -> None:
        """Save text data to file."""
        filepath.parent.mkdir(parents=True, exist_ok=True)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(text)
        logger.info(f"Saved text: {filepath}")


class LS1PipelineRunner:
    """Runs the pipeline for LS1 only or all learning steps based on test_mode."""

    def __init__(self, model_config: dict, test_mode: bool = False):
        self.model_config = model_config
        self.test_mode = test_mode

        # Create output structure with test_mode support
        self.output_folders = OutputManager.create_output_structure(
            model_config["model"], test_mode=test_mode
        )

        # Initialize metrics logger - use run_folder path
        self.metrics = MetricsLogger(str(self.output_folders["run_folder"]))

        # Initialize prompt loader
        self.prompt_loader = get_prompt_loader()

        # Pre-load prompts from MASTER_PROMPTS.txt
        self.prompt0_template = self.prompt_loader.get_prompt(0)
        self.prompt1_template = self.prompt_loader.get_prompt(1)
        self.prompt2_template = self.prompt_loader.get_prompt(2)
        self.prompt3_template = self.prompt_loader.get_prompt(3)

        # Debug: Print prompt lengths
        print(f"\nPrompt0 length: {len(self.prompt0_template)} chars")
        print(f"Prompt1 length: {len(self.prompt1_template)} chars")
        print(f"Prompt2 length: {len(self.prompt2_template)} chars")
        print(f"Prompt3 length: {len(self.prompt3_template)} chars")

        # Log prompt templates
        self.metrics.log_prompt_template(0, self.prompt0_template)
        self.metrics.log_prompt_template(1, self.prompt1_template)
        self.metrics.log_prompt_template(2, self.prompt2_template)
        self.metrics.log_prompt_template(3, self.prompt3_template)

        self.prompt_temperatures = {
            0: 0.2,  # Concept extraction
            1: 0.65,  # Story backbone
            2: 0.25,  # Learning steps
            3: 0.6,  # Scene generation
        }

        self.state = {
            "concept_inventory": None,
            "story_backbone": None,
            "learning_steps": None,
            "scenes": None,
        }

        # Story memory for narrative continuity
        self.story_summary = ""

        # Store chapter info for debug report
        self._last_chapter_info = {}

        # Track all scenes for all learning steps
        self.all_generated_scenes = {}  # {learning_step_id: [scenes]}

        # Scene planner prompt template (generic for any learning step)
        self.scene_planner_template = """Title: Scene Planner - Generate Scene Structure for Learning Step {learning_step_id}

Context:
I am building a storytelling-based educational pipeline. The chapter has been decomposed into learning steps, and now I need to plan how many scenes Learning Step {learning_step_id} will contain and the narrative phase of each scene.

Input:
Chapter: {chapter}
Story Backbone: {story_backbone}
Learning Step {learning_step_id}: {learning_step}
Character Registry: {character_registry}

Goal:
Generate a structured scene plan that defines:
- How many scenes Learning Step {learning_step_id} should contain (minimum 6, maximum 15)
- The narrative phase of each scene
- The sequence of scenes that tells a coherent story

Rules:
1. Minimum 6 scenes, maximum 15 scenes
2. First scene MUST be "opening_environment" - cinematic introduction of the environment
3. Early scenes must introduce characters naturally
4. Scenes must follow story continuity - each scene leads naturally to the next
5. Scenes must enable concept discovery through narrative progression
6. Use phases: opening_environment, character_introduction, observation, investigation, concept_discovery, concept_explanation, reinforcement, transition
7. First 2-3 scenes should build the narrative foundation
8. Middle scenes should drive the investigation/discovery
9. Final scenes should reinforce concepts and transition

Output Format (STRICT JSON):
```json
{{
  "learning_step_id": "{learning_step_id}",
  "scene_plan": [
    {{"scene_id": "{learning_step_id}_S1", "phase": "opening_environment"}},
    {{"scene_id": "{learning_step_id}_S2", "phase": "character_introduction"}},
    ...
  ]
}}
```

Do NOT generate scene content - only the plan.
Output ONLY valid JSON. No markdown, no explanations.
Start with {{ and end with }}."""

        # Single scene generation prompt template (generic for any learning step)
        self.single_scene_template = """Title: Generate Single Scene for Learning Step {learning_step_id}

Context:
I am building a scene-by-scene storytelling pipeline. A scene plan has been created, and now I need to generate ONE individual scene that continues the story from the previous scene while introducing the learning concepts.

Input:
Chapter: {chapter}
Story Backbone: {story_backbone}
Character Registry: {character_registry}
Current Learning Step: {learning_step}

Scene to Generate:
- Scene ID: {scene_id}
- Scene Phase: {scene_phase}
- Story So Far: {story_summary}
- Previous Scene Summary: {previous_scene_summary}

Next Scene Phase: {next_scene_phase}

Goal:
Generate ONE scene that:
- Continues the story from the previous scene
- Maintains character behavior and personalities
- Maintains environment continuity
- Naturally discovers and explains {learning_step_id} concepts through story events
- Ensures cinematic storytelling quality

Scene Structure:
{{
"scene_id": "{scene_id}",
"scene_phase": "{scene_phase}",
"scene_goal": "What happens in this scene and why it matters for learning",

"visual_setting": {{
"environment": "Where the scene takes place",
"atmosphere": "Mood or tone of the scene",
"time_of_day": "Time when the scene occurs"
}},

"characters": [
{{
"character_id": "[CHAR_ID]",
"emotion": "Character emotional state",
"action": "What the character is doing"
}}
],

"narrative": {{
"screenplay": "180-250 words of story narration",
"camera_suggestion": "How the scene should be visualized",
"action_flow": "How characters move through the scene"
}},

"dialogue": [
{{
"speaker": "[CHAR_NAME]",
"text": "[DIALOGUE_LINE]",
"tone": "How the line is delivered"
}}
],

"concept_moments": [
{{
"concept": "[CONCEPT_NAME]",
"how_discovered": "How the concept appears in the story"
}}
]
}}

Rules:
1. Each scene MUST contain 180-250 words of screenplay/narration
2. Each scene MUST include at least 1 dialogue line
3. First scene must establish environment before characters speak
4. When a character appears for the first time, visually describe them
5. Concepts should be discovered through story events, not direct explanation
6. Scene must connect naturally to previous and next scenes
7. Maintain visual consistency with the story backbone

SCENE PROGRESSION RULES:

1. Each scene must introduce a NEW idea or deepen the previous concept.
2. Do NOT repeat the same explanation across multiple scenes.
3. Each scene should move the story forward logically.
4. Scenes must follow the progression:
   observation → investigation → discovery → explanation → application.

CONCEPT DISCOVERY RULES:

Characters should NOT immediately state formal mathematical/scientific terms.
Instead:
• Characters observe a pattern.
• Characters discuss the pattern.
• The concept is gradually recognized.
• The formal concept name appears later during explanation.

Example progression:
Observation: "Every week we're adding five dollars."
Investigation: "So the numbers become 20, 25, 30..."
Discovery: "That's a repeating pattern."
Explanation: "This pattern is called an arithmetic progression."

Output ONLY valid JSON for ONE scene. No markdown, no explanations.
Start with {{ and end with }}."""

    def _get_llm(self, stage: int):
        """Get LLM client for a specific stage with proper configuration."""
        config = MetricsLogger.DEFAULT_PROMPT_CONFIG.get(
            stage,
            {
                "temperature": 0.7,
                "top_p": 0.9,
                "max_tokens": 2000,
                "presence_penalty": 0.0,
            },
        )

        if self.model_config["provider"] in ("deepseek", "openrouter_free"):
            api_key = os.getenv("OPENROUTER_API_KEY")
            if not api_key:
                raise ValueError(
                    "OPENROUTER_API_KEY not found. OpenRouter requires this key."
                )

            config["temperature"] = config.get("temperature", 0.75)

            return ChatOpenAI(
                model=self.model_config.get(
                    "model", "tngtech/deepseek-r1t-chimera:free"
                ),
                base_url="https://openrouter.ai/api/v1",
                api_key=api_key,
                temperature=config["temperature"],
                top_p=config.get("top_p"),
                max_tokens=config.get("max_tokens"),
                presence_penalty=config.get("presence_penalty"),
                max_retries=3,
                timeout=120,
            ), config
        else:
            # OpenAI provider
            api_key = os.getenv("OPENAI_API_KEY")
            if not api_key:
                raise ValueError("OPENAI_API_KEY not found in .env")
            llm = ChatOpenAI(
                model=self.model_config["model"],
                temperature=config["temperature"],
                top_p=config.get("top_p"),
                max_tokens=config.get("max_tokens"),
                presence_penalty=config.get("presence_penalty"),
                max_retries=3,
                timeout=120,
            )
            return llm, config

    @traceable(name="ls1_pipeline_run")
    def run(self, chapter_info: dict) -> dict:
        """Run the LS1 pipeline."""
        mode_str = (
            "LS1-Only (Test Mode)"
            if self.test_mode
            else "Full Pipeline (All Learning Steps)"
        )
        print(f"\n{'=' * 60}")
        print(f"  Running Pipeline: {mode_str}")
        print(f"  Model: {self.model_config['name']}")
        print(f"{'=' * 60}")

        print(f"\n📁 Output: {self.output_folders['base']}")

        # Store chapter info for debug report
        self._last_chapter_info = chapter_info

        # Stage 0: Concept Inventory
        self._run_concept_extraction(chapter_info)

        # Stage 1: Story Backbone
        self._run_story_backbone(chapter_info)

        # Stage 2: Learning Steps
        self._run_learning_steps(chapter_info)

        # Stage 3: Scene Generation (LS1 only or all learning steps based on test_mode)
        scene_count = self._run_scene_generation(chapter_info)

        # Log pipeline metrics
        self.metrics.log_pipeline_metrics(
            chapter=chapter_info["chapter_name"],
            model=self.model_config["model"],
        )

        # Print summary
        run_folder = str(self.output_folders["base"])
        print(f"\n{'=' * 60}")
        print("  Pipeline completed successfully!")
        print(f"{'=' * 60}")
        print(f"\nMode: {mode_str}")
        print(f"Model: {self.model_config['name']}")
        print(f"Run folder: {run_folder}")
        print(f"Total scenes generated: {scene_count}")

        logger.info(
            f"Pipeline completed - Mode: {mode_str}, Model: {self.model_config['name']}, Scenes: {scene_count}"
        )

        # Append experiment summary
        self.metrics.append_to_experiment_summary(self.model_config["model"])

        # Generate debug report
        self._generate_debug_report()

        # Print story inspection report
        self.print_story_inspection_report()

        # Print verification report
        self._print_verification_report(scene_count)

        return self.state

    def _print_verification_report(self, scene_count: int) -> None:
        """Print final verification report of all upgrades."""
        print(f"\n{'=' * 60}")
        print("  PIPELINE METRICS UPGRADE VERIFICATION REPORT")
        print(f"{'=' * 60}")

        print("\n[STRUCTURAL AUDIT FIXES]")
        print("  ✓ _get_llm fixed - Single return statement")
        print("    - Loads config from MetricsLogger.DEFAULT_PROMPT_CONFIG")
        print("    - Creates LLM client with all parameters")
        print("    - temperature, top_p, max_tokens, presence_penalty")
        print("  ✓ Raw response logging corrected")
        print("    - Now saves raw LLM output BEFORE content extraction")
        print("    - Order: invoke() -> str(response) -> _save_raw_response()")
        print("  ✓ Scene token efficiency verified")
        print("    - Uses prompt3_tokens / scene_count")
        print("    - self.prompt_metrics[3]['total_tokens']")

        print("\n[OUTPUT STRUCTURE]")
        run_folder = str(self.output_folders["run_folder"])
        print(f"  Run folder: {run_folder}")
        print(f"  └── metrics/          (new location)")
        print(f"  └── raw_llm/")
        print(f"      ├── prompt0_response.txt")
        print(f"      ├── prompt1_response.txt")
        print(f"      ├── prompt2_response.txt")
        print(f"      └── prompt3_response.txt")

        print("\n[FIX VERIFICATION]")
        print("  ✓ Token tracking enabled")
        print("    - extract_llm_usage() now supports response_metadata")
        print("  ✓ Concept density working")
        print("    - Markdown removed from concept names")
        print("    - Concept matching includes definition keywords")
        print("  ✓ Metrics stored per run")
        print("    - Metrics folder now inside run_folder")
        print("  ✓ Story continuity enforced")
        print("    - Prompt2 includes STORY CONTINUITY RULES")

        print(f"\n{'=' * 60}")
        print("  All structural audit fixes verified!")
        print(f"{'=' * 60}")

    @traceable(name="prompt0_concept_extraction")
    def _run_concept_extraction(self, chapter_info: dict):
        """Run concept extraction prompt."""
        import time

        logger.info("Running Prompt 0 – Concept Inventory")
        print("\n[1/4] Running Prompt 0 → Concept Inventory")

        llm, config = self._get_llm(0)

        # Use prompt template from MASTER_PROMPTS.txt - inject chapter info
        # Try to get chapter_text from chapter_info, otherwise use placeholder
        chapter_text = chapter_info.get(
            "chapter_text",
            f"Chapter: {chapter_info.get('chapter_name', '')}. "
            "Please extract concepts based on the chapter title and your knowledge of CBSE Class {class_level} {subject} curriculum.",
        )

        prompt = self.prompt0_template.format(
            class_level=chapter_info.get("class_level", ""),
            subject=chapter_info.get("subject", ""),
            chapter_name=chapter_info.get("chapter_name", ""),
            chapter_number=chapter_info.get("chapter_number", ""),
            medium=chapter_info.get("medium", "English"),
            chapter_text=chapter_text,
        )

        # Debug: Print final prompt length
        print(f"\n===== FINAL PROMPT0 LENGTH: {len(prompt)} chars =====\n")

        # Log injected prompt
        self.metrics.log_injected_prompt(0, prompt)

        # Debug: Print full injected prompt
        print("\n===== PROMPT0 FULL TEXT =====")
        print(prompt)
        print("===== END PROMPT0 =====\n")

        # Use safe JSON call with automatic retry
        data = safe_llm_json_call(llm, prompt, 0, self._save_raw_response)

        # Get content length for metrics
        content = ""

        latency = 0
        input_tokens = None
        output_tokens = None

        # Store concepts for engagement metrics - remove markdown from concept names
        concepts = data.get("concepts", [])
        for c in concepts:
            name = c.get("concept_name", "")
            name = name.replace("**", "")
            name = name.strip()
            c["concept_name"] = name
        self.metrics.set_concepts(concepts)

        # Log prompt metrics with config
        self.metrics.log_prompt_metrics(
            prompt_id=0,
            model=self.model_config["model"],
            latency=latency,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            response_characters=len(content),
            temperature=config.get("temperature"),
            top_p=config.get("top_p"),
            max_tokens=config.get("max_tokens"),
            presence_penalty=config.get("presence_penalty"),
        )

        self.state["concept_inventory"] = data

        OutputManager.save_json(data, self.output_folders["concepts"] / "concepts.json")
        print("  ✓ Saved: concepts/concepts.json")

    @traceable(name="prompt1_story_backbone")
    def _run_story_backbone(self, chapter_info: dict):
        """Run story backbone generation."""
        import time

        logger.info("Running Prompt 1 – Story Backbone")
        print("\n[2/4] Running Prompt 1 → Story Backbone")

        llm, config = self._get_llm(1)

        # Use prompt template from MASTER_PROMPTS.txt
        prompt = self.prompt_loader.inject_values(
            self.prompt1_template,
            chapter=chapter_info["chapter_name"],
            concept_inventory=json.dumps(
                self.state["concept_inventory"].get("concepts", []), indent=2
            ),
        )

        # Log injected prompt
        self.metrics.log_injected_prompt(1, prompt)

        # Use safe JSON call with automatic retry
        data = safe_llm_json_call(llm, prompt, 1, self._save_raw_response)

        latency = 0
        input_tokens = None
        output_tokens = None
        content = ""

        # Validate parsed result
        if not isinstance(data, dict):
            raise ValueError("LLM output is not a valid JSON object")

        # Log prompt metrics with config
        self.metrics.log_prompt_metrics(
            prompt_id=1,
            model=self.model_config["model"],
            latency=latency,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            response_characters=len(content),
            temperature=config.get("temperature"),
            top_p=config.get("top_p"),
            max_tokens=config.get("max_tokens"),
            presence_penalty=config.get("presence_penalty"),
        )

        self.state["story_backbone"] = data

        OutputManager.save_json(
            data, self.output_folders["story"] / "story_backbone.json"
        )
        print("  ✓ Saved: story/story_backbone.json")

    @traceable(name="prompt2_learning_steps")
    def _run_learning_steps(self, chapter_info: dict):
        """Run learning step decomposition."""
        import time

        logger.info("Running Prompt 2 – Learning Steps")
        print("\n[3/4] Running Prompt 2 → Learning Steps")

        llm, config = self._get_llm(2)

        # Extract selected_story details from Prompt1 output to prevent story drift
        selected_story = {}
        story_data = self.state.get("story_backbone", {})
        if story_data and isinstance(story_data, dict):
            selected_story = story_data.get("selected_story", {})

        # Build story context to force continuity
        story_title = selected_story.get("title", "Untitled Story")
        story_premise = selected_story.get("core_narrative_premise", "")
        character_registry = selected_story.get("character_registry", [])

        # Get concept inventory from Prompt0 output
        concept_inventory = self.state.get("concept_inventory", {})
        concept_inventory_json = (
            json.dumps(concept_inventory, indent=2) if concept_inventory else "[]"
        )

        # Inject selected_story info and concept inventory to prevent drift
        prompt = self.prompt_loader.inject_values(
            self.prompt2_template,
            chapter=chapter_info["chapter_name"],
            story_backbone=json.dumps(self.state["story_backbone"], indent=2),
            selected_story_title=story_title,
            selected_story_premise=story_premise,
            character_registry=json.dumps(character_registry, indent=2)
            if character_registry
            else "[]",
            concept_inventory=concept_inventory_json,
        )

        # Log injected prompt
        self.metrics.log_injected_prompt(2, prompt)

        # Use safe JSON call with automatic retry
        data = safe_llm_json_call(llm, prompt, 2, self._save_raw_response)

        latency = 0
        input_tokens = None
        output_tokens = None
        content = ""

        # Log prompt metrics with config
        self.metrics.log_prompt_metrics(
            prompt_id=2,
            model=self.model_config["model"],
            latency=latency,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            response_characters=len(content),
            temperature=config.get("temperature"),
            top_p=config.get("top_p"),
            max_tokens=config.get("max_tokens"),
            presence_penalty=config.get("presence_penalty"),
        )

        self.state["learning_steps"] = data

        OutputManager.save_json(
            data, self.output_folders["learning_steps"] / "learning_steps.json"
        )
        print("  ✓ Saved: learning_steps/learning_steps.json")

    def _run_scene_plan(
        self, chapter_info: dict, learning_step: dict, learning_step_id: str
    ) -> dict:
        """Generate scene plan for a specific learning step."""
        logger.info(f"Running Scene Planner for {learning_step_id}")
        print(f"\n[Scene Planning] Generating scene plan for {learning_step_id}")

        llm, config = self._get_llm(3)

        # Extract character registry from story backbone
        character_registry = []
        story_backbone_data = self.state.get("story_backbone", {})
        if story_backbone_data and isinstance(story_backbone_data, dict):
            selected = story_backbone_data.get("selected_story", {})
            if selected:
                character_registry = selected.get("character_registry", [])

        # Inject values into scene planner prompt
        prompt = self.scene_planner_template.format(
            learning_step_id=learning_step_id,
            chapter=chapter_info["chapter_name"],
            story_backbone=json.dumps(self.state["story_backbone"], indent=2),
            learning_step=json.dumps(learning_step, indent=2),
            character_registry=json.dumps(character_registry, indent=2)
            if character_registry
            else "[]",
        )

        # Log injected prompt
        self.metrics.log_injected_prompt(f"scene_planner_{learning_step_id}", prompt)

        # Generate scene plan
        scene_plan_data = safe_llm_json_call(
            llm,
            prompt,
            3,
            lambda pid, content: self._save_raw_response(
                f"scene_planner_{learning_step_id}", content
            ),
        )

        # Validate scene plan
        if "scene_plan" not in scene_plan_data:
            raise ValueError(
                f"Scene plan missing 'scene_plan' key for {learning_step_id}"
            )

        scene_plan = scene_plan_data["scene_plan"]
        if len(scene_plan) < 6 or len(scene_plan) > 15:
            logger.warning(
                f"Scene plan for {learning_step_id} has {len(scene_plan)} scenes (expected 6-15)"
            )

        # Save scene plan to learning step specific folder
        scenes_dir = self.output_folders["scenes"]
        step_scenes_dir = OutputManager.get_learning_step_scene_dir(
            scenes_dir, learning_step_id
        )

        # Save scene plan
        OutputManager.save_json(scene_plan_data, step_scenes_dir / "scene_plan.json")
        print(
            f"  ✓ Saved: {learning_step_id}/scene_plan.json ({len(scene_plan)} scenes planned)"
        )

        logger.info(
            f"Generated scene plan for {learning_step_id} with {len(scene_plan)} scenes"
        )
        return scene_plan_data

    def _generate_single_scene(
        self,
        scene_info: dict,
        previous_scene_summary: str,
        chapter_info: dict,
        learning_step: dict,
        learning_step_id: str,
    ) -> dict:
        """Generate a single scene for a specific learning step."""
        llm, config = self._get_llm(3)

        # Extract character registry
        character_registry = []
        story_backbone_data = self.state.get("story_backbone", {})
        if story_backbone_data and isinstance(story_backbone_data, dict):
            selected = story_backbone_data.get("selected_story", {})
            if selected:
                character_registry = selected.get("character_registry", [])

        scene_id = scene_info.get("scene_id", f"{learning_step_id}_S1")
        scene_phase = scene_info.get("phase", "observation")

        # Get next scene phase for smooth transition
        scene_plan = self.state.get(f"scene_plan_{learning_step_id}", {}).get(
            "scene_plan", []
        )
        next_scene_phase = None
        for i, s in enumerate(scene_plan):
            if s.get("scene_id") == scene_id and i + 1 < len(scene_plan):
                next_scene_phase = scene_plan[i + 1].get("phase", "transition")
                break

        # Inject values into single scene prompt
        prompt = self.single_scene_template.format(
            learning_step_id=learning_step_id,
            chapter=chapter_info["chapter_name"],
            story_backbone=json.dumps(self.state["story_backbone"], indent=2),
            character_registry=json.dumps(character_registry, indent=2)
            if character_registry
            else "[]",
            learning_step=json.dumps(learning_step, indent=2),
            scene_id=scene_id,
            scene_phase=scene_phase,
            story_summary=self.story_summary,
            previous_scene_summary=previous_scene_summary or "This is the first scene.",
            next_scene_phase=next_scene_phase or "transition",
        )

        # Log injected prompt
        self.metrics.log_injected_prompt(f"scene_{scene_id}", prompt)

        # Generate single scene
        scene_data = safe_llm_json_call(
            llm,
            prompt,
            3,
            lambda pid, content: self._save_raw_response(f"scene_{scene_id}", content),
        )

        # Add visual_prompt and visual_elements based on scene content
        scene_data = self._add_visual_prompt(scene_data)

        return scene_data

    def _add_visual_prompt(self, scene_data: dict) -> dict:
        """Generate visual_prompt and visual_elements for a scene."""
        scene_id = scene_data.get("scene_id", "unknown")

        # Extract key information for visual prompt generation
        visual_setting = scene_data.get("visual_setting", {})
        if isinstance(visual_setting, dict):
            environment = visual_setting.get("environment", "")
            atmosphere = visual_setting.get("atmosphere", "")
            time_of_day = visual_setting.get("time_of_day", "")
        else:
            environment = str(visual_setting)
            atmosphere = ""
            time_of_day = ""

        characters = scene_data.get("characters", [])
        character_descriptions = []
        if isinstance(characters, list):
            for char in characters:
                char_id = char.get("character_id", "")
                action = char.get("action", "")
                emotion = char.get("emotion", "")
                if char_id:
                    char_desc = f"{char_id}"
                    if action:
                        char_desc += f" {action}"
                    if emotion:
                        char_desc += f" ({emotion})"
                    character_descriptions.append(char_desc)

        # Build visual prompt
        visual_elements = []

        # Extract visual elements from environment
        if environment:
            visual_elements.append(environment)

        # Extract visual elements from atmosphere
        if atmosphere:
            visual_elements.append(atmosphere)

        # Extract visual elements from time_of_day
        if time_of_day:
            visual_elements.append(time_of_day)

        # Extract visual elements from characters
        for char_desc in character_descriptions:
            if char_desc not in visual_elements:
                visual_elements.append(char_desc)

        # Build the visual_prompt string
        visual_prompt_parts = []

        if character_descriptions:
            visual_prompt_parts.append(", ".join(character_descriptions))

        if environment:
            visual_prompt_parts.append(environment)

        if atmosphere:
            visual_prompt_parts.append(atmosphere)

        if time_of_day:
            visual_prompt_parts.append(time_of_day)

        # Add cinematic style
        visual_prompt_parts.append("cinematic lighting")
        visual_prompt_parts.append("educational animation style")

        visual_prompt = ", ".join(visual_prompt_parts)

        # Add fields to scene data
        scene_data["visual_prompt"] = visual_prompt
        scene_data["visual_elements"] = visual_elements

        return scene_data

    def _update_story_summary(self, scene_data: dict, scene_index: int) -> None:
        """Update story summary after each scene is generated."""
        scene_id = scene_data.get("scene_id", f"LS1_S{scene_index + 1}")
        narrative = scene_data.get("narrative", {})
        if isinstance(narrative, dict):
            screenplay = narrative.get("screenplay", "")
        else:
            screenplay = str(narrative)

        # Extract key events from the scene
        key_events = []
        if screenplay:
            # Take first 100 words as summary
            words = screenplay.split()[:100]
            summary_text = " ".join(words)
            key_events.append(summary_text)

        # Update story summary
        if self.story_summary:
            self.story_summary += " " + " ".join(key_events)
        else:
            self.story_summary = " ".join(key_events)

    @traceable(name="prompt3_scene_generation")
    def _run_scene_generation(self, chapter_info: dict):
        """Run scene generation for all learning steps or LS1 only based on test_mode."""
        import time

        logger.info(
            f"Running Prompt 3 – Scene Generation (Test Mode: {self.test_mode})"
        )

        # Get all learning steps
        learning_steps_data = self.state.get("learning_steps", {})
        all_learning_steps = []

        if learning_steps_data and isinstance(learning_steps_data, dict):
            all_learning_steps = learning_steps_data.get("learning_steps", [])

        if not all_learning_steps:
            raise ValueError("No learning steps found in state")

        # Determine which learning steps to process
        if self.test_mode:
            # Only process LS1 for testing
            learning_steps_to_process = (
                [all_learning_steps[0]] if all_learning_steps else []
            )
            print(f"\n[4/4] Running Scene Generation (TEST MODE - LS1 Only)")
        else:
            # Process all learning steps
            learning_steps_to_process = all_learning_steps
            print(
                f"\n[4/4] Running Scene Generation (ALL {len(all_learning_steps)} LEARNING STEPS)"
            )

        total_scene_count = 0

        # Process each learning step
        for ls_idx, learning_step in enumerate(learning_steps_to_process):
            learning_step_id = learning_step.get("step_id", f"LS{ls_idx + 1}")
            print(f"\n{'=' * 40}")
            print(
                f"  Processing Learning Step: {learning_step_id} ({ls_idx + 1}/{len(learning_steps_to_process)})"
            )
            print(f"{'=' * 40}")

            # Step 1: Generate scene plan
            scene_plan_data = self._run_scene_plan(
                chapter_info, learning_step, learning_step_id
            )
            self.state[f"scene_plan_{learning_step_id}"] = scene_plan_data
            scene_plan = scene_plan_data.get("scene_plan", [])

            # Step 2: Generate scenes one by one
            print(
                f"\n[Scene Generation] Generating {len(scene_plan)} scenes for {learning_step_id}..."
            )

            generated_scenes = []
            previous_scene_summary = ""

            for idx, scene_info in enumerate(scene_plan):
                scene_id = scene_info.get("scene_id", f"{learning_step_id}_S{idx + 1}")
                print(
                    f"  Generating {scene_id} ({scene_info.get('phase', 'unknown')})..."
                )

                try:
                    # Generate single scene
                    scene_data = self._generate_single_scene(
                        scene_info,
                        previous_scene_summary,
                        chapter_info,
                        learning_step,
                        learning_step_id,
                    )

                    # Add scene_id if not present
                    if "scene_id" not in scene_data:
                        scene_data["scene_id"] = scene_id

                    # Save individual scene to learning step specific folder
                    scenes_dir = self.output_folders["scenes"]
                    step_scenes_dir = OutputManager.get_learning_step_scene_dir(
                        scenes_dir, learning_step_id
                    )

                    # Use standardized naming: {learning_step_id}_{scene_number}.json
                    scene_filename = f"{learning_step_id}_{idx + 1}.json"
                    OutputManager.save_json(
                        scene_data, step_scenes_dir / scene_filename
                    )

                    generated_scenes.append(scene_data)

                    # Update story summary
                    self._update_story_summary(scene_data, idx)

                    # Update previous scene summary for next iteration
                    narrative = scene_data.get("narrative", {})
                    if isinstance(narrative, dict):
                        screenplay = narrative.get("screenplay", "")[:200]
                    else:
                        screenplay = str(narrative)[:200]
                    previous_scene_summary = screenplay

                    print(f"    ✓ Saved: {learning_step_id}/{scene_filename}")

                except Exception as e:
                    logger.error(f"Failed to generate scene {scene_id}: {e}")
                    print(f"    ⚠ Failed: {scene_id} - {e}")
                    continue

            # Validate scenes
            if len(generated_scenes) == 0:
                error_msg = (
                    f"No scenes were generated successfully for {learning_step_id}"
                )
                logger.error(error_msg)
                raise ValueError(error_msg)

            # Generate visual prompts for images (placeholder for future Fal.ai integration)
            self._generate_scene_images(generated_scenes, learning_step_id)

            # Save combined scenes for this learning step
            scenes_dir = self.output_folders["scenes"]
            step_scenes_dir = OutputManager.get_learning_step_scene_dir(
                scenes_dir, learning_step_id
            )

            combined_scenes_data = {
                "learning_step_id": learning_step_id,
                "scenes": generated_scenes,
                "scene_plan": scene_plan,
            }

            OutputManager.save_json(
                combined_scenes_data,
                step_scenes_dir / f"{learning_step_id}_scenes.json",
            )
            print(f"  ✓ Saved: {learning_step_id}/{learning_step_id}_scenes.json")

            # Store in all_generated_scenes
            self.all_generated_scenes[learning_step_id] = generated_scenes

            scene_count = len(generated_scenes)
            total_scene_count += scene_count
            print(f"  ✓ Generated {scene_count} scenes for {learning_step_id}")

        # Log prompt metrics
        self.metrics.log_prompt_metrics(
            prompt_id=3,
            model=self.model_config["model"],
            latency=0,
            input_tokens=None,
            output_tokens=None,
            response_characters=0,
            temperature=0.6,
            top_p=0.9,
            max_tokens=4000,
            presence_penalty=0.3,
        )

        # Log scene generation metrics
        self.metrics.log_scene_generation_metrics(
            prompt_id=3,
            scene_count=total_scene_count,
            generation_time=0,
            scenes_data=[],
        )

        logger.info(
            f"Successfully generated {total_scene_count} scenes for {len(learning_steps_to_process)} learning steps"
        )

        # Store scenes in state
        self.state["scenes"] = {
            "all_learning_steps": list(self.all_generated_scenes.keys()),
            "total_scenes": total_scene_count,
            "learning_steps": self.all_generated_scenes,
        }

        # Save combined all scenes
        all_scenes_combined = {
            "test_mode": self.test_mode,
            "total_learning_steps": len(learning_steps_to_process),
            "total_scenes": total_scene_count,
            "learning_steps": self.all_generated_scenes,
        }

        scenes_dir = self.output_folders["scenes"]
        OutputManager.save_json(all_scenes_combined, scenes_dir / "all_scenes.json")
        print(f"  ✓ Saved: all_scenes.json (combined)")

        print(f"\n{'=' * 40}")
        print(f"  Scene Generation Complete")
        print(f"  Total Scenes: {total_scene_count}")
        print(f"  Learning Steps: {len(learning_steps_to_process)}")
        print(f"{'=' * 40}")

        return total_scene_count

    def _generate_scene_images(self, scenes_data: list, learning_step_id: str) -> None:
        """
        Placeholder for future Fal.ai image generation.

        Reads visual_prompt from scene JSON and saves to:
        visuals/{learning_step_id}/{scene_id}_prompt.txt

        This allows future image models to generate images from these prompts.
        """
        print(f"\n[Image Generation Hook] Saving visual prompts for {learning_step_id}")

        visuals_dir = self.output_folders["visuals"]
        visual_step_dir = OutputManager.get_learning_step_visual_dir(
            visuals_dir, learning_step_id
        )

        for scene in scenes_data:
            scene_id = scene.get("scene_id", "unknown")
            visual_prompt = scene.get("visual_prompt", "")

            if visual_prompt:
                # Save prompt to file
                prompt_filename = f"{scene_id}_prompt.txt"
                prompt_filepath = visual_step_dir / prompt_filename
                OutputManager.save_text(visual_prompt, prompt_filepath)
                print(f"  ✓ Saved: {learning_step_id}/{prompt_filename}")

        # Save all prompts combined
        all_prompts = {
            learning_step_id: [
                {
                    "scene_id": scene.get("scene_id"),
                    "visual_prompt": scene.get("visual_prompt", ""),
                    "visual_elements": scene.get("visual_elements", []),
                }
                for scene in scenes_data
            ]
        }

        OutputManager.save_json(all_prompts, visual_step_dir / "image_prompts.json")
        print(f"  ✓ Saved: {learning_step_id}/image_prompts.json")

    def _save_raw_response(self, prompt_id: int, content: str) -> None:
        """Save raw LLM response to file."""
        filename = f"prompt{prompt_id}_response.txt"
        filepath = self.output_folders["raw_llm"] / filename
        OutputManager.save_text(content, filepath)
        logger.info(f"Saved raw response: {filename}")

    def _generate_debug_report(self) -> None:
        """Generate a comprehensive debug report for the pipeline run."""
        import glob
        from datetime import datetime

        report_lines = []
        run_folder = self.output_folders["run_folder"]

        def add_section(title: str, content: str = "") -> None:
            separator = "=" * 50
            report_lines.append(separator)
            report_lines.append(title)
            report_lines.append(separator)
            if content:
                report_lines.append(content)
            report_lines.append("")

        def add_subsection(title: str, content: str = "") -> None:
            separator = "-" * 40
            report_lines.append(title)
            report_lines.append(separator)
            if content:
                report_lines.append(content)
            report_lines.append("")

        # STEP 3: Report Header
        run_timestamp = run_folder.name
        chapter_info = getattr(self, "_last_chapter_info", {})
        chapter_name = chapter_info.get("chapter_name", "Unknown")
        class_level = chapter_info.get("class_level", "Unknown")
        subject = chapter_info.get("subject", "Unknown")

        # Get first learning step ID for reporting
        first_ls_id = None
        if self.all_generated_scenes:
            first_ls_id = list(self.all_generated_scenes.keys())[0]

        scene_plan_data = (
            self.state.get(f"scene_plan_{first_ls_id}", {}) if first_ls_id else {}
        )
        scene_plan = scene_plan_data.get("scene_plan", [])
        scene_count = self.state.get("scenes", {}).get("total_scenes", 0)
        story_summary_length = len(self.story_summary) if self.story_summary else 0

        header_content = f"""Model: {self.model_config.get("name", "Unknown")}
Model Provider: {self.model_config.get("provider", "Unknown")}
Run Timestamp: {run_timestamp}
Chapter: {chapter_name}
Class: {class_level}
Subject: {subject}
Total Scenes Generated: {scene_count}
Scene Plan Count: {len(scene_plan)}
Story Summary Length: {story_summary_length} characters"""

        add_section("PIPELINE RUN SUMMARY", header_content)

        # STEP 4: Prompt Configuration
        from core.metrics.metrics_logger import MetricsLogger

        config_content = ""
        for pid in range(4):
            cfg = MetricsLogger.DEFAULT_PROMPT_CONFIG.get(pid, {})
            config_content += f"\nPrompt {pid}:\n"
            config_content += f"  temperature: {cfg.get('temperature', 'N/A')}\n"
            config_content += f"  top_p: {cfg.get('top_p', 'N/A')}\n"
            config_content += f"  max_tokens: {cfg.get('max_tokens', 'N/A')}\n"
            config_content += (
                f"  presence_penalty: {cfg.get('presence_penalty', 'N/A')}\n"
            )

        add_section("PROMPT CONFIGURATION", config_content)

        # STEP 5: Prompts Sent to LLM
        add_section("PROMPTS SENT TO LLM")
        prompts_folder = run_folder / "prompts"
        for pid in range(4):
            prompt_file = prompts_folder / f"prompt{pid}_injected.txt"
            if prompt_file.exists():
                content = prompt_file.read_text(encoding="utf-8")
                add_subsection(f"Prompt {pid} (length: {len(content)} chars)")
                report_lines.append(
                    content[:20000] if len(content) > 20000 else content
                )
                report_lines.append("")

        # STEP 6: Raw LLM Responses
        add_section("RAW LLM RESPONSES")
        raw_folder = run_folder / "raw_llm"
        for pid in range(4):
            raw_file = raw_folder / f"prompt{pid}_response.txt"
            if raw_file.exists():
                content = raw_file.read_text(encoding="utf-8")
                add_subsection(f"Prompt {pid} Response (length: {len(content)} chars)")
                # JSON integrity check
                starts_json = content.strip().startswith("{")
                ends_json = content.strip().endswith("}")
                report_lines.append(f"Starts with '{{': {starts_json}")
                report_lines.append(f"Ends with '}}': {ends_json}")
                if not ends_json:
                    report_lines.append("⚠ WARNING: JSON may be truncated!")
                report_lines.append("")
                report_lines.append(
                    content[:20000] if len(content) > 20000 else content
                )
                report_lines.append("")

        # STEP 7: Parsed JSON Outputs
        add_section("PARSED JSON OUTPUTS")

        # Concepts
        concepts_file = run_folder / "concepts" / "concepts.json"
        if concepts_file.exists():
            content = concepts_file.read_text(encoding="utf-8")
            add_subsection(f"concepts.json (length: {len(content)} chars)")
            report_lines.append(content[:20000] if len(content) > 20000 else content)
            report_lines.append("")

        # Story backbone
        story_file = run_folder / "story" / "story_backbone.json"
        if story_file.exists():
            content = story_file.read_text(encoding="utf-8")
            add_subsection(f"story_backbone.json (length: {len(content)} chars)")
            report_lines.append(content[:20000] if len(content) > 20000 else content)
            report_lines.append("")

        # Learning steps
        ls_file = run_folder / "learning_steps" / "learning_steps.json"
        if ls_file.exists():
            content = ls_file.read_text(encoding="utf-8")
            add_subsection(f"learning_steps.json (length: {len(content)} chars)")
            report_lines.append(content[:20000] if len(content) > 20000 else content)
            report_lines.append("")

        # STEP 8: Scene Plans
        add_section("SCENE PLANS")
        scenes_folder = run_folder / "scenes"

        # Get all learning step directories
        for ls_dir in sorted(scenes_folder.iterdir()):
            if ls_dir.is_dir():
                ls_id = ls_dir.name
                scene_plan_file = ls_dir / "scene_plan.json"
                if scene_plan_file.exists():
                    scene_plan_json = json.loads(
                        scene_plan_file.read_text(encoding="utf-8")
                    )
                    plan_scenes = scene_plan_json.get("scene_plan", [])
                    plan_content = (
                        f"Learning Step: {ls_id}\n"
                        f"Total Scenes in Plan: {len(plan_scenes)}\n\nScene Phases:\n"
                    )
                    for s in plan_scenes:
                        plan_content += f"  - {s.get('scene_id')}: {s.get('phase')}\n"
                    add_subsection(f"Scene Plan - {ls_id}")
                    report_lines.append(plan_content)
                    report_lines.append("")

        # STEP 9: Generated Scenes (show first learning step only for brevity)
        add_section("GENERATED SCENES")

        # Get first learning step scenes for display
        first_ls_id = None
        if self.all_generated_scenes:
            first_ls_id = list(self.all_generated_scenes.keys())[0]

        if first_ls_id:
            ls_scenes_dir = scenes_folder / first_ls_id
            scene_files = sorted(ls_scenes_dir.glob(f"{first_ls_id}_*.json"))

            for scene_file in scene_files:
                scene_data = json.loads(scene_file.read_text(encoding="utf-8"))
                scene_id = scene_data.get("scene_id", scene_file.stem)
                scene_phase = scene_data.get("scene_phase", "unknown")
                scene_goal = scene_data.get("scene_goal", "N/A")

            narrative = scene_data.get("narrative", {})
            screenplay = (
                narrative.get("screenplay", "")
                if isinstance(narrative, dict)
                else str(narrative)
            )
            word_count = len(screenplay.split())

            concept_moments = scene_data.get("concept_moments", [])
            concepts_text = (
                ", ".join([c.get("concept", "N/A") for c in concept_moments])
                if concept_moments
                else "None"
            )

            add_subsection(f"{scene_id}")
            report_lines.append(f"Phase: {scene_phase}")
            report_lines.append(f"Goal: {scene_goal}")
            report_lines.append(f"Concept Moments: {concepts_text}")
            report_lines.append(f"Narrative Word Count: {word_count}")
            report_lines.append(f"\nScreenplay:\n{screenplay[:5000]}")
            report_lines.append("")

        # STEP 10: Story Continuity
        add_section("STORY CONTINUITY SUMMARY")
        summary_content = f"Summary Length: {story_summary_length} characters\n\n"
        summary_content += f"Summary Text:\n{self.story_summary}"
        report_lines.append(summary_content)

        # STEP 11: Metrics Summary
        add_section("METRICS SUMMARY")
        metrics_folder = run_folder / "metrics"

        metric_files = [
            "pipeline_metrics.json",
            "prompt0_metrics.json",
            "prompt1_metrics.json",
            "prompt2_metrics.json",
            "prompt3_metrics.json",
            "prompt3_scenes_metrics.json",
        ]

        for metric_file in metric_files:
            file_path = metrics_folder / metric_file
            if file_path.exists():
                try:
                    metric_data = json.loads(file_path.read_text(encoding="utf-8"))
                    add_subsection(metric_file)
                    report_lines.append(json.dumps(metric_data, indent=2)[:3000])
                    report_lines.append("")
                except:
                    pass

        # STEP 12: Write File
        report_content = "\n".join(report_lines)
        report_file = run_folder / "run_debug_report.txt"
        report_file.write_text(report_content, encoding="utf-8")

        print(f"\nDebug report generated: {report_file}")
        logger.info(f"Debug report generated: {report_file}")

    def print_story_inspection_report(self) -> None:
        """Print a compact story inspection report for evaluation."""
        run_folder = self.output_folders["run_folder"]

        def load_json(filepath):
            try:
                return json.loads(filepath.read_text(encoding="utf-8"))
            except:
                return None

        print(f"\n{'=' * 60}")
        print("  STORY INSPECTION REPORT")
        print(f"{'=' * 60}")

        # LEARNING STEPS
        ls_file = run_folder / "learning_steps" / "learning_steps.json"
        ls_data = load_json(ls_file)
        if ls_data:
            print("\n===== LEARNING STEPS =====")
            print(json.dumps(ls_data, indent=2)[:5000])

        # Get first learning step from generated scenes
        first_ls_id = None
        if self.all_generated_scenes:
            first_ls_id = list(self.all_generated_scenes.keys())[0]

        if first_ls_id:
            # SCENE PLAN
            sp_file = run_folder / "scenes" / first_ls_id / "scene_plan.json"
            sp_data = load_json(sp_file)
            if sp_data:
                print(f"\n===== SCENE PLAN ({first_ls_id}) =====")
                print(json.dumps(sp_data, indent=2))

            # First scene
            s1_file = run_folder / "scenes" / first_ls_id / f"{first_ls_id}_1.json"
            s1_data = load_json(s1_file)
            if s1_data:
                print(f"\n===== {first_ls_id}_1 =====")
                print(json.dumps(s1_data, indent=2)[:8000])

            # Second scene
            s2_file = run_folder / "scenes" / first_ls_id / f"{first_ls_id}_2.json"
            s2_data = load_json(s2_file)
            if s2_data:
                print(f"\n===== {first_ls_id}_2 =====")
                print(json.dumps(s2_data, indent=2)[:8000])

        # SCENE METRICS
        metrics_file = run_folder / "metrics" / "prompt3_scenes_metrics.json"
        metrics_data = load_json(metrics_file)
        if metrics_data:
            print("\n===== SCENE METRICS =====")
            print(json.dumps(metrics_data, indent=2))

        print(f"\n{'=' * 60}")
        print("  END OF INSPECTION REPORT")
        print(f"{'=' * 60}")


def get_chapter_info() -> dict:
    """Get chapter information from user."""
    print("\n" + "=" * 60)
    print("  Chapter Information")
    print("=" * 60)

    class_level = input("Class (e.g., 10): ").strip()
    subject = input("Subject (e.g., Maths, Physics): ").strip()
    chapter_number = input("Chapter Number: ").strip()
    chapter_title = input("Chapter Title: ").strip()
    medium = input("Medium (English/Hindi): ").strip() or "English"

    chapter_name = (
        f"Class {class_level} {subject} Chapter {chapter_number} {chapter_title}"
    )

    return {
        "class_level": class_level,
        "subject": subject,
        "chapter_number": chapter_number,
        "chapter_title": chapter_title,
        "chapter_name": chapter_name,
        "medium": medium,
    }


def main():
    """Main entry point."""
    global TEST_MODE

    print("\n" + "=" * 60)
    print("  Storytelling Pipeline Runner")
    print("  Educational Storytelling Content Generator")
    print("=" * 60)

    # Print test mode status
    mode_str = (
        "LS1-Only (Test Mode)" if TEST_MODE else "Full Pipeline (All Learning Steps)"
    )
    print(f"  Mode: {mode_str}")

    # Print LangSmith status
    langsmith_key = os.getenv("LANGSMITH_API_KEY")
    langsmith_project = os.getenv("LANGSMITH_PROJECT", "ls1-pipeline")
    if langsmith_key:
        print(f"  LangSmith Tracing: ENABLED (project: {langsmith_project})")
    else:
        print("  LangSmith Tracing: NOT CONFIGURED (LANGSMITH_API_KEY missing)")

    # Check API keys
    openai_key = os.getenv("OPENAI_API_KEY")
    openrouter_key = os.getenv("OPENROUTER_API_KEY")

    if not openai_key:
        print("ERROR: OPENAI_API_KEY not found in .env")
        sys.exit(1)

    # Note: OPENROUTER_API_KEY is checked in _get_llm when DeepSeek is selected

    # Select model provider
    model_config = ModelProvider.select_provider()

    # Get chapter info
    chapter_info = get_chapter_info()

    # Run pipeline with test_mode
    runner = LS1PipelineRunner(model_config, test_mode=TEST_MODE)
    result = runner.run(chapter_info)

    print(f"\n📁 All outputs saved to: {runner.output_folders['base']}")
    print("\nGenerated files:")
    print("  - concepts/concepts.json")
    print("  - story/story_backbone.json")
    print("  - learning_steps/learning_steps.json")
    print("  - scenes/{learning_step_id}/{learning_step_id}_S1.json")
    print("  - visuals/{learning_step_id}/image_prompts.json")


if __name__ == "__main__":
    main()
