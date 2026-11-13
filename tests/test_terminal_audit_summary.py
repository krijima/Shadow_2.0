"""Browser-level coverage for the assistant's end-of-task audit summary."""

from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parents[1]
ASSISTANT_URL = (ROOT / "extension" / "assistant" / "assistant.html").as_uri()


@pytest.mark.parametrize(
    ("mode", "event_type", "status"),
    [
        ("observe", "TASK_COMPLETE", "completed"),
        ("guide", "TASK_HALTED", "halted"),
        ("demo", "TASK_FAILED", "failed"),
    ],
)
def test_terminal_outcomes_render_audit_summary_for_every_mode(mode, event_type, status):
    """Removing terminal audit rendering would leave every mode without evidence."""
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        page.add_init_script(
            "window.chrome = { storage: { local: { set: () => Promise.resolve(), remove: () => Promise.resolve() } } };"
        )
        page.goto(ASSISTANT_URL)

        page.evaluate(
            """({ mode, eventType, status }) => {
                const send = message => window.dispatchEvent(new MessageEvent("message", { data: message }));
                send({ source: "SHADOW_CONTENT", type: "HOST_CONTEXT", hostname: "example.test", is_streamcove: mode === "demo" });
                send({ source: "SHADOW_CONTENT", type: "TASK_CREATED", task_id: "audit-task-42", mode });
                send({ source: "SHADOW_CONTENT", type: "ACTION_TAKEN", mode,
                    action: { element_text: "Open account settings" }, result: "dispatched", detections: [] });
                send({
                    source: "SHADOW_CONTENT",
                    type: eventType,
                    task_id: "audit-task-42",
                    mode,
                    status,
                    message: "Task finished safely.",
                    reason: "Task stopped at the requested boundary.",
                    error: "The navigation request failed.",
                    detections: [{ category: "fake_urgency", reason: "Artificial deadline" }],
                    approval_count: 1,
                });
            }""",
            {"mode": mode, "eventType": event_type, "status": status},
        )

        audit = page.locator(".terminal-audit-card:visible")
        assert audit.is_visible()
        assert audit.get_by_text(status.upper(), exact=True).is_visible()
        assert audit.get_by_text(mode.upper(), exact=True).is_visible()
        assert audit.get_by_text("3 STEPS", exact=True).is_visible()
        assert audit.get_by_text("1 PATTERN", exact=True).is_visible()
        assert audit.get_by_text("1 APPROVAL", exact=True).is_visible()

        report_action = page.locator("[data-audit-report-action]:visible")
        assert report_action.is_enabled()
        assert report_action.get_attribute("data-report-url") == "http://localhost:8001/api/evidence/audit-task-42/html"
        browser.close()


def test_terminal_audit_disables_report_action_without_a_task_id():
    """A missing task id must not create a broken evidence-report link."""
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        page.add_init_script(
            "window.chrome = { storage: { local: { set: () => Promise.resolve(), remove: () => Promise.resolve() } } };"
        )
        page.goto(ASSISTANT_URL)
        page.evaluate(
            """() => window.dispatchEvent(new MessageEvent("message", { data: {
                source: "SHADOW_CONTENT", type: "TASK_FAILED", mode: "observe", status: "failed", error: "No task id"
            }}))"""
        )

        assert page.locator(".terminal-audit-card:visible").is_visible()
        assert page.locator("[data-audit-report-action]:visible").is_disabled()
        browser.close()
