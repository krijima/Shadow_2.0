"""Acceptance checks against the unpacked extension and the two running services.

No host-page clicks in Demo: only Start and the final approval decision.
Unlike the legacy E2E checks, missing extension injection is a failure.
"""
import json
import os
import time
from pathlib import Path

import httpx
import pytest
from playwright.sync_api import sync_playwright
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
APP = "http://127.0.0.1:8080"
API = "http://127.0.0.1:8001"
GOAL = "Cancel my subscription. Do not accept discount offers or upgrades."


@pytest.fixture
def loaded_extension(tmp_path):
    events = []
    with sync_playwright() as p:
        harness = os.environ.get("SHADOW_EXTENSION_HARNESS") == "1"
        context = p.chromium.launch_persistent_context(
            str(tmp_path / "profile"), headless=harness,
            executable_path=os.environ.get("SHADOW_TEST_BROWSER", r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
            ignore_default_args=["--disable-extensions"],
            args=[f"--disable-extensions-except={ROOT / 'extension'}",
                  f"--load-extension={ROOT / 'extension'}"],
        )
        if harness:
            # Explicitly NOT an installed-extension check. Run the unmodified
            # scripts with only Chrome's transport/storage APIs bridged.
            context.route("**/__shadow__/**", lambda route: route.fulfill(
                path=str(ROOT / "extension" / route.request.url.split("/__shadow__/")[1])))
            bridge = """(() => {
              const listeners = [];
              window.chrome = { runtime: {
                id: 'test-bridge', getURL: path => '/__shadow__/' + path,
                onMessage: { addListener: fn => listeners.push(fn) },
                sendMessage: msg => new Promise((resolve, reject) => {
                  if (!chrome.runtime.id) { reject(new Error('Extension context invalidated.')); return; }
                  const key = '__shadow_test_tab';
                  if (!sessionStorage.getItem(key)) sessionStorage.setItem(key, String(Math.floor(Math.random() * 1000000000)));
                  listeners[0](msg, {tab:{id:Number(sessionStorage.getItem(key))}}, resolve);
                })
              }, storage: { local: {
                get: async keys => { const data = JSON.parse(localStorage.getItem('shadow-test') || '{}');
                  return keys ? Object.fromEntries(keys.filter(k => k in data).map(k => [k, data[k]])) : data; },
                set: async data => { const old = JSON.parse(localStorage.getItem('shadow-test') || '{}');
                  localStorage.setItem('shadow-test', JSON.stringify({...old, ...data})); },
                remove: async keys => { const data = JSON.parse(localStorage.getItem('shadow-test') || '{}');
                  keys.forEach(k => delete data[k]); localStorage.setItem('shadow-test', JSON.stringify(data)); }
              }}};
            })();"""
            context.add_init_script(bridge + "\n" + (ROOT / "extension/background.js").read_text(encoding="utf-8")
                                    + "\n" + (ROOT / "extension/navigation.js").read_text(encoding="utf-8")
                                    + "\nif (window === window.top) {\n" + (ROOT / "extension/content.js").read_text(encoding="utf-8") + "\n}")
        def record(response):
            if "/api/" in response.url:
                try:
                    events.append({"url": response.url, "status": response.status,
                                   "request": response.request.post_data,
                                   "body": response.json()})
                except Exception:
                    pass
        context.on("response", record)
        context.on("request", lambda request: events.append({"request_url": request.url, "method": request.method})
                   if "/api/subscription/cancel" in request.url else None)
        page = context.new_page()
        page.on("pageerror", lambda error: events.append({"pageerror": str(error)}))
        page.goto(APP + "/static/index.html")
        page.locator("#shadow-assistant-frame").wait_for(timeout=10000)
        worker = SimpleNamespace(evaluate=page.evaluate) if harness else (context.service_workers[0] if context.service_workers else context.wait_for_event("serviceworker"))
        yield page, worker, events
        (tmp_path / "extension-events.json").write_text(json.dumps(events, indent=2))
        print(f"Extension trace: {tmp_path / 'extension-events.json'}")
        context.close()


def panel(page):
    return page.frame_locator("#shadow-assistant-frame")


def wait_for(page, predicate, events, timeout=120):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        page.wait_for_timeout(250)
        if predicate():
            return
        if panel(page).locator("#errorSection:not(.hidden), #completionSection:not(.hidden)").is_visible():
            break
    pytest.fail(f"Timed out at {page.url}\nPanel: {panel(page).locator('body').inner_text()}\nTrace: {json.dumps(events[-8:], indent=2)}")


def subscription():
    return httpx.get(APP + "/api/subscription?user_id=demo").json()["status"]


def start(page, mode="demo", goal=GOAL):
    frame = panel(page)
    frame.locator(f"#modeBtn{mode.title()}").click()
    frame.locator("#instructionInput").fill(goal)
    frame.locator("#startBtn").click()


@pytest.mark.parametrize("approved", [False, True], ids=["reject", "approve"])
def test_demo_start_navigates_without_intermediate_clicks(loaded_extension, approved):
    page, worker, events = loaded_extension
    httpx.post(APP + "/api/scenario", json={"name": "none"}).raise_for_status()
    httpx.post(APP + "/api/subscription/reset?user_id=demo").raise_for_status()
    assert subscription() == "active"
    start(page)
    wait_for(page, lambda: panel(page).locator("#approvalModal:not(.hidden)").is_visible(), events)
    assert "cancel_confirm.html" in page.url
    stored = worker.evaluate("() => chrome.storage.local.get(null)")
    task_id = stored["active_task_id"]
    print(f"Final approval task={task_id}, stored={stored}")
    assert stored["active_mode"] == "demo"
    assert httpx.get(f"{API}/api/task/{task_id}").json()["mode"] == "demo"
    assert subscription() == "active"
    panel(page).locator("#approveBtn" if approved else "#rejectBtn").click()
    if approved:
        wait_for(page, lambda: "cancel_success.html" in page.url, events)
        wait_for(page, lambda: panel(page).locator("#headerStatusText").inner_text() == "COMPLETED", events)
        assert subscription() == "cancelled"
        assert sum(e.get("method") == "POST" and "/api/subscription/cancel" in e.get("request_url", "") for e in events) == 1, events
    else:
        page.wait_for_timeout(2000)
        assert subscription() == "active"
        page.reload()
        page.wait_for_timeout(2500)
        assert subscription() == "active"
        assert not panel(page).locator("#approvalModal:not(.hidden)").is_visible()
    assert not any(e.get("status") == 409 for e in events), events
    for event in events:
        if "/api/navigate" in event.get("url", ""):
            assert event["body"].get("mode") == "demo", event
            assert event["body"]["action"]["action"] != "highlight", event


def test_observe_reversible_navigation_then_explicit_pause_restores(loaded_extension):
    page, worker, events = loaded_extension
    start(page, "observe", GOAL)
    wait_for(page, lambda: "subscription.html" in page.url and page.locator(".shadow-guidance-target").count() == 1, events)
    assert page.locator(".shadow-guidance-target").get_attribute("data-shadow-id") == "btn-cancel-subscription"
    assert panel(page).locator("#headerStatusText").inner_text() == "REVIEW ON PAGE"
    stored = worker.evaluate("() => chrome.storage.local.get(null)")
    assert stored["active_mode"] == "observe"
    assert stored["active_paused_reason"] == "review_on_page"
    panel(page).locator("#pauseBtn").click()
    page.reload()
    page.wait_for_timeout(1000)
    restored = worker.evaluate("() => chrome.storage.local.get(null)")
    assert restored["active_running"] is False
    assert restored["active_paused_reason"] == "user_pause"
    assert "active" in panel(page).locator("#modeBtnObserve").get_attribute("class")
    assert panel(page).locator("#pauseBtnText").inner_text() == "Resume"
    panel(page).locator("#pauseBtn").click()
    wait_for(page, lambda: page.locator(".shadow-guidance-target").count() == 1, events)
    assert httpx.get(f"{API}/api/task/{stored['active_task_id']}").json()["status"] == "paused"
    assert not any(e.get("status") == 409 for e in events), events


def test_restore_terminal_task_offers_new_task_without_navigate(loaded_extension):
    page, worker, events = loaded_extension
    task = httpx.post(API + "/api/task", json={"instruction": GOAL, "mode": "demo"}).json()["task_id"]
    httpx.patch(f"{API}/api/task/{task}/status", json={"status": "cancelled"}).raise_for_status()
    worker.evaluate(f"() => chrome.storage.local.set({json.dumps({'active_task_id': task, 'active_running': True, 'active_status': 'active', 'active_mode': 'demo', 'active_goal': GOAL})})")
    events.clear()
    page.reload()
    wait_for(page, lambda: panel(page).locator("#errorSection:not(.hidden)").is_visible(), events, timeout=10)
    assert "Start New Task" in panel(page).locator("#retryBtn").inner_text()
    assert not any("/api/navigate" in e.get("url", "") for e in events), events
    panel(page).locator("#retryBtn").click()
    assert panel(page).locator("#startBtn").is_visible()


@pytest.mark.skipif(os.environ.get("SHADOW_EXTENSION_HARNESS") != "1", reason="Runtime invalidation is injected only in the explicit script harness")
def test_invalidated_content_stops_resume_attempts(loaded_extension):
    page, worker, events = loaded_extension
    start(page, "guide", "Open subscription management")
    wait_for(page, lambda: page.locator(".shadow-guide-box").count() == 1, events)
    panel(page).locator("#pauseBtn").click()
    wait_for(page, lambda: panel(page).locator("#pauseBtnText").inner_text() == "Resume", events)
    page.evaluate("() => { chrome.runtime.id = undefined; }")
    panel(page).locator("#pauseBtn").click()
    wait_for(page, lambda: panel(page).locator("#errorSection:not(.hidden)").is_visible(), events, timeout=5)
    assert "Extension reloaded. Refresh this page and start again" in panel(page).locator("#errorMsg").inner_text()
    assert not panel(page).locator("#pauseBtn").is_visible()
    assert panel(page).locator("#retryBtn").is_disabled()
    page.reload()
    wait_for(page, lambda: panel(page).locator("#errorSection:not(.hidden)").is_visible(), events, timeout=10)
    assert panel(page).locator("#retryBtn").is_enabled()
    panel(page).locator("#retryBtn").click()
    httpx.post(APP + "/api/subscription/reset?user_id=demo").raise_for_status()
    start(page, "demo")
    wait_for(page, lambda: panel(page).locator("#approvalModal:not(.hidden)").is_visible(), events)
    assert "cancel_confirm.html" in page.url
    assert subscription() == "active"
    panel(page).locator("#rejectBtn").click()


def test_demo_after_restored_observe_needs_only_start(loaded_extension):
    page, worker, events = loaded_extension
    start(page, "guide", "Open subscription management")
    wait_for(page, lambda: page.locator(".shadow-guide-box").count() == 1, events)
    panel(page).locator("#pauseBtn").click()
    wait_for(page, lambda: panel(page).locator("#pauseBtnText").inner_text() == "Resume", events)
    page.reload()
    page.wait_for_timeout(1500)
    assert "active" in panel(page).locator("#modeBtnGuide").get_attribute("class")
    panel(page).locator("#stopBtn").click()
    httpx.post(APP + "/api/subscription/reset?user_id=demo").raise_for_status()
    events.clear()
    start(page, "demo")
    wait_for(page, lambda: panel(page).locator("#approvalModal:not(.hidden)").is_visible(), events)
    assert "cancel_confirm.html" in page.url
    assert subscription() == "active"
    task = worker.evaluate("() => chrome.storage.local.get(null)")
    assert task["active_mode"] == "demo"
    assert httpx.get(f"{API}/api/task/{task['active_task_id']}").json()["mode"] == "demo"
    assert all(e["body"].get("mode") == "demo" for e in events if "/api/navigate" in e.get("url", "")), events
    panel(page).locator("#rejectBtn").click()


@pytest.mark.skipif(os.environ.get("SHADOW_EXTENSION_HARNESS") != "1", reason="Delay injection uses the explicit transport bridge")
def test_late_rejection_does_not_pause_a_replacement_task(loaded_extension):
    page, worker, events = loaded_extension
    httpx.post(APP + "/api/subscription/reset?user_id=demo").raise_for_status()
    start(page)
    wait_for(page, lambda: panel(page).locator("#approvalModal:not(.hidden)").is_visible(), events)
    page.evaluate("""() => {
      const send = chrome.runtime.sendMessage;
      chrome.runtime.sendMessage = async msg => {
        const result = await send(msg);
        if (msg.type === 'APPROVE_ACTION' && !msg.approved) {
          await new Promise(resolve => { window.releaseRejection = resolve; });
        }
        return result;
      };
    }""")
    panel(page).locator("#rejectBtn").click()
    page.wait_for_function("() => typeof window.releaseRejection === 'function'")
    panel(page).locator("#stopBtn").click()
    start(page)
    wait_for(page, lambda: panel(page).locator("#approvalModal:not(.hidden)").is_visible(), events)
    replacement = worker.evaluate("() => chrome.storage.local.get(null)")["active_task_id"]
    page.evaluate("() => window.releaseRejection()")
    page.wait_for_timeout(500)
    assert httpx.get(f"{API}/api/task/{replacement}").json()["status"] == "active"
    assert worker.evaluate("() => chrome.storage.local.get(null)")["active_task_id"] == replacement
    assert subscription() == "active"
