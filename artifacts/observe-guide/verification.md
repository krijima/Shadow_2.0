# Observe and Guide update

Existing checkout and earlier Demo fixes preserved; changes remain uncommitted.

## Behavior

- Observe follows validated reversible navigation automatically. Form submissions, destructive or ambiguous controls, cross-origin links, and low-confidence proposals stop at on-page review. The actual control is highlighted with its website label.
- Guide shows one nearby box. Clicking the box dispatches only a validated reversible step. Clicking the website control follows the user's action. Both paths wait for a page/dialog change, activate a backend-paused task before its next navigation request, then present the next box without Resume.
- Review boxes never dispatch consequential controls. The user confirms those on the website. The normal-site completion view does not claim StreamCove database verification.
- Explicit Pause survives navigation and delayed storage/status responses. Duplicate box clicks, synthetic website-generated clicks, reinjection, and unrelated DOM changes do not cause duplicate navigation.
- A control's current semantics are compared with the classified snapshot immediately before dispatch. A changed target becomes review-only.
- Persisted task ownership is checked against the real Chrome tab ID and site. Opening another activated tab does not take over the current task.
- The popup requests access only to the selected site and registers content scripts for its later page transitions. Other origins need their own activation. This uses Chrome's [optional host permissions](https://developer.chrome.com/docs/extensions/reference/api/permissions) and [registered content scripts](https://developer.chrome.com/docs/extensions/reference/api/scripting).
- Demo retains its StreamCove boundary, final ShadowLock approval, single submission, Reject preservation and API-confirmed completion.

## Validation

- Full local suite: **98 passed**, 145 deprecation warnings (initial complete run).
- Final controlled browser-harness checks: **8 passed**, including Observe automatic navigation to final cancellation review; Guide box and native-control clicks across full-page and delayed-dialog updates; manual website final confirmation; duplicate/synthetic click rejection; explicit pause; target revalidation; unrelated-tab isolation; delayed guide setup.
- Backend policy: 11 cases covering real labels, submit buttons, dangerous links, cross-site links, ambiguous controls, low confidence, and mode-specific behavior.
- Site activation: 2 executable popup tests covering granted and declined site access and persistent script registration.
- StreamCove Demo/recovery regression: **7 passed** in the focused run, including fresh Reject/Approve flows. Those Demo runs start from the panel and let SHADOW perform intermediate clicks. The Approve test asserts exactly one cancellation POST, API ACTIVE before approval, and CANCELLED/COMPLETED afterwards.
- JavaScript syntax checks and git diff --check pass. Separate read-only review found no remaining important issues after the safety/race fixes.

Final whole-suite confirmation: **98 passed, 259 deprecation warnings in 249.12 seconds**, recorded in suite-final.log. The final controlled browser log is browser-final.log (8 passed).

## Harness and live-browser limits

The controlled website is served through Playwright routing at https://membership.test. The repository's real background, navigation, content, and assistant scripts run in installed Chrome. The Chrome runtime/storage boundary is bridged explicitly. Initial runs used the live backend and configured model; the initial 98-test complete suite passed. A repeat run then had three API transport timeouts while waiting for planner responses. To make the controlled navigation regression deterministic, its final fixture substitutes only the external model call and runs the real FastAPI endpoints, validators, policy, status transitions and database through TestClient. Demo regressions continue to use the running backend on 127.0.0.1:8001 and StreamCove on 127.0.0.1:8080.

Live unpacked-extension behavior on public websites and the new per-site browser permission prompt are **unverified in this session**. Previously observed local limits remain: installed Chrome did not inject the extension from test launch flags, and Windows Application Control blocked Playwright's bundled Chromium. No Windows/browser protections were changed. Legacy loaded-extension tests can return successfully when injection is missing; their pass count does not prove an unpacked-extension check.

The navigation policy is deliberately conservative and recognizes common English navigation labels. Arbitrary websites, cross-origin workflows, embedded frames, closed shadow roots, and misleading site controls are not guaranteed to work automatically. Uncertain steps stop for website review rather than gaining execution permission from model prose.

## Files changed for this update

- backend/navigation_policy.py: DOM-derived reversible-navigation classification.
- backend/main.py and backend/boundaries.py: Observe/Guide policy responses and observed control semantics.
- extension/navigation.js: guide boxes, click/transition continuation, target revalidation, pause guards.
- extension/content.js: controller integration, active-dialog reading, ownership and restoration.
- extension/background.js: tab identity and loading both content modules.
- extension/manifest.json and extension/popup/popup.js: optional per-site activation and persistent injection.
- extension/assistant/assistant.js and assistant.html: compact actual-label guidance, logs for internal IDs, mode copy and normal-site completion.
- tests/test_navigation_modes_browser.py, test_navigation_modes_policy.py and test_site_activation.py: new regressions.
- tests/test_demo_panel_navigation.py: load the new module and update obsolete Observe expectations while preserving Demo assertions.
- README.md and docs/superpowers/plans/2026-11-13-observe-guide.md: behavior and implementation notes.

Earlier uncommitted Demo fixes in shadow_lock.py, shadow_navigate.py and task_recovery tests were retained.

## Use on an ordinary website

Reload SHADOW at edge://extensions and refresh the website. Open the SHADOW extension popup, choose Activate SHADOW, and allow that site. Select Observe or Guide and click Start with the goal. Ordinary-site consequential confirmation remains on the website. Demo continues at http://127.0.0.1:8080/static/index.html.

Run the local suite from the project directory:

```powershell
$env:SHADOW_EXTENSION_HARNESS='1'
python -m pytest tests -q
```
