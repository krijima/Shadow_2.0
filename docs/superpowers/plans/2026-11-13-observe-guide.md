# Observe and Guide navigation implementation plan

Goal: implement the user's specified automatic reversible Observe navigation and click-following Guide behavior on activated ordinary websites, preserving verified StreamCove Demo approval.

Design: a deterministic policy classifies the planner's actual observed target, never trusting planner prose as permission to mutate. Observe clicks only clearly named same-origin navigation links or non-submit navigation/disclosure controls; all other actions become on-page review. Guide shows a single nearby box; only reversible steps may be dispatched by that box. Direct website clicks remain the user's actions. Content owns continuation, waits for a meaningful DOM/URL change, and confirms backend activation before replanning a waiting task. Explicit user pauses remain pauses. Demo keeps its existing loop and approval.

Normal sites: activation requests optional permission for the selected site's HTTP/HTTPS origin pattern and registers a persistent content script for that site. No blanket auto-activation on other websites. Re-activation/reinjection must not duplicate the panel or event listeners.

Alternatives: planner-only safety would trust page text and generated prose too much; broad automatic clicks would also change consequential controls. Use conservative DOM-based classification instead. Keep the existing Chrome runtime/backend architecture.

- [x] Add failing backend policy and real-script browser harness tests using non-StreamCove pages, with full-page and same-page transitions, final mutation counters and duplicate-click checks.
- [x] Implement Observe/Guide policy responses and compact website-label guidance; retain Demo handling.
- [x] Implement on-page guide boxes, guarded transition detection and serialized backend resume/replanning. Preserve user pause, stale runtime recovery and task identity guards.
- [x] Add per-site permission/content-script registration and reinjection guard for ordinary sites.
- [x] Update obsolete tests for the newly requested Observe/Guide semantics. Run focused browser tests, StreamCove Demo regressions, relevant backend checks and the project suite. Record live-browser limitations.

Verification focus: submit buttons named Settings; malicious/cross-origin links; rapid duplicate clicks; delayed dialog rendering; unrelated DOM changes; explicit pauses; final confirmation never dispatched in Observe/Guide; backend paused state reconciliation; navigation injection on granted domains only.
