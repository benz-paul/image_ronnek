"""
Test script to debug the entire pipeline step by step.
Run with: python test_flow.py
"""

import os
import json
import re
from pathlib import Path
from dotenv import load_dotenv

# Load env
load_dotenv(override=True)

print("=" * 70)
print("TESTING PIPELINE STEP BY STEP - DETAILED LOGS")
print("=" * 70)

# Test 1: Check API Key
print("\n" + "=" * 70)
print("[TEST 1] CHECKING API KEY")
print("=" * 70)
api_key = os.getenv("OPENAI_API_KEY")
if api_key:
    print(f"✓ API Key found: {api_key[:15]}...")
else:
    print("✗ ERROR: No API Key found!")
    exit(1)

# Test 2: Initialize components
print("\n" + "=" * 70)
print("[TEST 2] INITIALIZING COMPONENTS")
print("=" * 70)
from graph.pipeline_graph import LLMService
from agents.prompt_injector_agent import PromptInjectorAgent
from state.pipeline_state import create_initial_state

llm = LLMService(model="gpt-4o-mini")
pi = PromptInjectorAgent(model="gpt-4o-mini")
print(f"✓ LLM Model: {llm.llm.model_name}")
print(f"✓ PI Model: {pi.llm.model_name}")

# Test 3: Create initial state
print("\n" + "=" * 70)
print("[TEST 3] CREATING INITIAL STATE")
print("=" * 70)
state = create_initial_state(
    chapter_name="Class 10 Maths Chapter 5 Arithmetic Progression",
    chapter_title="Arithmetic Progression",
    class_level="10",
    subject="Maths",
    chapter_number="5",
    medium="English",
)
state.run_folder = "outputs/test_debug"
state.pdf_path = "knowledge/Chapter 5 Arithmetic Progression Maths.pdf"
Path(state.run_folder).mkdir(parents=True, exist_ok=True)
print(f"✓ Chapter: {state.user_inputs.chapter_name}")
print(f"✓ Class: {state.user_inputs.class_level}")
print(f"✓ Subject: {state.user_inputs.subject}")
print(f"✓ Medium: {state.user_inputs.medium}")
print(f"✓ PDF Path: {state.pdf_path}")
print(f"✓ PDF Exists: {Path(state.pdf_path).exists()}")

# Test 4: Test Prompt 0
print("\n" + "=" * 70)
print("[TEST 4] PROMPT 0 - INJECTION")
print("=" * 70)
prompt0 = pi.inject_prompt0(state)
print(f"✓ Prompt0 generated, length: {len(prompt0)}")
print("\n--- PROMPT0 CONTENT (first 500 chars) ---")
print(prompt0[:500])
print("--- END PROMPT0 ---")

# Test 5: Execute Prompt 0
print("\n" + "=" * 70)
print("[TEST 5] PROMPT 0 - EXECUTION")
print("=" * 70)
print("Sending to LLM...")
response0 = llm.invoke(prompt0)
print(f"✓ Response received, length: {len(response0)}")
print("\n--- RESPONSE0 CONTENT (first 500 chars) ---")
print(response0[:500])
print("--- END RESPONSE0 ---")

state.prompt0_output = response0
(Path(state.run_folder) / "prompt0_output.txt").write_text(response0, encoding="utf-8")
print("✓ Saved to prompt0_output.txt")

# Test 6: Test Prompt 1
print("\n" + "=" * 70)
print("[TEST 6] PROMPT 1 - INJECTION")
print("=" * 70)
prompt1 = pi.inject_prompt1(state)
print(f"✓ Prompt1 generated, length: {len(prompt1)}")
print("\n--- PROMPT1 FIRST 1000 CHARS ---")
print(prompt1[:1000])
print("\n--- PROMPT1 LAST 500 CHARS ---")
print(prompt1[-500:])
print("--- END PROMPT1 ---")

# Test 7: Execute Prompt 1
print("\n" + "=" * 70)
print("[TEST 7] PROMPT 1 - EXECUTION")
print("=" * 70)
print("Sending to LLM...")
response1 = llm.invoke(prompt1)
print(f"✓ Response received, length: {len(response1)}")
print("\n--- RESPONSE1 FULL CONTENT ---")
print(response1)
print("--- END RESPONSE1 ---")

state.prompt1_output = response1
(Path(state.run_folder) / "prompt1_output.txt").write_text(response1, encoding="utf-8")
print("✓ Saved to prompt1_output.txt")

# Test 8: Parse Prompt 1
print("\n" + "=" * 70)
print("[TEST 8] PROMPT 1 - PARSING")
print("=" * 70)

# Try JSON first
response1_clean = response1.strip()
if response1_clean.startswith("```json"):
    response1_clean = response1_clean[7:]
elif response1_clean.startswith("```"):
    response1_clean = response1_clean[3:]
if response1_clean.endswith("```"):
    response1_clean = response1_clean[:-3]
response1_clean = response1_clean.strip()

try:
    data1 = json.loads(response1_clean)
    print("✓ JSON parsed successfully!")
    print(f"  Keys: {list(data1.keys())}")
    selected = data1.get("selected_story", {})
    title = selected.get("title", "Selected Story")
    # Extract core_premise - check both key names
    core_premise = selected.get("core_narrative_premise", "") or selected.get(
        "core_premise", ""
    )
    print(f"  Selected story title: {title}")
    print(f"  Premise length: {len(core_premise)}")
    # Store extracted values, not full dict
    state.selected_story = {"title": title, "core_premise": core_premise}
    print("✓ Set state.selected_story")
except json.JSONDecodeError as e:
    print(f"✗ JSON parse FAILED: {e}")
    print("  Using text fallback...")

    # Text fallback - find title
    title = "Selected Story"
    title_match = re.search(
        r"(?:Title|Story)[:\s]+\*?(.+?)(?:\n|$|\*\*)", response1, re.IGNORECASE
    )
    if title_match:
        title = title_match.group(1).strip()
        title = re.sub(r"^\*+|\*+$", "", title).strip()

    # Find core premise
    core_premise = ""
    premise_match = re.search(
        r"(?:Core Narrative Premise|Premise)[:\s]+\n?(.+?)(?:\n\n|\n###|\n---|$)",
        response1,
        re.DOTALL | re.IGNORECASE,
    )
    if premise_match:
        core_premise = premise_match.group(1).strip()[:2000]

    print(f"  Text fallback - title: {title}")
    print(f"  Text fallback - premise length: {len(core_premise)}")
    state.selected_story = {"title": title, "core_premise": core_premise}
    print("✓ Set state.selected_story from text fallback")

print(f"\n>>> FINAL state.selected_story: {state.selected_story.get('title', 'NONE')}")
# Check both key names
premise = state.selected_story.get("core_premise", "") or state.selected_story.get(
    "core_narrative_premise", ""
)
print(f">>> Premise length: {len(premise)}")

# Test 9: Test Prompt 2
print("\n" + "=" * 70)
print("[TEST 9] PROMPT 2 - INJECTION")
print("=" * 70)
prompt2 = pi.inject_prompt2(state)
print(f"✓ Prompt2 generated, length: {len(prompt2)}")
print("\n--- PROMPT2 FIRST 1000 CHARS ---")
print(prompt2[:1000])
print("\n--- PROMPT2 LAST 500 CHARS ---")
print(prompt2[-500:])
print("--- END PROMPT2 ---")

# Test 10: Execute Prompt 2
print("\n" + "=" * 70)
print("[TEST 10] PROMPT 2 - EXECUTION")
print("=" * 70)
print("Sending to LLM...")
response2 = llm.invoke(prompt2)
print(f"✓ Response received, length: {len(response2)}")
print("\n--- RESPONSE2 FULL CONTENT ---")
print(response2)
print("--- END RESPONSE2 ---")

state.prompt2_output = response2
(Path(state.run_folder) / "prompt2_output.txt").write_text(response2, encoding="utf-8")
print("✓ Saved to prompt2_output.txt")

# Test 11: Parse Prompt 2
print("\n" + "=" * 70)
print("[TEST 11] PROMPT 2 - PARSING")
print("=" * 70)

response2_clean = response2.strip()
if response2_clean.startswith("```json"):
    response2_clean = response2_clean[7:]
elif response2_clean.startswith("```"):
    response2_clean = response2_clean[3:]
if response2_clean.endswith("```"):
    response2_clean = response2_clean[:-3]
response2_clean = response2_clean.strip()

try:
    data2 = json.loads(response2_clean)
    print("✓ JSON parsed successfully!")
    print(f"  Keys: {list(data2.keys())}")
    learning_steps = data2.get("learning_steps", [])
    print(f"  Number of learning steps: {len(learning_steps)}")
    for i, ls in enumerate(learning_steps):
        print(f"    LS{i + 1}: {ls.get('title', 'NO TITLE')}")
    state.learning_steps_list = learning_steps
    print("✓ Set state.learning_steps_list")
except json.JSONDecodeError as e:
    print(f"✗ JSON parse FAILED: {e}")
    print("  Using text fallback...")

    # Text fallback
    learning_steps = []
    # Look for patterns like "1. Title" or "LS1 - Title"
    ls_pattern = r"(?:\d+[.\s]+|LS\d+[.\s-]+)([^\n]+)"
    matches = re.finditer(ls_pattern, response2, re.IGNORECASE)

    for i, match in enumerate(matches):
        title = match.group(1).strip()[:100]
        learning_steps.append(
            {
                "learning_step_id": f"LS{i + 1}",
                "title": title,
                "concepts_introduced": [],
                "narrative_moment": f"Learning step {i + 1}: {title}",
                "scenes": [],
            }
        )

    print(f"  Text fallback - found {len(learning_steps)} learning steps")
    for i, ls in enumerate(learning_steps):
        print(f"    LS{i + 1}: {ls.get('title')}")
    state.learning_steps_list = learning_steps
    print("✓ Set state.learning_steps_list from text fallback")

print(f"\n>>> FINAL state.learning_steps_list count: {len(state.learning_steps_list)}")

# Test 12: Test Prompt 3
print("\n" + "=" * 70)
print("[TEST 12] PROMPT 3 - INJECTION FOR LS1")
print("=" * 70)
if state.learning_steps_list:
    prompt3 = pi.inject_prompt3(state, 0)
    print(f"✓ Prompt3 generated, length: {len(prompt3)}")
    print("\n--- PROMPT3 CONTENT (first 800 chars) ---")
    print(prompt3[:800])
    print("--- END PROMPT3 ---")
else:
    print("✗ Skipped - no learning steps found")

print("\n" + "=" * 70)
print("ALL TESTS COMPLETED")
print("=" * 70)
print(f"\nCheck output folder: {state.run_folder}")
