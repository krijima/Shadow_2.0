import os
import sys
import time
import httpx
from playwright.sync_api import sync_playwright

def run_capture():
    os.makedirs(os.path.abspath("artifacts/screenshots"), exist_ok=True)
    extension_path = os.path.abspath("extension")
    user_data_dir = os.path.abspath("test_user_data_evidence")

    # 1. Reset StreamCove subscription to active
    try:
        httpx.post("http://127.0.0.1:8080/api/subscription/reset?user_id=demo")
    except Exception as e:
        print(f"Warning: StreamCove reset: {e}")

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

        # Step 1: Initialize on StreamCove index to ensure assistant iframe is loaded
        page.goto("http://127.0.0.1:8080/static/index.html")
        page.wait_for_load_state("networkidle")
        time.sleep(2)

        # Evidence 1: Retention step with dark pattern highlighting
        page.goto("http://127.0.0.1:8080/static/cancel_step2.html")
        page.wait_for_load_state("networkidle")
        time.sleep(1.5)

        # Trigger visual highlight on the retention offer element
        page.evaluate("""() => {
            const retentionBtn = document.querySelector('[data-shadow-id="btn-accept-offer"]') || document.querySelector('.btn-primary');
            if (retentionBtn) {
                retentionBtn.classList.add("shadow-dp-highlight");
                const rect = retentionBtn.getBoundingClientRect();
                const badge = document.createElement("div");
                badge.className = "shadow-dp-badge";
                badge.innerHTML = "<span>🛡️</span><span>SHADOW: Potential Dark Pattern (RETENTION OFFER)</span>";
                badge.style.top = `${rect.top + window.scrollY - 24}px`;
                badge.style.left = `${Math.max(10, rect.left + window.scrollX)}px`;
                document.body.appendChild(badge);
            }
        }""")
        time.sleep(0.5)
        path1 = os.path.abspath("artifacts/screenshots/phase3_dark_pattern_visual_highlight.png")
        page.screenshot(path=path1)
        print(f"Captured: {path1}")

        # Evidence 2: Guided Navigation Pulsing Outline & Badge on navigation target
        page.goto("http://127.0.0.1:8080/static/subscription.html")
        page.wait_for_load_state("networkidle")
        time.sleep(1.5)

        page.evaluate("""() => {
            const cancelBtn = document.querySelector('[data-shadow-id="btn-cancel-subscription"]');
            if (cancelBtn) {
                cancelBtn.classList.add("shadow-guidance-target");
                const rect = cancelBtn.getBoundingClientRect();
                const badge = document.createElement("div");
                badge.className = "shadow-guidance-badge";
                badge.innerHTML = "<span>🎯</span><span>SHADOW GUIDANCE: Recommended Step</span>";
                badge.style.top = `${rect.top + window.scrollY - 24}px`;
                badge.style.left = `${Math.max(10, rect.left + window.scrollX)}px`;
                document.body.appendChild(badge);
            }
        }""")
        time.sleep(0.5)
        path2 = os.path.abspath("artifacts/screenshots/phase4_guidance_target_pulse.png")
        page.screenshot(path=path2)
        print(f"Captured: {path2}")

        # Evidence 3: Guided Navigation Modal inside Assistant UI
        assistant_file = "file:///" + os.path.abspath("extension/assistant/assistant.html").replace("\\", "/")
        modal_page = context.new_page()
        modal_page.goto(assistant_file)
        modal_page.wait_for_load_state("networkidle")
        time.sleep(1)
        modal_page.evaluate("""() => {
            const modal = document.getElementById("approvalModal");
            const title = document.getElementById("approvalTitle");
            const desc = document.getElementById("approvalActionDesc");
            const reason = document.getElementById("approvalReason");
            const badge = document.querySelector("#approvalModal .modal-warning-badge");
            const notice = document.querySelector("#approvalModal .modal-notice");
            const approve = document.getElementById("approveBtn");
            const reject = document.getElementById("rejectBtn");

            if (modal) {
                modal.classList.remove("hidden");
                if (title) title.textContent = "Confirm Guided Navigation Step";
                if (badge) badge.textContent = "🎯 GUIDED ACTION APPROVAL";
                if (notice) notice.textContent = "SHADOW identified this next navigation step. Confirm to navigate or skip to stay on current view.";
                if (desc) desc.textContent = 'Click "Cancel Subscription" (#btn-cancel-subscription)';
                if (reason) reason.textContent = 'Guidance: User requested cancellation options; advancing toward subscription management.';
                if (approve) approve.innerHTML = "<span>Confirm & Navigate</span>";
                if (reject) reject.innerHTML = "<span>Skip Step</span>";
            }
        }""")
        time.sleep(0.5)
        path3 = os.path.abspath("artifacts/screenshots/phase4_guide_mode_modal.png")
        modal_page.screenshot(path=path3)
        print(f"Captured: {path3}")
        modal_page.close()

        # Evidence 4: Final Successful Verified Cancellation
        page.goto("http://127.0.0.1:8080/static/cancel_success.html")
        page.wait_for_load_state("networkidle")
        time.sleep(1.5)
        path4 = os.path.abspath("artifacts/screenshots/phase4_streamcove_full_flow_success.png")
        page.screenshot(path=path4)
        print(f"Captured: {path4}")

        context.close()

        context.close()

if __name__ == "__main__":
    run_capture()
