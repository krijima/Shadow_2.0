"""Backend contracts behind panel restoration and action-specific approval."""
import sys
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
import main

client = TestClient(main.app)


@pytest.mark.parametrize("origin,target,href,needs_approval", [
    ("http://127.0.0.1:8080/static/subscription.html", "btn-cancel-subscription", "cancel_step1.html", False),
    ("http://127.0.0.1:8080/static/subscription.html", "btn-cancel-subscription", "cancel_success.html", True),
    ("http://127.0.0.1:8080/static/cancel_confirm.html", "btn-confirm-cancel", "", True),
    ("https://example.com/subscription.html", "btn-cancel-subscription", "cancel_step1.html", True),
])
def test_approval_distinguishes_navigation_from_final_action(monkeypatch, origin, target, href, needs_approval):
    from boundaries import SnapshotBoundary
    SnapshotBoundary.permit_domain("example.com")
    monkeypatch.setattr(main, "GEMINI_API_KEY", "test-key")
    monkeypatch.setattr(main.navigator, "plan_next_action", lambda *args: {
        "action": "click", "element_id": target, "value": "",
        "reason": "Click Cancel Subscription to continue the cancellation process.", "confidence": 1.0})
    mode = "demo" if origin.startswith("http://127") else "observe"
    task = client.post("/api/task", json={"instruction": "Cancel subscription", "mode": mode, "url": origin}).json()
    if mode == "observe":
        # Exercise the lock directly: Observe correctly converts clicks to highlights.
        assert main.locker.requires_approval({"action": "click", "element_id": target,
                                             "reason": "Cancel subscription"})
        return
    response = client.post("/api/navigate", json={"task_id": task["task_id"], "page_snapshot": {
        "url": origin, "elements": [{"shadow_id": target, "tag": "a", "href": href,
                                     "text": "Cancel Subscription", "visible": True, "enabled": True}],
        "page_text": "Manage subscription"}})
    assert response.status_code == 200, response.text
    assert response.json()["requires_approval"] is needs_approval


def test_terminal_task_resume_does_not_confirm_active():
    task = client.post("/api/task", json={"instruction": "Cancel subscription", "mode": "demo"}).json()["task_id"]
    client.patch(f"/api/task/{task}/status", json={"status": "cancelled"})
    result = client.patch(f"/api/task/{task}/status", json={"status": "active"}).json()
    assert result["status"] == "cancelled"
    assert result["ok"] is False


def test_plans_are_not_reused_between_goals_or_modes(monkeypatch):
    from types import SimpleNamespace
    from shadow_navigate import ShadowNavigate, optimizer
    planner = ShadowNavigate()
    answers = iter([
        '{"action":"click","element_id":"settings","reason":"Open settings","confidence":1}',
        '{"action":"click","element_id":"subscription","reason":"Manage subscription","confidence":1}',
    ])
    planner._client = SimpleNamespace(models=SimpleNamespace(generate_content=lambda **kwargs: SimpleNamespace(text=next(answers))))
    snapshot = {"url": "http://127.0.0.1:8080/static/index.html", "elements": [
        {"shadow_id": "settings", "text": "Settings"}, {"shadow_id": "subscription", "text": "Subscription"}]}
    first = planner.plan_next_action(snapshot, {"id": "cache-observe", "mode": "observe", "authorized_goal": "Find settings"}, [])
    second = planner.plan_next_action(snapshot, {"id": "cache-demo", "mode": "demo", "authorized_goal": "Cancel subscription"}, [])
    assert first["element_id"] == "settings"
    assert second["element_id"] == "subscription"


def test_completion_requires_subscription_api_confirmation(monkeypatch):
    import urllib.request
    # A cancelled row in a local database must not override an ACTIVE API result.
    class Response:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def read(self): return b'{"status":"active"}'
    monkeypatch.setattr(urllib.request, "urlopen", lambda *args, **kwargs: Response())
    class Database(Response):
        def execute(self, *args): return self
        def fetchone(self): return ("cancelled",)
    monkeypatch.setattr(main.sqlite3, "connect", lambda *args, **kwargs: Database())
    assert main.verify_streamcove_cancellation() is False
