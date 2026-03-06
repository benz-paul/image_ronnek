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

from state.pipeline_state import PipelineState


class PromptInjectorAgent:
    """
    Agent that automatically prepares prompts by filling input fields
    using LLM reasoning.
    """

    def __init__(self, model: str = "gpt-4o-mini", temperature: float = 0.7):
        """
        Initialize the Prompt Injector Agent.

        Args:
            model: LLM model to use
            temperature: Sampling temperature
        """
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY environment variable not set")

        self.llm = ChatOpenAI(model=model, temperature=temperature, max_retries=3)

        # Load prompt templates
        self.prompts_dir = Path(__file__).parent.parent / "prompts"
        self._load_prompt_templates()

    def _load_prompt_templates(self) -> None:
        """Load all prompt templates from files."""
        self.prompt_templates: Dict[str, str] = {}

        for i in range(5):  # prompt0 to prompt4
            prompt_file = self.prompts_dir / f"prompt{i}.txt"
            if prompt_file.exists():
                with open(prompt_file, "r", encoding="utf-8") as f:
                    self.prompt_templates[f"prompt{i}"] = f.read()

    def _prepare_prompt_with_llm(
        self, prompt_template: str, context: Dict[str, Any]
    ) -> str:
        """
        Fill placeholder fields in prompt template using LLM.

        Strategy:
        1. First do simple string replacement for basic fields
        2. Then use LLM to fill complex content areas

        Args:
            prompt_template: The base prompt with [FIELD] placeholders
            context: Dict containing all data to fill

        Returns:
            Prepared prompt with input fields filled
        """
        result = prompt_template

        # Step 1: Simple string replacement for basic fields
        simple_fields = {
            "[Chapter Name]": context.get("Chapter", ""),
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
        selected_story_narrative = ""
        if state.selected_story:
            selected_story_narrative = state.selected_story.get("core_premise", "")
        elif state.prompt1_output:
            selected_story_narrative = self._extract_selected_story(
                state.prompt1_output
            )

        return {
            "Chapter": state.user_inputs.chapter_name,
            "Class": state.user_inputs.class_level,
            "Subject": state.user_inputs.subject,
            "Medium": state.user_inputs.medium,
            "Concept Inventory": state.prompt0_output or "",
            "Selected Real-World Story Narrative": selected_story_narrative,
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

        # Current learning step
        current_ls = {}
        if 0 <= learning_step_index < len(learning_steps):
            current_ls = learning_steps[learning_step_index]

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
        - Chapter: (Insert the chapter name used in previous prompts)
        - Selected Real-World Story Narrative: (Insert the selected story backbone...)
        - Concept Inventory: (Insert the Concept Inventory output...)

        Args:
            state: Current pipeline state

        Returns:
            Injected prompt ready for execution
        """
        template = self.prompt_templates.get("prompt2", "")
        context = self._build_context_prompt2(state)
        return self._prepare_prompt_with_llm(template, context)

    def inject_prompt3(self, state: PipelineState, learning_step_index: int) -> str:
        """
        Inject values into Prompt 3 template for a specific learning step using LLM.

        Prompt 3 Input Fields:
        - Chapter: (Insert the chapter name)
        - Story Backbone: (Insert the selected story backbone...)
        - Previous Learning Step: (Insert the previous learning step...)
        - Current Learning Step: (Insert the current learning step...)
        - Next Learning Step: (Insert the next learning step...)

        Args:
            state: Current pipeline state
            learning_step_index: Index of the learning step to process

        Returns:
            Injected prompt ready for execution
        """
        template = self.prompt_templates.get("prompt3", "")
        context = self._build_context_prompt3(state, learning_step_index)
        return self._prepare_prompt_with_llm(template, context)

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
