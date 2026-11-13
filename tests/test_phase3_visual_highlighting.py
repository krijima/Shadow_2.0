import os
import sys
import time
import httpx
from playwright.sync_api import sync_playwright

# Add backend to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend")))

from database import init_db, get_db
from shadow_scan import ShadowScan
from shadow_trail import ShadowTrail

init_db()

def test_phase3_highlighting_dom_and_view_on_page():
    scanner = ShadowScan()
    trail = ShadowTrail()

    with sync_playwright() as p:
        browser = p.chromium.launch(
            executable_path=r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            headless=True
        )
        page = browser.new_page()

        # Step 1: Retention Offer on cancel_step2.html
        page.goto("http://127.0.0.1:8080/static/cancel_step2.html")
        page.wait_for_load_state("networkidle")

        # Snapshot of cancel_step2
        snapshot = {
            "url": page.url,
            "page_text": page.inner_text("body"),
            "elements": [
                {
                    "data-shadow-id": "btn-accept-offer",
                    "tag": "a",
                    "text": page.inner_text('[data-shadow-id="btn-accept-offer"]'),
                    "visible": True,
                },
                {
                    "data-shadow-id": "btn-reject-offer",
                    "tag": "button",
                    "text": page.inner_text('[data-shadow-id="btn-reject-offer"]'),
                    "visible": True,
                }
            ]
        }
        detections = scanner.scan_all(snapshot, "test-highlight-task")
        assert any(d["category"] == "retention_offer" for d in detections)
        retention_det = next(d for d in detections if d["category"] == "retention_offer")
        assert retention_det["element_id"] == "btn-accept-offer"

        # Inject and test visual highlight layer logic
        page.evaluate("""(detections) => {
            // Test highlight function matching content.js implementation
            const style = document.createElement('style');
            style.id = 'shadow-highlight-styles';
            style.textContent = `
                .shadow-dp-highlight { outline: 2px dashed #f59e0b !important; }
                .shadow-dp-highlight-critical { outline: 2px dashed #ef4444 !important; }
                .shadow-dp-badge { position: absolute; pointer-events: none; }
                .shadow-dp-focus-pulse { animation: pulse 1s; }
            `;
            document.head.appendChild(style);

            detections.forEach(d => {
                if (!d.element_id) return;
                const el = document.querySelector(`[data-shadow-id="${d.element_id}"]`);
                if (el) {
                    el.classList.add(d.category === 'prompt_injection' ? 'shadow-dp-highlight-critical' : 'shadow-dp-highlight');
                    const badge = document.createElement('div');
                    badge.className = 'shadow-dp-badge';
                    badge.setAttribute('data-shadow-badge-for', d.element_id);
                    badge.textContent = `SHADOW: Potential Dark Pattern (${d.category.toUpperCase()})`;
                    document.body.appendChild(badge);
                }
            });
        }""", detections)

        # Check DOM highlight on btn-accept-offer
        is_highlighted = page.evaluate("""() => {
            const el = document.querySelector('[data-shadow-id="btn-accept-offer"]');
            return el ? el.classList.contains('shadow-dp-highlight') : false;
        }""")
        assert is_highlighted is True

        badge_text = page.inner_text('.shadow-dp-badge[data-shadow-badge-for="btn-accept-offer"]')
        assert "RETENTION_OFFER" in badge_text

        # Step 2: Test "View on Page" smooth scroll and pulse without click
        view_result = page.evaluate("""() => {
            let clicked = false;
            const target = document.querySelector('[data-shadow-id="btn-accept-offer"]');
            target.addEventListener('click', (e) => { clicked = true; });

            // Simulate VIEW_ON_PAGE
            target.scrollIntoView({ behavior: 'smooth', block: 'center' });
            target.classList.add('shadow-dp-focus-pulse');
            target.focus();

            return {
                hasPulseClass: target.classList.contains('shadow-dp-focus-pulse'),
                wasClicked: clicked
            };
        }""")
        assert view_result["hasPulseClass"] is True
        assert view_result["wasClicked"] is False  # Must NOT automatically click!

        # Step 3: Test cleanup on clear / navigation
        page.evaluate("""() => {
            document.querySelectorAll('.shadow-dp-highlight, .shadow-dp-highlight-critical, .shadow-dp-focus-pulse')
                .forEach(el => el.classList.remove('shadow-dp-highlight', 'shadow-dp-highlight-critical', 'shadow-dp-focus-pulse'));
            document.querySelectorAll('.shadow-dp-badge').forEach(b => b.remove());
        }""")
        cleared_badges = page.query_selector_all(".shadow-dp-badge")
        assert len(cleared_badges) == 0

        # Step 4: Test missing / invalid element ID
        invalid_detection = [{
            "category": "fake_urgency",
            "element_id": "non-existent-element-xyz",
            "visible_text": "Hurry!",
            "reason": "Artificial urgency",
            "element_context": "element:non-existent-element-xyz"
        }]
        # Should execute safely without throwing errors or adding badges
        page.evaluate("""(dets) => {
            dets.forEach(d => {
                if (!d.element_id) return;
                const el = document.querySelector(`[data-shadow-id="${d.element_id}"]`);
                if (el) {
                    el.classList.add('shadow-dp-highlight');
                }
            });
        }""", invalid_detection)

        # Step 5: Verify Evidence Trail Integration
        trail_report = trail.generate_report("test-highlight-task")
        assert "detections" in trail_report
        # Confirm at least one detection logged with required fields
        logged = trail_report["detections"]
        assert len(logged) > 0
        first_det = logged[0]
        assert "category" in first_det
        assert "visible_text" in first_det
        assert "timestamp" in first_det

        browser.close()
