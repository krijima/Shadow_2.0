"""Local browser fixture; never accesses a real GitHub account."""
from pathlib import Path
from playwright.sync_api import sync_playwright


def test_observe_opens_native_billing_disclosure_and_advances():
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        page.route("https://github.test/**", lambda route: route.fulfill(
            content_type="text/html", body='''<h1>Public profile</h1>
            <details><summary data-shadow-id="billing">Billing and licensing</summary>
            <a href="/settings/billing/licensing">Licensing</a></details>'''))
        page.goto("https://github.test/settings/profile")
        page.add_script_tag(path=str(Path(__file__).resolve().parents[1] / "extension/navigation.js"))
        result = page.evaluate("""async () => {
          let clicks = 0;
          const target = () => ({shadow_id: 'billing', tag: 'summary', type: null,
            text: 'Billing and licensing', accessible_name: 'Billing and licensing',
            href: null, in_form: false, role: null, controls: '',
            expanded: String(document.querySelector('details').open), has_popup: false, menu_context: false});
          const api = {snapshot: () => ({elements: [target()]}), mode: () => 'observe', task: () => 'github-fixture',
            execute: () => {clicks++; document.querySelector('summary').click(); return {result: 'clicked'};},
            post: () => {}, send: async () => ({status: 'paused'}),
            storage: {set: async () => {}}, clear: () => {}, highlight: () => {}};
          const controller = new ShadowPageGuidance(api);
          const advanced = await controller.navigate({action: {action: 'click', element_id: 'billing'},
            navigation_target: target(), reversible: true});
          return {advanced, clicks, open: document.querySelector('details').open};
        }""")
        assert result == {"advanced": True, "clicks": 1, "open": True}
        browser.close()
