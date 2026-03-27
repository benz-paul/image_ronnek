"""
Per-run cost and token tracker.

Accumulates LLM token usage, FAL image generation counts, and AWS Polly
character counts across a pipeline run, then computes estimated dollar costs.

Usage:
    tracker = RunCostTracker()
    tracker.add_llm_usage(result["usage"], label="prompt_3a")
    tracker.add_image_generation("fal-flux2pro", success_count=12)
    tracker.add_polly_synthesis(narrator_text, engine="neural")
    tracker.save(run_folder / "metrics")

Output files:
    metrics/token_usage.json   — per-label token counts + totals
    metrics/cost_report.json   — estimated dollar costs per service
"""

import json
from pathlib import Path
from typing import Dict, List, Any, Optional


# ---------------------------------------------------------------------------
# Pricing constants (as of Q1 2026 — update if rates change)
# ---------------------------------------------------------------------------

# DeepSeek V3.2 via OpenRouter
LLM_INPUT_PRICE_PER_M  = 0.27   # USD per 1M input tokens
LLM_OUTPUT_PRICE_PER_M = 1.10   # USD per 1M output tokens

# FAL.ai — per successful image (landscape_16_9 ≈ 1 megapixel)
FAL_IMAGE_PRICING: Dict[str, float] = {
    "fal-flux2pro":    0.030,   # Flux 2 Pro: $0.03/MP (first MP)
    "fal-juggernaut":  0.035,   # Juggernaut Pro: $0.035/MP
    "gpt-image-1.5":   0.040,   # GPT-image-1.5: ~$0.04/image (low quality)
    "fal-flux-dev":    0.025,   # FLUX.1 Dev: $0.025/MP
    "fal-flux-schnell": 0.003,  # FLUX.1 Schnell: $0.003/MP
}
DEFAULT_FAL_PRICE = 0.030  # fallback for unknown models

# AWS Polly — per character synthesized
POLLY_STANDARD_PRICE_PER_M = 4.00   # USD per 1M characters (standard engine)
POLLY_NEURAL_PRICE_PER_M   = 16.00  # USD per 1M characters (neural engine)


class RunCostTracker:
    """Accumulates token/usage data and computes estimated run costs."""

    def __init__(self):
        # LLM tracking
        self._llm_entries: List[Dict[str, Any]] = []
        self._llm_input_total  = 0
        self._llm_output_total = 0

        # Image tracking — {model_name: {"attempted": N, "success": N}}
        self._image_counts: Dict[str, Dict[str, int]] = {}

        # Polly tracking
        self._polly_standard_chars = 0
        self._polly_neural_chars   = 0

    # ------------------------------------------------------------------
    # Accumulation methods
    # ------------------------------------------------------------------

    def add_llm_usage(self, usage: Optional[Dict[str, Any]], label: str = "") -> None:
        """
        Record token usage from one LLM call.

        Args:
            usage:  Dict with keys like prompt_tokens/input_tokens and
                    completion_tokens/output_tokens (handles multiple formats).
            label:  Human-readable label (e.g. "prompt_3a", "prompt_3b_S1").
        """
        if not usage:
            return

        # Handle various API response formats
        input_tokens  = (
            usage.get("prompt_tokens")
            or usage.get("input_tokens")
            or usage.get("promptTokens", 0)
        )
        output_tokens = (
            usage.get("completion_tokens")
            or usage.get("output_tokens")
            or usage.get("completionTokens", 0)
        )
        total_tokens  = (
            usage.get("total_tokens")
            or usage.get("totalTokens")
            or (input_tokens + output_tokens)
        )

        self._llm_input_total  += input_tokens
        self._llm_output_total += output_tokens

        self._llm_entries.append({
            "label":          label,
            "input_tokens":   input_tokens,
            "output_tokens":  output_tokens,
            "total_tokens":   total_tokens,
        })

    def add_image_generation(
        self, model_name: str, attempted: int = 1, success: int = 1
    ) -> None:
        """
        Record one or more image generation attempts for a model.

        Args:
            model_name: e.g. "fal-flux2pro", "fal-juggernaut"
            attempted:  Number of requests attempted
            success:    Number of successful generations (billed)
        """
        if model_name not in self._image_counts:
            self._image_counts[model_name] = {"attempted": 0, "success": 0}
        self._image_counts[model_name]["attempted"] += attempted
        self._image_counts[model_name]["success"]   += success

    def add_polly_synthesis(self, text: str, engine: str = "standard") -> None:
        """
        Record characters synthesized by Polly.

        Args:
            text:   The text synthesized (character count determines billing).
            engine: "standard" or "neural".
        """
        char_count = len(text.strip()) if text else 0
        if engine == "neural":
            self._polly_neural_chars   += char_count
        else:
            self._polly_standard_chars += char_count

    # ------------------------------------------------------------------
    # Cost computation
    # ------------------------------------------------------------------

    def compute_total(self) -> Dict[str, Any]:
        """
        Compute full cost breakdown.

        Returns:
            Dict with per-service costs and grand total.
        """
        # LLM cost
        llm_input_cost  = (self._llm_input_total  / 1_000_000) * LLM_INPUT_PRICE_PER_M
        llm_output_cost = (self._llm_output_total / 1_000_000) * LLM_OUTPUT_PRICE_PER_M
        llm_total       = llm_input_cost + llm_output_cost

        # Image cost
        image_breakdown: Dict[str, Any] = {}
        image_total = 0.0
        for model_name, counts in self._image_counts.items():
            price_per_image = FAL_IMAGE_PRICING.get(model_name, DEFAULT_FAL_PRICE)
            model_cost      = counts["success"] * price_per_image
            image_total    += model_cost
            image_breakdown[model_name] = {
                "attempted":       counts["attempted"],
                "success":         counts["success"],
                "price_per_image": price_per_image,
                "estimated_cost":  round(model_cost, 4),
            }

        # Polly cost
        polly_standard_cost = (self._polly_standard_chars / 1_000_000) * POLLY_STANDARD_PRICE_PER_M
        polly_neural_cost   = (self._polly_neural_chars   / 1_000_000) * POLLY_NEURAL_PRICE_PER_M
        polly_total         = polly_standard_cost + polly_neural_cost

        grand_total = llm_total + image_total + polly_total

        return {
            "llm": {
                "model":         "deepseek/deepseek-v3.2 via OpenRouter",
                "input_tokens":  self._llm_input_total,
                "output_tokens": self._llm_output_total,
                "total_tokens":  self._llm_input_total + self._llm_output_total,
                "input_cost":    round(llm_input_cost, 4),
                "output_cost":   round(llm_output_cost, 4),
                "total_cost":    round(llm_total, 4),
                "pricing_note":  f"${LLM_INPUT_PRICE_PER_M}/M input, ${LLM_OUTPUT_PRICE_PER_M}/M output",
            },
            "images": {
                "breakdown":     image_breakdown,
                "total_cost":    round(image_total, 4),
            },
            "audio_polly": {
                "standard_chars":       self._polly_standard_chars,
                "neural_chars":         self._polly_neural_chars,
                "standard_cost":        round(polly_standard_cost, 4),
                "neural_cost":          round(polly_neural_cost, 4),
                "total_cost":           round(polly_total, 4),
                "pricing_note":         f"${POLLY_STANDARD_PRICE_PER_M}/M standard, ${POLLY_NEURAL_PRICE_PER_M}/M neural",
            },
            "grand_total_usd": round(grand_total, 4),
        }

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def save(self, metrics_dir: Path) -> None:
        """
        Save token_usage.json and cost_report.json to metrics_dir.

        Args:
            metrics_dir: Directory to save files (created if missing).
        """
        metrics_dir = Path(metrics_dir)
        metrics_dir.mkdir(parents=True, exist_ok=True)

        # token_usage.json
        token_usage = {
            "entries":       self._llm_entries,
            "total_input":   self._llm_input_total,
            "total_output":  self._llm_output_total,
            "total_tokens":  self._llm_input_total + self._llm_output_total,
        }
        with open(metrics_dir / "token_usage.json", "w", encoding="utf-8") as f:
            json.dump(token_usage, f, indent=2)

        # cost_report.json
        cost_report = self.compute_total()
        with open(metrics_dir / "cost_report.json", "w", encoding="utf-8") as f:
            json.dump(cost_report, f, indent=2)

        total = cost_report["grand_total_usd"]
        print(f"[METRICS] Cost report saved → metrics/cost_report.json  (est. ${total:.4f})")
        print(f"[METRICS] Token usage saved → metrics/token_usage.json  ({token_usage['total_tokens']} tokens)")
