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
            model=model, temperature=temperature, max_retries=3, timeout=120
        )

    def invoke(
        self,
        prompt: str,
        system_message: Optional[str] = None,
        attachments: Optional[list] = None,
    ) -> str:
        """
        Invoke the LLM with a prompt.

        Args:
            prompt: User prompt
            system_message: Optional system message
            attachments: Optional list of file paths (PDFs, images) to attach

        Returns:
            LLM response as string
        """
        from langchain_core.messages import HumanMessage, SystemMessage

        messages = []
        if system_message:
            messages.append(SystemMessage(content=system_message))

        # Handle attachments (PDF, images)
        content_parts = [{"type": "text", "text": prompt}]

        if attachments:
            for attachment_path in attachments:
                if Path(attachment_path).exists():
                    file_path = Path(attachment_path)

                    if file_path.suffix.lower() == ".pdf":
                        from pypdf import PdfReader

                        pdf_text = []
                        reader = PdfReader(attachment_path)
                        for page in reader.pages:
                            text = page.extract_text()
                            if text:
                                pdf_text.append(text)

                        full_text = "\n\n".join(pdf_text)
                        content_parts.append(
                            {
                                "type": "text",
                                "text": f"\n\n[PDF CONTENT FROM {file_path.name}]\n{full_text}",
                            }
                        )

        messages.append(HumanMessage(content=content_parts))

        response = self.llm.invoke(messages)
        return response.content if hasattr(response, "content") else str(response)


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
        graph.add_node("image_check", self._node_image_check)
        graph.add_node("execute_prompt4", self._node_execute_prompt4)
        graph.add_node("generate_ppt", self._node_generate_ppt)

        # Set entry point
        graph.set_entry_point("initialize")

        # Add edges
        graph.add_edge("initialize", "execute_prompt0")
        graph.add_edge("execute_prompt0", "execute_prompt1")
        graph.add_edge("execute_prompt1", "execute_prompt2")
        graph.add_edge("execute_prompt2", "execute_prompt3")

        # Conditional edges for loop handling - create router functions
        def router_prompt3(state: PipelineState) -> str:
            """Router for prompt3 loop.

            After prompt3 runs, index is incremented. We check if there
            are more learning steps to process.
            """
            current_idx = state.current_learning_step_index
            total_ls = len(state.learning_steps_list)

            # If current_idx >= total_ls, all learning steps are processed
            if current_idx >= total_ls:
                return "image_check"

            # If there are more learning steps, continue with prompt3
            return "execute_prompt3"

        def router_prompt4(state: PipelineState) -> str:
            """Router for prompt4 loop.

            Checks if there are more scenes to process in current learning step,
            or more learning steps to process.
            """
            ls_index = state.current_learning_step_index
            scene_index = state.current_scene_index
            total_ls = len(state.learning_steps_list)

            # If all learning steps are done, go to ppt_check
            if ls_index >= total_ls:
                return "ppt_check"

            # Get current learning step's scenes
            current_ls = state.learning_steps_list[ls_index]
            scenes = current_ls.get("scenes", [])

            print(
                f"  DEBUG ROUTER: LS{ls_index + 1} - scenes from state: {len(scenes)}"
            )

            # If no scenes at root, check in learning_steps array
            if not scenes and "learning_steps" in current_ls:
                ls_arr = current_ls.get("learning_steps", [])
                # Find matching LS by ID
                for ls in ls_arr:
                    ls_id = ls.get("learning_step_id", "")
                    if (
                        ls_id == f"LS{ls_index + 1}"
                        or ls_id == f"LS{ls_index + 1}".replace("LS", "")
                    ):
                        scenes = ls.get("scenes", [])
                        break
                if not scenes and ls_arr:
                    scenes = ls_arr[0].get("scenes", [])

            total_scenes = len(scenes)

            # If current scene index >= total scenes, check next learning step
            if scene_index >= total_scenes:
                next_ls_index = ls_index + 1
                if next_ls_index >= total_ls:
                    return "ppt_check"
                else:
                    # Will move to next learning step in the node
                    return "execute_prompt4"

            # More scenes in current learning step
            return "execute_prompt4"

        graph.add_conditional_edges(
            "execute_prompt3",
            router_prompt3,
            {
                "execute_prompt3": "execute_prompt3",
                "image_check": "image_check",
            },
        )

        # Image check conditional - ask user if they want to generate images
        def router_image_check(state: PipelineState) -> str:
            """Router for image check - depends on user decision stored in state."""
            if getattr(state, "generate_images", False):
                return "execute_prompt4"
            else:
                return "END"

        graph.add_conditional_edges(
            "image_check",
            router_image_check,
            {
                "execute_prompt4": "execute_prompt4",
                "END": END,
            },
        )
        graph.add_conditional_edges(
            "execute_prompt4",
            router_prompt4,
            {
                "execute_prompt4": "execute_prompt4",
                "ppt_check": "ppt_check",
            },
        )

        # Add PPT check node
        graph.add_node("ppt_check", self._node_ppt_check)

        # PPT check conditional
        def router_ppt_check(state: PipelineState) -> str:
            """Router for PPT check - depends on user decision stored in state."""
            if getattr(state, "generate_ppt", False):
                return "generate_ppt"
            else:
                return "END"

        graph.add_conditional_edges(
            "ppt_check",
            router_ppt_check,
            {
                "generate_ppt": "generate_ppt",
                "END": END,
            },
        )
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
        # Create run folder - use chapter_title to avoid duplication
        folder_title = state.user_inputs.chapter_title or state.user_inputs.chapter_name
        folder_name = f"{state.user_inputs.class_level}_{state.user_inputs.subject}_{folder_title}".lower().replace(
            " ", "_"
        )
        state.run_folder = f"outputs/{folder_name}"

        # Create necessary directories
        Path(state.run_folder).mkdir(parents=True, exist_ok=True)
        (Path(state.run_folder) / "learning_steps").mkdir(
            exist_ok=True
        )  # Prompt2 outputs
        (Path(state.run_folder) / "scenes").mkdir(exist_ok=True)  # Prompt3 outputs
        (Path(state.run_folder) / "images").mkdir(exist_ok=True)  # Prompt4 outputs

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

        # Execute via LLM with PDF attachment
        pdf_attachments = []
        if state.pdf_path and Path(state.pdf_path).exists():
            pdf_attachments.append(state.pdf_path)
            print(f"  Attaching PDF: {state.pdf_path}")

        response = self.llm_service.invoke(injected_prompt, attachments=pdf_attachments)

        # Store output
        state.prompt0_output = response

        # Save to file
        run_folder = Path(state.run_folder)
        (run_folder / "prompts").mkdir(exist_ok=True)
        (run_folder / "prompts" / "prompt0_injected.txt").write_text(
            injected_prompt, encoding="utf-8"
        )
        (run_folder / "outputs" / "prompt0_output.txt").write_text(
            response, encoding="utf-8"
        )

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

        # Debug: print response info
        print(
            f"  DEBUG: Response type: {type(response)}, length: {len(response) if response else 0}"
        )

        # Store output
        state.prompt1_output = response

        # Parse and select best story
        selected_story = self._parse_story_backbone(response)
        print(
            f"  DEBUG: Parsed selected_story: {selected_story.get('title', 'NONE')} - premise length: {len(selected_story.get('core_premise', ''))}"
        )
        state.selected_story = selected_story

        # Verify storage
        print(
            f"  DEBUG: Stored state.selected_story: {state.selected_story.get('title', 'NONE')} - premise length: {len(state.selected_story.get('core_premise', ''))}"
        )

        # Save to file
        run_folder = Path(state.run_folder)
        (run_folder / "prompts" / "prompt1_injected.txt").write_text(
            injected_prompt, encoding="utf-8"
        )
        (run_folder / "outputs" / "prompt1_output.txt").write_text(
            response, encoding="utf-8"
        )

        return {
            "prompt1_output": response,
            "selected_story": selected_story,
            "current_prompt_id": "prompt2",
        }

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

        # Debug: print response info
        print(
            f"  DEBUG: Response type: {type(response)}, length: {len(response) if response else 0}"
        )

        # Store output
        state.prompt2_output = response

        # Parse learning steps
        learning_steps = self._parse_learning_steps(response)
        state.learning_steps_list = learning_steps

        # Save to file
        run_folder = Path(state.run_folder)
        (run_folder / "prompts" / "prompt2_injected.txt").write_text(
            injected_prompt, encoding="utf-8"
        )
        (run_folder / "outputs" / "prompt2_output.txt").write_text(
            response, encoding="utf-8"
        )

        # Save learning steps JSON
        learning_steps_dir = run_folder / "learning_steps"
        for i, ls in enumerate(learning_steps):
            ls_path = learning_steps_dir / f"LS{i + 1}.json"
            with open(ls_path, "w", encoding="utf-8") as f:
                json.dump(ls, f, indent=2)
            state.learning_step_json_paths.append(str(ls_path))

        return {
            "prompt2_output": response,
            "learning_steps_list": learning_steps,
            "learning_step_json_paths": state.learning_step_json_paths,
            "current_learning_step_index": 0,
            "current_prompt_id": "prompt3",
        }

    def _node_image_check(self, state: PipelineState) -> Dict[str, Any]:
        """
        Ask user if they want to generate images.

        Args:
            state: Current pipeline state

        Returns:
            State updates with generate_images flag
        """
        print("\n" + "=" * 50)
        print("  Learning Steps Generation Complete!")
        print(f"  Generated {len(state.learning_steps_list)} learning steps")
        print("=" * 50)

        response = input("\nDo you want to generate images? (y/n): ").strip().lower()
        generate_images = response in ["y", "yes"]

        if generate_images:
            print("\nProceeding to image generation...")
        else:
            print("\nSkipping image generation.")
            print("Pipeline will end here. No PPT will be generated.")

        return {"generate_images": generate_images}

    def _node_ppt_check(self, state: PipelineState) -> Dict[str, Any]:
        """
        Ask user if they want to generate PPT.

        Args:
            state: Current pipeline state

        Returns:
            State updates with generate_ppt flag
        """
        print("\n" + "=" * 50)
        print("  Image Generation Complete!")
        print(f"  Generated {len(state.image_paths)} images")
        print("=" * 50)

        response = input("\nDo you want to generate PPT? (y/n): ").strip().lower()
        generate_ppt = response in ["y", "yes"]

        if generate_ppt:
            print("\nProceeding to PPT generation...")
        else:
            print("\nSkipping PPT generation.")
            print("Pipeline will end here.")

        return {"generate_ppt": generate_ppt}

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

        # Save to file (separate folder for prompt3 outputs)
        run_folder = Path(state.run_folder)
        ls_path = run_folder / "scenes" / f"LS{current_index + 1}_scenes.json"

        # Debug: print what we got
        print(f"  DEBUG: LS{current_index + 1} - JSON keys: {list(scenes_json.keys())}")

        # Update the learning step with scenes - handle different JSON formats
        scenes = scenes_json.get("scenes", [])

        # If scenes not at root, check inside learning_steps array
        if not scenes and "learning_steps" in scenes_json:
            learning_steps_arr = scenes_json.get("learning_steps", [])
            print(
                f"  DEBUG: LS{current_index + 1} - Found {len(learning_steps_arr)} learning steps in JSON"
            )
            # Find scenes for the current learning step
            for ls in learning_steps_arr:
                ls_id = ls.get("learning_step_id", "")
                print(f"  DEBUG: LS{current_index + 1} - Checking LS ID: {ls_id}")
                if (
                    ls_id == f"LS{current_index + 1}"
                    or ls_id == f"LS{current_index + 1}".replace("LS", "")
                ):
                    scenes = ls.get("scenes", [])
                    print(
                        f"  DEBUG: LS{current_index + 1} - Found scenes for {ls_id}: {len(scenes)}"
                    )
                    break
            # If not found by ID, just use the first one
            if not scenes and learning_steps_arr:
                scenes = learning_steps_arr[0].get("scenes", [])
                print(
                    f"  DEBUG: LS{current_index + 1} - Using first LS scenes: {len(scenes)}"
                )

        print(f"  DEBUG: LS{current_index + 1} - Total scenes extracted: {len(scenes)}")

        if current_index < len(state.learning_steps_list):
            state.learning_steps_list[current_index]["scenes"] = scenes

            with open(ls_path, "w", encoding="utf-8") as f:
                json.dump(scenes_json, f, indent=2)

        # Save prompt
        (
            run_folder / "prompts" / f"prompt3_LS{current_index + 1}_injected.txt"
        ).write_text(injected_prompt, encoding="utf-8")

        # Update indices for next iteration
        next_index = current_index + 1

        return {
            "learning_steps_list": state.learning_steps_list,
            "current_learning_step_index": next_index,
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
            return {}

        current_ls = state.learning_steps_list[ls_index]
        scenes = current_ls.get("scenes", [])

        if scene_index >= len(scenes):
            return {}

        current_scene = scenes[scene_index]

        # Inject prompt for image generation
        injected_prompt = self.prompt_injector.inject_prompt4(state, current_scene)

        # Generate image (or image prompt)
        result = self.image_generator.generate_image(
            scene_data=current_scene, state=state, learning_step_id=f"LS{ls_index + 1}"
        )

        # Save image prompt
        run_folder = Path(state.run_folder)
        (
            run_folder
            / "images"
            / f"LS{ls_index + 1}_{current_scene.get('scene_id', 'S1')}.txt"
        ).write_text(result.get("image_prompt", ""), encoding="utf-8")

        # Track image path
        state.image_paths.append(result.get("image_path", ""))

        # Calculate next indices
        next_scene_index = scene_index + 1
        next_ls_index = ls_index

        # Check if we need to move to next learning step
        if next_scene_index >= len(scenes):
            # Move to next learning step
            next_ls_index = ls_index + 1
            next_scene_index = 0

        # Check if all done
        all_done = next_ls_index >= len(state.learning_steps_list)

        return {
            "image_paths": state.image_paths,
            "current_scene_index": next_scene_index,
            "current_learning_step_index": next_ls_index,
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

                    if state.current_learning_step_index < len(
                        state.learning_steps_list
                    ):
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
            output_filename="lesson_output.pptx",
        )

        state.ppt_output_path = output_path
        state.is_complete = True

        return {"ppt_output_path": output_path, "is_complete": True}

    def _parse_story_backbone(self, response: str) -> Dict[str, Any]:
        """
        Parse the story backbone response to extract selected story (JSON format).

        Args:
            response: Raw LLM response (JSON)

        Returns:
            Selected story dictionary
        """
        # Clean the response - remove markdown code blocks if present
        response = response.strip()
        if response.startswith("```json"):
            response = response[7:]
        elif response.startswith("```"):
            response = response[3:]
        if response.endswith("```"):
            response = response[:-3]
        response = response.strip()

        try:
            data = json.loads(response)
            # Try to get selected_story first
            selected = data.get("selected_story", {})
            if selected:
                title = selected.get("title", "Selected Story")
                # Check both possible key names
                core_premise = selected.get(
                    "core_narrative_premise", ""
                ) or selected.get("core_premise", "")
                print(
                    f"  DEBUG: JSON Parsed - title: {title}, premise length: {len(core_premise)}"
                )
                return {
                    "title": title,
                    "core_premise": core_premise,
                    "raw_response": response,
                }

            # Fallback to first story in stories array
            stories = data.get("stories", [])
            if stories:
                first_story = stories[0]
                title = first_story.get("title", "Selected Story")
                core_premise = first_story.get(
                    "core_narrative_premise", ""
                ) or first_story.get("core_premise", "")
                print(
                    f"  DEBUG: JSON Parsed (fallback) - title: {title}, premise length: {len(core_premise)}"
                )
                return {
                    "title": title,
                    "core_premise": core_premise,
                    "raw_response": response,
                }

            print(f"  DEBUG: JSON Parsed - No selected_story or stories found")
            return {
                "title": "Selected Story",
                "core_premise": "",
                "raw_response": response,
            }

        except json.JSONDecodeError as e:
            print(f"  DEBUG: JSON parsing failed: {e}")
            # Fallback: parse text format
            print("  DEBUG: Trying text format fallback...")

            # Try to find story title - fix to remove prefixes like "Overview:", "Story Overview:"
            title = "Selected Story"
            title_match = re.search(
                r"(?:Title|Story)[:\s]+\*?(.+?)(?:\n|$|\*\*)", response, re.IGNORECASE
            )
            if title_match:
                title = title_match.group(1).strip()
                title = re.sub(r"^\*+|\*+$", "", title).strip()
                # Remove prefixes like "Overview:", "Story Overview:"
                title = re.sub(
                    r"^(?:Overview|Story Overview)[:\s]*",
                    "",
                    title,
                    flags=re.IGNORECASE,
                ).strip()

            # Try to find core premise - get FULL text, not truncated
            core_premise = ""
            # Look for "Core Narrative Premise:" or "Core Premise:" followed by content
            premise_match = re.search(
                r"(?:Core Narrative Premise|Core Premise)[:\s]*\n?(.+?)(?=\n\n|\n###|\n---|$)",
                response,
                re.DOTALL | re.IGNORECASE,
            )
            if premise_match:
                core_premise = premise_match.group(1).strip()
                # Don't truncate - get full story

            print(
                f"  DEBUG: Text fallback - title: {title}, premise length: {len(core_premise)}"
            )

            return {
                "title": title,
                "core_premise": core_premise,
                "raw_response": response,
            }

    def _parse_learning_steps(self, response: str) -> list:
        """
        Parse learning steps from prompt 2 output (JSON format).

        Args:
            response: Raw LLM response (JSON)

        Returns:
            List of learning step dictionaries
        """
        # Clean the response - remove markdown code blocks if present
        response = response.strip()
        if response.startswith("```json"):
            response = response[7:]
        elif response.startswith("```"):
            response = response[3:]
        if response.endswith("```"):
            response = response[:-3]
        response = response.strip()

        try:
            data = json.loads(response)
            learning_steps = data.get("learning_steps", [])
            print(f"  DEBUG: Parsed {len(learning_steps)} learning steps from JSON")
            return learning_steps
        except json.JSONDecodeError as e:
            print(f"  DEBUG: JSON parsing failed: {e}")
            # Fallback - try to find any JSON-like structure
            return []

        # If we get here, JSON parsing succeeded but returned empty
        # Add text fallback
        print("  DEBUG: JSON returned empty, trying text fallback...")

        # Parse text format - improved to extract more details
        learning_steps = []

        # Look for numbered learning steps with more context
        # Pattern: "1. Title" or "LS1 - Title" or "**Title**"
        ls_pattern = r"(?:\d+[.\s]+|LS\d+[.\s-]+)\*?([^\n]+)\*?"
        matches = list(re.finditer(ls_pattern, response, re.IGNORECASE))

        for i, match in enumerate(matches):
            title = match.group(1).strip()[:100]

            # Try to find narrative/description after the title
            # Look for text between this match and the next numbered item
            start_pos = match.end()
            next_pos = matches[i + 1].start() if i + 1 < len(matches) else len(response)
            between_text = response[start_pos:next_pos].strip()

            # Clean up the description - remove bullets, get first paragraph
            narrative = (
                between_text[:500]
                if between_text
                else f"Learning step {i + 1}: {title}"
            )
            # Remove bullet points and numbering
            narrative = re.sub(r"^[\s\d\.\-\*]+", "", narrative, flags=re.MULTILINE)
            narrative = narrative.split("\n\n")[0][:500]  # First paragraph only

            learning_steps.append(
                {
                    "learning_step_id": f"LS{i + 1}",
                    "title": title,
                    "concepts_introduced": [],  # Keep empty if not found
                    "narrative_moment": narrative,
                    "scenes": [],
                }
            )

        if learning_steps:
            print(f"  DEBUG: Text fallback found {len(learning_steps)} learning steps")
            for i, ls in enumerate(learning_steps[:3]):
                print(f"    LS{i + 1}: {ls.get('title', 'NO TITLE')[:50]}")
                print(f"    Narrative: {ls.get('narrative_moment', '')[:50]}...")

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
                        "visual_setting": {"environment": "", "atmosphere": ""},
                        "narrative": {
                            "screenplay": response[:500],
                            "camera_suggestion": "",
                            "action_flow": "",
                        },
                        "dialogue": [],
                    }
                ]
            }

    def run(
        self,
        chapter_name: str,
        class_level: str,
        subject: str,
        chapter_number: str = "",
        chapter_title: str = "",
        medium: str = "English",
        pdf_path: Optional[str] = None,
    ) -> PipelineState:
        """
        Run the complete pipeline.

        Args:
            chapter_name: Full name of the chapter (e.g., "Class 10 Maths Chapter 5 Arithmetic Progression")
            chapter_title: Short title (e.g., "Arithmetic Progression")
            class_level: Class level
            subject: Subject
            chapter_number: Chapter number
            medium: Language medium
            pdf_path: Path to PDF file (if already available)

        Returns:
            Final pipeline state
        """
        # Use chapter_title for folder naming, fallback to chapter_name if not provided
        folder_title = chapter_title if chapter_title else chapter_name

        # Create initial state
        state = create_initial_state(
            chapter_name=chapter_name,
            chapter_title=chapter_title,
            class_level=class_level,
            subject=subject,
            chapter_number=chapter_number,
            medium=medium,
        )

        # Set PDF path if provided
        if pdf_path:
            state.pdf_path = pdf_path
            state.pdf_source = "provided"

        # Create run folder - use chapter_title to avoid duplication
        folder_name = f"{class_level}_{subject}_{folder_title}".lower().replace(
            " ", "_"
        )
        state.run_folder = f"outputs/{folder_name}"
        Path(state.run_folder).mkdir(parents=True, exist_ok=True)
        (Path(state.run_folder) / "learning_steps").mkdir(exist_ok=True)
        (Path(state.run_folder) / "images").mkdir(exist_ok=True)
        (Path(state.run_folder) / "prompts").mkdir(exist_ok=True)
        (Path(state.run_folder) / "outputs").mkdir(exist_ok=True)

        # Run the graph
        config = {"configurable": {"thread_id": "storytelling-pipeline"}}

        final_state = None
        for state_update in self.graph.stream(state, config):
            final_state = state_update

        return final_state if final_state else state


def create_pipeline_graph() -> PipelineGraph:
    """Factory function to create PipelineGraph."""
    return PipelineGraph()
