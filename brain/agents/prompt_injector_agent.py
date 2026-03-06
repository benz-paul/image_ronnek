"""
Prompt Injector Agent - Automatically prepares prompts before execution.

This agent receives the prompt template and relevant data from state,
uses LLM to fill only the INPUT fields, and outputs a fully prepared
prompt ready to send to the LLM.

The user should NEVER manually edit prompt templates.
The prompt injector uses LLM to intelligently fill input fields.
"""

import os
import re
import json
from pathlib import Path
from typing import Any, Dict, Optional

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from brain.pipeline.state.pipeline_state import PipelineState


class PromptInjectorAgent:
    """
    Agent that automatically prepares prompts by filling input fields
    using LLM reasoning.
    """

    def __init__(self, model: str = "deepseek", temperature: float = 0.7):
        """
        Initialize the Prompt Injector Agent.

        Args:
            model: LLM model to use (currently only deepseek supported)
            temperature: Sampling temperature
        """
        # Use OpenRouter for DeepSeek v3.2
        api_key = os.getenv("OPENROUTER_API_KEY")
        if not api_key:
            raise ValueError(
                "OPENROUTER_API_KEY environment variable not set. "
                "Please set OPENROUTER_API_KEY in your .env file."
            )

        self.llm = ChatOpenAI(
            model="deepseek/deepseek-chat",
            temperature=temperature,
            max_retries=3,
            timeout=120,
            base_url="https://openrouter.ai/api/v1",
            api_key=api_key,
        )

        # Load prompt templates
        self.prompts_dir = Path(__file__).parent.parent / "prompt_engine" / "prompts"
        self._load_prompt_templates()

    def _load_prompt_templates(self) -> None:
        """Load all prompt templates from MASTER_PROMPTS.txt."""
        self.prompt_templates: Dict[str, str] = {}

        # Use the prompt_loader to properly load from MASTER_PROMPTS.txt
        from brain.prompt_engine.core.prompt_loader import get_prompt_loader

        # Build the correct path to MASTER_PROMPTS.txt
        prompts_path = (
            Path(__file__).parent.parent
            / "prompt_engine"
            / "prompts"
            / "MASTER_PROMPTS.txt"
        )

        loader = get_prompt_loader(str(prompts_path))

        # Load prompts 0-4 from MASTER_PROMPTS.txt
        try:
            self.prompt_templates["prompt0"] = loader.get_prompt(0)
            self.prompt_templates["prompt1"] = loader.get_prompt(1)
            self.prompt_templates["prompt2"] = loader.get_prompt(2)
            self.prompt_templates["prompt3"] = loader.get_prompt(3)
            self.prompt_templates["prompt4"] = loader.get_prompt(4)
            print(f"  DEBUG: Loaded all prompts from MASTER_PROMPTS.txt")
        except KeyError as e:
            print(f"  ERROR: Failed to load prompts: {e}")

    def _prepare_prompt_with_llm(
        self, prompt_template: str, context: Dict[str, Any]
    ) -> str:
        """
        Fill placeholder fields in prompt template using LLM.

        Strategy:
        1. First do simple string replacement for basic fields
        2. Then use LLM to fill complex content areas

        Args:
            prompt_template: The base prompt with [FIELD] or {FIELD} placeholders
            context: Dict containing all data to fill

        Returns:
            Prepared prompt with input fields filled
        """
        # Debug: Print raw template before any injection
        print("\n" + "=" * 60)
        print("DEBUG: Raw Template (first 1000 chars)")
        print("=" * 60)
        print(prompt_template[:1000] if prompt_template else "EMPTY!")
        print("=" * 60 + "\n")

        result = prompt_template

        # --- FIXED: Deterministic replacements for Prompt2 placeholders ---

        # Handle [Chapter Name] placeholder
        if context.get("Chapter"):
            result = result.replace("[Chapter Name]", context["Chapter"])
            result = result.replace("{chapter_name}", context["Chapter"])
            result = result.replace(
                "(Insert the chapter name used in previous prompts)", context["Chapter"]
            )

        # Handle {concept_inventory} curly brace placeholder
        if context.get("Concept Inventory"):
            result = result.replace("{concept_inventory}", context["Concept Inventory"])
            result = result.replace(
                "(Insert the **Concept Inventory output generated from Prompt 0**)",
                context["Concept Inventory"],
            )
            result = result.replace(
                "(Insert the Concept Inventory output...)",
                context["Concept Inventory"],
            )

        # Handle [selected_story_title]
        if context.get("Selected Story Title"):
            result = result.replace(
                "[selected_story_title]", context["Selected Story Title"]
            )

        # Handle [selected_story_premise]
        if context.get("Selected Story Premise"):
            result = result.replace(
                "[selected_story_premise]", context["Selected Story Premise"]
            )

        # Handle [character_registry]
        if context.get("Character Registry"):
            result = result.replace(
                "[character_registry]", context["Character Registry"]
            )

        # Handle Selected Real-World Story Narrative (full premise)
        if context.get("Selected Real-World Story Narrative"):
            result = result.replace(
                "(Insert the selected story backbone output from the previous prompt — specifically the **Core Narrative Premise** of the chosen story)",
                context["Selected Real-World Story Narrative"],
            )
            result = result.replace(
                "(Insert the **selected story backbone output from the story backbone generation prompt**, specifically the **Core Narrative Premise of the chosen story**)",
                context["Selected Real-World Story Narrative"],
            )

        # Step 1: Simple string replacement for basic fields
        simple_fields = {
            "[Chapter]": context.get("Chapter", ""),
            "[CHAPTER]": context.get("Chapter", ""),
            "[Class]": context.get("Class", ""),
            "[Subject]": context.get("Subject", ""),
            "[Medium]": context.get("Medium", ""),
        }

        for placeholder, value in simple_fields.items():
            if value:
                result = result.replace(placeholder, str(value))

        # Step 2: Use LLM to fill complex content areas
        # These are larger text blocks that need intelligent insertion
        complex_fields = [
            "Concept Inventory",
            "Selected Real-World Story Narrative",
            "Story Backbone",
            "Previous Learning Step",
            "Current Learning Step",
            "Next Learning Step",
        ]

        for field in complex_fields:
            if field in context and context[field]:
                # Find placeholder pattern for this field
                placeholder_patterns = [
                    f"[{field}]",
                    f"({field})",
                    f"[Output from {field}]",
                    f"(Insert {field.lower()}...)",
                    f"(Insert the **{field} output generated from Prompt 0**)",
                    f"(Insert the {field.lower()} output...)",
                    f"(Insert the {field.lower()}...)",
                    f"(Insert the **selected story backbone output from the story backbone generation prompt**, specifically the **Core Narrative Premise of the chosen story**)",
                    f"(Insert the **previous learning step output from the learning step decomposition prompt**)",
                    f"(Insert the **current learning step from the learning step decomposition output**)",
                    f"(Insert the **next learning step from the learning step decomposition output**)",
                    f"({field} output from the story backbone generation prompt)",
                    f"({field} output from the learning step decomposition prompt)",
                    f"({field} from the learning step decomposition output)",
                ]

                for placeholder in placeholder_patterns:
                    if placeholder in result:
                        value = context[field]
                        if isinstance(value, str):
                            # Use LLM to intelligently insert this content
                            result = self._fill_complex_field(
                                result, placeholder, value
                            )
                        break

        # FIXED: Check for remaining placeholders and warn
        remaining_placeholders = re.findall(r"[\[{][\w\s\-_*]+[\]}]", result)
        if remaining_placeholders:
            # Filter out common false positives
            filtered = [
                p
                for p in remaining_placeholders
                if not any(
                    skip in p.lower()
                    for skip in [
                        "json",
                        "example",
                        "output format",
                        "output rules",
                        "important",
                        "constraint",
                        "rule",
                    ]
                )
            ]
            if filtered:
                print("\n" + "!" * 60)
                print("WARNING: Unreplaced placeholders found!")
                print("!" * 60)
                print(f"Remaining placeholders: {filtered[:10]}")  # Show first 10
                print("!" * 60 + "\n")

        # Debug: Print final injected prompt
        print("\n" + "=" * 60)
        print("DEBUG: Final Injected Prompt (first 1500 chars)")
        print("=" * 60)
        print(result[:1500] if result else "EMPTY!")
        print("=" * 60 + "\n")

        return result

    def _fill_complex_field(self, template: str, placeholder: str, value: str) -> str:
        """
        Use LLM to intelligently fill a complex field placeholder.
        """
        system_msg = """You are a prompt editor. Your task is to replace a placeholder in a document with provided content.
Simply insert the content in place of the placeholder.
Do NOT rewrite, summarize, or modify the content.
Do NOT add any explanations.
Return the document with the placeholder replaced."""

        user_msg = f"""Replace the placeholder with this content:

PLACEHOLDER TO REPLACE:
{placeholder}

CONTENT TO INSERT:
{value}

DOCUMENT:
{template}

Simply return the document with the placeholder replaced. Keep all other text unchanged."""

        try:
            response = self.llm.invoke(
                [SystemMessage(content=system_msg), HumanMessage(content=user_msg)]
            )
            return response.content
        except Exception as e:
            # Fallback: simple replace
            return template.replace(placeholder, value)

    def _format_context(self, context: Dict[str, Any]) -> str:
        """Format context data for LLM."""
        lines = []
        for key, value in context.items():
            if value is None:
                value = ""
            if isinstance(value, dict):
                value = json.dumps(value, indent=2)
            elif not isinstance(value, str):
                value = str(value)
            lines.append(f"{key}:\n{value}\n")
        return "\n".join(lines)

    def _build_context_prompt0(self, state: PipelineState) -> Dict[str, Any]:
        """Build context for Prompt 0."""
        return {
            "Chapter": state.user_inputs.chapter_name,
            "Class": state.user_inputs.class_level,
            "Subject": state.user_inputs.subject,
            "Medium": state.user_inputs.medium,
        }

    def _build_context_prompt1(self, state: PipelineState) -> Dict[str, Any]:
        """Build context for Prompt 1."""
        return {
            "Chapter": state.user_inputs.chapter_name,
            "Class": state.user_inputs.class_level,
            "Subject": state.user_inputs.subject,
            "Medium": state.user_inputs.medium,
            "Concept Inventory": state.prompt0_output or "",
        }

    def _build_context_prompt2(self, state: PipelineState) -> Dict[str, Any]:
        """Build context for Prompt 2."""
        # Get selected story from prompt1 output
        selected_story_title = ""
        selected_story_premise = ""
        character_registry = ""

        if state.selected_story:
            selected_story_title = state.selected_story.get("title", "")
            selected_story_premise = state.selected_story.get("core_premise", "")
            # Try to get character registry if available
            if isinstance(state.selected_story, dict):
                characters = state.selected_story.get("characters", [])
                if characters:
                    character_registry = json.dumps(characters, indent=2)
        elif state.prompt1_output:
            # Extract from prompt1 output if not already selected
            parsed = self._extract_story_from_prompt1(state.prompt1_output)
            selected_story_title = parsed.get("title", "")
            selected_story_premise = parsed.get("core_premise", "")

        print(f"  DEBUG Prompt2 Context:")
        print(
            f"    - Title: {selected_story_title[:50] if selected_story_title else 'EMPTY'}..."
        )
        print(
            f"    - Premise: {selected_story_premise[:50] if selected_story_premise else 'EMPTY'}..."
        )
        print(f"    - Concept Inventory: {'SET' if state.prompt0_output else 'EMPTY'}")

        return {
            "Chapter": state.user_inputs.chapter_name,
            "Class": state.user_inputs.class_level,
            "Subject": state.user_inputs.subject,
            "Medium": state.user_inputs.medium,
            "Concept Inventory": state.prompt0_output or "",
            "Selected Story Title": selected_story_title,
            "Selected Story Premise": selected_story_premise,
            "Selected Real-World Story Narrative": selected_story_premise,
            "Character Registry": character_registry,
        }

    def _extract_story_from_prompt1(self, prompt1_output: str) -> Dict[str, Any]:
        """Extract story details from Prompt 1 output."""
        try:
            # Try to parse as JSON
            data = json.loads(prompt1_output)
            if "selected_story" in data:
                return data["selected_story"]
            if "stories" in data and len(data["stories"]) > 0:
                return data["stories"][0]
        except (json.JSONDecodeError, KeyError):
            pass

        # Fallback: extract from text
        title_match = re.search(r'"title":\s*"([^"]+)"', prompt1_output)
        premise_match = re.search(
            r'"core_narrative_premise":\s*"([^"]+)"', prompt1_output, re.DOTALL
        )

        return {
            "title": title_match.group(1) if title_match else "",
            "core_premise": premise_match.group(1)[:500] if premise_match else "",
        }

    def _build_context_prompt3(
        self, state: PipelineState, learning_step_index: int
    ) -> Dict[str, Any]:
        """Build context for Prompt 3."""
        chapter_name = state.user_inputs.chapter_name

        # Story backbone
        story_backbone = ""
        if state.selected_story:
            story_backbone = state.selected_story.get("core_premise", "")
            print(
                f"  DEBUG: Prompt3 - Using story: {state.selected_story.get('title', 'NONE')} - premise length: {len(story_backbone)}"
            )
        else:
            print(f"  DEBUG: Prompt3 - selected_story is EMPTY!")

        # Learning steps
        learning_steps = state.learning_steps_list

        # FIX 3: Select current learning step by learning_step_id rather than purely by index
        if 0 <= learning_step_index < len(learning_steps):
            current_ls = learning_steps[learning_step_index]
        else:
            current_ls = {}
        if current_ls:
            print(
                f"  DEBUG: Prompt3 - Using learning_step_index: {learning_step_index}"
            )
            print(
                f"  DEBUG: Prompt3 - Current LS title: {current_ls.get('title', 'NONE')[:50]}"
            )
            print(
                f"  DEBUG: Prompt3 - Current LS ID: {current_ls.get('learning_step_id', 'NONE')}"
            )

        # Previous learning step
        prev_ls = {}
        if learning_step_index > 0:
            prev_ls = learning_steps[learning_step_index - 1]

        # Next learning step
        next_ls = {}
        if learning_step_index < len(learning_steps) - 1:
            next_ls = learning_steps[learning_step_index + 1]

        return {
            "Chapter": chapter_name,
            "Class": state.user_inputs.class_level,
            "Subject": state.user_inputs.subject,
            "Medium": state.user_inputs.medium,
            "Story Backbone": story_backbone,
            "Previous Learning Step": json.dumps(prev_ls, indent=2) if prev_ls else "",
            "Current Learning Step": json.dumps(current_ls, indent=2)
            if current_ls
            else "",
            "Next Learning Step": json.dumps(next_ls, indent=2) if next_ls else "",
        }

    def _build_context_prompt4(
        self, state: PipelineState, scene_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Build context for Prompt 4."""
        # Extract scene information
        scene_goal = scene_data.get("scene_goal", "")
        scene_id = scene_data.get("scene_id", "")

        # Get narrative text
        narrative = scene_data.get("narrative", {})
        teaching_narrative = narrative.get("screenplay", "")

        # Get concept focus
        concept_focus = scene_data.get("concept_focus", "")

        # Get dialogues
        dialogues = scene_data.get("dialogue", [])
        character_dialogues = "\n".join(
            [f"{d.get('speaker', '')}: {d.get('text', '')}" for d in dialogues]
        )

        # Get the full learning step JSON for context
        current_ls = {}
        if state.learning_steps_list and 0 <= state.current_learning_step_index < len(
            state.learning_steps_list
        ):
            current_ls = state.learning_steps_list[state.current_learning_step_index]

        return {
            "Chapter": state.user_inputs.chapter_name,
            "Class": state.user_inputs.class_level,
            "Subject": state.user_inputs.subject,
            "Medium": state.user_inputs.medium,
            "scene_goal": scene_goal,
            "Teaching Narrative": teaching_narrative,
            "Concept Focus": concept_focus,
            "Character dialogues": character_dialogues,
            "Scene ID": scene_id,
            "JSON Structure Used": json.dumps(current_ls, indent=2),
        }

    def inject_prompt0(self, state: PipelineState) -> str:
        """
        Inject values into Prompt 0 template using LLM.

        Prompt 0 Input Fields:
        - Chapter: [Chapter Name]

        Args:
            state: Current pipeline state

        Returns:
            Injected prompt ready for execution
        """
        template = self.prompt_templates.get("prompt0", "")
        context = self._build_context_prompt0(state)
        return self._prepare_prompt_with_llm(template, context)

    def inject_prompt1(self, state: PipelineState) -> str:
        """
        Inject values into Prompt 1 template using LLM.

        Prompt 1 Input Fields:
        - Chapter: [Chapter Name]
        - Concept Inventory: [Output from Prompt 0]

        Args:
            state: Current pipeline state

        Returns:
            Injected prompt ready for execution
        """
        template = self.prompt_templates.get("prompt1", "")
        context = self._build_context_prompt1(state)
        return self._prepare_prompt_with_llm(template, context)

    def inject_prompt2(self, state: PipelineState) -> str:
        """
        Inject values into Prompt 2 template using LLM.

        Prompt 2 Input Fields:
        - Chapter: [Chapter Name]
        - Selected Story Title: [selected_story_title]
        - Selected Story Premise: [selected_story_premise]
        - Character Registry: [character_registry]
        - Concept Inventory: {concept_inventory}

        Args:
            state: Current pipeline state

        Returns:
            Injected prompt ready for execution
        """
        template = self.prompt_templates.get("prompt2", "")

        print("\n" + "=" * 60)
        print("INJECT_PROMPT2: Building context...")
        print("=" * 60)

        context = self._build_context_prompt2(state)

        # Debug: Show context keys and sample values
        print("\nContext keys being passed:")
        for key in context.keys():
            val = context[key]
            if isinstance(val, str):
                print(f"  - {key}: {val[:80] if val else 'EMPTY'}...")
            else:
                print(f"  - {key}: {type(val).__name__}")

        print("\n" + "=" * 60)
        print("INJECT_PROMPT2: Calling _prepare_prompt_with_llm...")
        print("=" * 60 + "\n")

        injected_prompt = self._prepare_prompt_with_llm(template, context)

        return injected_prompt

    def inject_prompt3(self, state: PipelineState, learning_step_index: int) -> str:
        """
        Inject values into Prompt 3 template for a specific learning step.

        MODIFIED: Removes large JSON schema block and replaces with clean
        instruction-based prompt to avoid placeholder issues.

        Args:
            state: Current pipeline state
            learning_step_index: Index of the learning step to process

        Returns:
            Injected prompt ready for execution
        """
        print("\n" + "=" * 60)
        print("INJECT_PROMPT3: Building clean prompt...")
        print("=" * 60)

        # Get context data
        context = self._build_context_prompt3(state, learning_step_index)

        chapter = context.get("Chapter", "")
        story_backbone = context.get("Story Backbone", "")
        current_ls = context.get("Current Learning Step", "")
        prev_ls = context.get("Previous Learning Step", "")
        next_ls = context.get("Next Learning Step", "")

        # Build clean prompt WITHOUT large JSON schema
        prompt_parts = []

        # Header
        prompt_parts.append(
            "You are generating educational story scenes for a chapter."
        )
        prompt_parts.append("")

        # Input Data
        prompt_parts.append(f"Chapter: {chapter}")
        prompt_parts.append("")

        prompt_parts.append("Story Backbone:")
        prompt_parts.append(
            story_backbone if story_backbone else "(No story backbone provided)"
        )
        prompt_parts.append("")

        prompt_parts.append("Current Learning Step:")
        prompt_parts.append(current_ls if current_ls else "(No learning step data)")
        prompt_parts.append("")

        if prev_ls:
            prompt_parts.append("Previous Learning Step:")
            prompt_parts.append(prev_ls)
            prompt_parts.append("")

        if next_ls:
            prompt_parts.append("Next Learning Step:")
            prompt_parts.append(next_ls)
            prompt_parts.append("")

        # Clean instruction-based output specification
        prompt_parts.append("=" * 50)
        prompt_parts.append("TASK:")
        prompt_parts.append("Generate 3 to 5 scenes for the given learning step.")
        prompt_parts.append("")
        prompt_parts.append("Each scene must include:")
        prompt_parts.append("- scene_id (e.g., S1, S2, S3)")
        prompt_parts.append("- title (short title for the scene)")
        prompt_parts.append("- description (what happens in the scene, 2-3 sentences)")
        prompt_parts.append("- dialogue (character conversations, if applicable)")
        prompt_parts.append("- visual_description (what to show in the image)")
        prompt_parts.append("")

        # Output format
        prompt_parts.append("OUTPUT FORMAT (STRICT JSON ONLY):")
        prompt_parts.append("{")
        prompt_parts.append('  "scenes": [')
        prompt_parts.append("    {")
        prompt_parts.append('      "scene_id": "S1",')
        prompt_parts.append('      "title": "...",')
        prompt_parts.append('      "description": "...",')
        prompt_parts.append('      "dialogue": "...",')
        prompt_parts.append('      "visual_description": "..."')
        prompt_parts.append("    }")
        prompt_parts.append("  ]")
        prompt_parts.append("}")
        prompt_parts.append("")

        # Rules
        prompt_parts.append("RULES:")
        prompt_parts.append("- Output ONLY valid JSON")
        prompt_parts.append("- No explanations or text before/after JSON")
        prompt_parts.append("- No 'status' or 'message' fields")
        prompt_parts.append("- Use the story backbone to create engaging scenes")
        prompt_parts.append("- Include at least 1 dialogue per scene")
        prompt_parts.append("- Make visual_description detailed for image generation")

        # Join parts
        injected_prompt = "\n".join(prompt_parts)

        # Validate: Check for remaining placeholders
        print("\n[VALIDATION] Checking for unreplaced placeholders...")
        remaining_brackets = re.findall(r"[\[{][^\[\]{}]+[\]}]", injected_prompt)

        if remaining_brackets:
            # Filter out false positives
            false_positives = {"json", "scene_id", "s1", "s2", "s3"}
            actual_remaining = [
                r
                for r in remaining_brackets
                if r.strip("[]{}").lower() not in false_positives
            ]

            if actual_remaining:
                print("\n" + "!" * 60)
                print("ERROR: Unreplaced placeholders detected!")
                print(f"Found: {actual_remaining}")
                print("!" * 60)
                raise ValueError(
                    f"Unreplaced placeholders in prompt3: {actual_remaining}"
                )

        print("  [VALIDATION] ✓ No placeholders detected")

        # Debug: Log final prompt
        print("\n" + "=" * 60)
        print("Final Prompt3 sent to LLM (cleaned)")
        print("=" * 60)
        print(
            injected_prompt[:1000] if len(injected_prompt) > 1000 else injected_prompt
        )
        print("..." if len(injected_prompt) > 1000 else "")
        print("=" * 60 + "\n")

        return injected_prompt

    def inject_prompt4(self, state: PipelineState, scene_data: Dict[str, Any]) -> str:
        """
        Inject values into Prompt 4 template for image generation using LLM.

        Prompt 4 Input Fields:
        - scene_goal: [SCENE_GOAL]
        - Teaching Narrative: [TEACHING_NARRATIVE]
        - Concept Focus: [CONCEPT_FOCUS]
        - Character dialogues: [CHARACTER_DIALOGUES]
        - Scene ID: [SCENE_ID]
        - JSON Structure Used: [JSON_GENERATED]

        Args:
            state: Current pipeline state
            scene_data: Scene data from learning step JSON

        Returns:
            Injected prompt ready for image generation
        """
        template = self.prompt_templates.get("prompt4", "")
        context = self._build_context_prompt4(state, scene_data)
        return self._prepare_prompt_with_llm(template, context)

    def inject_prompt4_for_scene(
        self,
        scene_data: Dict[str, Any],
        story_backbone: Dict[str, Any],
        chapter_name: str = "Class 10 Maths Chapter 5 Arithmetic Progression",
        class_level: str = "10",
        subject: str = "Maths",
    ) -> str:
        """
        Simplified prompt 4 injection for testing without full state.

        Args:
            scene_data: Scene data from LS JSON
            story_backbone: Story backbone data
            chapter_name: Chapter name
            class_level: Class level
            subject: Subject

        Returns:
            Injected prompt ready for image generation
        """
        template = self.prompt_templates.get("prompt4", "")

        # Extract scene info
        scene_id = scene_data.get("scene_id", "S1")
        scene_goal = scene_data.get("scene_goal", "")
        concept_focus = scene_data.get("concept_focus", "")
        emotional_tone = scene_data.get("emotional_tone", "")

        # Get narrative
        narrative = scene_data.get("narrative", {})
        screenplay = narrative.get("screenplay", "")
        camera_suggestion = narrative.get("camera_suggestion", "")

        # Get dialogues
        dialogues = scene_data.get("dialogue", [])
        dialogue_text = "\n".join(
            [f"{d.get('speaker', 'Character')}: {d.get('text', '')}" for d in dialogues]
        )

        # Get visual setting
        visual_setting = scene_data.get("visual_setting", {})
        environment = visual_setting.get("environment", "")
        atmosphere = visual_setting.get("atmosphere", "")

        # Build context
        context = {
            "Chapter": chapter_name,
            "Class": class_level,
            "Subject": subject,
            "scene_goal": scene_goal,
            "Teaching Narrative": screenplay,
            "Concept Focus": concept_focus,
            "Character dialogues": dialogue_text,
            "Scene ID": scene_id,
            "JSON Structure Used": json.dumps(scene_data, indent=2),
            "Story Backbone": story_backbone.get("core_premise", ""),
            "Environment": environment,
            "Atmosphere": atmosphere,
            "Camera Suggestion": camera_suggestion,
        }

        return self._prepare_prompt_with_llm(template, context)

    def _extract_selected_story(self, prompt1_output: str) -> str:
        """
        Extract the selected story backbone from Prompt 1 output.

        Args:
            prompt1_output: Raw output from Prompt 1

        Returns:
            Core narrative premise of the selected story
        """
        # Try to find the first story's core premise
        # Look for patterns like "Core Narrative Premise" or "Core Premise"
        patterns = [
            r"Core Narrative Premise[:\s]+(.+?)(?=\n\d+\.|\n---|\n\*\*|\nOverall|\Z)",
            r"Core Premise[:\s]+(.+?)(?=\n\d+\.|\n---|\n\*\*|\nOverall|\Z)",
        ]

        for pattern in patterns:
            match = re.search(pattern, prompt1_output, re.DOTALL | re.IGNORECASE)
            if match:
                return match.group(1).strip()

        # Fallback: return first 1000 chars
        return prompt1_output[:1000]

    def inject(self, prompt_id: str, state: PipelineState, **kwargs) -> str:
        """
        Generic inject method that routes to the appropriate prompt-specific method.

        Args:
            prompt_id: Prompt identifier (prompt0, prompt1, etc.)
            state: Current pipeline state
            **kwargs: Additional arguments (e.g., learning_step_index, scene_data)

        Returns:
            Injected prompt ready for execution
        """
        if prompt_id == "prompt0":
            return self.inject_prompt0(state)
        elif prompt_id == "prompt1":
            return self.inject_prompt1(state)
        elif prompt_id == "prompt2":
            return self.inject_prompt2(state)
        elif prompt_id == "prompt3":
            learning_step_index = kwargs.get("learning_step_index", 0)
            return self.inject_prompt3(state, learning_step_index)
        elif prompt_id == "prompt4":
            scene_data = kwargs.get("scene_data", {})
            return self.inject_prompt4(state, scene_data)
        else:
            raise ValueError(f"Unknown prompt ID: {prompt_id}")


def create_prompt_injector() -> PromptInjectorAgent:
    """Factory function to create PromptInjectorAgent."""
    return PromptInjectorAgent()
