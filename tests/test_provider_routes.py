"""Official provider guidance is matched to visible DOM controls, never executed as a URL."""
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from provider_routes import get_provider_route, match_provider_action


GOAL = "Cancel my subscription. Do not accept discounts."


def el(id, label, *, tag="a", href=None, role=None, popup=False, expanded=None,
       menu=False, controls="", in_form=False):
    return {"shadow_id": id, "tag": tag, "type": "button" if tag == "button" else None,
            "text": label, "accessible_name": label, "href": href, "role": role,
            "has_popup": popup, "expanded": expanded, "menu_context": menu,
            "controls": controls, "in_form": in_form, "visible": True, "enabled": True}


def test_apple_music_open_menu_selects_settings_instead_of_toggling_my_account():
    url = "https://music.apple.com/us/new"
    route = get_provider_route(url, GOAL)
    snapshot = {"url": url, "page_text": "Apple Music", "elements": [
        el("account", "My Account", tag="button", popup=True, expanded="true"),
        el("settings", "Settings", tag="button", role="menuitem", menu=True),
    ]}
    step = match_provider_action(route, snapshot)
    assert step["action"]["element_id"] == "settings"
    assert step["route_step"] == "settings"


def test_provider_route_ignores_matching_heading_and_uses_visible_settings_link():
    url = "https://music.apple.com/us/new"
    route = get_provider_route(url, GOAL)
    snapshot = {"url": url, "page_text": "Apple Music Settings", "elements": [
        el("heading", "Settings", tag="h1"),
        el("settings", "Settings", tag="a", href="/us/account/settings", role="menuitem", menu=True),
    ]}
    step = match_provider_action(route, snapshot)
    assert step["action"]["element_id"] == "settings"


def test_apple_music_closed_menu_uses_only_verified_menu_opener():
    url = "https://music.apple.com/us/new"
    route = get_provider_route(url, GOAL)
    closed = {"url": url, "page_text": "Apple Music", "elements": [
        el("account", "My Account", tag="button", popup=True, expanded="false")
    ]}
    step = match_provider_action(route, closed)
    assert step["action"]["element_id"] == "account"
    assert step["stalled_guidance"] == "Open Settings to continue."

    unverified = {"url": url, "page_text": "Apple Music", "elements": [
        el("account", "My Account", tag="button")
    ]}
    assert match_provider_action(route, unverified) is None


def test_apple_settings_route_and_final_cancel_are_matched_from_current_dom():
    url = "https://music.apple.com/us/account/settings"
    route = get_provider_route(url, GOAL)
    manage_snapshot = {"url": url, "page_text": "Subscriptions", "elements": [
        el("manage", "Manage", tag="button", role="button", menu=True)
    ]}
    step = match_provider_action(route, manage_snapshot)
    assert step["action"]["element_id"] == "manage"
    assert step["route_step"] == "manage_subscription"

    final_snapshot = {"url": "https://music.apple.com/us/account/subscriptions", "page_text": "Active", "elements": [
        el("cancel", "Cancel Subscription", tag="button", role="button")
    ]}
    step = match_provider_action(route, final_snapshot)
    assert step["action"]["element_id"] == "cancel"
    assert step["final"] is True


@pytest.mark.parametrize("url,expected,labels", [
    ("https://open.spotify.com/", "spotify", ("Manage your plan", "Cancel subscription")),
    ("https://www.amazon.in/", "amazon_prime_india", ("Your Prime Membership", "Manage membership", "End membership")),
])
def test_official_provider_sources_and_entry_steps(url, expected, labels):
    route = get_provider_route(url, GOAL)
    assert route["provider"] == expected
    assert route["help_url"].startswith("https://")
    known = {label for options in route["steps"].values() for label in options}
    assert all(label in known for label in labels)


def test_spotify_matches_manage_link_and_stops_before_cancel():
    route = get_provider_route("https://open.spotify.com/", GOAL)
    snapshot = {"url": "https://open.spotify.com/", "page_text": "Premium", "elements": [
        el("manage", "Manage your plan", href="https://open.spotify.com/account/plan")
    ]}
    assert match_provider_action(route, snapshot)["action"]["element_id"] == "manage"
    final = {"url": "https://open.spotify.com/account/plan", "page_text": "Premium", "elements": [
        el("cancel", "Cancel subscription", tag="button")
    ]}
    assert match_provider_action(route, final)["final"] is True


def test_amazon_prime_india_matches_route_and_stops_before_end_membership():
    route = get_provider_route("https://www.amazon.in/", GOAL)
    entry = {"url": "https://www.amazon.in/", "page_text": "Prime", "elements": [
        el("prime", "Your Prime Membership", href="https://www.amazon.in/gp/primecentral")
    ]}
    assert match_provider_action(route, entry)["action"]["element_id"] == "prime"
    final = {"url": "https://www.amazon.in/gp/primecentral", "page_text": "Prime membership", "elements": [
        el("end", "End membership", tag="button")
    ]}
    assert match_provider_action(route, final)["final"] is True


def test_partner_billed_state_returns_handoff_without_click():
    route = get_provider_route("https://open.spotify.com/account/plan", GOAL)
    snapshot = {"url": "https://open.spotify.com/account/plan",
                "page_text": "Your Premium subscription is billed through Google Play.", "elements": [
                    el("manage", "Manage your plan", href="https://open.spotify.com/account/plan")
                ]}
    step = match_provider_action(route, snapshot)
    assert step["handoff"] == "Google Play"
    assert step.get("action") is None


def test_backend_returns_action_and_policy_for_current_apple_menu_dom(monkeypatch):
    import main
    from fastapi.testclient import TestClient
    monkeypatch.setattr(main, "GEMINI_API_KEY", "test-key")
    monkeypatch.setattr(main.navigator, "plan_next_action", lambda *args: {
        "action": "click", "element_id": "my-account", "reason": "Planner repeats opener", "confidence": 0.98})
    client = TestClient(main.app)
    url = "https://music.apple.com/us/new"
    task_id = client.post("/api/task", json={"instruction": GOAL, "mode": "observe", "url": url}).json()["task_id"]
    response = client.post("/api/navigate", json={"task_id": task_id, "page_snapshot": {
        "url": url, "page_text": "Apple Music Settings", "elements": [
            el("my-account", "My Account", tag="button", popup=True, expanded="true"),
            el("settings", "Settings", tag="button", role="menuitem", menu=True),
        ]}})
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["action"]["element_id"] == "settings"
    assert data["action"]["action"] == "click"
    assert data["route_provider"] == "apple_music"
    assert data["route_step"] == "settings"
    assert data["reversible"] is True
    assert data["waiting_for_user"] is False
    assert data["policy_decision"] == "auto_navigate"


def test_backend_holds_provider_final_control_even_when_generic_membership_link_exists(monkeypatch):
    import main
    from fastapi.testclient import TestClient
    client = TestClient(main.app)
    url = "https://www.amazon.in/gp/primecentral"
    task_id = client.post("/api/task", json={"instruction": GOAL, "mode": "observe", "url": url}).json()["task_id"]
    response = client.post("/api/navigate", json={"task_id": task_id, "page_snapshot": {
        "url": url, "page_text": "Your Prime Membership", "elements": [
            el("manage", "Manage membership", tag="button", popup=True, expanded="false"),
            el("end", "End membership", tag="button", role="menuitem", menu=True),
        ]}})
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["route_step"] == "final"
    assert data["action"]["element_id"] == "end"
    assert data["action"]["action"] == "highlight"
    assert data["guidance"] == "Review cancellation."
    assert data["waiting_for_user"] is True
