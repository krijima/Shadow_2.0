"""Exercise the production popup's script registration and activation boundary."""
from pathlib import Path
import pytest
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize('already_active', [False, True])
def test_popup_installs_provider_and_audit_helpers_on_real_site(already_active):
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        page.set_content(''.join(f'<div id="{name}"></div>' for name in (
            'siteHost', 'statusDot', 'statusText', 'actionBtnText', 'infoText')) +
            '<button id="actionBtn">Activate</button>')
        page.evaluate('''active => {
          window.calls = {executed: [], registrations: []};
          window.chrome = {
            tabs: {query: async () => [{id: 7, url: 'https://pocketfm.com/'}],
                   sendMessage: async (id, msg) => ({alive: active})},
            permissions: {request: async () => true},
            scripting: {
              getRegisteredContentScripts: async () => [{id: 'shadow-https---pocketfm-com--', js: ['navigation.js','content.js']}],
              updateContentScripts: async data => calls.registrations.push(...data),
              registerContentScripts: async data => calls.registrations.push(...data),
              executeScript: async data => calls.executed.push(data.files)},
            storage: {local: {get: async () => ({}), set: async () => {}}},
            runtime: {sendMessage: async () => ({ok: true})}};
          window.close = () => {};
        }''', already_active)
        page.add_script_tag(path=str(ROOT / 'extension/popup/popup.js'))
        page.evaluate('() => initPopup()')
        page.locator('#actionBtn').click()
        page.wait_for_function('() => calls.executed.length > 0')
        calls = page.evaluate('() => calls')
        assert calls['executed'][-1] == ['terminal_audit.js', 'pocketfm.js', 'navigation.js', 'content.js']
        assert calls['registrations'][-1]['js'] == calls['executed'][-1]
        browser.close()
