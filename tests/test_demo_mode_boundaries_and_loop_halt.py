"""
Tests for Demo Mode Origin Enforcement, Semantic Loop / No-Progress Detection,
Step Budget Halt Status, and Verified StreamCove Cancellation.
"""
import pytest
import sqlite3
from pathlib import Path
from fastapi.testclient import TestClient

import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

import main
from main import app, verify_streamcove_cancellation
from config import is_streamcove_url
from loop_detector import LoopDetector, extract_semantic_state
from database import get_db, create_task, get_task, update_task_status, log_action

client = TestClient(app)


def test_is_streamcove_url_boundary():
    """Verify origin boundary checks."""
    assert is_streamcove_url("http://localhost:8080/static/index.html") is True
    assert is_streamcove_url("http://127.0.0.1:8080/static/cancel_step1.html") is True
    assert is_streamcove_url("http://localhost:8081/test") is True

    # External websites must be rejected
    assert is_streamcove_url("https://one.google.com/u/3/settings") is False
    assert is_streamcove_url("https://google.com") is False
    assert is_streamcove_url("https://amazon.com/prime") is False
    assert is_streamcove_url("http://localhost:3000") is False


def test_external_site_demo_mode_halted_immediately():
    """
    Test 1: If a task has mode='demo' but runs on an external site like Google One,
    the backend immediately halts the task with status='halted' and returns blocked=True.
    """
    create_resp = client.post("/api/task", json={
        "instruction": "Cancel Google One subscription",
        "mode": "demo",
        "url": "https://one.google.com/u/3/settings"
    })
    assert create_resp.status_code == 200
    task_id = create_resp.json()["task_id"]

    # Even if created in demo mode, navigate on external site must halt
    snapshot = {
        "url": "https://one.google.com/u/3/settings",
        "elements": [
            {
                "shadow_id": "shadow-act-1",
                "tag": "button",
                "text": "Cancel membership",
                "role": "button",
                "visible": True,
                "enabled": True,
            }
        ],
        "page_text": "Google One Settings. Cancel membership."
    }

    # First ensure domain is permitted so snapshot boundary allows it
    from boundaries import SnapshotBoundary
    SnapshotBoundary.permit_domain("one.google.com")

    # Force task to demo mode in DB to test the navigate_endpoint safety check
    update_task_status(task_id, "active")
    conn = get_db()
    conn.execute("UPDATE tasks SET mode='demo' WHERE id=?", (task_id,))
    conn.commit()
    conn.close()

    nav_resp = client.post("/api/navigate", json={
        "task_id": task_id,
        "page_snapshot": snapshot,
    })
    assert nav_resp.status_code == 200
    data = nav_resp.json()

    assert data["blocked"] is True
    assert data["status"] == "halted"
    assert "Demo Mode is restricted to StreamCove" in data["action"]["reason"]

    # Check database status
    task = get_task(task_id)
    assert task["status"] == "halted"


def test_semantic_no_progress_and_oscillation_halt():
    """
    Test 2: Detect repeating attempts with dynamic regenerated IDs that return to
    the same meaningful page or dialog state.
    """
    detector = LoopDetector()
    test_task_id = "test-loop-task-001"

    # Simulate Google One dialog where button IDs alternate shadow-act-20, shadow-act-24, shadow-act-28...
    # but semantic state (tag, role, text) is identical
    page_state_1 = {
        "url": "https://one.google.com/settings",
        "elements": [
            {"shadow_id": "shadow-act-20", "tag": "button", "role": "button", "text": "Cancel", "visible": True},
            {"shadow_id": "shadow-act-21", "tag": "button", "role": "button", "text": "Keep plan", "visible": True},
        ],
        "page_text": "Cancel your subscription?"
    }

    # Step 1: Initial click
    is_stalled, desc, reason = detector.record_step(test_task_id, page_state_1, {"action": "click", "element_id": "shadow-act-20", "element_text": "Cancel"})
    assert is_stalled is False
    assert "Initial page state" in desc

    # Step 2: Page re-renders with new dynamic ID shadow-act-24 but same semantic content
    page_state_2 = {
        "url": "https://one.google.com/settings",
        "elements": [
            {"shadow_id": "shadow-act-24", "tag": "button", "role": "button", "text": "Cancel", "visible": True},
            {"shadow_id": "shadow-act-25", "tag": "button", "role": "button", "text": "Keep plan", "visible": True},
        ],
        "page_text": "Cancel your subscription?"
    }

    is_stalled, desc, reason = detector.record_step(test_task_id, page_state_2, {"action": "click", "element_id": "shadow-act-24", "element_text": "Cancel"})
    assert "No state change detected" in desc

    # Step 3: Page re-renders again with shadow-act-28 and still no semantic change
    page_state_3 = {
        "url": "https://one.google.com/settings",
        "elements": [
            {"shadow_id": "shadow-act-28", "tag": "button", "role": "button", "text": "Cancel", "visible": True},
            {"shadow_id": "shadow-act-29", "tag": "button", "role": "button", "text": "Keep plan", "visible": True},
        ],
        "page_text": "Cancel your subscription?"
    }

    is_stalled, desc, reason = detector.record_step(test_task_id, page_state_3, {"action": "click", "element_id": "shadow-act-28", "element_text": "Cancel"})
    assert is_stalled is True
    assert "produced zero state change" in reason


def test_step_limit_boundary_halts_task():
    """
    Test 3: Step budget limit must record status as 'halted' instead of 'completed'.
    """
    from boundaries import ActionBoundary
    boundary = ActionBoundary()

    task = {
        "id": "task-budget-test",
        "steps_taken": 25,
        "mode": "demo",
        "user_instruction": "Cancel subscription",
        "authorized_goal": "Cancel subscription"
    }
    snapshot_data = {
        "url": "http://localhost:8080/static/index.html",
        "elements": [{"shadow_id": "shadow-act-1", "tag": "button", "text": "Next", "visible": True, "enabled": True}],
        "page_text": "StreamCove Next page",
        "elements_count": 1,
    }

    from boundaries import ValidatedSnapshot
    validated = ValidatedSnapshot(**snapshot_data)

    is_valid, err, val_action = boundary.validate_action({"action": "click", "element_id": "shadow-act-1", "reason": "Proceed to next step"}, validated, task)
    assert is_valid is False
    assert "Maximum navigation step budget reached (25). Task halted." in err


def test_streamcove_cancellation_verification_and_rejection():
    """
    Test 4: StreamCove cancellation:
    - Reject leaves subscription active.
    - Completed is only returned when verified.
    """
    import urllib.request
    import json

    # 1. Reset StreamCove subscription to active
    reset_req = urllib.request.Request("http://127.0.0.1:8080/api/subscription/reset", data=b"{}", headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(reset_req) as resp:
        assert json.loads(resp.read().decode())["status"] == "active"

    assert verify_streamcove_cancellation("demo") is False

    # 2. Cancel subscription directly on StreamCove
    cancel_payload = json.dumps({"user_id": "demo", "confirmed": True}).encode()
    cancel_req = urllib.request.Request("http://127.0.0.1:8080/api/subscription/cancel", data=cancel_payload, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(cancel_req) as resp:
        assert json.loads(resp.read().decode())["status"] == "cancelled"

    assert verify_streamcove_cancellation("demo") is True

    # Reset back to active for clean state
    with urllib.request.urlopen(reset_req) as resp:
        assert json.loads(resp.read().decode())["status"] == "active"


def test_shadow_trail_report_renders_halted_status_and_explanation():
    """
    Test 5: ShadowTrail HTML report renders HALTED badge with #f97316 color
    and shows the Halt Explanation in the Execution Context.
    """
    from shadow_trail import ShadowTrail
    trail = ShadowTrail()

    task_id = "test-halted-report-task"
    conn = get_db()
    conn.execute("DELETE FROM tasks WHERE id=?", (task_id,))
    conn.execute("DELETE FROM actions WHERE task_id=?", (task_id,))
    conn.commit()
    conn.close()

    create_task(
        task_id=task_id,
        user_instruction="Cancel subscription",
        authorized_goal="Cancel subscription",
        mode="demo"
    )
    update_task_status(task_id, "halted", current_url="https://one.google.com/settings")
    log_action(
        task_id=task_id,
        step_number=1,
        action_type="blocked",
        element_id="shadow-act-20",
        element_text="Cancel membership",
        reason="Maximum navigation step budget reached (25). Task halted.",
        result="blocked"
    )

    html = trail.generate_html_report(task_id)
    assert "HALTED" in html
    assert "#f97316" in html
    assert "Halt Explanation" in html
    assert "Maximum navigation step budget reached" in html


def test_read_and_highlight_do_not_count_towards_stalled_progress():
    """
    Test 6: Read, highlight, and non-mutating events must NOT trigger stalled progress
    counter in LoopDetector. Stalled progress is ONLY counted after an executed mutating action.
    """
    detector = LoopDetector()
    task_id = "test-observe-read-highlight-task"

    snapshot = {
        "url": "http://localhost:8080/static/account.html",
        "elements": [
            {"shadow_id": "btn-settings", "tag": "button", "role": "button", "text": "Settings gear", "visible": True},
            {"shadow_id": "link-profile", "tag": "a", "role": "link", "text": "Profile", "visible": True},
        ],
        "page_text": "Account Settings. Settings gear icon."
    }

    # Step 1: Initial state loaded
    is_stalled, desc, _ = detector.record_step(task_id, snapshot, {"action": "read", "element_id": "btn-settings", "reason": "Observe page"})
    assert is_stalled is False
    assert detector._consecutive_no_change.get(task_id, 0) == 0

    # Step 2: Highlight action on the same page snapshot
    is_stalled, desc, _ = detector.record_step(task_id, snapshot, {"action": "highlight", "element_id": "btn-settings", "reason": "Highlight settings gear"})
    assert is_stalled is False
    # Crucial: consecutive no-change count must stay 0 because previous action was non-mutating
    assert detector._consecutive_no_change.get(task_id, 0) == 0
    assert "State unchanged after non-mutating action" in desc

    # Step 3: Another read/highlight step on the same page snapshot
    is_stalled, desc, _ = detector.record_step(task_id, snapshot, {"action": "read", "element_id": "btn-settings", "reason": "Observe again"})
    assert is_stalled is False
    assert detector._consecutive_no_change.get(task_id, 0) == 0

    # Step 4: Now execute a mutating action (click) that produces no change
    is_stalled, desc, _ = detector.record_step(task_id, snapshot, {"action": "click", "element_id": "btn-settings", "reason": "Click settings"})
    assert is_stalled is False
    # Now that a mutating action was executed, consecutive no change increments on next step
    is_stalled, desc, _ = detector.record_step(task_id, snapshot, {"action": "click", "element_id": "btn-settings", "reason": "Click settings again"})
    assert is_stalled is False
    assert detector._consecutive_no_change.get(task_id, 0) == 1

    # Second consecutive zero change after click halts
    is_stalled, desc, stall_reason = detector.record_step(task_id, snapshot, {"action": "click", "element_id": "btn-settings", "reason": "Click settings 3rd time"})
    assert is_stalled is True
    assert "produced zero state change" in stall_reason


def test_observe_find_and_highlight_settings_gear():
    """
    Test 7: Fresh Observe task with 'Find and highlight the Settings gear.'
    Verifies that the backend returns action='highlight' targeting the control,
    does not execute autonomous clicks, and does not halt on stalled progress.
    """
    create_resp = client.post("/api/task", json={
        "instruction": "Find and highlight the Settings gear.",
        "mode": "observe",
        "url": "http://localhost:8080/static/account.html"
    })
    assert create_resp.status_code == 200
    task_id = create_resp.json()["task_id"]
    assert create_resp.json()["mode"] == "observe"

    snapshot = {
        "url": "http://localhost:8080/static/account.html",
        "elements": [
            {
                "shadow_id": "btn-settings-gear",
                "tag": "button",
                "text": "Settings gear",
                "role": "button",
                "visible": True,
                "enabled": True,
            },
            {
                "shadow_id": "link-profile",
                "tag": "a",
                "text": "Profile information",
                "role": "link",
                "visible": True,
                "enabled": True,
            }
        ],
        "page_text": "Account Settings. Click the Settings gear to configure preferences."
    }

    nav_resp = client.post("/api/navigate", json={
        "task_id": task_id,
        "page_snapshot": snapshot,
    })
    assert nav_resp.status_code == 200
    data = nav_resp.json()

    # Must NOT be blocked or halted
    assert data["blocked"] is False
    assert data.get("status") != "halted"

    # Action must be highlight or read targeting the control
    act = data["action"]
    assert act["action"] in ("highlight", "read")
    if act.get("element_id"):
        assert act["action"] == "highlight"
        assert act["element_id"] in ("btn-settings-gear", "link-profile")

