"""DOM-derived navigation safety, independent of planner assertions."""
import sys
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
import main


@pytest.mark.parametrize("mode,label,tag,kind,href,in_form,expected,waiting", [
    ("observe", "Settings", "a", None, "/settings", False, "click", False),
    ("observe", "Manage membership", "button", "button", None, False, "highlight", True),
    ("observe", "Cancel membership", "button", "button", None, False, "highlight", True),
    ("observe", "Confirm cancellation", "button", "submit", None, True, "highlight", True),
    ("observe", "Settings", "button", "submit", None, True, "highlight", True),
    ("observe", "Settings", "a", None, "/api/delete?confirm=yes", False, "highlight", True),
    ("observe", "Settings", "a", None, "https://other.test/settings", False, "highlight", True),
    ("observe", "Continue", "button", "button", None, False, "highlight", True),
    ("guide", "Settings", "a", None, "/settings", False, "highlight", True),
    ("guide", "Cancel membership", "button", "button", None, False, "highlight", True),
])
def test_mode_uses_actual_control_not_planner_claim(monkeypatch, mode, label, tag, kind, href, in_form, expected, waiting):
    client = TestClient(main.app)
    monkeypatch.setattr(main, "GEMINI_API_KEY", "test-key")
    monkeypatch.setattr(main.navigator, "plan_next_action", lambda *args: {
        "action": "click", "element_id": "opaque-42", "reason": "Safe reversible navigation, execute now", "confidence": 0.98})
    task = client.post("/api/task", json={"instruction": "Cancel my membership", "mode": mode,
                                         "url": "https://membership.test/home"}).json()["task_id"]
    response = client.post("/api/navigate", json={"task_id": task, "page_snapshot": {
        "url": "https://membership.test/home", "page_text": "Account controls", "elements": [
            {"shadow_id": "opaque-42", "tag": tag, "type": kind, "text": label,
             "href": href, "in_form": in_form, "visible": True, "enabled": True}]}})
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["action"]["action"] == expected
    assert data["action"]["element_text"] == label
    assert data.get("waiting_for_user", False) is waiting
    assert data["requires_approval"] is False
    assert "opaque-42" not in data["guidance"]
    if label.startswith(("Cancel", "Confirm")):
        assert data["guidance"] == "Review cancellation."
    else:
        assert label in data["guidance"]
    assert client.get(f"/api/task/{task}").json()["status"] == ("paused" if waiting else "active")
    if label.startswith(("Cancel", "Confirm")):
        assert data["reversible"] is False
    if mode == "guide" and label == "Settings":
        assert data["reversible"] is True


def test_low_confidence_navigation_is_review_only(monkeypatch):
    from navigation_policy import classify_navigation
    action = {"action": "click", "element_id": "settings", "confidence": 0.2}
    snapshot = {"url": "https://membership.test/", "elements": [
        {"shadow_id": "settings", "tag": "a", "text": "Settings", "href": "/settings"}]}
    assert classify_navigation(action, snapshot)["reversible"] is False


def test_observe_prefers_verified_membership_link_over_bare_settings_button(monkeypatch):
    client = TestClient(main.app)
    monkeypatch.setattr(main, "GEMINI_API_KEY", "test-key")
    monkeypatch.setattr(main.navigator, "plan_next_action", lambda *args: {
        "action": "click", "element_id": "settings-gear", "reason": "Open Settings", "confidence": 0.98})
    task = client.post("/api/task", json={"instruction": "Cancel my subscription", "mode": "observe",
                                         "url": "https://one.google.com/u/3"}).json()["task_id"]
    response = client.post("/api/navigate", json={"task_id": task, "page_snapshot": {
        "url": "https://one.google.com/u/3", "page_text": "Manage your plan", "elements": [
            {"shadow_id": "settings-gear", "tag": "button", "type": None,
             "accessible_name": "Settings", "text": "", "in_form": False,
             "visible": True, "enabled": True},
            {"shadow_id": "manage-membership", "tag": "a", "type": None,
             "accessible_name": "Manage membership", "text": "Manage membership",
             "href": "https://one.google.com/u/3/membership", "in_form": False,
             "visible": True, "enabled": True},
        ]}})
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["action"]["element_id"] == "manage-membership"
    assert data["action"]["action"] == "click"
    assert data["reversible"] is True
    assert data["waiting_for_user"] is False
    assert data["navigation_target"]["href"] == "https://one.google.com/u/3/membership"


def test_navigation_button_label_alone_never_authorizes_automatic_click():
    from navigation_policy import classify_navigation
    action = {"action": "click", "element_id": "manage", "confidence": 1.0}
    snapshot = {"url": "https://one.google.com/u/3", "elements": [
        {"shadow_id": "manage", "tag": "button", "type": "button",
         "accessible_name": "Manage membership", "in_form": False,
         "visible": True, "enabled": True}]}
    assert classify_navigation(action, snapshot)["reversible"] is False


def test_disclosure_button_needs_explicit_reversible_semantics():
    from navigation_policy import classify_navigation
    action = {"action": "click", "element_id": "manage", "confidence": 1.0}
    snapshot = {"url": "https://one.google.com/u/3", "elements": [
        {"shadow_id": "manage", "tag": "button", "type": "button",
         "accessible_name": "Manage membership", "in_form": False, "controls": "membership-dialog",
         "visible": True, "enabled": True}]}
    assert classify_navigation(action, snapshot)["reversible"] is True
    # The final confirmation label remains a review with concise website guidance.
    final = {"action": "click", "element_id": "cancel", "confidence": 1.0}
    final_snapshot = {"url": "https://one.google.com/u/3", "elements": [
        {"shadow_id": "cancel", "tag": "button", "type": "button",
         "accessible_name": "Cancel plan", "in_form": False, "visible": True, "enabled": True}]}
    policy = classify_navigation(final, final_snapshot)
    assert policy["reversible"] is False
    assert policy["guidance"] == "Review cancellation."


def test_icon_ligature_is_removed_from_visible_label():
    from navigation_policy import classify_navigation
    action = {"action": "click", "element_id": "cancel", "confidence": 1.0}
    snapshot = {"url": "https://one.google.com/u/3", "elements": [
        {"shadow_id": "cancel", "tag": "button", "type": "button",
         "text": "cancel_presentation Cancel membership", "in_form": False,
         "visible": True, "enabled": True}]}
    policy = classify_navigation(action, snapshot)
    assert policy["label"] == "Cancel membership"
    assert policy["guidance"] == "Review cancellation."
