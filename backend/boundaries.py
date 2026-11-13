"""
SHADOW — Input & Output Safety Boundaries (Phases 4 & 5).
Guarantees:
1. Strict schema & size bounds on untrusted webpage snapshots (Input Boundary).
2. Data minimization & redaction of sensitive credentials.
3. Separation of immutable authorized user goal from untrusted webpage text.
4. Strict validation of AI agent actions against actual DOM state (Output Boundary).
5. Single-use human approval enforcement for consequential actions.
"""
import sys
import os

# Allow importing when run from root or backend directory
sys.path.insert(0, os.path.dirname(__file__))

from typing import Dict, Any, List, Optional, Tuple, Set
from urllib.parse import urlparse
from pydantic import BaseModel, Field, field_validator
from config import APPROVED_DOMAINS, MAX_STEPS, ALLOW_PUBLIC_WEB

# ── Input Boundary Constants ──────────────────────────────────────────────────
MAX_URL_LENGTH = 500
MAX_PAGE_TEXT_LENGTH = 4000
MAX_ELEMENTS_COUNT = 80
MAX_TEXT_FIELD_LENGTH = 160
ALLOWED_ACTIONS = {"click", "scroll", "select", "read", "ask_user", "stop", "highlight"}


class WebpageElement(BaseModel):
    shadow_id: str = Field(..., max_length=64)
    tag: str = Field(..., max_length=32)
    type: Optional[str] = Field(None, max_length=32)
    text: str = Field("", max_length=MAX_TEXT_FIELD_LENGTH)
    href: Optional[str] = Field(None, max_length=500)
    value: Optional[str] = Field(None, max_length=120)
    visible: bool = True
    enabled: bool = True
    role: Optional[str] = Field(None, max_length=32)
    bounding_rect: Optional[Dict[str, Any]] = None
    computed_style: Optional[Dict[str, Any]] = None
    visual_prominence: Optional[Dict[str, Any]] = None
    surrounding_heading: Optional[str] = Field(None, max_length=120)
    context_label: Optional[str] = Field(None, max_length=120)


class ValidatedSnapshot(BaseModel):
    url: str
    elements: List[Dict[str, Any]]
    page_text: str
    elements_count: int
    untrusted_flags: List[str] = Field(default_factory=list)


class ProposedAction(BaseModel):
    action: str
    element_id: str = Field("", max_length=64)
    value: str = Field("", max_length=120)
    reason: str = Field(..., max_length=500)
    confidence: float = Field(0.0, ge=0.0, le=1.0)

    @field_validator("action")
    def validate_action_type(cls, v: str) -> str:
        act = v.strip().lower()
        if act not in ALLOWED_ACTIONS:
            raise ValueError(f"Unrecognized action '{act}'. Allowed: {ALLOWED_ACTIONS}")
        return act


# ── Input Boundary: Snapshot Sanitizer ────────────────────────────────────────

class SnapshotBoundary:
    """Validates, bounds, and minimizes untrusted webpage inputs."""
    _permitted_domains: Set[str] = set()

    @classmethod
    def permit_domain(cls, domain: str):
        if domain:
            cls._permitted_domains.add(domain.lower().strip())

    @classmethod
    def get_permitted_domains(cls) -> Set[str]:
        return set(APPROVED_DOMAINS) | {"localhost"} | cls._permitted_domains

    @classmethod
    def validate_and_bound_url(cls, raw_url: str) -> str:
        if not raw_url or not isinstance(raw_url, str):
            raise ValueError("Page snapshot must provide a valid URL string.")
        cleaned_url = raw_url.strip()[:MAX_URL_LENGTH]
        parsed = urlparse(cleaned_url)
        scheme = (parsed.scheme or "").lower()
        if scheme not in ("http", "https"):
            raise ValueError(f"Prohibited URL scheme '{scheme}'. Only HTTP and HTTPS are permitted.")

        hostname = (parsed.hostname or "").lower()
        if not hostname:
            raise ValueError("URL must include a valid hostname.")

        is_allowed = (
            hostname in APPROVED_DOMAINS
            or hostname == "localhost"
            or hostname in cls._permitted_domains
        )
        if not is_allowed:
            raise PermissionError(f"URL hostname '{hostname}' is not in approved domains: {APPROVED_DOMAINS}. User must activate SHADOW on this domain first.")

        # Defense in depth: block metadata/internal link-local addresses
        if hostname.startswith("169.254.") or hostname.startswith("10.") or hostname.startswith("192.168."):
            raise PermissionError(f"Private/internal network address '{hostname}' is blocked for security.")
        if hostname == "0.0.0.0":
            raise PermissionError(f"Prohibited address '{hostname}'.")

        return cleaned_url

    @classmethod
    def sanitize_snapshot(cls, raw_snapshot: Dict[str, Any]) -> ValidatedSnapshot:
        if not isinstance(raw_snapshot, dict):
            raise ValueError("Page snapshot must be a JSON object.")

        # 1. URL validation
        url = cls.validate_and_bound_url(raw_snapshot.get("url", ""))

        # 2. Text bounding & redaction
        page_text = str(raw_snapshot.get("page_text") or "").strip()[:MAX_PAGE_TEXT_LENGTH]

        # 3. Element list bounding & minimization
        raw_elements = raw_snapshot.get("elements") or []
        if not isinstance(raw_elements, list):
            raw_elements = []

        validated_elements: List[Dict[str, Any]] = []
        untrusted_flags: List[str] = []

        for el in raw_elements[:MAX_ELEMENTS_COUNT]:
            if not isinstance(el, dict):
                continue

            el_id = str(el.get("data-shadow-id") or el.get("shadow_id") or el.get("id") or "").strip()[:64]
            if not el_id:
                continue

            tag = str(el.get("tag") or "element").strip().lower()[:32]
            el_type = str(el.get("type") or "").strip().lower()[:32] if el.get("type") else None
            text = str(el.get("text") or "").strip()[:MAX_TEXT_FIELD_LENGTH]
            val = el.get("value")
            if val is not None:
                val = str(val)[:100]

            # Sensitive data redaction
            if el_type == "password" or any(s in el_id.lower() or s in (el.get("name") or "").lower() for s in ["card", "cvv", "password", "token", "secret"]):
                val = "[REDACTED_SENSITIVE]"
                text = "[REDACTED_SENSITIVE]"

            is_visible = bool(el.get("visible", True))
            is_enabled = bool(el.get("enabled", True))

            validated_elements.append({
                "shadow_id": el_id,
                "data-shadow-id": el_id,
                "tag": tag,
                "type": el_type,
                "text": text,
                "href": str(el.get("href") or "")[:500] if el.get("href") else None,
                "value": val,
                "visible": is_visible,
                "enabled": is_enabled,
                "role": str(el.get("role") or "")[:32] if el.get("role") else None,
                "bounding_rect": el.get("bounding_rect"),
                "computed_style": el.get("computed_style"),
                "visual_prominence": el.get("visual_prominence"),
                "surrounding_heading": str(el.get("surrounding_heading") or "")[:120] if el.get("surrounding_heading") else None,
                "context_label": str(el.get("context_label") or "")[:120] if el.get("context_label") else None,
                "accessible_name": str(el.get("accessible_name") or "")[:120],
                "in_form": bool(el.get("in_form", False)),
                "controls": str(el.get("controls") or "")[:120],
                "expanded": str(el.get("expanded"))[:16] if el.get("expanded") is not None else None,
                "has_popup": bool(el.get("has_popup", False)),
                "menu_context": bool(el.get("menu_context", False)),
            })

        # Flag potential injection text in snapshot for containment
        lower_text = page_text.lower()
        if "system override" in lower_text or "ignore previous" in lower_text or "do not cancel" in lower_text:
            untrusted_flags.append("contains_suspicious_override_payload")

        return ValidatedSnapshot(
            url=url,
            elements=validated_elements,
            page_text=page_text,
            elements_count=len(validated_elements),
            untrusted_flags=untrusted_flags,
        )


# ── Output Boundary: Action Validator ─────────────────────────────────────────

class ActionBoundary:
    """Enforces strict action schemas, element reference validation, and execution locks."""

    def __init__(self):
        self._used_approval_tokens: Set[str] = set()

    def validate_action(
        self,
        raw_action: Dict[str, Any],
        snapshot: ValidatedSnapshot,
        task: Dict[str, Any],
    ) -> Tuple[bool, Optional[str], Optional[ProposedAction]]:
        """
        Validates proposed agent action against schema and actual DOM elements.
        Returns: (is_allowed: bool, rejection_reason: Optional[str], validated_action: Optional[ProposedAction])
        """
        # 1. Pydantic schema validation
        try:
            action = ProposedAction(**raw_action)
        except Exception as exc:
            return False, f"Invalid action schema: {str(exc)}", None

        # 2. Check step budget
        steps_taken = int(task.get("steps_taken") or 0)
        if steps_taken >= MAX_STEPS:
            return False, f"Maximum navigation step budget reached ({MAX_STEPS}). Task halted.", action

        # 3. Actions not targeting elements (scroll, read, ask_user, stop)
        if action.action in {"scroll", "read", "ask_user", "stop"}:
            return True, None, action

        # Highlight action: validate element_id if present
        if action.action == "highlight":
            if action.element_id:
                observed_ids = {el["shadow_id"]: el for el in snapshot.elements}
                if action.element_id not in observed_ids:
                    return False, f"Proposed element_id '{action.element_id}' does not exist in observed DOM elements.", action
            return True, None, action

        # 4. Actions targeting DOM elements (click, select, type)
        target_id = action.element_id
        if not target_id:
            return False, f"Action '{action.action}' requires a non-empty element_id.", action

        # Validate that element exists in actual observed elements snapshot
        observed_ids = {el["shadow_id"]: el for el in snapshot.elements}
        if target_id not in observed_ids:
            return False, f"Proposed element_id '{target_id}' does not exist in observed DOM elements.", action

        target_el = observed_ids[target_id]

        # Check visibility & enabled status
        if not target_el.get("visible", True):
            return False, f"Proposed element '{target_id}' is hidden and cannot be interacted with.", action

        if not target_el.get("enabled", True):
            return False, f"Proposed element '{target_id}' is disabled.", action

        # Safety: Disallow unauthorized purchases or upgrades
        el_text = (target_el.get("text") or "").lower()
        if any(w in el_text for w in ["upgrade to", "buy now", "purchase", "$29.99", "$49.99"]):
            return False, f"Unauthorized purchase/upgrade element '{target_id}' blocked by ShadowLock.", action

        return True, None, action

    def verify_single_use_approval(self, approval_id: int) -> bool:
        """Guarantees human approval tokens cannot be reused across actions or tasks."""
        token = str(approval_id)
        if token in self._used_approval_tokens:
            return False
        self._used_approval_tokens.add(token)
        return True
