"""
Integration test verifying Universal Observer on real public websites (Wikipedia).
"""
import os
import sys
import pytest
from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend")))
from boundaries import SnapshotBoundary
from shadow_scan import ShadowScan

def test_wikipedia_universal_observer_and_scan():
    # 1. User permits en.wikipedia.org and docs.python.org
    SnapshotBoundary.permit_domain("en.wikipedia.org")
    SnapshotBoundary.permit_domain("docs.python.org")

    with sync_playwright() as p:
        browser = p.chromium.launch(
            executable_path=r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            headless=True
        )
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            locale="en-US"
        )
        page = context.new_page()

        # Try Wikipedia, fallback to Python Docs if Wikimedia triggers anti-bot WAF
        target_url = "https://en.wikipedia.org/wiki/Dark_pattern"
        page.goto(target_url, timeout=30000)
        if "Wikimedia Error" in page.title():
            target_url = "https://docs.python.org/3/"
            page.goto(target_url, timeout=30000)

        assert any(k in page.title() for k in ("Dark pattern", "Python", "Documentation"))

        # Evaluate universal observer logic in real browser context
        snapshot = page.evaluate("""() => {
            const selectors = [
                "button",
                "a[href]",
                "input:not([type='hidden'])",
                "select",
                "textarea",
                "h1", "h2", "h3",
                '[role="button"]',
                '[role="link"]',
                '[role="search"]',
                '.badge',
            ];
            const allElements = document.querySelectorAll(selectors.join(","));
            const elements = [];
            let autoIdx = 1;

            for (const el of allElements) {
                const rect = el.getBoundingClientRect();
                if (rect.width <= 1 || rect.height <= 1) continue;
                const style = window.getComputedStyle(el);
                if (style.display === "none" || style.visibility === "hidden" || parseFloat(style.opacity || "1") < 0.05) continue;

                let shadowId = el.getAttribute("data-shadow-id") || `shadow-act-${autoIdx++}`;
                el.setAttribute("data-shadow-id", shadowId);

                elements.push({
                    shadow_id: shadowId,
                    "data-shadow-id": shadowId,
                    tag: el.tagName.toLowerCase(),
                    type: el.getAttribute("type") || null,
                    text: (el.innerText || "").trim().substring(0, 80),
                    href: el.href || null,
                    visible: true,
                    enabled: !(el.disabled || el.getAttribute("aria-disabled") === "true"),
                    bounding_rect: { x: Math.round(rect.x), y: Math.round(rect.y), width: Math.round(rect.width), height: Math.round(rect.height) },
                });
                if (elements.length >= 60) break;
            }

            return {
                url: location.href,
                title: document.title,
                elements_count: elements.length,
                elements: elements,
                page_text: (document.body.innerText || "").trim().substring(0, 2000),
            };
        }""")

        browser.close()

    # Verify structured universal observations
    assert snapshot["elements_count"] > 10
    assert any(el["tag"] == "h1" for el in snapshot["elements"])
    assert any(el["tag"] == "a" for el in snapshot["elements"])

    # 2. Verify SnapshotBoundary bounds and accepts Wikipedia snapshot
    validated = SnapshotBoundary.sanitize_snapshot(snapshot)
    assert validated.url.startswith("https://en.wikipedia.org")
    assert validated.elements_count > 10

    # 3. Verify ShadowScan does not invent false positives on legitimate public encyclopedia
    scanner = ShadowScan()
    detections = scanner.scan_all(validated.model_dump(), "wiki-test-task")
    # Wikipedia informational content should NOT be flagged as deceptive urgency or confirm shaming
    assert not any(d["category"] in ("confirm_shaming", "fake_urgency") for d in detections)


def test_github_docs_universal_observer():
    SnapshotBoundary.permit_domain("docs.github.com")

    with sync_playwright() as p:
        browser = p.chromium.launch(
            executable_path=r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            headless=True
        )
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = context.new_page()

        page.goto("https://docs.github.com/en", timeout=30000)
        assert "GitHub" in page.title()

        snapshot = page.evaluate("""() => {
            const selectors = ["button", "a[href]", "input", "nav", "h1", "h2", '[role="button"]', '[role="link"]'];
            const allElements = document.querySelectorAll(selectors.join(","));
            const elements = [];
            let autoIdx = 1;

            for (const el of allElements) {
                const rect = el.getBoundingClientRect();
                if (rect.width <= 1 || rect.height <= 1) continue;
                const style = window.getComputedStyle(el);
                if (style.display === "none" || style.visibility === "hidden") continue;

                let shadowId = el.getAttribute("data-shadow-id") || `shadow-act-${autoIdx++}`;
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
                if (elements.length >= 50) break;
            }

            return {
                url: location.href,
                elements_count: elements.length,
                elements: elements,
                page_text: (document.body.innerText || "").trim().substring(0, 2000),
            };
        }""")

        browser.close()

    assert snapshot["elements_count"] > 10
    validated = SnapshotBoundary.sanitize_snapshot(snapshot)
    assert validated.url.startswith("https://docs.github.com")
    assert validated.elements_count > 10
