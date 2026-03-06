"""
Metrics Logger - Records pipeline execution metrics for traceability.

This module provides functionality to:
- Log prompt execution metrics (timing, tokens, etc.)
- Save prompt templates for reproducibility
- Save injected prompts sent to LLMs
- Track pipeline-level metrics
- Track image generation metrics
- Calculate efficiency metrics
"""

import json
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional


class MetricsLogger:
    """Records metrics for pipeline execution."""

    # Default model configurations per prompt
    DEFAULT_PROMPT_CONFIG = {
        0: {
            "temperature": 0.2,
            "top_p": 1.0,
            "max_tokens": 2000,
            "presence_penalty": 0.0,
        },
        1: {
            "temperature": 0.65,
            "top_p": 0.95,
            "max_tokens": 3000,
            "presence_penalty": 0.0,
        },
        2: {
            "temperature": 0.25,
            "top_p": 1.0,
            "max_tokens": 2500,
            "presence_penalty": 0.0,
        },
        3: {
            "temperature": 0.7,
            "top_p": 0.9,
            "max_tokens": 4000,
            "presence_penalty": 0.3,
        },
    }

    def __init__(self, run_folder: str):
        """
        Initialize the metrics logger.

        Args:
            run_folder: Path to the run folder where metrics will be saved
        """
        self.run_folder = Path(run_folder)
        self.metrics_folder = self.run_folder / "metrics"
        self.prompts_folder = self.run_folder / "prompts"

        # Create directories
        self.metrics_folder.mkdir(parents=True, exist_ok=True)
        self.prompts_folder.mkdir(parents=True, exist_ok=True)

        # Track pipeline-level metrics
        self.pipeline_start_time = time.time()
        self.total_tokens_used = 0
        self.total_scenes_generated = 0

        # Store prompt metrics for pipeline summary
        self.prompt_metrics = {}

        # Store concepts for engagement metrics
        self.concepts = []

        # Store prompt version
        self.prompt_version = "1.0"

    def _extract_version_from_template(self, template: str) -> str:
        """Extract version from prompt template if available."""
        import re

        patterns = [
            r"Version:\s*([\d.]+)",
            r"version:\s*([\d.]+)",
            r"#\s*Version\s*([\d.]+)",
            r"v([\d.]+)",
        ]
        for pattern in patterns:
            match = re.search(pattern, template[:500])
            if match:
                return match.group(1)
        return "1.0"

    def set_concepts(self, concepts: list) -> None:
        """Store concepts for engagement metrics calculation."""
        self.concepts = concepts

    def log_prompt_template(self, prompt_id: int, template: str) -> None:
        """
        Save the raw prompt template.

        Args:
            prompt_id: Prompt number (0-4)
            template: Raw prompt template from MASTER_PROMPTS.txt
        """
        # Extract version from first prompt only
        if prompt_id == 0:
            self.prompt_version = self._extract_version_from_template(template)

        filename = f"prompt{prompt_id}_template.txt"
        filepath = self.prompts_folder / filename

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(template)

        print(f"  ✓ Saved prompt template: {filename}")

    def log_injected_prompt(self, prompt_id: int, prompt: str) -> None:
        """
        Save the injected prompt (with values filled in).

        Args:
            prompt_id: Prompt number (0-4)
            prompt: The final prompt sent to the LLM
        """
        filename = f"prompt{prompt_id}_injected.txt"
        filepath = self.prompts_folder / filename

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(prompt)

        print(f"  ✓ Saved injected prompt: {filename}")

    def _calculate_efficiency_metrics(
        self,
        latency: float,
        input_tokens: Optional[int],
        output_tokens: Optional[int],
        response_characters: int,
        prompt_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Calculate efficiency metrics from raw data.

        Args:
            prompt_id: Optional prompt ID to calculate scene-specific metrics

        Returns:
            Dictionary with efficiency metrics
        """
        efficiency = {}

        total_tokens = None
        if input_tokens is not None and output_tokens is not None:
            total_tokens = input_tokens + output_tokens

            # Tokens per second (throughput)
            if latency > 0:
                efficiency["tokens_per_second"] = round(total_tokens / latency, 2)

            # Tokens per scene - only for prompt 3 (scene generation)
            if prompt_id == 3 and self.total_scenes_generated > 0:
                efficiency["tokens_per_scene"] = round(
                    total_tokens / self.total_scenes_generated, 2
                )

        # Characters per second
        if latency > 0 and response_characters > 0:
            efficiency["characters_per_second"] = round(
                response_characters / latency, 2
            )

        return efficiency

    def _calculate_scene_efficiency_metrics(
        self,
        scene_count: int,
        generation_time: float,
        total_tokens: Optional[int],
    ) -> Dict[str, Any]:
        """
        Calculate scene generation efficiency metrics.

        Returns:
            Dictionary with scene efficiency metrics
        """
        efficiency = {}

        # Scenes per second
        if generation_time > 0 and scene_count > 0:
            efficiency["scenes_per_second"] = round(scene_count / generation_time, 2)

        # Latency per scene
        if scene_count > 0:
            efficiency["latency_per_scene"] = round(generation_time / scene_count, 3)

        # Tokens per scene
        if total_tokens is not None and scene_count > 0:
            efficiency["tokens_per_scene"] = round(total_tokens / scene_count, 2)

        return efficiency

    def log_prompt_metrics(
        self,
        prompt_id: int,
        model: str,
        latency: float,
        input_tokens: Optional[int] = None,
        output_tokens: Optional[int] = None,
        response_characters: int = 0,
        temperature: Optional[float] = None,
        top_p: Optional[float] = None,
        max_tokens: Optional[int] = None,
        presence_penalty: Optional[float] = None,
    ) -> None:
        """
        Log metrics for a prompt execution.

        Args:
            prompt_id: Prompt number (0-4)
            model: Model used
            latency: Time taken in seconds
            input_tokens: Number of input tokens (if available)
            output_tokens: Number of output tokens (if available)
            response_characters: Length of response in characters
            temperature: Model temperature setting
            top_p: Model top_p setting
            max_tokens: Max tokens setting
            presence_penalty: Presence penalty setting
        """
        total_tokens = None
        if input_tokens is not None and output_tokens is not None:
            total_tokens = input_tokens + output_tokens
            self.total_tokens_used += total_tokens

        # Calculate efficiency metrics
        efficiency = self._calculate_efficiency_metrics(
            latency, input_tokens, output_tokens, response_characters, prompt_id
        )

        # Get default config if not provided
        default_config = self.DEFAULT_PROMPT_CONFIG.get(prompt_id, {})

        metrics = {
            "prompt_id": prompt_id,
            "model": model,
            "timestamp": datetime.now().isoformat(),
            "latency_seconds": round(latency, 3),
            "tokens_input": input_tokens,
            "tokens_output": output_tokens,
            "total_tokens": total_tokens,
            "response_characters": response_characters,
            # Model configuration
            "temperature": temperature or default_config.get("temperature"),
            "top_p": top_p or default_config.get("top_p"),
            "max_tokens": max_tokens or default_config.get("max_tokens"),
            "presence_penalty": presence_penalty
            or default_config.get("presence_penalty"),
            # Efficiency metrics
            "efficiency": efficiency,
        }

        # Store for pipeline summary
        self.prompt_metrics[prompt_id] = metrics

        # Write to file
        filename = f"prompt{prompt_id}_metrics.json"
        filepath = self.metrics_folder / filename

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(metrics, f, indent=2)

    def log_scene_generation_metrics(
        self,
        prompt_id: int,
        scene_count: int,
        generation_time: float,
        scenes_data: Optional[list] = None,
    ) -> None:
        """
        Log metrics for scene generation including engagement metrics.

        Args:
            prompt_id: Prompt number (usually 3)
            scene_count: Number of scenes generated
            generation_time: Time taken for scene generation
            scenes_data: Optional list of scene dictionaries for quality metrics
        """
        self.total_scenes_generated = scene_count

        # Get total tokens for scene efficiency calculation
        total_tokens = None
        if prompt_id in self.prompt_metrics:
            total_tokens = self.prompt_metrics[prompt_id].get("total_tokens")

        # Calculate scene efficiency metrics
        efficiency = self._calculate_scene_efficiency_metrics(
            scene_count, generation_time, total_tokens
        )

        # Calculate engagement metrics if scenes data available
        engagement = self._calculate_engagement_metrics(scenes_data)

        # Update the prompt3 metrics with scene info
        if prompt_id in self.prompt_metrics:
            self.prompt_metrics[prompt_id]["scene_count"] = scene_count
            self.prompt_metrics[prompt_id]["scene_generation_time"] = round(
                generation_time, 3
            )
            self.prompt_metrics[prompt_id]["scene_efficiency"] = efficiency
            self.prompt_metrics[prompt_id]["engagement_metrics"] = engagement

        metrics = {
            "prompt_id": prompt_id,
            "scene_count": scene_count,
            "generation_time_seconds": round(generation_time, 3),
            "timestamp": datetime.now().isoformat(),
            "efficiency": efficiency,
            "engagement_metrics": engagement,
        }

        filename = f"prompt{prompt_id}_scenes_metrics.json"
        filepath = self.metrics_folder / filename

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(metrics, f, indent=2)

    def _calculate_engagement_metrics(
        self, scenes_data: Optional[list]
    ) -> Dict[str, Any]:
        """
        Calculate engagement metrics from scene data.

        Args:
            scenes_data: List of scene dictionaries

        Returns:
            Dictionary with engagement metrics
        """
        if not scenes_data:
            return {
                "dialogue_line_count": 0,
                "scene_word_count": 0,
                "average_dialogue_length": 0,
                "concept_density": 0,
            }

        total_dialogue_lines = 0
        total_dialogue_words = 0
        total_scene_words = 0
        total_concept_mentions = 0

        # Build list of concept terms to search for
        concept_terms = []
        for concept in self.concepts:
            if isinstance(concept, dict):
                name = concept.get("concept_name", "").lower().replace("**", "").strip()
                if name:
                    concept_terms.append(name)
                    # Also add definition keywords for matching
                    definition = concept.get("definition", "")
                    if definition:
                        # Extract key terms from definition (first few words)
                        def_words = definition.lower().split()[:3]
                        for word in def_words:
                            if len(word) > 3:
                                concept_terms.append(word)
            elif isinstance(concept, str):
                concept_terms.append(concept.lower().replace("**", "").strip())

        for scene in scenes_data:
            # Count dialogue lines
            dialogue = scene.get("dialogue", [])
            if isinstance(dialogue, list):
                total_dialogue_lines += len(dialogue)
                for line in dialogue:
                    if isinstance(line, dict):
                        text = line.get("text", "") or line.get("content", "")
                        total_dialogue_words += len(text.split())

            # Collect all scene text for word count and concept search
            scene_text_parts = []

            # Get narrative text
            narrative = scene.get("narrative", "")
            if isinstance(narrative, dict):
                narrative = narrative.get("screenplay", "") or str(narrative)
            if isinstance(narrative, str):
                scene_text_parts.append(narrative)
                total_scene_words += len(narrative.split())

            # Get dialogue text
            if isinstance(dialogue, list):
                for line in dialogue:
                    if isinstance(line, dict):
                        text = line.get("text", "") or line.get("content", "")
                        scene_text_parts.append(text)

            # Count concept mentions in scene text
            combined_scene_text = " ".join(scene_text_parts).lower()
            for term in concept_terms:
                total_concept_mentions += combined_scene_text.count(term)

        scene_count = len(scenes_data)

        # Calculate averages
        avg_dialogue_length = 0
        if total_dialogue_lines > 0:
            avg_dialogue_length = round(total_dialogue_words / total_dialogue_lines, 2)

        # Concept density: concept mentions per total words
        concept_density = 0
        if total_scene_words > 0 and total_concept_mentions > 0:
            concept_density = round(total_concept_mentions / total_scene_words, 4)

        # Characters per scene
        characters_per_scene = 0
        if scene_count > 0:
            characters_per_scene = round(total_scene_words / scene_count, 2)

        # Dialogue ratio (dialogue words / total words)
        dialogue_ratio = 0
        if total_scene_words > 0:
            dialogue_ratio = round(total_dialogue_words / total_scene_words, 4)

        return {
            "dialogue_line_count": total_dialogue_lines,
            "scene_word_count": total_scene_words,
            "average_dialogue_length": avg_dialogue_length,
            "concept_density": concept_density,
            "total_concept_mentions": total_concept_mentions,
            "characters_per_scene": characters_per_scene,
            "dialogue_ratio": dialogue_ratio,
        }

    def validate_scenes(self, scenes_data: Optional[list]) -> Dict[str, Any]:
        """
        Validate scenes against quality requirements.

        Checks:
        - scene_word_count >= 150
        - dialogue_line_count >= 1
        - concept_moments or concept_focus present

        Args:
            scenes_data: List of scene dictionaries

        Returns:
            Dictionary with validation results
        """
        import logging

        logger = logging.getLogger(__name__)

        validation_results = {
            "total_scenes": 0,
            "passed": 0,
            "failed": 0,
            "warnings": [],
            "all_valid": True,
        }

        if not scenes_data:
            validation_results["warnings"].append(
                "No scenes data provided for validation"
            )
            validation_results["all_valid"] = False
            return validation_results

        validation_results["total_scenes"] = len(scenes_data)

        for idx, scene in enumerate(scenes_data):
            scene_id = scene.get("scene_id", f"scene_{idx}")
            issues = []

            # Check word count
            narrative = scene.get("narrative", "")
            if isinstance(narrative, dict):
                narrative = narrative.get("screenplay", "") or str(narrative)
            word_count = len(narrative.split()) if isinstance(narrative, str) else 0

            if word_count < 150:
                issues.append(f"word_count={word_count} (expected >= 150)")

            # Check dialogue lines
            dialogue = scene.get("dialogue", [])
            if not isinstance(dialogue, list) or len(dialogue) < 1:
                issues.append("dialogue_line_count < 1")

            # Check concept information (supports both concept_moments and concept_focus)
            concepts = scene.get("concept_moments") or scene.get("concept_focus")
            if not concepts:
                issues.append("concept information missing")

            if issues:
                validation_results["failed"] += 1
                validation_results["all_valid"] = False
                warning_msg = f"Scene {scene_id}: {', '.join(issues)}"
                validation_results["warnings"].append(warning_msg)
                logger.warning(f"Scene validation failed: {warning_msg}")
            else:
                validation_results["passed"] += 1

        # Log validation summary
        logger.info(
            f"Scene validation: {validation_results['passed']}/{validation_results['total_scenes']} passed"
        )

        # Save validation results
        filepath = self.metrics_folder / "scene_validation.json"
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(validation_results, f, indent=2)

        return validation_results

    def log_pipeline_metrics(
        self,
        chapter: str,
        model: str,
    ) -> Dict[str, Any]:
        """
        Log pipeline-level metrics with efficiency calculations.

        Args:
            chapter: Chapter name
            model: Model used

        Returns:
            Pipeline metrics dictionary
        """
        total_runtime = time.time() - self.pipeline_start_time

        # Collect all prompt metrics
        prompt_summary = []
        total_latency = 0
        prompt_count = 0

        for pid in sorted(self.prompt_metrics.keys()):
            pm = self.prompt_metrics[pid]
            latency = pm.get("latency_seconds", 0)
            if latency:
                total_latency += latency
                prompt_count += 1

            prompt_summary.append(
                {
                    "prompt_id": pid,
                    "latency_seconds": latency,
                    "total_tokens": pm.get("total_tokens"),
                    "efficiency": pm.get("efficiency", {}),
                }
            )

        # Calculate pipeline-level efficiency metrics
        avg_prompt_latency = 0
        avg_tokens_per_prompt = 0
        avg_tokens_per_scene = 0

        if prompt_count > 0:
            avg_prompt_latency = round(total_latency / prompt_count, 3)

        if self.total_tokens_used > 0 and prompt_count > 0:
            avg_tokens_per_prompt = round(self.total_tokens_used / prompt_count, 2)

        if self.total_scenes_generated > 0:
            avg_tokens_per_scene = round(
                self.total_tokens_used / self.total_scenes_generated, 2
            )

        metrics = {
            "run_id": self.run_folder.name,
            "chapter": chapter,
            "model": model,
            "timestamp": datetime.now().isoformat(),
            "total_runtime_seconds": round(total_runtime, 3),
            "total_tokens_used": self.total_tokens_used,
            "total_scenes_generated": self.total_scenes_generated,
            # Efficiency metrics
            "avg_prompt_latency": avg_prompt_latency,
            "avg_tokens_per_prompt": avg_tokens_per_prompt,
            "avg_tokens_per_scene": avg_tokens_per_scene,
            "prompt_summary": prompt_summary,
        }

        filepath = self.metrics_folder / "pipeline_metrics.json"
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(metrics, f, indent=2)

        return metrics

    def log_image_generation_metrics(
        self,
        scene_id: str,
        model: str,
        generation_time: float,
        resolution: str = "1792x1024",
        success: bool = True,
        error: Optional[str] = None,
    ) -> None:
        """
        Log metrics for image generation.

        Args:
            scene_id: Scene identifier (e.g., 'LS1_S1')
            model: Model used for image generation
            generation_time: Time taken in seconds
            resolution: Image resolution
            success: Whether generation succeeded
            error: Error message if failed
        """
        metrics = {
            "scene_id": scene_id,
            "model": model,
            "timestamp": datetime.now().isoformat(),
            "generation_time_seconds": round(generation_time, 3),
            "resolution": resolution,
            "success": success,
            "error": error,
        }

        # Append to existing file or create new
        filepath = self.metrics_folder / "image_generation_metrics.json"

        existing_metrics = []
        if filepath.exists():
            with open(filepath, "r", encoding="utf-8") as f:
                try:
                    existing_metrics = json.load(f)
                except json.JSONDecodeError:
                    existing_metrics = []

        if isinstance(existing_metrics, dict):
            existing_metrics = [existing_metrics]

        existing_metrics.append(metrics)

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(existing_metrics, f, indent=2)

    def append_to_experiment_summary(self, model: str) -> None:
        """
        Append this run's metrics to the experiment comparison file.

        Args:
            model: Model name for the output directory
        """
        # Get pipeline metrics
        if not self.prompt_metrics:
            return

        total_runtime = time.time() - self.pipeline_start_time

        # Read existing experiment summary or create new
        summary_file = Path("outputs") / model / "experiment_summary.json"
        existing_runs = []

        if summary_file.exists():
            try:
                with open(summary_file, "r", encoding="utf-8") as f:
                    existing_runs = json.load(f)
            except json.JSONDecodeError:
                existing_runs = []

        if not isinstance(existing_runs, list):
            existing_runs = [existing_runs]

        # Calculate avg prompt latency
        total_latency = 0
        prompt_count = 0
        for pid, pm in self.prompt_metrics.items():
            latency = pm.get("latency_seconds", 0)
            if latency:
                total_latency += latency
                prompt_count += 1

        avg_prompt_latency = (
            round(total_latency / prompt_count, 3) if prompt_count > 0 else 0
        )

        # Calculate avg tokens per scene (using prompt 3 tokens)
        prompt3_tokens = None
        if 3 in self.prompt_metrics:
            prompt3_tokens = self.prompt_metrics[3].get("total_tokens")

        avg_tokens_per_scene = 0
        if prompt3_tokens and self.total_scenes_generated > 0:
            avg_tokens_per_scene = round(
                prompt3_tokens / self.total_scenes_generated, 2
            )

        # Get chapter info
        chapter = ""
        pipeline_metrics_file = self.metrics_folder / "pipeline_metrics.json"
        if pipeline_metrics_file.exists():
            with open(pipeline_metrics_file, "r", encoding="utf-8") as f:
                pm = json.load(f)
                chapter = pm.get("chapter", "")

        # Add this run with expanded fields
        run_summary = {
            "run_id": self.run_folder.name,
            "timestamp": datetime.now().isoformat(),
            "model": model,
            "chapter": chapter,
            "prompt_version": self.prompt_version,
            "total_runtime_seconds": round(total_runtime, 3),
            "total_tokens": self.total_tokens_used,
            "total_scenes": self.total_scenes_generated,
            "avg_prompt_latency": avg_prompt_latency,
            "avg_tokens_per_scene": avg_tokens_per_scene,
            "prompt_count": prompt_count,
        }

        existing_runs.append(run_summary)

        # Save back
        summary_file.parent.mkdir(parents=True, exist_ok=True)
        with open(summary_file, "w", encoding="utf-8") as f:
            json.dump(existing_runs, f, indent=2)

        print(f"  ✓ Updated experiment summary: {summary_file}")

    def get_summary(self) -> Dict[str, Any]:
        """
        Get a summary of all metrics.

        Returns:
            Dictionary with metric summary
        """
        return {
            "run_folder": str(self.run_folder),
            "total_tokens": self.total_tokens_used,
            "total_scenes": self.total_scenes_generated,
            "prompts_logged": list(self.prompt_metrics.keys()),
        }
