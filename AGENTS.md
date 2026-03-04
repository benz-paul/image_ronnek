# Storytelling Pipeline Automation System

A production-grade Python automation system that executes a multi-step storytelling pipeline using LangChain and GPT-4o-mini.

## Project Structure

```
project_root/
├── prompt_file.txt          # Prompts for the pipeline
├── main.py                  # Main entry point
├── core/
│   ├── logger.py            # Structured logging
│   ├── llm_client.py        # LLM client with retry mechanism
│   ├── prompt_loader.py     # Dynamic prompt loading
│   ├── state_manager.py     # Pipeline state management
│   └── pipeline_controller.py  # Pipeline orchestration
├── agents/
│   ├── pdf_agent.py         # PDF retrieval
│   ├── concept_agent.py     # Concept inventory extraction
│   ├── backbone_agent.py   # Story backbone generation
│   ├── learning_steps_agent.py  # Learning step decomposition
│   ├── scene_generator_agent.py  # Scene generation
│   └── image_prompt_agent.py     # Image prompt generation
├── runs/                    # Generated chapter runs
└── logs/                    # Pipeline logs
```

## Requirements

- Python 3.10+
- OpenAI API Key

## Installation

### 1. Create Virtual Environment

**Windows:**
```bash
python -m venv venv
venv\Scripts\activate
```

**Mac/Linux:**
```bash
python -m venv venv
source venv/bin/activate
```

### 2. Install Dependencies

```bash
pip install langchain
pip install langchain-openai
pip install openai
pip install python-dotenv
pip install pydantic
pip install requests
```

### 3. Set Environment Variables

Create a `.env` file in the project root:

```bash
OPENAI_API_KEY=your_api_key_here
```

Or set it in your environment:

**Windows:**
```bash
set OPENAI_API_KEY=your_api_key_here
```

**Mac/Linux:**
```bash
export OPENAI_API_KEY=your_api_key_here
```

## Running the System

### Basic Execution

```bash
python main.py
```

### Input Format

When prompted, enter:

```
Class: 10
Subject: Physics
Chapter Number: 12
Chapter Title: Electricity
Medium: English
```

### Pipeline Steps

The system will execute:

1. **PDF Retrieval** - Downloads the official NCERT chapter PDF
2. **Prompt 0 - Concept Inventory** - Extracts concepts from the chapter
3. **Prompt 1 - Story Backbone** - Generates story backbone possibilities
4. **Prompt 2 - Learning Steps** - Decomposes chapter into learning steps
5. **Prompt 3 - Scene Generation** - Generates scenes for each learning step
6. **Prompt 4 - Image Prompts** (optional) - Generates image prompts for scenes

### Output Structure

Each chapter run creates:

```
runs/{class}_{subject}_{chapter}/
├── chapter.pdf
├── prompts/
│   ├── prompt0_sent.txt
│   ├── prompt1_sent.txt
│   └── ...
├── outputs/
│   ├── concept_inventory.txt
│   ├── story_backbone.txt
│   └── ...
├── raw/
│   ├── prompt0_raw.txt
│   └── ...
├── json/
│   ├── concept_inventory.json
│   ├── story_backbone.json
│   ├── learning_steps.json
│   ├── scenes_LS1.json
│   ├── scenes_LS2.json
│   └── scenes_full.json
└── image_prompts/
    └── image_prompts.json
```

## Logging

Logs are stored in:
- Console: Real-time execution output
- File: `logs/pipeline.log`

## Error Handling

- Automatic retry for failed LLM calls (3 attempts)
- Robust error detection and logging
- Pipeline continues safely on partial failures

## Configuration

### LLM Settings

Modify `core/llm_client.py` to adjust:
- Model (default: gpt-4o-mini)
- Temperature (default: 0.7)
- Max retries (default: 3)
- Timeout (default: 120 seconds)

### Prompt Customization

Edit `prompt_file.txt` to modify prompts. The system loads prompts dynamically without modification.

## Architecture

The system follows clean architecture principles:

- **Single Responsibility**: Each module has one clear purpose
- **Dependency Injection**: Agents are created via factory functions
- **State Management**: Centralized state tracking across pipeline
- **Structured Logging**: Comprehensive logging for debugging
- **Error Handling**: Graceful error recovery with retries

## Troubleshooting

### API Key Issues
Ensure `OPENAI_API_KEY` is set correctly in your environment.

### PDF Download Issues
Some NCERT PDFs may have download restrictions. The system will log the URL if download fails.

### JSON Parsing Errors
If the LLM returns malformed JSON, the system logs the raw response for debugging.

## License

For internal use only.
