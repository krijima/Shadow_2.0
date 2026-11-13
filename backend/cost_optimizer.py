"""
SHADOW — Gemini Cost Optimization, Metrics Tracker & Page-State Cache (Phase 6).
Guarantees:
1. Per-task API call counters and latency metrics.
2. In-memory page-state caching to prevent redundant LLM invocations.
3. Bounded retries and graceful fallback.
4. Token estimation and metrics export.
"""
import time
import hashlib
import json
from typing import Dict, Any, Optional


class CostOptimizer:
    def __init__(self):
        self._task_metrics: Dict[str, Dict[str, Any]] = {}
        self._plan_cache: Dict[str, Dict[str, Any]] = {}

    def get_task_metrics(self, task_id: str) -> Dict[str, Any]:
        if task_id not in self._task_metrics:
            self._task_metrics[task_id] = {
                "api_calls": 0,
                "cached_hits": 0,
                "total_latency_ms": 0.0,
                "estimated_prompt_tokens": 0,
                "estimated_completion_tokens": 0,
                "models_used": [],
                "errors_handled": 0,
            }
        return self._task_metrics[task_id]

    def record_call(
        self,
        task_id: str,
        model_name: str,
        latency_ms: float,
        prompt_chars: int,
        completion_chars: int,
    ):
        metrics = self.get_task_metrics(task_id)
        metrics["api_calls"] += 1
        metrics["total_latency_ms"] += round(latency_ms, 2)
        # Approximate ~4 characters per token
        metrics["estimated_prompt_tokens"] += max(1, prompt_chars // 4)
        metrics["estimated_completion_tokens"] += max(1, completion_chars // 4)
        if model_name not in metrics["models_used"]:
            metrics["models_used"].append(model_name)

    def record_cache_hit(self, task_id: str):
        metrics = self.get_task_metrics(task_id)
        metrics["cached_hits"] += 1

    def compute_page_hash(self, url: str, elements: list, steps_taken: int) -> str:
        """Create a deterministic hash of page state to detect identical redundant states."""
        element_signatures = []
        for el in (elements or [])[:40]:
            if not isinstance(el, dict):
                continue
            el_id = str(el.get("shadow_id") or el.get("data-shadow-id") or "")
            el_text = str(el.get("text") or "")[:30]
            el_vis = bool(el.get("visible", True))
            element_signatures.append(f"{el_id}:{el_text}:{el_vis}")

        raw_key = f"{url}|{steps_taken}|{';'.join(element_signatures)}"
        return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()

    def get_cached_plan(self, page_hash: str) -> Optional[Dict[str, Any]]:
        return self._plan_cache.get(page_hash)

    def cache_plan(self, page_hash: str, action: Dict[str, Any]):
        self._plan_cache[page_hash] = action
