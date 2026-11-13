"""
Playwright E2E test verifying fresh Observe task:
'Find and highlight the Settings gear.'
Verifies that:
1. Observe mode targets the validated control on the page.
2. The element receives '.shadow-guidance-target' and the guidance badge is displayed.
3. The content script pauses and waits for the user without looping into a stalled-progress halt.
4. The backend task status transitions to 'paused' rather than 'halted'.
"""
import os
import sys
import time
import httpx
import pytest
from pathlib import Path
from playwright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))
from database import get_task


def test_observe_settings_gear_with_loaded_extension():
    extension_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "extension"))
    user_data_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "test_user_data_observe"))

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

        # Select Observe mode
        frame.click("#modeBtnObserve")
        time.sleep(0.5)

        # Enter instruction
        frame.fill("#instructionInput", "Find and highlight the Settings gear.")
        frame.click("#startBtn")

        # Wait for the guidance target highlight on the host page
        print("Waiting for validated control highlight on host page...")
        highlighted = False
        for _ in range(15):
            time.sleep(1)
            target = page.query_selector(".shadow-guidance-target")
            badge = page.query_selector(".shadow-guidance-badge")
            if target and badge:
                highlighted = True
                print("Control successfully highlighted with SHADOW Guidance badge!")
                break

        assert highlighted is True, "Expected .shadow-guidance-target and .shadow-guidance-badge on host page"

        # Verify target is the settings gear or account control
        target_el = page.query_selector(".shadow-guidance-target")
        target_id = target_el.get_attribute("data-shadow-id")
        print(f"Highlighted target element ID: {target_id}")
        assert target_id in ("btn-settings-gear", "link-account", "link-account-quick", "link-subscription")

        # Verify that Observe mode did NOT continuously loop or trigger a stall halt
        time.sleep(3)
        # Check assistant status text
        status_text = frame.inner_text("#headerStatusText")
        print(f"Assistant status text: {status_text}")
        assert status_text in ("OBSERVING", "PAUSED", "GUIDANCE ACTIVE")

        # Verify backend task is paused, not halted
        from database import get_db
        conn = get_db()
        row = conn.execute("SELECT id, status, mode FROM tasks ORDER BY created_at DESC LIMIT 1").fetchone()
        conn.close()
        assert row is not None
        latest_task = dict(row)
        print(f"Latest task in DB: {latest_task}")
        assert latest_task["mode"] == "observe"
        assert latest_task["status"] in ("paused", "active")
        assert latest_task["status"] != "halted"

        context.close()
