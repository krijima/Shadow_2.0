# Provider Route Automation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** Follow verified reversible cancellation routes for Apple Music, Spotify, and Amazon Prime India, then stop at account-changing controls.

**Architecture:** A small provider-route catalog supplies official help citations and ordered label intents. Backend selection matches route intents to live, visible snapshot controls and then reuses the existing safety policy; extension logic waits for a stable URL/DOM snapshot before requesting another step.

**Tech Stack:** FastAPI/Python, MV3 extension JavaScript, existing pytest/Playwright harness.

**Spec:** `docs/superpowers/specs/2026-11-13-provider-cancellation-routes-design.md`

## Global Constraints

- Do not click final cancellation, renewal, submission, or account-change actions.
- Route text and model output are hints; live DOM evidence and origin policy gate dispatch.
- Preserve explicit Pause, Guide click continuation, and StreamCove Demo approval and Reject behavior.
- Keep the backend on `127.0.0.1:8001` and StreamCove on `127.0.0.1:8080`.

## Review Focus

- Apple menu is already open: choose Settings without clicking My Account again.
- Apple menu renders late at the same URL: wait for the menu item, then re-snapshot.
- Menu trigger produces no state change: stop and show specific route guidance.
- Partner-billed membership: identify the handoff without submitting an account change.
- Official cross-origin link: request only that origin’s permission before following it.

---

### Task 1: Provider route catalog and backend selection

**Files:** Create `backend/provider_routes.py`; modify `backend/navigation_policy.py`, `backend/boundaries.py`, `backend/main.py`; test `tests/test_provider_routes.py` and `tests/test_navigation_modes_policy.py`.

- [ ] Add failing tests for Apple menu-open priority, verified closed-menu trigger, Spotify Manage your plan, Amazon Prime India membership route, partner handoff, and final-action stop.
- [ ] Run those tests and verify they fail for the current planner-only route selection.
- [ ] Add official source URLs and ordered route intents; select only current visible matching controls.
- [ ] Revalidate selected candidate through ActionBoundary, ShadowLock, and navigation policy.
- [ ] Run provider and policy tests.

### Task 2: Same-page menu state and stable snapshots

**Files:** Modify `extension/content.js`, `extension/navigation.js`; test `tests/test_navigation_modes_browser.py`.

- [ ] Add failing Apple harness cases for an already-open menu and a menu whose Settings row appears after a delayed same-URL mutation.
- [ ] Confirm the existing behavior repeats My Account or plans before Settings appears.
- [ ] Wait for a stable visible-control signature after progress and replan from a fresh snapshot.
- [ ] Show “Open Settings to continue.” after a no-change menu attempt without repeating the click.
- [ ] Verify one opener click maximum and zero final cancellation clicks.

### Task 3: Provider origins and Guide/Observe confirmation boundary

**Files:** Modify `extension/background.js`, `extension/assistant/assistant.js`, `extension/assistant/assistant.html`, `extension/content.js`; add/update provider route browser tests.

- [ ] Add tests for provider-origin permission request/decline, Guide click continuation, and final cancellation non-dispatch.
- [ ] Request only the required official origin through a user-triggered browser permission prompt and register the content scripts after grant.
- [ ] Preserve user-confirmed partner handoff and stop before account changes.
- [ ] Run provider, Guide, and permission tests.

### Task 4: StreamCove regression and completion checks

**Files:** No additional production files expected.

- [ ] Run StreamCove Demo Approve and Reject panel flows in the existing harness.
- [ ] Run the full relevant suite, JavaScript syntax checks, and `git diff --check`.
- [ ] Record route sources, exact pass counts, and any live Edge steps that remained harness-only.
