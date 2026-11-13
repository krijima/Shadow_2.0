"""
SHADOW — Semantic Loop & Stalled Progress Detector.
Detects repeated attempts that return to the same meaningful page or dialog state,
comparing page, dialog, and control labels so regenerated element IDs don't count as progress.
Logs what changed after each click and halts when progress stalls.
"""
from urllib.parse import urlparse, parse_qs, urlencode
import hashlib
import re
from typing import Dict, Any, List, Tuple, Optional


def normalize_url(url: str) -> str:
    """Normalize URL by stripping volatile query parameters and fragments."""
    if not url:
        return ""
    try:
        parsed = urlparse(url)
        # Filter out tracking query params
        ignored_params = {
            "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
            "gclid", "gad_source", "gbraid", "wbraid", "g1_landing_page", "_", "ref"
        }
        query_dict = parse_qs(parsed.query)
        filtered_query = {k: v for k, v in query_dict.items() if k.lower() not in ignored_params}
        new_query = urlencode(filtered_query, doseq=True)
        return f"{parsed.scheme}://{parsed.netloc}{parsed.path}" + (f"?{new_query}" if new_query else "")
    except Exception:
        return url.split("#")[0]


def extract_semantic_state(snapshot: Dict[str, Any], semantic_only: bool = False) -> Dict[str, Any]:
    """
    Extract meaningful semantic fingerprint of page and dialog state.
    Ignores dynamic/ephemeral element IDs (such as 'shadow-act-12').
    """
    url = snapshot.get("url", "")
    norm_url = normalize_url(url)
    elements = snapshot.get("elements", [])
    page_text = (snapshot.get("page_text") or "").strip()

    # 1. Identify meaningful page, dialog, and menu state. A complete control
    # list is intentionally not progress: feeds frequently add controls while
    # the user remains in the same flow.
    dialog_titles = []
    page_titles = []
    menu_items = []
    for el in elements:
        if not isinstance(el, dict):
            continue
        role = (el.get("role") or "").lower()
        tag = (el.get("tag") or "").lower()
        text = (el.get("text") or el.get("accessible_name") or "").strip()
        if not text:
            continue
        if role in ("dialog", "alertdialog", "alert"):
            dialog_titles.append(text[:60])
        if tag in ("h1", "h2", "h3") or role == "heading":
            page_titles.append(text[:60])
        if (el.get("menu_context") or role in ("menu", "menuitem", "listbox", "option")
                or str(el.get("expanded")).lower() == "true"):
            menu_items.append(f"{role}:{text[:60]}")

    dialog_summary = " | ".join(sorted(set(dialog_titles[:4]))) if dialog_titles else "none"
    page_summary = " | ".join(sorted(set(page_titles[:2]))) if page_titles else "none"
    menu_summary = " | ".join(sorted(set(menu_items[:6]))) if menu_items else "none"

    # 2. Extract stable interactive control signatures (tag, role, normalized_text)
    control_signatures = []
    for el in elements:
        if not isinstance(el, dict):
            continue
        if not el.get("visible", True):
            continue

        tag = (el.get("tag") or "").lower()
        role = (el.get("role") or "").lower()
        text = (el.get("text") or el.get("accessible_name") or el.get("value") or "").strip()
        # Clean text
        text_clean = re.sub(r"\s+", " ", text).lower()[:60]

        if tag in ("button", "a", "input", "select", "textarea") or role in ("button", "link", "menuitem", "tab"):
            control_signatures.append(f"{tag}:{role}:{text_clean}")

    # Sort to avoid ordering variations
    control_signatures_sorted = tuple(sorted(control_signatures))

    # 3. Normalized text excerpt
    cleaned_text = re.sub(r"\s+", " ", page_text).lower()[:300]

    # Deterministic fingerprint hash
    if semantic_only:
        sig_raw = f"{norm_url}###{page_summary}###{dialog_summary}###{menu_summary}"
    else:
        sig_raw = f"{norm_url}###{dialog_summary}###{';'.join(control_signatures_sorted)}###{cleaned_text[:150]}"
    sig_hash = hashlib.sha256(sig_raw.encode("utf-8")).hexdigest()[:16]

    return {
        "url": norm_url,
        "page_summary": page_summary,
        "dialog_summary": dialog_summary,
        "menu_summary": menu_summary,
        "controls": control_signatures_sorted,
        "controls_count": len(control_signatures_sorted),
        "text_excerpt": cleaned_text[:120],
        "signature_hash": sig_hash,
    }


class LoopDetector:
    """
    Detects navigation loops, oscillations, and stalled progress across steps.
    """

    def __init__(self):
        # task_id -> list of semantic states
        self._task_history: Dict[str, List[Dict[str, Any]]] = {}
        # task_id -> list of actions taken
        self._action_history: Dict[str, List[Dict[str, Any]]] = {}
        # task_id -> consecutive zero-change count
        self._consecutive_no_change: Dict[str, int] = {}

    def reset(self, task_id: str):
        """Reset state tracking for a task."""
        self._task_history.pop(task_id, None)
        self._action_history.pop(task_id, None)
        self._consecutive_no_change.pop(task_id, None)

    def record_step(
        self,
        task_id: str,
        page_snapshot: Dict[str, Any],
        proposed_action: Dict[str, Any],
        semantic_only: bool = False,
    ) -> Tuple[bool, str, Optional[str]]:
        """
        Record a navigation step and check if progress has stalled.

        Returns:
            (is_stalled: bool, change_description: str, stall_reason: Optional[str])
        """
        current_state = extract_semantic_state(page_snapshot, semantic_only=semantic_only)
        history = self._task_history.setdefault(task_id, [])
        actions = self._action_history.setdefault(task_id, [])

        action_type = proposed_action.get("action", "unknown")
        action_text = (
            proposed_action.get("element_text")
            or proposed_action.get("element_id")
            or proposed_action.get("value")
            or "element"
        )

        if not history:
            # First step
            history.append(current_state)
            actions.append(proposed_action)
            self._consecutive_no_change[task_id] = 0
            return False, "Initial page state loaded", None

        prev_state = history[-1]
        MUTATING_ACTIONS = {"click", "select", "type"}

        last_action = actions[-1] if actions else {}
        last_action_type = (last_action.get("action") or "").lower()
        last_action_desc = (
            last_action.get("element_text")
            or last_action.get("element_id")
            or last_action.get("action")
            or "action"
        )

        # 1. Compare previous state to current state to determine what changed
        url_changed = prev_state["url"] != current_state["url"]
        page_changed = prev_state["page_summary"] != current_state["page_summary"]
        dialog_changed = prev_state["dialog_summary"] != current_state["dialog_summary"]
        menu_changed = prev_state["menu_summary"] != current_state["menu_summary"]
        prev_controls = set(prev_state["controls"])
        curr_controls = set(current_state["controls"])
        controls_added = len(curr_controls - prev_controls)
        controls_removed = len(prev_controls - curr_controls)
        controls_changed = controls_added > 0 or controls_removed > 0

        # Build human-readable change description
        change_parts = []
        if url_changed:
            change_parts.append(f"URL changed to '{current_state['url']}'")
        if page_changed:
            change_parts.append(f"Page updated ('{current_state['page_summary']}')")
        if dialog_changed:
            change_parts.append(f"Dialog updated ('{current_state['dialog_summary']}')")
        if menu_changed:
            change_parts.append(f"Menu updated ('{current_state['menu_summary']}')")
        if not semantic_only and controls_changed:
            change_parts.append(f"Controls updated (+{controls_added}, -{controls_removed})")

        has_state_changed = (url_changed or page_changed or dialog_changed or menu_changed) if semantic_only \
            else (url_changed or dialog_changed or controls_changed)

        if has_state_changed:
            change_desc = f"DOM changed: {', '.join(change_parts)}"
            self._consecutive_no_change[task_id] = 0
        else:
            # Count stalled progress ONLY after an executed action expected to change the page!
            if last_action_type in MUTATING_ACTIONS:
                change_desc = f"No state change detected after {last_action_type} on '{last_action_desc}'"
                self._consecutive_no_change[task_id] = self._consecutive_no_change.get(task_id, 0) + 1
            else:
                change_desc = f"State unchanged after non-mutating action '{last_action_type or action_type}'"
                # Do not increment _consecutive_no_change for non-mutating actions (read, highlight, scroll, etc.)

        # 2. Check for Consecutive Zero Progress (2 consecutive mutating clicks with 0 change)
        if self._consecutive_no_change.get(task_id, 0) >= 2:
            stall_reason = (
                f"Navigation stalled: Consecutive actions on '{last_action_desc}' produced zero state change. "
                f"The page or dialog did not progress. Task halted."
            )
            return True, change_desc, stall_reason

        # 3. Check for Repeated State Re-visitation (Cycle / Loop Detection)
        # Distinct visits: only count when transitioning back into this state from a different state
        sig = current_state["signature_hash"]
        if (last_action_type in MUTATING_ACTIONS or action_type in MUTATING_ACTIONS) and prev_state["signature_hash"] != sig:
            distinct_visits = []
            for s in history:
                s_hash = s["signature_hash"]
                if not distinct_visits or distinct_visits[-1] != s_hash:
                    distinct_visits.append(s_hash)
            visit_count = distinct_visits.count(sig)

            # If we have returned to the exact same semantic state 3 or more times:
            if visit_count >= 2:  # 2 previous visits + current return = 3 visits
                stall_reason = (
                    f"Navigation stalled: Repeated action on '{last_action_desc}' returned to the same meaningful "
                    f"page/dialog state ({visit_count + 1} times). Regenerated element IDs did not advance the flow. Task halted."
                )
                return True, change_desc, stall_reason

            # 4. Check for 2-State Alternating Cycle (A -> B -> A -> B)
            if len(history) >= 4:
                s1, s2, s3, s4 = [s["signature_hash"] for s in history[-4:]]
                if s1 == s3 and s2 == s4 and s1 != s2 and sig == s2:
                    stall_reason = (
                        f"Navigation stalled: Oscillating between two identical dialog states without progress. "
                        f"Repeated actions on '{last_action_desc}' halted."
                    )
                    return True, change_desc, stall_reason

        # Record into history
        history.append(current_state)
        actions.append(proposed_action)

        return False, change_desc, None
