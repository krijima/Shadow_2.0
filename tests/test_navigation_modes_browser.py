"""Real extension scripts + live backend on a non-StreamCove fixture origin."""
import json
import os
import re
import sys
from pathlib import Path
from urllib.parse import urlparse
import httpx
import pytest
from test_demo_panel_navigation import loaded_extension, panel, start, wait_for, API

SITE = "https://membership.test"


@pytest.fixture
def membership_site(loaded_extension, monkeypatch):
    page, worker, events = loaded_extension
    if os.environ.get("SHADOW_EXTENSION_HARNESS") == "1":
        from fastapi.testclient import TestClient
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
        import main
        main.init_db()
        # Replace only the external model call. The real API, status transitions,
        # snapshot validation, navigation policy and browser scripts are exercised.
        def fixture_plan(snapshot, task, history):
            ids = {e['shadow_id'] for e in snapshot['elements']}
            target = next((key for key in ['nav-3', 'nav-2', 'nav-1', 'final-4'] if key in ids), '')
            return {'action': 'click' if target else 'stop', 'element_id': target,
                    'reason': 'Next fixture navigation' if target else 'Membership cancelled on page',
                    'confidence': 1.0, 'planner': 'fixture'}
        monkeypatch.setattr(main.navigator, 'plan_next_action', fixture_plan)
        api_client = TestClient(main.app)
        worker.api_client = api_client
        # Real MV3 background fetches have loopback host permission. In the
        # script harness they run in a web origin, so bridge that transport to
        # the live API without weakening Chrome's private-network protections.
        def backend_fetch(source, url, options):
            response = api_client.request(options.get('method', 'GET'), url,
                                          content=options.get('body'), headers=options.get('headers'))
            events.append({'url': url, 'status': response.status_code,
                           'request': options.get('body'), 'body': response.json()})
            return {'status': response.status_code, 'body': response.text}
        page.context.expose_binding('shadowTestFetch', backend_fetch)
        page.context.add_init_script("""(() => {
          const original = window.fetch;
          window.fetch = async (url, options = {}) => {
            if (String(url).startsWith('http://127.0.0.1:8001/')) {
              const result = await window.shadowTestFetch(String(url), options);
              return new Response(result.body, {status:result.status, headers:{'Content-Type':'application/json'}});
            }
            return original(url, options);
          };
        })();""")
    def serve(route):
        path = urlparse(route.request.url).path
        if path.startswith("/__shadow__/"):
            route.fallback()
            return
        content = {
            "/": '<h1>My account</h1><a data-shadow-id="nav-1" href="/settings">Settings</a>',
            "/settings": '''<h1>Account settings</h1>
              <button type="button" data-shadow-id="nav-2" aria-controls="membership-dialog" onclick="openMembership()">Manage membership</button>
              <script>function openMembership() {
                localStorage.manageClicks = Number(localStorage.manageClicks || 0) + 1;
                setTimeout(() => { const d = document.createElement('div'); d.id='membership-dialog'; d.role='dialog';
                  d.innerHTML='<h2>Membership details</h2><a data-shadow-id="nav-3" href="/membership">View membership</a>';
                  document.body.appendChild(d); }, 600);
              }</script>''',
            "/membership": '''<h1>Your membership</h1><p>Membership is ACTIVE.</p>
              <button type="button" data-shadow-id="final-4" onclick="localStorage.finalClicks=Number(localStorage.finalClicks || 0)+1; this.previousElementSibling.textContent='Membership CANCELLED.'; this.remove()">Cancel membership</button>''',
        }.get(path, "<h1>Missing page</h1>")
        route.fulfill(content_type="text/html", body=f"<!doctype html><html><body>{content}</body></html>")
    page.context.route(SITE + "/**", serve)
    page.goto(SITE + "/")
    page.locator("#shadow-assistant-frame").wait_for()
    events.clear()
    yield page, worker, events


@pytest.fixture
def provider_site(loaded_extension, monkeypatch):
    page, worker, events = loaded_extension
    from fastapi.testclient import TestClient
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
    import main
    main.init_db()
    monkeypatch.setattr(main, "GEMINI_API_KEY", "test-key")
    # Deliberately keeps choosing My Account whenever it exists. Official route
    # selection must prefer a visible Settings menu item over that planner hint.
    monkeypatch.setattr(main.navigator, "plan_next_action", lambda snapshot, task, history: {
        "action": "click" if any(e["shadow_id"] == "my-account" for e in snapshot["elements"]) else "stop",
        "element_id": "my-account" if any(e["shadow_id"] == "my-account" for e in snapshot["elements"]) else "",
        "reason": "Planner route hint", "confidence": 0.98})
    api_client = TestClient(main.app)
    worker.api_client = api_client

    def backend_fetch(source, url, options):
        response = api_client.request(options.get("method", "GET"), url,
                                      content=options.get("body"), headers=options.get("headers"))
        body = response.json()
        events.append({"url": url, "status": response.status_code,
                       "request": options.get("body"), "body": body})
        return {"status": response.status_code, "body": response.text}
    page.context.expose_binding("shadowTestFetch", backend_fetch)
    page.context.add_init_script("""(() => {
      const original = window.fetch;
      window.fetch = async (url, options = {}) => {
        if (String(url).startsWith('http://127.0.0.1:8001/')) {
          const result = await window.shadowTestFetch(String(url), options);
          return new Response(result.body, {status:result.status, headers:{'Content-Type':'application/json'}});
        }
        return original(url, options);
      };
    })();""")

    def serve(route):
        parsed = urlparse(route.request.url)
        path = parsed.path
        if path.startswith("/__shadow__/"):
            route.fallback()
            return
        if parsed.hostname == "music.apple.com":
            open_menu = "open=1" in parsed.query or path.endswith("/account/settings")
            if path.endswith("/account/settings"):
                body = '''<h1>Settings</h1><h2>Subscriptions</h2><button type="button" data-shadow-id="manage-subscriptions" aria-haspopup="dialog">Manage</button>
                  <script>document.querySelector('[data-shadow-id="manage-subscriptions"]').onclick=()=>location.href='/us/account/subscriptions';</script>'''
            elif path.endswith("/account/subscriptions"):
                body = '''<h1>Subscriptions</h1><p>Apple Music is Active</p><button type="button" data-shadow-id="cancel-subscription" onclick="localStorage.cancelClicks=Number(localStorage.cancelClicks||0)+1">Cancel Subscription</button>'''
            elif open_menu:
                body = '''<h1>Apple Music</h1><button type="button" data-shadow-id="my-account" aria-haspopup="menu" aria-expanded="true" onclick="localStorage.accountClicks=Number(localStorage.accountClicks||0)+1">My Account</button>
                  <div role="menu"><a role="menuitem" data-shadow-id="apple-settings" href="/us/account/settings">Settings</a></div>'''
            else:
                if "rerender=1" in parsed.query:
                    # The replacement intentionally has no data-shadow-id. The
                    # extension assigns a fresh temporary ID on each render.
                    body = '''<h1>Apple Music</h1><button type="button" aria-haspopup="menu" aria-expanded="false" onclick="rerenderAccount(this)">My Account</button>
                      <script>function rerenderAccount(button) {
                        localStorage.accountClicks = Number(localStorage.accountClicks || 0) + 1;
                        const replacement = button.cloneNode(true);
                        replacement.onclick = () => rerenderAccount(replacement);
                        button.replaceWith(replacement);
                        setTimeout(() => { const note = document.createElement('p'); note.textContent = 'Feed refreshed'; document.body.appendChild(note); }, 100);
                      }</script>'''
                elif "nochange=1" in parsed.query:
                    body = '''<h1>Apple Music</h1><button type="button" data-shadow-id="my-account" aria-haspopup="menu" aria-expanded="false" onclick="localStorage.accountClicks=Number(localStorage.accountClicks||0)+1">My Account</button>'''
                else:
                    body = '''<h1>Apple Music</h1><button type="button" data-shadow-id="my-account" aria-haspopup="menu" aria-expanded="false" onclick="openAccountMenu()">My Account</button>
                      <script>function openAccountMenu(){localStorage.accountClicks=Number(localStorage.accountClicks||0)+1;const b=document.querySelector('[data-shadow-id="my-account"]');setTimeout(()=>b.setAttribute('aria-expanded','true'),350);setTimeout(()=>{const m=document.createElement('div');m.setAttribute('role','menu');m.innerHTML='<a role="menuitem" data-shadow-id="apple-settings" href="/us/account/settings">Settings</a>';document.body.appendChild(m)},900)}</script>'''
        elif parsed.hostname == "open.spotify.com":
            if path == "/account/plan":
                body = '''<h1>Your plan</h1><p>Premium</p><button data-shadow-id="spotify-cancel" onclick="localStorage.cancelClicks=Number(localStorage.cancelClicks||0)+1">Cancel subscription</button>'''
            else:
                body = '''<h1>Spotify</h1><a data-shadow-id="spotify-manage" href="/account/plan">Manage your plan</a>'''
        else:
            if path == "/gp/primecentral":
                body = '''<h1>Your Prime Membership</h1><button type="button" data-shadow-id="amazon-manage" aria-haspopup="menu" aria-expanded="false" onclick="openManageMenu()">Manage membership</button>
                  <script>function openManageMenu(){localStorage.manageClicks=Number(localStorage.manageClicks||0)+1;const b=document.querySelector('[data-shadow-id="amazon-manage"]');setTimeout(()=>{b.setAttribute('aria-expanded','true');const m=document.createElement('div');m.setAttribute('role','menu');const e=document.createElement('button');e.setAttribute('role','menuitem');e.setAttribute('data-shadow-id','amazon-end');e.textContent='End membership';e.onclick=()=>localStorage.endClicks=Number(localStorage.endClicks||0)+1;m.appendChild(e);document.body.appendChild(m)},500)}</script>'''
            else:
                body = '''<h1>Amazon</h1><a data-shadow-id="amazon-prime" href="/gp/primecentral">Your Prime Membership</a>'''
        route.fulfill(content_type="text/html", body=f"<!doctype html><html><body>{body}</body></html>")

    page.context.route(re.compile(r"https://(music\.apple\.com|open\.spotify\.com|www\.amazon\.in)/.*"), serve)
    events.clear()
    yield page, worker, events


def task_state(worker):
    stored = worker.evaluate("() => chrome.storage.local.get(null)")
    client = getattr(worker, 'api_client', httpx)
    return stored, client.get(f"{API}/api/task/{stored['active_task_id']}").json()


def test_observe_follows_reversible_pages_and_dialog_then_reviews_final(membership_site):
    page, worker, events = membership_site
    start(page, "observe", "Cancel my membership. Open Settings, manage membership, and view membership details. Do not accept offers.")
    wait_for(page, lambda: page.url == SITE + "/membership" and page.locator('.shadow-guidance-target').count() == 1, events, timeout=60)
    assert page.locator('.shadow-guidance-target').inner_text() == "Cancel membership"
    assert page.locator('.shadow-guidance-badge').inner_text() == "Review cancellation."
    assert page.evaluate("Number(localStorage.manageClicks)") == 1
    assert page.evaluate("Number(localStorage.finalClicks || 0)") == 0
    stored, task = task_state(worker)
    assert task["mode"] == "observe" and task["status"] == "paused"
    assert stored["active_paused_reason"] == "review_on_page"
    assert not panel(page).locator('#approvalModal:not(.hidden)').is_visible()
    page.wait_for_timeout(1800)
    assert page.evaluate("Number(localStorage.finalClicks || 0)") == 0
    assert not any(e.get('status') == 409 for e in events), events
    assert "nav-" not in panel(page).locator('#timelineList').inner_text()


@pytest.mark.parametrize("via_box", [True, False], ids=["guide-box", "website-control"])
def test_guide_tracks_full_page_and_delayed_dialog_without_resume(membership_site, via_box):
    page, worker, events = membership_site
    start(page, "guide", "Cancel my membership. Open Settings, manage membership, and view membership details.")
    wait_for(page, lambda: page.locator('.shadow-guide-box').count() == 1, events, timeout=30)
    assert page.locator('.shadow-guide-box').inner_text() == "Open Settings."
    page.locator('.shadow-guide-box' if via_box else '[data-shadow-id="nav-1"]').click()
    wait_for(page, lambda: page.url == SITE + "/settings" and page.locator('.shadow-guide-box').count() == 1, events, timeout=30)
    assert page.locator('.shadow-guide-box').inner_text() == "Open Manage membership."
    page.locator('.shadow-guide-box' if via_box else '[data-shadow-id="nav-2"]').click()
    wait_for(page, lambda: page.locator('.shadow-guide-box').count() == 1 and page.locator('.shadow-guide-box').inner_text() == "Open View membership.", events, timeout=30)
    assert page.evaluate("Number(localStorage.manageClicks)") == 1
    assert page.locator('.shadow-guidance-target').inner_text() == "View membership"
    page.locator('.shadow-guide-box' if via_box else '[data-shadow-id="nav-3"]').click()
    wait_for(page, lambda: page.url == SITE + "/membership" and page.locator('.shadow-guide-box').count() == 1, events, timeout=30)
    assert page.locator('.shadow-guide-box').inner_text() == "Review cancellation."
    page.locator('.shadow-guide-box').click()
    page.wait_for_timeout(800)
    assert page.evaluate("Number(localStorage.finalClicks || 0)") == 0
    assert task_state(worker)[1]["status"] == "paused"
    assert not any(e.get('status') == 409 for e in events), events
    navs = [e for e in events if '/api/navigate' in e.get('url', '')]
    assert len(navs) == 4, json.dumps(navs, indent=2)
    if not via_box:
        # Consequential confirmation belongs to the website, not the guide box.
        page.locator('[data-shadow-id="final-4"]').click()
        wait_for(page, lambda: panel(page).locator('#headerStatusText').inner_text() == 'COMPLETED', events, timeout=30)
        assert page.evaluate("Number(localStorage.finalClicks)") == 1
        assert not panel(page).locator('.verified-card').is_visible()


def test_guide_ignores_noise_and_double_box_clicks(membership_site):
    page, worker, events = membership_site
    start(page, "guide", "Open Settings, manage membership and view membership details to cancel membership.")
    wait_for(page, lambda: page.locator('.shadow-guide-box').count() == 1, events, timeout=30)
    # Unrelated page changes are not a user's consent to navigate.
    page.evaluate("() => document.body.appendChild(document.createElement('p')).textContent = 'Live clock changed'")
    page.evaluate("() => document.querySelector('.shadow-guide-box').click()")
    page.wait_for_timeout(500)
    assert page.url == SITE + "/"
    assert len([e for e in events if '/api/navigate' in e.get('url', '')]) == 1
    page.locator('.shadow-guide-box').click()
    wait_for(page, lambda: page.url == SITE + "/settings" and page.locator('.shadow-guide-box').count() == 1, events, timeout=30)
    # Reinjection must not add a second content controller or click listener.
    page.add_script_tag(path=str(Path(__file__).resolve().parents[1] / 'extension/content.js'))
    page.locator('.shadow-guide-box').dblclick()
    wait_for(page, lambda: page.locator('.shadow-guide-box').count() == 1 and page.locator('.shadow-guide-box').inner_text() == "Open View membership.", events, timeout=30)
    assert page.evaluate("Number(localStorage.manageClicks)") == 1
    assert len([e for e in events if '/api/navigate' in e.get('url', '')]) == 3
    assert page.locator('#shadow-assistant-frame').count() == 1
    assert not any(e.get('status') == 409 for e in events)


def test_explicit_pause_survives_manual_navigation(membership_site):
    page, worker, events = membership_site
    start(page, "guide", "Open Settings and manage membership.")
    wait_for(page, lambda: page.locator('.shadow-guide-box').count() == 1, events, timeout=30)
    panel(page).locator('#pauseBtn').click()
    page.locator('[data-shadow-id="nav-1"]').click()
    page.wait_for_url(SITE + '/settings')
    page.wait_for_timeout(1000)
    stored, task = task_state(worker)
    assert task['status'] == 'paused'
    assert stored['active_paused_reason'] == 'user_pause'
    assert panel(page).locator('#pauseBtnText').inner_text() == 'Resume'
    assert len([e for e in events if '/api/navigate' in e.get('url', '')]) == 1
    panel(page).locator('#pauseBtn').click()
    wait_for(page, lambda: page.locator('.shadow-guide-box').count() == 1, events, timeout=30)
    assert not any(e.get('status') == 409 for e in events)


def test_guide_revalidates_control_changed_after_highlight(membership_site):
    page, worker, events = membership_site
    start(page, "guide", "Open Settings and manage membership.")
    wait_for(page, lambda: page.locator('.shadow-guide-box').count() == 1, events, timeout=30)
    page.evaluate("""() => {
      const control = document.querySelector('[data-shadow-id="nav-1"]');
      control.textContent = 'Cancel membership';
      control.href = '/api/delete';
      control.onclick = () => { localStorage.dangerClicks = '1'; };
    }""")
    page.locator('.shadow-guide-box').click()
    page.wait_for_timeout(500)
    assert page.url == SITE + '/'
    assert page.evaluate("Number(localStorage.dangerClicks || 0)") == 0
    assert page.locator('.shadow-guide-box').inner_text() == 'Review cancellation.'


def test_another_tab_does_not_restore_the_active_task(membership_site):
    page, worker, events = membership_site
    start(page, 'guide', 'Open Settings and manage membership.')
    wait_for(page, lambda: page.locator('.shadow-guide-box').count() == 1, events, timeout=30)
    other = page.context.new_page()
    other.goto(SITE + '/settings')
    other.locator('#shadow-assistant-frame').wait_for()
    other.wait_for_timeout(1000)
    assert panel(other).locator('#startBtn').is_visible()
    assert other.locator('.shadow-guide-box').count() == 0
    assert page.locator('.shadow-guide-box').count() == 1
    assert task_state(worker)[1]['status'] == 'paused'
    assert len([e for e in events if '/api/navigate' in e.get('url', '')]) == 1
    other.close()


def test_pause_during_pending_guide_setup_stays_paused(membership_site):
    page, worker, events = membership_site
    page.evaluate("""() => {
      const show = ShadowPageGuidance.prototype.show;
      ShadowPageGuidance.prototype.show = function(response) {
        const storage = this.api.storage, set = storage.set.bind(storage);
        storage.set = async data => {
          storage.set = set;
          window.guideSetupPending = true;
          await new Promise(resolve => { window.finishGuideSetup = resolve; });
          return set(data);
        };
        return show.call(this, response);
      };
    }""")
    start(page, 'guide', 'Open Settings and manage membership.')
    page.wait_for_function('() => window.guideSetupPending === true')
    panel(page).locator('#pauseBtn').click()
    page.wait_for_function("() => JSON.parse(localStorage.getItem('shadow-test')).active_paused_reason === 'user_pause'")
    page.evaluate('() => window.finishGuideSetup()')
    page.wait_for_timeout(400)
    assert page.locator('.shadow-guide-box').count() == 0
    assert task_state(worker)[0]['active_paused_reason'] == 'user_pause'
    page.reload()
    page.wait_for_timeout(800)
    assert panel(page).locator('#pauseBtnText').inner_text() == 'Resume'
    assert task_state(worker)[1]['status'] == 'paused'


@pytest.mark.parametrize("already_open", [False, True], ids=["delayed-menu", "menu-already-open"])
def test_apple_music_one_start_opens_settings_and_stops_before_cancel(provider_site, already_open):
    page, worker, events = provider_site
    page.goto(f"https://music.apple.com/us/new?{'open=1' if already_open else ''}")
    page.locator("#shadow-assistant-frame").wait_for()
    events.clear()
    start(page, "observe", "Cancel my Apple Music subscription.")
    wait_for(page, lambda: page.url.endswith("/us/account/subscriptions") and
             page.locator("[data-shadow-id='cancel-subscription']").count() == 1 and
             page.locator(".shadow-guidance-target").count() == 1, events, timeout=45)
    assert page.locator(".shadow-guidance-target").inner_text() == "Cancel Subscription"
    assert "Review cancellation." in panel(page).locator("#timelineList").inner_text()
    assert page.evaluate("Number(localStorage.accountClicks || 0)") == (0 if already_open else 1)
    assert page.evaluate("Number(localStorage.cancelClicks || 0)") == 0
    task = task_state(worker)[1]
    assert task["status"] == "paused"
    assert task["mode"] == "observe"
    navigations = [e for e in events if e.get("url", "").endswith("/api/navigate")]
    assert navigations[0]["body"].get("route_step") == ("settings" if already_open else "account_menu")
    assert any('"apple-settings"' in str(e.get("request")) or "Settings" in str(e.get("request"))
               for e in navigations)
    assert not any(e.get("status") == 409 for e in events)


def test_apple_nochange_opener_is_clicked_once_then_shows_specific_guidance(provider_site):
    page, worker, events = provider_site
    page.goto("https://music.apple.com/us/new?nochange=1")
    page.locator("#shadow-assistant-frame").wait_for()
    events.clear()
    start(page, "observe", "Cancel my Apple Music subscription.")
    wait_for(page, lambda: page.locator(".shadow-guidance-badge").inner_text() == "Open Settings to continue.",
             events, timeout=25)
    assert page.evaluate("Number(localStorage.accountClicks || 0)") == 1
    # Observe gives the planner one alternate, verified reversible option. The
    # provider route returns the same opener, so it is rejected without a click.
    assert len([e for e in events if e.get("url", "").endswith("/api/navigate")]) == 2
    assert task_state(worker)[1]["status"] == "paused"


def test_observe_re_rendered_control_is_clicked_once_then_pauses(provider_site):
    """Fresh temporary IDs and feed churn must not count as navigation progress."""
    page, worker, events = provider_site
    page.goto("https://music.apple.com/us/new?rerender=1")
    page.locator("#shadow-assistant-frame").wait_for()
    events.clear()
    start(page, "observe", "Cancel my Apple Music subscription.")
    wait_for(page, lambda: page.locator(".shadow-guidance-badge").count() == 1, events, timeout=25)
    assert page.evaluate("Number(localStorage.accountClicks || 0)") == 1
    assert page.locator(".shadow-guidance-badge").inner_text() == "Open Settings to continue."
    assert len([e for e in events if e.get("url", "").endswith("/api/navigate")]) == 2
    assert task_state(worker)[1]["status"] == "paused"


@pytest.mark.parametrize("provider_url,final_selector,final_counter", [
    ("https://open.spotify.com/", "[data-shadow-id='spotify-cancel']", "cancelClicks"),
    ("https://www.amazon.in/", "[data-shadow-id='amazon-end']", "endClicks"),
])
def test_spotify_and_amazon_routes_stop_before_consequential_click(provider_site, provider_url, final_selector, final_counter):
    page, worker, events = provider_site
    page.goto(provider_url)
    page.locator("#shadow-assistant-frame").wait_for()
    events.clear()
    start(page, "observe", "Cancel my subscription.")
    wait_for(page, lambda: page.locator(final_selector).count() == 1 and
             page.locator(".shadow-guidance-target").count() == 1, events, timeout=45)
    assert "Review cancellation." in panel(page).locator("#timelineList").inner_text()
    assert page.evaluate(f"Number(localStorage.{final_counter} || 0)") == 0
    task = task_state(worker)[1]
    assert task["mode"] == "observe" and task["status"] == "paused"
    assert not any(e.get("status") == 409 for e in events)
