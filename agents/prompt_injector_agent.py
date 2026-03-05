"""
Prompt Injector Agent - Automatically prepares prompts before execution.

This agent receives the prompt template and relevant data from state,
fills only the INPUT fields, and outputs a fully prepared prompt ready to send to the LLM.

The user should NEVER manually edit prompt templates.
The prompt injector must only modify INPUT fields.
"""

import os
import re
from pathlib import Path
from typing import Any, Dict, Optional

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
        
        self.llm = ChatOpenAI(
            model=model,
            temperature=temperature,
            max_retries=3
        )
        
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
    
    def inject_prompt0(self, state: PipelineState) -> str:
        """
        Inject values into Prompt 0 template.
        
        Prompt 0 Input Fields:
        - Chapter: [Chapter Name]
        
        Args:
            state: Current pipeline state
            
        Returns:
            Injected prompt ready for execution
        """
        template = self.prompt_templates.get("prompt0", "")
        
        # Get chapter name from state
        chapter_name = state.user_inputs.chapter_name
        
        # Fill input fields
        injected = template.replace("[Chapter Name]", chapter_name)
        
        return injected
    
    def inject_prompt1(self, state: PipelineState) -> str:
        """
        Inject values into Prompt 1 template.
        
        Prompt 1 Input Fields:
        - Chapter: [Chapter Name]
        - Concept Inventory: [Output from Prompt 0]
        
        Args:
            state: Current pipeline state
            
        Returns:
            Injected prompt ready for execution
        """
        template = self.prompt_templates.get("prompt1", "")
        
        # Get values from state
        chapter_name = state.user_inputs.chapter_name
        concept_inventory = state.prompt0_output or ""
        
        # Fill input fields
        injected = template.replace("[Chapter Name]", chapter_name)
        injected = injected.replace("[Output from Prompt 0 concept inventories]", concept_inventory)
        
        return injected
    
    def inject_prompt2(self, state: PipelineState) -> str:
        """
        Inject values into Prompt 2 template.
        
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
        
        # Get values from state
        chapter_name = state.user_inputs.chapter_name
        
        # Get selected story from prompt1 output
        selected_story_narrative = ""
        if state.selected_story:
            selected_story_narrative = state.selected_story.get("core_premise", "")
        elif state.prompt1_output:
            # Try to extract from prompt1 output
            selected_story_narrative = self._extract_selected_story(state.prompt1_output)
        
        concept_inventory = state.prompt0_output or ""
        
        # Fill input fields - handle various placeholder formats
        replacements = {
            "(Insert the chapter name used in previous prompts)": chapter_name,
            "(Insert the selected story backbone output from the previous prompt — specifically the **Core Narrative Premise** of the chosen story)": selected_story_narrative,
            "(Insert the **selected story backbone output from the story backbone generation prompt**, specifically the **Core Narrative Premise of the chosen story**)": selected_story_narrative,
            "(Insert the Concept Inventory output generated from Prompt 0)": concept_inventory,
            "(Insert the **Concept Inventory output generated from Prompt 0**)": concept_inventory,
            "[Chapter Name]": chapter_name,
        }
        
        injected = template
        for placeholder, value in replacements.items():
            injected = injected.replace(placeholder, value)
        
        return injected
    
    def inject_prompt3(self, state: PipelineState, learning_step_index: int) -> str:
        """
        Inject values into Prompt 3 template for a specific learning step.
        
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
        
        # Get values from state
        chapter_name = state.user_inputs.chapter_name
        
        # Story backbone
        story_backbone = ""
        if state.selected_story:
            story_backbone = state.selected_story.get("core_premise", "")
        
        # Learning steps
        learning_steps = state.learning_steps_list
        
        # Current learning step
        current_ls = ""
        if 0 <= learning_step_index < len(learning_steps):
            current_ls = str(learning_steps[learning_step_index])
        
        # Previous learning step
        prev_ls = ""
        if learning_step_index > 0:
            prev_ls = str(learning_steps[learning_step_index - 1])
        
        # Next learning step
        next_ls = ""
        if learning_step_index < len(learning_steps) - 1:
            next_ls = str(learning_steps[learning_step_index + 1])
        
        # Fill input fields
        replacements = {
            "(Insert the chapter name used in the previous prompts)": chapter_name,
            "(Insert the **selected story backbone output from the story backbone generation prompt**, specifically the **Core Narrative Premise of the chosen story**)": story_backbone,
            "(Insert the **previous learning step output from the learning step decomposition prompt**)": prev_ls,
            "(Insert the current learning step from the learning step decomposition output)": current_ls,
            "(Insert the **next learning step from the learning step decomposition output**)": next_ls,
            "[Chapter Name]": chapter_name,
        }
        
        injected = template
        for placeholder, value in replacements.items():
            injected = injected.replace(placeholder, value)
        
        return injected
    
    def inject_prompt4(self, state: PipelineState, scene_data: Dict[str, Any]) -> str:
        """
        Inject values into Prompt 4 template for image generation.
        
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
        character_dialogues = "\n".join([
            f"{d.get('speaker', '')}: {d.get('text', '')}"
            for d in dialogues
        ])
        
        # Get the full learning step JSON for context
        current_ls = state.learning_steps_list[state.current_learning_step_index] if state.learning_steps_list else {}
        json_structure = str(current_ls)
        
        # Fill input fields
        replacements = {
            "[SCENE_GOAL]": scene_goal,
            "[TEACHING_NARRATIVE]": teaching_narrative,
            "[CONCEPT_FOCUS]": concept_focus,
            "[CHARACTER_DIALOGUES]": character_dialogues,
            "[SCENE_ID]": scene_id,
            "[JSON_GENERATED]": json_structure,
        }
        
        injected = template
        for placeholder, value in replacements.items():
            injected = injected.replace(placeholder, value)
        
        return injected
    
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
