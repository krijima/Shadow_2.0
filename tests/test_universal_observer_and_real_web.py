"""
Tests for Phase 1 & 2: Real-Website Permissioning and Universal Webpage Observer.
"""
import sys
import os
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend")))

from boundaries import SnapshotBoundary, ActionBoundary, ValidatedSnapshot, ProposedAction
from shadow_lock import ShadowLock


def test_real_website_permissioning():
    # 1. Unapproved external origin is rejected by default
    with pytest.raises(PermissionError):
        SnapshotBoundary.validate_and_bound_url("https://unpermitted-external-domain.com/page")

    # 2. Localhost and 127.0.0.1 are always permitted
    assert "localhost" in SnapshotBoundary.validate_and_bound_url("http://localhost:8080/static/index.html")
    assert "127.0.0.1" in SnapshotBoundary.validate_and_bound_url("http://127.0.0.1:8080/static/index.html")

    # 3. User activates domain (e.g. en.wikipedia.org)
    SnapshotBoundary.permit_domain("en.wikipedia.org")
    wiki_url = "https://en.wikipedia.org/wiki/Dark_pattern"
    assert SnapshotBoundary.validate_and_bound_url(wiki_url) == wiki_url

    # 4. Dangerous schemes and SSRF addresses remain strictly blocked
    with pytest.raises(ValueError):
        SnapshotBoundary.validate_and_bound_url("javascript:alert(1)")

    with pytest.raises(ValueError):
        SnapshotBoundary.validate_and_bound_url("file:///etc/passwd")

    with pytest.raises(PermissionError):
        SnapshotBoundary.validate_and_bound_url("http://169.254.169.254/latest/meta-data")


def test_universal_observer_sanitization_and_data_minimization():
    # Snapshot containing arbitrary external page elements with sensitive fields
    raw_snapshot = {
        "url": "https://en.wikipedia.org/wiki/Main_Page",
        "page_text": "Wikipedia, the free encyclopedia.",
        "elements": [
            {
                "data-shadow-id": "shadow-act-1",
                "tag": "input",
                "type": "search",
                "text": "Search Wikipedia",
                "value": "machine learning",
                "visible": True,
                "enabled": True,
            },
            {
                "data-shadow-id": "shadow-act-2",
                "tag": "input",
                "type": "password",
                "text": "Password",
                "value": "super_secret_password_123",  # Must be redacted
                "visible": True,
                "enabled": True,
            },
            {
                "data-shadow-id": "shadow-act-3",
                "tag": "input",
                "type": "checkbox",
                "text": "Remember me",
                "checked": True,
                "value": "token_session_private",  # Must not leak private token
                "visible": True,
                "enabled": True,
            },
            {
                "data-shadow-id": "shadow-act-4",
                "tag": "button",
                "type": "submit",
                "text": "Search",
                "visible": True,
                "enabled": True,
            }
        ]
    }

    validated = SnapshotBoundary.sanitize_snapshot(raw_snapshot)
    assert validated.elements_count == 4

    # Verify password redaction
    pwd_elem = next(el for el in validated.elements if el["shadow_id"] == "shadow-act-2")
    assert pwd_elem["value"] == "[REDACTED_SENSITIVE]"

    # Verify non-sensitive search input value preserved
    search_elem = next(el for el in validated.elements if el["shadow_id"] == "shadow-act-1")
    assert search_elem["value"] == "machine learning"


def test_pre_action_revalidation():
    action_boundary = ActionBoundary()
    task = {"steps_taken": 2, "authorized_goal": "Search topic"}

    snapshot = ValidatedSnapshot(
        url="https://en.wikipedia.org/wiki/Main_Page",
        page_text="Wikipedia",
        elements_count=2,
        elements=[
            {"shadow_id": "btn-search", "visible": True, "enabled": True, "tag": "button", "text": "Search"},
            {"shadow_id": "btn-disabled", "visible": True, "enabled": False, "tag": "button", "text": "Disabled"}
        ]
    )

    # Valid visible element passes
    valid, err, _ = action_boundary.validate_action(
        {"action": "click", "element_id": "btn-search", "reason": "Click search"},
        snapshot,
        task
    )
    assert valid is True
    assert err is None

    # Disabled element rejected
    valid, err, _ = action_boundary.validate_action(
        {"action": "click", "element_id": "btn-disabled", "reason": "Click disabled button"},
        snapshot,
        task
    )
    assert valid is False
    assert "disabled" in err.lower()

    # Missing/stale element rejected
    valid, err, _ = action_boundary.validate_action(
        {"action": "click", "element_id": "stale-deleted-element", "reason": "Click missing"},
        snapshot,
        task
    )
    assert valid is False
    assert "does not exist in observed DOM" in err


def test_shadow_lock_consequential_actions_require_approval():
    locker = ShadowLock()

    # StreamCove button requires approval
    assert locker.requires_approval({"action": "click", "element_id": "btn-confirm-cancel"}) is True

    # Real-website consequential actions require approval
    assert locker.requires_approval({
        "action": "click",
        "element_id": "shadow-act-42",
        "element_text": "Confirm Cancellation",
        "reason": "Final subscription cancellation"
    }) is True

    assert locker.requires_approval({
        "action": "click",
        "element_id": "btn-delete-acc",
        "element_text": "Permanently Delete Account",
        "reason": "Irreversible account deletion"
    }) is True

    # Benign navigation clicks do NOT require approval
    assert locker.requires_approval({
        "action": "click",
        "element_id": "link-nav-search",
        "element_text": "Search",
        "reason": "Navigate to search bar"
    }) is False
