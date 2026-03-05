"""
Flow Tracker Agent - Controls workflow transitions and manages loops.

Responsible for:
- Knowing current pipeline stage
- Updating state transitions
- Determining next prompt execution
- Managing loops (learning steps and scenes)
"""

from typing import Any, Dict, Literal, Optional
from enum import Enum

from state.pipeline_state import PipelineState


class PipelineStage(str, Enum):
    """Enumeration of all pipeline stages."""
    START = "start"
    PROMPT0 = "prompt0"          # Concept Inventory
    PROMPT1 = "prompt1"          # Story Backbone
    PROMPT2 = "prompt2"          # Learning Steps Decomposition
    PROMPT3_LOOP = "prompt3_loop"  # Learning Step to Scenes (loop)
    PROMPT4_LOOP = "prompt4_loop"  # Scene to Image (loop)
    PPT_GENERATION = "ppt_generation"
    COMPLETE = "complete"
    ERROR = "error"


class FlowTrackerAgent:
    """
    Agent responsible for tracking and controlling the pipeline flow.
    Manages state transitions and determines next steps in the workflow.
    """
    
    def __init__(self):
        """Initialize the Flow Tracker Agent."""
        self.current_stage: PipelineStage = PipelineStage.START
        self.stage_transitions: Dict[PipelineStage, PipelineStage] = {
            PipelineStage.START: PipelineStage.PROMPT0,
            PipelineStage.PROMPT0: PipelineStage.PROMPT1,
            PipelineStage.PROMPT1: PipelineStage.PROMPT2,
            PipelineStage.PROMPT2: PipelineStage.PROMPT3_LOOP,
            PipelineStage.PROMPT3_LOOP: PipelineStage.PROMPT4_LOOP,
            PipelineStage.PROMPT4_LOOP: PipelineStage.PPT_GENERATION,
            PipelineStage.PPT_GENERATION: PipelineStage.COMPLETE,
        }
    
    def get_current_stage(self) -> PipelineStage:
        """Get the current pipeline stage."""
        return self.current_stage
    
    def set_stage(self, stage: PipelineStage) -> None:
        """Manually set the current stage."""
        self.current_stage = stage
    
    def get_next_stage(self) -> PipelineStage:
        """
        Get the next stage in the pipeline.
        
        Returns:
            Next PipelineStage
        """
        return self.stage_transitions.get(self.current_stage, PipelineStage.COMPLETE)
    
    def advance(self) -> PipelineStage:
        """
        Advance to the next stage.
        
        Returns:
            The new current stage
        """
        next_stage = self.get_next_stage()
        self.current_stage = next_stage
        return next_stage
    
    def should_continue_learning_step_loop(self, state: PipelineState) -> bool:
        """
        Determine if we should continue processing learning steps.
        
        Args:
            state: Current pipeline state
            
        Returns:
            True if there are more learning steps to process
        """
        return state.current_learning_step_index < len(state.learning_steps_list)
    
    def should_continue_scene_loop(self, state: PipelineState) -> bool:
        """
        Determine if we should continue processing scenes in current learning step.
        
        Args:
            state: Current pipeline state
            
        Returns:
            True if there are more scenes to process
        """
        from state.pipeline_state import get_scenes_for_current_learning_step
        
        scenes = get_scenes_for_current_learning_step(state)
        return state.current_scene_index < len(scenes)
    
    def get_current_prompt_id(self, stage: PipelineStage) -> str:
        """
        Get the prompt ID for the current stage.
        
        Args:
            stage: Current pipeline stage
            
        Returns:
            Prompt ID string
        """
        stage_to_prompt = {
            PipelineStage.PROMPT0: "prompt0",
            PipelineStage.PROMPT1: "prompt1",
            PipelineStage.PROMPT2: "prompt2",
            PipelineStage.PROMPT3_LOOP: "prompt3",
            PipelineStage.PROMPT4_LOOP: "prompt4",
        }
        return stage_to_prompt.get(stage, "")
    
    def determine_next_action(self, state: PipelineState) -> Dict[str, Any]:
        """
        Determine the next action based on current state.
        
        This is the main decision-making method that Flow Tracker uses
        to guide the LangGraph workflow.
        
        Args:
            state: Current pipeline state
            
        Returns:
            Dictionary with action details:
            {
                "action": "execute_prompt" | "continue_loop" | "next_stage" | "complete",
                "prompt_id": str,
                "learning_step_index": int,
                "scene_index": int,
                "message": str
            }
        """
        # Determine based on current stage
        if self.current_stage == PipelineStage.START:
            return {
                "action": "execute_prompt",
                "prompt_id": "prompt0",
                "learning_step_index": 0,
                "scene_index": 0,
                "message": "Starting pipeline - executing Prompt 0"
            }
        
        elif self.current_stage == PipelineStage.PROMPT0:
            return {
                "action": "execute_prompt",
                "prompt_id": "prompt1",
                "learning_step_index": 0,
                "scene_index": 0,
                "message": "Executing Prompt 1 - Story Backbone"
            }
        
        elif self.current_stage == PipelineStage.PROMPT1:
            return {
                "action": "execute_prompt",
                "prompt_id": "prompt2",
                "learning_step_index": 0,
                "scene_index": 0,
                "message": "Executing Prompt 2 - Learning Steps"
            }
        
        elif self.current_stage == PipelineStage.PROMPT2:
            # Initialize learning step loop
            state.current_learning_step_index = 0
            state.current_scene_index = 0
            return {
                "action": "execute_prompt",
                "prompt_id": "prompt3",
                "learning_step_index": 0,
                "scene_index": 0,
                "message": f"Executing Prompt 3 for Learning Step 1"
            }
        
        elif self.current_stage == PipelineStage.PROMPT3_LOOP:
            if self.should_continue_learning_step_loop(state):
                # Continue with next learning step
                idx = state.current_learning_step_index
                return {
                    "action": "execute_prompt",
                    "prompt_id": "prompt3",
                    "learning_step_index": idx,
                    "scene_index": 0,
                    "message": f"Executing Prompt 3 for Learning Step {idx + 1}"
                }
            else:
                # Move to scene image loop
                return {
                    "action": "next_stage",
                    "prompt_id": "prompt4",
                    "learning_step_index": 0,
                    "scene_index": 0,
                    "message": "All learning steps processed - moving to image generation"
                }
        
        elif self.current_stage == PipelineStage.PROMPT4_LOOP:
            # Check if there are more scenes in current learning step
            if self.should_continue_scene_loop(state):
                idx = state.current_scene_index
                ls_idx = state.current_learning_step_index
                return {
                    "action": "execute_prompt",
                    "prompt_id": "prompt4",
                    "learning_step_index": ls_idx,
                    "scene_index": idx,
                    "message": f"Generating image for Scene {idx + 1} of Learning Step {ls_idx + 1}"
                }
            elif self.should_continue_learning_step_loop(state):
                # Move to next learning step, reset scene index
                state.current_learning_step_index += 1
                state.current_scene_index = 0
                ls_idx = state.current_learning_step_index
                return {
                    "action": "execute_prompt",
                    "prompt_id": "prompt4",
                    "learning_step_index": ls_idx,
                    "scene_index": 0,
                    "message": f"Generating image for Scene 1 of Learning Step {ls_idx + 1}"
                }
            else:
                # All done - move to PPT generation
                return {
                    "action": "next_stage",
                    "prompt_id": "ppt",
                    "learning_step_index": 0,
                    "scene_index": 0,
                    "message": "All images generated - generating PPT"
                }
        
        elif self.current_stage == PipelineStage.PPT_GENERATION:
            return {
                "action": "complete",
                "prompt_id": "",
                "learning_step_index": 0,
                "scene_index": 0,
                "message": "Pipeline complete!"
            }
        
        else:
            return {
                "action": "complete",
                "prompt_id": "",
                "learning_step_index": 0,
                "scene_index": 0,
                "message": "Unknown stage - completing"
            }
    
    def advance_after_prompt_execution(self, state: PipelineState) -> PipelineStage:
        """
        Called after a prompt is executed to determine next stage.
        
        Args:
            state: Current pipeline state
            
        Returns:
            Next PipelineStage
        """
        if self.current_stage == PipelineStage.PROMPT2:
            # Parse learning steps from output and enter loop
            if state.learning_steps_list:
                self.current_stage = PipelineStage.PROMPT3_LOOP
                state.current_prompt_id = "prompt3"
            else:
                self.current_stage = PipelineStage.ERROR
                state.error_message = "No learning steps found in prompt2 output"
        
        elif self.current_stage == PipelineStage.PROMPT3_LOOP:
            # After each prompt3 execution, increment learning step index
            state.current_learning_step_index += 1
            
            if not self.should_continue_learning_step_loop(state):
                # Move to prompt4 loop when all learning steps processed
                self.current_stage = PipelineStage.PROMPT4_LOOP
                state.current_learning_step_index = 0
                state.current_scene_index = 0
                state.current_prompt_id = "prompt4"
            else:
                state.current_prompt_id = "prompt3"
        
        elif self.current_stage == PipelineStage.PROMPT4_LOOP:
            # After each prompt4 execution, increment scene index
            state.current_scene_index += 1
            
            if not self.should_continue_scene_loop(state):
                # Move to next learning step
                state.current_learning_step_index += 1
                state.current_scene_index = 0
            
            if not self.should_continue_learning_step_loop(state):
                # All done - move to PPT generation
                self.current_stage = PipelineStage.PPT_GENERATION
                state.current_prompt_id = "ppt"
            else:
                state.current_prompt_id = "prompt4"
        
        else:
            # Simple advance for prompt0, prompt1
            self.advance()
            state.current_prompt_id = self.get_current_prompt_id(self.current_stage)
        
        return self.current_stage
    
    def reset(self) -> None:
        """Reset the flow tracker to initial state."""
        self.current_stage = PipelineStage.START


def create_flow_tracker() -> FlowTrackerAgent:
    """Factory function to create FlowTrackerAgent."""
    return FlowTrackerAgent()
