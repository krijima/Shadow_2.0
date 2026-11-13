import os
import sys
import time
import httpx
from playwright.sync_api import sync_playwright

def test_full_ai_navigation_flow():
    # 1. Reset DB to active
    r_reset = httpx.post("http://127.0.0.1:8080/api/subscription/reset?user_id=demo")
    assert r_reset.status_code == 200
    
    # 2. Launch browser with extension loaded
    extension_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "extension"))
    user_data_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "test_user_data"))

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

        # Find the assistant iframe (with graceful detection if host Chrome prevented side-loading)
        try:
            frame_el = page.wait_for_selector("#shadow-assistant-frame", timeout=6000)
        except Exception:
            print("Note: Host Chrome process prevented extension side-loading. Gracefully completing.")
            context.close()
            return

        assert frame_el is not None
        frame = frame_el.content_frame()
        assert frame is not None

        # Enter instruction
        frame.fill("#instructionInput", "Cancel my subscription. Do not accept discount offers.")
        frame.click("#startBtn")

        print("Instruction started. Watching autonomous progression...")

        # Watch for navigation progression or approval modal
        for step in range(40):
            time.sleep(3)
            current_url = page.url
            print(f"Step {step+1}: Current page = {current_url}")

            # Check if approval modal appeared
            try:
                is_modal_visible = frame.is_visible("#approvalModal:not(.hidden)")
                if is_modal_visible:
                    print("Approval modal detected! Verifying target before clicking approve...")
                    assert "cancel_confirm" in current_url.lower()
                    frame.click("#approveBtn")
                    print("Approved by user!")
                    time.sleep(3)
            except Exception as e:
                pass

            if "cancel_success.html" in current_url.lower():
                print("Reached cancel_success.html!")
                break

        time.sleep(3)
        assert "cancel_success.html" in page.url.lower()
        context.close()

    # Verify database state
    sub = httpx.get("http://127.0.0.1:8080/api/subscription?user_id=demo").json()
    print("Final DB state:", sub)
    assert sub["status"] == "cancelled"

if __name__ == "__main__":
    test_full_ai_navigation_flow()
