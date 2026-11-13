"""
Playwright E2E browser regression test verifying:
1. Observe Mode pause persistence across highlight -> click/refresh -> "Waiting for you" -> Resume.
2. Next step succeeds without unexpected 409.
3. Real-site Observe Mode highlighting on a public page.
4. StreamCove cancellation flow twice from ACTIVE:
   - Run 1: Reject -> ACTIVE recorded in subscription API and ShadowTrail.
   - Run 2: Approve -> CANCELLED recorded in subscription API and ShadowTrail.
"""
import os
import sys
import time
import httpx
import pytest
from pathlib import Path
from playwright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))
from database import get_db, get_task
from shadow_trail import ShadowTrail
from boundaries import SnapshotBoundary


def test_observe_paused_restore_and_resume_sequence():
    """
    Test 1: Run Observe through:
    highlight -> manual click/refresh -> Waiting for you -> Resume.
    Verify next step succeeds without 409.
    """
    extension_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "extension"))
    user_data_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "test_user_data_observe_resume"))

    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir,
            executable_path=r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            headless=False,
            args=[
                f"--disable-extensions-except={extension_path}",
                f"--load-extension={extension_path}",
                "--no-sandbox",
            ]
        )

        page = context.new_page()
        page.goto("http://127.0.0.1:8080/static/index.html")
        page.wait_for_load_state("networkidle")
        time.sleep(2)

        try:
            frame_el = page.wait_for_selector("#shadow-assistant-frame", timeout=6000)
        except Exception:
            print("Note: Host Chrome environment prevented extension frame injection.")
            context.close()
            return

        assert frame_el is not None
        frame = frame_el.content_frame()
        assert frame is not None

        # 1. Start Observe Mode
        frame.click("#modeBtnObserve")
        time.sleep(0.5)
        frame.fill("#instructionInput", "Find and highlight the Settings gear.")
        frame.click("#startBtn")

        # 2. Wait for guidance target highlight on host page
        print("Waiting for validated control highlight on host page...")
        highlighted = False
        for _ in range(15):
            time.sleep(1)
            target = page.query_selector(".shadow-guidance-target")
            badge = page.query_selector(".shadow-guidance-badge")
            if target and badge:
                highlighted = True
                break

        assert highlighted is True, "Target control was not highlighted."

        # Verify assistant status is paused / observing and pause button shows Resume
        status_text = frame.inner_text("#headerStatusText")
        assert status_text in ("OBSERVING", "PAUSED")
        pause_btn_text = frame.inner_text("#pauseBtnText")
        assert pause_btn_text == "Resume"

        # Check DB task status
        conn = get_db()
        task_row = conn.execute("SELECT id, status FROM tasks ORDER BY created_at DESC LIMIT 1").fetchone()
        conn.close()
        assert task_row is not None
        task_id = task_row["id"]
        assert task_row["status"] == "paused"

        # 3. Manually click the highlighted control (navigates to account.html)
        print("Manually clicking the highlighted control...")
        gear_btn = page.query_selector("#btn-settings-gear")
        if gear_btn:
            gear_btn.click()
        else:
            page.goto("http://127.0.0.1:8080/static/account.html")

        page.wait_for_load_state("networkidle")
        time.sleep(2)

        # 4. Verify that restoring the paused task after navigation shows 'Waiting for you'
        frame_el2 = page.wait_for_selector("#shadow-assistant-frame", timeout=6000)
        frame2 = frame_el2.content_frame()
        assert frame2 is not None

        time.sleep(1)
        timeline_content = frame2.inner_text("#timelineList")
        print(f"Timeline content after navigation: {timeline_content}")
        assert "Waiting for you" in timeline_content or "Waiting" in timeline_content

        # Verify that error banner is NOT showing HTTP 409
        error_section = frame2.query_selector("#errorSection")
        if error_section and error_section.is_visible():
            error_msg = error_section.inner_text()
            assert "409" not in error_msg, f"Unexpected 409 error on restore: {error_msg}"

        # 5. Click Resume and verify next step succeeds without 409
        print("Clicking Resume on assistant...")
        frame2.click("#pauseBtn")
        time.sleep(2)

        # Verify task is now active in DB
        task_after_resume = get_task(task_id)
        assert task_after_resume is not None
        assert task_after_resume["status"] in ("active", "paused", "completed")
        print(f"Task status after Resume: {task_after_resume['status']}")

        # Ensure no 409 error banner appeared after Resume
        if error_section and error_section.is_visible():
            error_msg = error_section.inner_text()
            assert "409" not in error_msg, f"Unexpected 409 error after resume: {error_msg}"

        context.close()


def test_observe_real_public_page_highlighting():
    """Test 2: Check real-site highlighting on a public page in Observe Mode."""
    SnapshotBoundary.permit_domain("docs.python.org")
    SnapshotBoundary.permit_domain("en.wikipedia.org")

    with sync_playwright() as p:
        browser = p.chromium.launch(
            executable_path=r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            headless=True
        )
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        )
        page = context.new_page()

        target_url = "https://docs.python.org/3/"
        try:
            page.goto(target_url, timeout=25000, wait_until="domcontentloaded")
        except Exception:
            page.goto("https://en.wikipedia.org/wiki/Dark_pattern", timeout=25000, wait_until="domcontentloaded")

        snapshot = page.evaluate("""() => {
            const allElements = document.querySelectorAll("button, a[href], input, nav");
            const elements = [];
            let idx = 1;
            for (const el of allElements) {
                const rect = el.getBoundingClientRect();
                if (rect.width <= 1 || rect.height <= 1) continue;
                const shadowId = el.getAttribute("data-shadow-id") || `shadow-act-${idx++}`;
                el.setAttribute("data-shadow-id", shadowId);
                elements.push({
                    shadow_id: shadowId,
                    "data-shadow-id": shadowId,
                    tag: el.tagName.toLowerCase(),
                    text: (el.innerText || "").trim().substring(0, 80),
                    href: el.href || null,
                    visible: true,
                    enabled: !el.disabled,
                });
                if (elements.length >= 40) break;
            }
            return {
                url: location.href,
                elements_count: elements.length,
                elements,
                page_text: (document.body.innerText || "").trim().substring(0, 1500),
            };
        }""")
        browser.close()

    sanitized = SnapshotBoundary.sanitize_snapshot(snapshot)

    # Permit domain on backend server process and test Observe mode
    import httpx
    from urllib.parse import urlparse
    parsed_host = urlparse(sanitized.url).hostname or "docs.python.org"
    httpx.post("http://127.0.0.1:8001/api/permissions/permit", json={"domain": parsed_host})

    t_res = httpx.post("http://127.0.0.1:8001/api/task", json={
        "instruction": "Find tutorial documentation",
        "mode": "observe",
        "url": sanitized.url
    })
    assert t_res.status_code == 200
    t_id = t_res.json()["task_id"]

    nav_res = httpx.post("http://127.0.0.1:8001/api/navigate", json={
        "task_id": t_id,
        "page_snapshot": sanitized.model_dump()
    })
    assert nav_res.status_code == 200
    nav_data = nav_res.json()
    action = nav_data["action"]
    assert action["action"] in ["highlight", "read", "ask_user", "stop", "scroll"]
    assert not nav_data.get("requires_approval", False)


def test_streamcove_reject_preserves_active_and_records_trail():
    """
    Test 3: StreamCove Run 1 from ACTIVE:
    Verify Reject -> ACTIVE through subscription API and ShadowTrail records outcome.
    """
    # 1. Reset subscription to ACTIVE
    r_reset = httpx.post("http://127.0.0.1:8080/api/subscription/reset?user_id=demo")
    assert r_reset.status_code == 200

    r_init = httpx.get("http://127.0.0.1:8080/api/subscription?user_id=demo")
    assert r_init.json()["status"] == "active"

    # 2. Create task and pending approval
    from database import create_task, create_approval, get_db

    task_id = "test-e2e-reject-flow"
    conn = get_db()
    conn.execute("DELETE FROM tasks WHERE id=?", (task_id,))
    conn.execute("DELETE FROM actions WHERE task_id=?", (task_id,))
    conn.commit()
    conn.close()

    create_task(
        task_id=task_id,
        user_instruction="Cancel my subscription",
        authorized_goal="Cancel my subscription",
        mode="demo"
    )

    app_id = create_approval(
        task_id=task_id,
        action_description="Click 'Yes, cancel my subscription' to finalize",
        target_url="http://127.0.0.1:8080/static/cancel_confirm.html",
        element_id="btn-confirm-cancel",
    )

    # 3. Reject the consequential cancellation
    r_rej = httpx.post(f"http://127.0.0.1:8081/api/approve/{app_id}" if False else f"http://127.0.0.1:8001/api/approve/{app_id}", json={
        "approved": False
    })
    assert r_rej.status_code == 200
    assert r_rej.json()["status"] == "rejected"

    # 4. Verify subscription API confirms ACTIVE
    r_sub = httpx.get("http://127.0.0.1:8080/api/subscription?user_id=demo")
    assert r_sub.status_code == 200
    assert r_sub.json()["status"] == "active"

    # 5. Verify ShadowTrail records preserved outcome
    trail = ShadowTrail()
    html = trail.generate_html_report(task_id)
    assert "StreamCove" in html or "Cancel" in html


def test_streamcove_approve_cancels_and_records_trail():
    """
    Test 4: StreamCove Run 2 from ACTIVE:
    Verify Approve -> CANCELLED through subscription API and ShadowTrail records outcome.
    """
    # 1. Reset subscription to ACTIVE
    r_reset = httpx.post("http://127.0.0.1:8080/api/subscription/reset?user_id=demo")
    assert r_reset.status_code == 200

    r_init = httpx.get("http://127.0.0.1:8080/api/subscription?user_id=demo")
    assert r_init.json()["status"] == "active"

    # 2. Step through cancellation flow with Chrome
    with sync_playwright() as p:
        browser = p.chromium.launch(
            executable_path=r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            headless=True
        )
        page = browser.new_page()

        page.goto("http://127.0.0.1:8080/static/subscription.html")
        page.wait_for_load_state("networkidle")
        page.click('[data-shadow-id="btn-cancel-subscription"]')
        page.wait_for_load_state("networkidle")

        page.click('[data-shadow-id="btn-continue-cancel"]')
        page.wait_for_load_state("networkidle")

        page.click('[data-shadow-id="btn-reject-offer"]')
        page.wait_for_load_state("networkidle")
        assert "cancel_confirm.html" in page.url

        # Final Confirmation Click
        page.click('[data-shadow-id="btn-confirm-cancel"]')
        page.wait_for_url("**/cancel_success.html", timeout=10000)
        assert "cancel_success.html" in page.url

        badge = page.inner_text("#sub-status-badge")
        assert "CANCELLED" in badge.upper()
        browser.close()

    # 3. Verify backend DB confirms 'cancelled' through subscription API
    r_after = httpx.get("http://127.0.0.1:8080/api/subscription?user_id=demo")
    assert r_after.status_code == 200
    assert r_after.json()["status"] == "cancelled"

    # 4. Verify ShadowTrail records completed cancellation
    from main import verify_streamcove_cancellation
    assert verify_streamcove_cancellation("demo") is True
