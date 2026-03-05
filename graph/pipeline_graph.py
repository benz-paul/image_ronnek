"""
LangGraph Pipeline - Main orchestration graph for the agentic pipeline.

This module defines the LangGraph workflow that:
- Manages state transitions
- Coordinates agents
- Handles loops for learning steps and scenes
- Integrates LangSmith tracing
"""

import os
import json
import re
from pathlib import Path
from typing import Any, Dict, Optional, Union

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI

# Import our custom modules
from state.pipeline_state import PipelineState, create_initial_state
from agents.flow_tracker_agent import FlowTrackerAgent, PipelineStage
from agents.prompt_injector_agent import PromptInjectorAgent
from services.image_generator import ImageGeneratorService
from services.ppt_generator import PPTGeneratorService


# Set up LangSmith if available
def setup_langsmith():
    """Configure LangSmith for tracing."""
    langsmith_api_key = os.getenv("LANGSMITH_API_KEY")
    langsmith_project = os.getenv("LANGSMITH_PROJECT", "storytelling-pipeline")
    
    if langsmith_api_key:
        os.environ["LANGSMITH_API_KEY"] = langsmith_api_key
        os.environ["LANGSMITH_PROJECT"] = langsmith_project
        os.environ["LANGSMITH_TRACING"] = "true"
        return True
    return False


class LLMService:
    """
    Service for executing LLM calls with LangSmith tracing.
    """
    
    def __init__(self, model: str = "gpt-4o-mini", temperature: float = 0.7):
        """
        Initialize LLM service.
        
        Args:
            model: Model name
            temperature: Sampling temperature
        """
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY environment variable not set")
        
        self.llm = ChatOpenAI(
            model=model,
            temperature=temperature,
            max_retries=3,
            timeout=120
        )
    
    def invoke(self, prompt: str, system_message: Optional[str] = None) -> str:
        """
        Invoke the LLM with a prompt.
        
        Args:
            prompt: User prompt
            system_message: Optional system message
            
        Returns:
            LLM response as string
        """
        from langchain_core.messages import HumanMessage, SystemMessage
        
        messages = []
        if system_message:
            messages.append(SystemMessage(content=system_message))
        
        messages.append(HumanMessage(content=prompt))
        
        response = self.llm.invoke(messages)
        return response.content if hasattr(response, 'content') else str(response)


class PipelineGraph:
    """
    Main LangGraph pipeline for the storytelling pipeline.
    """
    
    def __init__(self):
        """Initialize the pipeline."""
        # Set up LangSmith
        setup_langsmith()
        
        # Initialize services
        self.llm_service = LLMService()
        self.flow_tracker = FlowTrackerAgent()
        self.prompt_injector = PromptInjectorAgent()
        self.image_generator = ImageGeneratorService()
        self.ppt_generator = PPTGeneratorService()
        
        # Create the graph
        self.graph = self._create_graph()
    
    def _create_graph(self) -> StateGraph:
        """
        Create the LangGraph state graph.
        
        Returns:
            Compiled StateGraph
        """
        # Define the graph
        graph = StateGraph(PipelineState)
        
        # Add nodes
        graph.add_node("initialize", self._node_initialize)
        graph.add_node("execute_prompt0", self._node_execute_prompt0)
        graph.add_node("execute_prompt1", self._node_execute_prompt1)
        graph.add_node("execute_prompt2", self._node_execute_prompt2)
        graph.add_node("execute_prompt3", self._node_execute_prompt3)
        graph.add_node("execute_prompt4", self._node_execute_prompt4)
        graph.add_node("generate_ppt", self._node_generate_ppt)
        graph.add_node("check_continuation", self._node_check_continuation)
        
        # Set entry point
        graph.set_entry_point("initialize")
        
        # Add edges
        graph.add_edge("initialize", "execute_prompt0")
        graph.add_edge("execute_prompt0", "execute_prompt1")
        graph.add_edge("execute_prompt1", "execute_prompt2")
        graph.add_edge("execute_prompt2", "execute_prompt3")
        graph.add_edge("execute_prompt3", "check_continuation")
        graph.add_edge("execute_prompt4", "check_continuation")
        graph.add_edge("generate_ppt", END)
        
        # Compile with checkpointer
        checkpointer = MemorySaver()
        return graph.compile(checkpointer=checkpointer)
    
    def _node_initialize(self, state: PipelineState) -> Dict[str, Any]:
        """
        Initialize node - set up run folder and PDF.
        
        Args:
            state: Current pipeline state
            
        Returns:
            State updates
        """
        # Create run folder
        folder_name = f"{state.user_inputs.class_level}_{state.user_inputs.subject}_{state.user_inputs.chapter_name}".lower().replace(" ", "_")
        state.run_folder = f"outputs/{folder_name}"
        
        # Create necessary directories
        Path(state.run_folder).mkdir(parents=True, exist_ok=True)
        Path(state.run_folder) / "learning_steps".mkdir(exist_ok=True)
        Path(state.run_folder) / "images".mkdir(exist_ok=True)
        
        # Set initial prompt ID
        state.current_prompt_id = "prompt0"
        
        # Handle PDF - check knowledge folder first (PRESERVED from original)
        # This is handled externally before running the graph
        # But we ensure state.pdf_path is set
        
        return {"current_prompt_id": "prompt0"}
    
    def _node_execute_prompt0(self, state: PipelineState) -> Dict[str, Any]:
        """
        Execute Prompt 0 - Concept Inventory Extraction.
        
        Args:
            state: Current pipeline state
            
        Returns:
            State updates
        """
        # Inject prompt
        injected_prompt = self.prompt_injector.inject_prompt0(state)
        
        # Execute via LLM (with PDF attachment would happen here in real implementation)
        # For now, execute with the injected prompt
        response = self.llm_service.invoke(injected_prompt)
        
        # Store output
        state.prompt0_output = response
        
        # Save to file
        run_folder = Path(state.run_folder)
        (run_folder / "prompts").mkdir(exist_ok=True)
        (run_folder / "prompts" / "prompt0_injected.txt").write_text(injected_prompt)
        (run_folder / "outputs" / "prompt0_output.txt").write_text(response)
        
        return {"prompt0_output": response, "current_prompt_id": "prompt1"}
    
    def _node_execute_prompt1(self, state: PipelineState) -> Dict[str, Any]:
        """
        Execute Prompt 1 - Story Backbone Generation.
        
        Args:
            state: Current pipeline state
            
        Returns:
            State updates
        """
        # Inject prompt
        injected_prompt = self.prompt_injector.inject_prompt1(state)
        
        # Execute via LLM
        response = self.llm_service.invoke(injected_prompt)
        
        # Store output
        state.prompt1_output = response
        
        # Parse and select best story
        selected_story = self._parse_story_backbone(response)
        state.selected_story = selected_story
        
        # Save to file
        run_folder = Path(state.run_folder)
        (run_folder / "prompts" / "prompt1_injected.txt").write_text(injected_prompt)
        (run_folder / "outputs" / "prompt1_output.txt").write_text(response)
        
        return {"prompt1_output": response, "selected_story": selected_story, "current_prompt_id": "prompt2"}
    
    def _node_execute_prompt2(self, state: PipelineState) -> Dict[str, Any]:
        """
        Execute Prompt 2 - Learning Steps Decomposition.
        
        Args:
            state: Current pipeline state
            
        Returns:
            State updates
        """
        # Inject prompt
        injected_prompt = self.prompt_injector.inject_prompt2(state)
        
        # Execute via LLM
        response = self.llm_service.invoke(injected_prompt)
        
        # Store output
        state.prompt2_output = response
        
        # Parse learning steps
        learning_steps = self._parse_learning_steps(response)
        state.learning_steps_list = learning_steps
        
        # Save to file
        run_folder = Path(state.run_folder)
        (run_folder / "prompts" / "prompt2_injected.txt").write_text(injected_prompt)
        (run_folder / "outputs" / "prompt2_output.txt").write_text(response)
        
        # Save learning steps JSON
        learning_steps_dir = run_folder / "learning_steps"
        for i, ls in enumerate(learning_steps):
            ls_path = learning_steps_dir / f"LS{i+1}.json"
            with open(ls_path, "w") as f:
                json.dump(ls, f, indent=2)
            state.learning_step_json_paths.append(str(ls_path))
        
        return {
            "prompt2_output": response,
            "learning_steps_list": learning_steps,
            "learning_step_json_paths": state.learning_step_json_paths,
            "current_learning_step_index": 0,
            "current_prompt_id": "prompt3"
        }
    
    def _node_execute_prompt3(self, state: PipelineState) -> Dict[str, Any]:
        """
        Execute Prompt 3 - Learning Step to Scenes Generation.
        
        Args:
            state: Current pipeline state
            
        Returns:
            State updates
        """
        current_index = state.current_learning_step_index
        
        # Inject prompt for current learning step
        injected_prompt = self.prompt_injector.inject_prompt3(state, current_index)
        
        # Execute via LLM
        response = self.llm_service.invoke(injected_prompt)
        
        # Parse the response into scenes JSON
        scenes_json = self._parse_scenes_json(response)
        
        # Save to file
        run_folder = Path(state.run_folder)
        ls_path = run_folder / "learning_steps" / f"LS{current_index + 1}_scenes.json"
        
        # Update the learning step with scenes
        if current_index < len(state.learning_steps_list):
            state.learning_steps_list[current_index]["scenes"] = scenes_json.get("scenes", [])
            
            with open(ls_path, "w") as f:
                json.dump(scenes_json, f, indent=2)
        
        # Save prompt
        (run_folder / "prompts" / f"prompt3_LS{current_index + 1}_injected.txt").write_text(injected_prompt)
        
        return {
            "learning_steps_list": state.learning_steps_list,
            "current_prompt_id": "prompt4"
        }
    
    def _node_execute_prompt4(self, state: PipelineState) -> Dict[str, Any]:
        """
        Execute Prompt 4 - Scene Image Generation.
        
        Args:
            state: Current pipeline state
            
        Returns:
            State updates
        """
        ls_index = state.current_learning_step_index
        scene_index = state.current_scene_index
        
        # Get current learning step and scene
        if ls_index >= len(state.learning_steps_list):
            return {"current_prompt_id": "ppt"}
        
        current_ls = state.learning_steps_list[ls_index]
        scenes = current_ls.get("scenes", [])
        
        if scene_index >= len(scenes):
            return {"current_prompt_id": "ppt"}
        
        current_scene = scenes[scene_index]
        
        # Inject prompt for image generation
        injected_prompt = self.prompt_injector.inject_prompt4(state, current_scene)
        
        # Generate image (or image prompt)
        result = self.image_generator.generate_image(
            scene_data=current_scene,
            state=state,
            learning_step_id=f"LS{ls_index + 1}"
        )
        
        # Save image prompt
        run_folder = Path(state.run_folder)
        (run_folder / "images" / f"LS{ls_index + 1}_{current_scene.get('scene_id', 'S1')}.txt").write_text(
            result.get("image_prompt", "")
        )
        
        # Track image path
        state.image_paths.append(result.get("image_path", ""))
        
        return {
            "image_paths": state.image_paths,
            "current_scene_index": scene_index + 1
        }
    
    def _node_check_continuation(self, state: PipelineState) -> str:
        """
        Check if we should continue loops or move to next stage.
        
        Args:
            state: Current pipeline state
            
        Returns:
            Next node name
        """
        current_prompt = state.current_prompt_id
        
        if current_prompt == "prompt3":
            # Check if more learning steps to process
            if state.current_learning_step_index < len(state.learning_steps_list):
                # Continue with next learning step
                return "execute_prompt3"
            else:
                # Move to image generation
                state.current_learning_step_index = 0
                state.current_scene_index = 0
                state.current_prompt_id = "prompt4"
                return "execute_prompt4"
        
        elif current_prompt == "prompt4":
            # Check if more scenes to process
            ls_index = state.current_learning_step_index
            scene_index = state.current_scene_index
            
            if ls_index < len(state.learning_steps_list):
                current_ls = state.learning_steps_list[ls_index]
                scenes = current_ls.get("scenes", [])
                
                if scene_index < len(scenes):
                    # Continue with next scene
                    return "execute_prompt4"
                else:
                    # Move to next learning step
                    state.current_learning_step_index += 1
                    state.current_scene_index = 0
                    
                    if state.current_learning_step_index < len(state.learning_steps_list):
                        return "execute_prompt4"
            
            # All done - generate PPT
            return "generate_ppt"
        
        return "generate_ppt"
    
    def _node_generate_ppt(self, state: PipelineState) -> Dict[str, Any]:
        """
        Generate the final PowerPoint presentation.
        
        Args:
            state: Current pipeline state
            
        Returns:
            State updates
        """
        # Generate PPT
        output_path = self.ppt_generator.generate_ppt(
            state=state,
            learning_steps_dir=str(Path(state.run_folder) / "learning_steps"),
            output_filename="lesson_output.pptx"
        )
        
        state.ppt_output_path = output_path
        state.is_complete = True
        
        return {
            "ppt_output_path": output_path,
            "is_complete": True
        }
    
    def _parse_story_backbone(self, response: str) -> Dict[str, Any]:
        """
        Parse the story backbone response to extract selected story.
        
        Args:
            response: Raw LLM response
            
        Returns:
            Selected story dictionary
        """
        # Try to extract the first/best story
        title = "Selected Story"
        core_premise = response[:500]  # Default to first 500 chars
        
        # Try to find title
        title_match = re.search(r"(?:Story Title|Title)[:\s]+(.+?)(?:\n|$)", response, re.IGNORECASE)
        if title_match:
            title = title_match.group(1).strip()
        
        # Try to find core premise
        premise_match = re.search(
            r"(?:Core Narrative Premise|Premise)[:\s]+(.+?)(?=\n\d+\.|\n---|\n\*\*|\nOverall|\Z)",
            response, re.DOTALL | re.IGNORECASE
        )
        if premise_match:
            core_premise = premise_match.group(1).strip()
        
        return {
            "title": title,
            "core_premise": core_premise,
            "raw_response": response
        }
    
    def _parse_learning_steps(self, response: str) -> list:
        """
        Parse learning steps from prompt 2 output.
        
        Args:
            response: Raw LLM response
            
        Returns:
            List of learning step dictionaries
        """
        learning_steps = []
        
        # Simple parsing - split by numbered steps
        step_pattern = r"(?:Learning Step|Step)\s*(\d+)[:\s]*(.+?)(?=(?:Learning Step|Step)\s*\d+[:\s]|$)"
        matches = re.finditer(step_pattern, response, re.DOTALL | re.IGNORECASE)
        
        for match in matches:
            step_id = match.group(1).strip()
            step_content = match.group(2).strip()
            
            # Extract title
            title = f"Learning Step {step_id}"
            title_match = re.search(r"Title[:\s]*(.+?)(?:\n|$)", step_content, re.IGNORECASE)
            if title_match:
                title = title_match.group(1).strip()
            
            # Extract concepts
            concepts = []
            concepts_match = re.search(
                r"Concepts Introduced[:\s]*(.+?)(?=\nNarrative|$)",
                step_content, re.DOTALL | re.IGNORECASE
            )
            if concepts_match:
                concepts_text = concepts_match.group(1)
                concepts = [c.strip().lstrip("*-").strip() for c in concepts_text.split("\n") if c.strip()]
            
            # Extract narrative moment
            narrative = ""
            narrative_match = re.search(
                r"Narrative Moment[:\s]*(.+?)(?=\nConcept Coverage|$)",
                step_content, re.DOTALL | re.IGNORECASE
            )
            if narrative_match:
                narrative = narrative_match.group(1).strip()
            
            learning_steps.append({
                "learning_step_id": f"LS{step_id}",
                "title": title,
                "concepts_introduced": concepts,
                "narrative_moment": narrative,
                "scenes": []
            })
        
        # If no structured parsing worked, create a simple entry
        if not learning_steps:
            learning_steps.append({
                "learning_step_id": "LS1",
                "title": "Learning Step 1",
                "concepts_introduced": [],
                "narrative_moment": response[:500],
                "scenes": []
            })
        
        return learning_steps
    
    def _parse_scenes_json(self, response: str) -> Dict[str, Any]:
        """
        Parse scenes JSON from prompt 3 response.
        
        Args:
            response: Raw LLM response
            
        Returns:
            Scenes dictionary
        """
        # Try to extract JSON
        response = response.strip()
        
        # Remove markdown code blocks if present
        if response.startswith("```json"):
            response = response[7:]
        elif response.startswith("```"):
            response = response[3:]
        
        if response.endswith("```"):
            response = response[:-3]
        
        response = response.strip()
        
        try:
            return json.loads(response)
        except json.JSONDecodeError:
            # If parsing fails, return a minimal structure
            return {
                "scenes": [
                    {
                        "scene_id": "S1",
                        "scene_order": 1,
                        "scene_phase": "hook",
                        "scene_goal": "Generated scene",
                        "concept_focus": "",
                        "emotional_tone": "neutral",
                        "visual_setting": {
                            "environment": "",
                            "atmosphere": ""
                        },
                        "narrative": {
                            "screenplay": response[:500],
                            "camera_suggestion": "",
                            "action_flow": ""
                        },
                        "dialogue": []
                    }
                ]
            }
    
    def run(
        self,
        chapter_name: str,
        class_level: str,
        subject: str,
        chapter_number: str = "",
        medium: str = "English",
        pdf_path: Optional[str] = None
    ) -> PipelineState:
        """
        Run the complete pipeline.
        
        Args:
            chapter_name: Name of the chapter
            class_level: Class level
            subject: Subject
            chapter_number: Chapter number
            medium: Language medium
            pdf_path: Path to PDF file (if already available)
            
        Returns:
            Final pipeline state
        """
        # Create initial state
        state = create_initial_state(
            chapter_name=chapter_name,
            class_level=class_level,
            subject=subject,
            chapter_number=chapter_number,
            medium=medium
        )
        
        # Set PDF path if provided
        if pdf_path:
            state.pdf_path = pdf_path
            state.pdf_source = "provided"
        
        # Create run folder
        folder_name = f"{class_level}_{subject}_{chapter_name}".lower().replace(" ", "_")
        state.run_folder = f"outputs/{folder_name}"
        Path(state.run_folder).mkdir(parents=True, exist_ok=True)
        Path(state.run_folder) / "learning_steps".mkdir(exist_ok=True)
        Path(state.run_folder) / "images".mkdir(exist_ok=True)
        Path(state.run_folder) / "prompts".mkdir(exist_ok=True)
        Path(state.run_folder) / "outputs".mkdir(exist_ok=True)
        
        # Run the graph
        config = {"configurable": {"thread_id": "storytelling-pipeline"}}
        
        final_state = None
        for state_update in self.graph.stream(state, config):
            final_state = state_update
        
        return final_state if final_state else state


def create_pipeline_graph() -> PipelineGraph:
    """Factory function to create PipelineGraph."""
    return PipelineGraph()
