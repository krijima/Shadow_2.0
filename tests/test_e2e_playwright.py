import os
import sys
import pytest
import sqlite3
import subprocess
import time
import httpx
from playwright.sync_api import sync_playwright

def test_streamcove_cancellation_flow():
    # 1. Start StreamCove server as a background process for test
    streamcove_proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "server:app", "--port", "8081", "--host", "127.0.0.1"],
        cwd=os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "streamcove")),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )

    try:
        # Wait for server to come up and reset subscription to active
        for _ in range(15):
            try:
                httpx.post("http://127.0.0.1:8081/api/subscription/reset?user_id=demo")
                r = httpx.get("http://127.0.0.1:8081/api/subscription?user_id=demo")
                if r.status_code == 200 and r.json()["status"] == "active":
                    break
            except Exception:
                time.sleep(0.5)

        # 2. Verify initial active subscription state
        res = httpx.get("http://127.0.0.1:8081/api/subscription?user_id=demo")
        assert res.status_code == 200
        assert res.json()["status"] == "active"

        # 3. Use Playwright to step through the cancellation journey using installed Chrome
        with sync_playwright() as p:
            browser = p.chromium.launch(
                executable_path=r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                headless=True
            )
            page = browser.new_page()

            # Step A: Home
            page.goto("http://127.0.0.1:8081/static/index.html")
            assert "StreamCove" in page.title()
            
            # Step B: Subscription Page
            page.click('[data-shadow-id="link-subscription"]')
            page.wait_for_load_state("networkidle")
            assert "subscription" in page.url.lower()

            # Step C: Cancel Step 1
            page.click('[data-shadow-id="btn-cancel-subscription"]')
            page.wait_for_load_state("networkidle")
            assert "cancel_step1" in page.url.lower()

            # Step D: Retention Offer (Step 2)
            page.click('[data-shadow-id="btn-continue-cancel"]')
            page.wait_for_load_state("networkidle")
            assert "cancel_step2" in page.url.lower()

            # Reject retention offer
            page.click('[data-shadow-id="btn-reject-offer"]')
            page.wait_for_load_state("networkidle")
            assert "cancel_confirm" in page.url.lower()

            # Step E: Confirm Cancel
            page.click('[data-shadow-id="btn-confirm-cancel"]')
            page.wait_for_url("**/cancel_success.html")
            assert "cancel_success" in page.url.lower()

            # Verify UI confirmed cancellation
            status_text = page.inner_text("#sub-status-badge")
            assert "CANCELLED" in status_text.upper()

            browser.close()

        # 4. Verify DB state genuinely updated to cancelled
        res_after = httpx.get("http://127.0.0.1:8081/api/subscription?user_id=demo")
        assert res_after.status_code == 200
        assert res_after.json()["status"] == "cancelled"

    finally:
        streamcove_proc.terminate()
        streamcove_proc.wait()
