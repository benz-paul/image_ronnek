# Storytelling Pipeline - Agentic Implementation Specification

## Project Overview

Build a production-grade Python automation system using LangGraph, LangChain, and LangSmith that executes a multi-step storytelling pipeline for generating educational content from NCERT chapters.

## Architecture Requirements

### Core Technologies
- **LangGraph**: For workflow orchestration, state management, and conditional routing
- **LangChain**: For LLM integration and prompt management
- **LangSmith**: For tracing and monitoring pipeline execution

### Agent Requirements

#### 1. FlowTrackerAgent
- Tracks current pipeline stage (which prompt is executing)
- Tracks exact state of entire flow
- Knows what prompt is next
- Monitors learning step and scene indices during loops
- Maintains execution history

#### 2. PromptInjectorAgent  
- Uses **LLM (not string replacement)** to prepare prompts
- Takes base prompt template + user inputs + previous prompt outputs
- Sends to LLM with instruction: "Fill ONLY input fields, keep rest unchanged"
- Returns fully prepared prompt with input fields filled
- Each prompt must ALWAYS include user inputs (class, subject, chapter, medium)

#### 3. PDF Retrieval (PRESERVED)
- Check knowledge folder for existing PDF
- If exists, use it
- If not, download from NCERT
- Copy to run folder

### State Management
- Use PipelineState (Pydantic model) for centralized state
- Store all prompt outputs for use in subsequent prompts
- Track loop indices (learning_step_index, scene_index)

---

## Pipeline Flow (Step by Step)

### Phase 1: Initialization
1. User provides:
   - Class (e.g., "10")
   - Subject (e.g., "Maths")
   - Chapter Number (e.g., "5")
   - Chapter Title (e.g., "Arithmetic Progression")
   - Medium (e.g., "English")

2. Create run folder: `{class}_{subject}_{chapter_title}` 
   - Example: `10_maths_arithmetic_progression`
   - **IMPORTANT**: Use only chapter_title (not full chapter_name)

3. PDF Agent checks knowledge folder, copies or downloads PDF

---

### Phase 2: Prompt Execution

#### Prompt 0 - Concept Inventory
**Input Fields to Fill:**
- Chapter: [Chapter Name]

**Process:**
1. FlowTracker: Update state to "prompt0"
2. PromptInjector: 
   - Take prompt0 template + user inputs
   - Use LLM to fill input field
   - Return prepared prompt
3. Send prepared prompt to LLM
4. Store output as `prompt0_output` in state

#### Prompt 1 - Story Backbone Generation
**Input Fields to Fill:**
- Chapter: [Chapter Name]
- Concept Inventory: [Output from Prompt 0]

**Process:**
1. FlowTracker: Update state to "prompt1"
2. PromptInjector:
   - Take prompt1 template + user inputs + prompt0_output
   - Use LLM to fill input fields only
   - Return prepared prompt
3. Send prepared prompt to LLM
4. Store output as `prompt1_output` in state

#### Prompt 2 - Learning Steps Decomposition
**Input Fields to Fill:**
- Chapter: (Insert chapter name)
- Selected Real-World Story Narrative: (Insert core premise from prompt1)
- Concept Inventory: (Insert prompt0 output)

**Process:**
1. FlowTracker: Update state to "prompt2"
2. PromptInjector:
   - Take prompt2 template + user inputs + prompt0_output + prompt1_output
   - Use LLM to fill input fields
   - Return prepared prompt
3. Send prepared prompt to LLM
4. Parse output into learning_steps_list (JSON array)
5. Store each learning step as `LS{index}.json`

#### Prompt 3 - Scene Generation (LOOP per Learning Step)
**Input Fields:**
- Chapter: [Chapter Name]
- Story Backbone: [Core Narrative Premise from prompt1]
- Previous Learning Step: [Previous LS from learning_steps_list]
- Current Learning Step: [Current LS from learning_steps_list]
- Next Learning Step: [Next LS from learning_steps_list]
- JSON Template: [The JSON schema - unchanged]

**Process (LOOP):**
For each learning_step_index in learning_steps_list:
1. FlowTracker: Update state - current_learning_step_index, current_prompt_id="prompt3"
2. PromptInjector:
   - Take prompt3 template + user inputs + prompt1_output + prev/cur/next learning steps
   - Use LLM to fill input fields (only the 3 learning step fields change per iteration)
   - Return prepared prompt
3. Send prepared prompt to LLM
4. Parse output into LS{index}_scenes.json
5. Update state: learning_step_json_paths.append(path)
6. Check continuation: more learning steps? → loop or move to prompt4

#### Prompt 4 - Image Generation (NESTED LOOP per Scene)
**Input Fields:**
- scene_goal: [SCENE_GOAL]
- Teaching Narrative: [TEACHING_NARRATIVE]
- Concept Focus: [CONCEPT_FOCUS]
- Character dialogues: [CHARACTER_DIALOGUES]
- Scene ID: [SCENE_ID]
- JSON Structure Used: [Full LS JSON]

**Process (NESTED LOOP):**
For each learning_step_index:
  For each scene in LS{index}_scenes.json:
    1. FlowTracker: Update state - current_learning_step_index, current_scene_index, current_prompt_id="prompt4"
    2. PromptInjector:
       - Take prompt4 template + user inputs + scene_data + current LS JSON
       - Use LLM to fill input fields
       - Return prepared prompt
    3. Send prepared prompt to image generation LLM
    4. Save image as `ls{index}_s{scene_index}.png` in images folder
    5. Update state: image_paths.append(image_path)
    6. Check continuation: more scenes? → loop or next LS

---

### Phase 3: PowerPoint Generation

**Structure:**
- Slide 1: Title (Subject + Class + Chapter Name)
- Slide 2: Learning Step 1 Title
- Slides 3+: All scenes from LS1 (one scene per slide)
- Next LS title slide + its scene slides
- Continue for all learning steps

---

## Output Structure

```
outputs/{class}_{subject}_{chapter_title}/
├── chapter.pdf
├── prompts/
│   ├── prompt0_injected.txt      # What was sent to LLM
│   ├── prompt1_injected.txt
│   ├── prompt2_injected.txt
│   ├── prompt3_LS1_injected.txt
│   ├── prompt3_LS2_injected.txt
│   └── prompt4_LS1_S1_injected.txt
├── outputs/
│   ├── prompt0_output.txt
│   ├── prompt1_output.txt
│   └── prompt2_output.txt
├── learning_steps/
│   ├── LS1.json
│   ├── LS1_scenes.json
│   ├── LS2.json
│   ├── LS2_scenes.json
│   └── ...
├── images/
│   ├── ls1_s1.png
│   ├── ls1_s2.png
│   └── ...
└── lesson_output.pptx
```

---

## PromptInjectorAgent Implementation Details

The key differentiator: **LLM-based prompt preparation** (not string replacement)

```python
def prepare_prompt(self, prompt_template: str, context: dict) -> str:
    """
    Use LLM to intelligently fill input fields in prompt template.
    
    Args:
        prompt_template: The base prompt with [FIELD] placeholders
        context: Dict containing user_inputs and previous prompt outputs
        
    Returns:
        Prepared prompt with ONLY input fields filled
    """
    system_message = """You are a prompt preparation assistant.
Your task is to take a prompt template and provided context data.
Fill ONLY the input fields in the template with the provided context.
DO NOT modify any other part of the prompt.
DO NOT add explanations.
Return ONLY the modified prompt."""
    
    user_message = f"""Here is the prompt template:

{prompt_template}

Here is the context data (use these values to fill the input fields):

{self._format_context(context)}

Instructions:
1. Identify all input fields in the template (they appear as [FIELD_NAME] or (Insert...))
2. Fill each input field with the appropriate value from the context
3. Keep ALL other text in the prompt unchanged
4. Return ONLY the modified prompt, nothing else"""

    response = self.llm.invoke([SystemMessage(content=system_message), 
                                HumanMessage(content=user_message)])
    return response.content
```

---

## FlowTrackerAgent Implementation Details

```python
class FlowTrackerAgent:
    """Tracks pipeline execution state."""
    
    def __init__(self):
        self.current_stage: PipelineStage = PipelineStage.INIT
        self.current_prompt_id: str = ""
        self.current_learning_step_index: int = 0
        self.current_scene_index: int = 0
        self.execution_history: List[dict] = []
    
    def update(self, stage: PipelineStage, metadata: dict = None):
        """Update and log state changes."""
        self.execution_history.append({
            "stage": stage,
            "prompt_id": self.current_prompt_id,
            "ls_index": self.current_learning_step_index,
            "scene_index": self.current_scene_index,
            "metadata": metadata or {}
        })
    
    def get_next_prompt(self) -> str:
        """Determine next prompt to execute."""
        # Logic based on current state
```

---

## Key Implementation Notes

1. **User Inputs ALWAYS attached**: Every prompt must receive user inputs (class, subject, chapter, medium) as part of the context

2. **PromptInjector uses LLM**: Not simple string replacement - the LLM decides how to fill fields intelligently

3. **State persistence**: PipelineState persists across all LangGraph nodes

4. **Looping**: 
   - prompt3 loops over learning_steps_list
   - prompt4 has nested loops (learning steps × scenes)

5. **LangSmith tracing**: Enable for all LLM calls

6. **Error handling**: Continue pipeline on partial failures, log errors

---

## Testing Checklist

- [ ] Folder name correct: `10_maths_arithmetic_progression` (not `10_maths_class_10_maths...`)
- [ ] User inputs present in all prompts
- [ ] Each learning step creates LS{index}.json and LS{index}_scenes.json
- [ ] Images named correctly: ls1_s1.png, ls1_s2.png, etc.
- [ ] PPT has correct structure (title → LS title → scenes → next LS...)
- [ ] LangSmith shows proper tracing of all stages
