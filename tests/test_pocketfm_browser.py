"""Real extension controller on a local Pocket FM fixture; no real subscription is modified."""
import pytest
from test_navigation_modes_browser import provider_site, task_state
from test_demo_panel_navigation import loaded_extension, panel, start, wait_for


@pytest.mark.parametrize('decision', ['approve', 'reject', 'disabled', 'delegated', 'hover-heading'])
def test_pocketfm_one_start_then_only_final_approval(provider_site, decision):
    page, worker, events = provider_site
    body = '''<!doctype html><html><head><meta charset="utf-8"></head><body><h1>Pocket FM</h1>
      <button onclick="localStorage.storeClicks=Number(localStorage.storeClicks||0)+1">Store</button>
      <div style="position:absolute;right:20px;top:10px;cursor:pointer" onclick="openProfile()">
        <img width="45" height="45" alt="Anonymous" src="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='45' height='45'%3E%3C/svg%3E"></div>
      <div id="view"></div>
      <script>
      const view=document.querySelector('#view');
      function openProfile(){localStorage.profileClicks=Number(localStorage.profileClicks||0)+1;
        view.innerHTML='<div style="cursor:pointer" onclick="manage()">Manage Subscriptions</div>'}
      function manage(){localStorage.manageClicks=Number(localStorage.manageClicks||0)+1;
        setTimeout(()=>view.innerHTML='<section role="dialog"><h2>Active subscriptions</h2><div style="cursor:pointer" onclick="plan()"><span>60 mins daily</span><p>Premium · Renews monthly</p></div></section>',800)}
      function plan(){localStorage.planClicks=Number(localStorage.planClicks||0)+1;
        view.innerHTML='<section role="dialog"><h2>Current plan details</h2><p>Status Active</p><button DISABLED onclick="cancelPlan()">Cancel Subscription</button></section>'}
      function cancelPlan(){localStorage.cancelClicks=Number(localStorage.cancelClicks||0)+1;
        view.innerHTML='<section role="dialog"><h2>Subscription cancelled</h2><p>Cancellation successful</p></section>'}
      </script></body></html>'''.replace('DISABLED', 'disabled' if decision == 'disabled' else '')
    if decision == 'delegated':
        body = body.replace('cursor:pointer', 'cursor:default').replace(
            'onclick="openProfile()"', 'id="account-trigger"').replace(
            'alt="Anonymous"', 'alt=""').replace(
            'const view=', "document.addEventListener('click', event => { if(event.target.closest('#account-trigger')) openProfile(); }); const view=")
    if decision == 'hover-heading':
        body = body.replace('onclick="openProfile()"', 'onmouseenter="openProfile()"').replace(
            '<span>60 mins daily</span>', '<h5><span>✨</span>60 mins daily</h5>')
    def serve(route):
        if '/__shadow__/' in route.request.url:
            route.fallback()
        else:
            route.fulfill(content_type='text/html', body=body)
    page.context.route('https://pocketfm.com/**', serve)
    page.goto('https://pocketfm.com/')
    page.locator('#shadow-assistant-frame').wait_for()
    events.clear()
    # The first-page shortcut fills the instruction; Start runs the same-tab flow.
    panel(page).locator('#modeBtnObserve').click()
    panel(page).locator('#quickTagCancel').click()
    assert 'Cancel my subscription' in panel(page).locator('#instructionInput').input_value()
    panel(page).locator('#startBtn').click()
    if decision == 'disabled':
        wait_for(page, lambda: 'disabled' in panel(page).locator('#timelineList').inner_text().lower(), events, timeout=35)
        assert not panel(page).locator('#askUserModal:not(.hidden)').is_visible()
    else:
        wait_for(page, lambda: panel(page).locator('#approvalModal:not(.hidden)').is_visible(), events, timeout=35)
    assert page.evaluate('Number(localStorage.storeClicks||0)') == 0
    assert page.evaluate('Number(localStorage.profileClicks||0)') == 1
    assert page.evaluate('Number(localStorage.manageClicks||0)') == 1
    assert page.evaluate('Number(localStorage.planClicks||0)') == 1
    assert page.evaluate('Number(localStorage.cancelClicks||0)') == 0
    if decision == 'disabled':
        assert task_state(worker)[1]['status'] == 'paused'
        return
    assert page.url == 'https://pocketfm.com/'
    panel(page).locator('#approveBtn' if decision in ('approve', 'delegated', 'hover-heading') else '#rejectBtn').click()
    if decision in ('approve', 'delegated', 'hover-heading'):
        wait_for(page, lambda: panel(page).locator('#headerStatusText').inner_text() == 'COMPLETED', events, timeout=30)
        assert page.evaluate('Number(localStorage.cancelClicks||0)') == 1
    else:
        page.wait_for_timeout(1200)
        assert page.evaluate('Number(localStorage.cancelClicks||0)') == 0


def test_pocketfm_guide_waits_for_each_manual_website_click(provider_site):
    page, worker, events = provider_site
    body = r'''<html><head><meta charset="utf-8"></head><body><h1>Pocket FM</h1>
      <button aria-label="Profile" onclick="step('manage')">Profile</button><div id="view"></div>
      <script>
      const view = document.querySelector('#view');
      function step(name){localStorage[name]=Number(localStorage[name]||0)+1;
        if(name==='manage') view.innerHTML='<button onclick="step(\'plan\')">Manage Subscriptions</button>';
        if(name==='plan') view.innerHTML='<h2>Active subscriptions</h2><button onclick="step(\'details\')">60 mins daily</button>';
        if(name==='details') view.innerHTML='<h2>Current plan details</h2><button onclick="step(\'cancel\')">Cancel Subscription</button>';
      }
      </script></body></html>'''
    def serve(route):
        if '/__shadow__/' in route.request.url:
            route.fallback()
        else:
            route.fulfill(content_type='text/html; charset=utf-8', body=body)
    page.context.route('https://pocketfm.com/**', serve)
    page.goto('https://pocketfm.com/')
    page.locator('#shadow-assistant-frame').wait_for()
    start(page, 'guide', 'Cancel my Pocket FM subscription')
    for label, counter in [('Profile', 'manage'), ('Manage Subscriptions', 'plan'),
                           ('60 mins daily', 'details'), ('Cancel Subscription', 'cancel')]:
        wait_for(page, lambda: page.locator('.shadow-guidance-target').count() == 1 and
            page.locator('.shadow-guidance-target').inner_text() == label, events, timeout=25)
        page.wait_for_timeout(700)
        assert page.evaluate(f'Number(localStorage.{counter}||0)') == 0
        if counter != 'cancel':
            page.locator('.shadow-guidance-target').click()
    assert task_state(worker)[1]['status'] == 'paused'
    assert page.evaluate('Number(localStorage.cancel||0)') == 0
