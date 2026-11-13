# StreamCove Demo recovery verification

Baseline: `7c8baea`. Changes are uncommitted in the existing checkout. Existing runtime databases/cache changes were preserved.

## Confirmed findings

- The assistant had two independent restoration paths. Cached mode assignments did not update the selected mode pill, while delayed HOST_CONTEXT selected Demo unconditionally on StreamCove. This reproduced an Observe task with Demo selected, and a host-context race that could overwrite a mode selected before Start. Initialization now waits for the iframe and backend reconciliation before enabling task input; one owner restores the session, and mode is propagated through TASK_CREATED and START_TASK.
- A fresh cancellation task (`ec45e913-8b01-43a1-b158-c3cb66e55895`) reached subscription.html, then POST /api/navigate returned HTTP 200, mode demo, requires_approval true for btn-cancel-subscription. This was an intermediate navigation link. Commit 788a143 added generic cancellation phrases intended for external sites but applied them to StreamCove too. The fix exempts exact known same-origin intermediate navigation routes; final confirmation and external consequential controls retain ShadowLock approval.
- Planner cache keys omitted task, goal, and mode. A focused failing test proved the second task received the first task's plan. Keys now include all three.
- Cached active tasks were restored without backend reconciliation. A cancelled task produced HTTP 409 with body `{"detail":"Task is not active (status: cancelled). Resume it first."}`. This is separate from runtime invalidation and does not establish the cause of the earlier paused-task 409.
- Terminal Resume returned ok=true even when backend status remained cancelled. Resume now requires status=active, and terminal responses return ok=false.
- Reject did not persist a pause; refresh recreated approval. A delayed Reject response could also pause a replacement task. Both now have regression coverage.
- Invalidated runtime is detected once, further commands stop, and a page-level notice survives an unloaded extension iframe: "Extension reloaded. Refresh this page and start again". On refresh a session marker prevents automatic continuation of the obsolete session and offers Start New Task.
- Completion now checks the StreamCove subscription API; an old cancelled database row cannot override an ACTIVE API response.

## Validation actually performed

1. `SHADOW_EXTENSION_HARNESS=1 python -m pytest tests -q --tb=short`: 76 passed, 85 deprecation warnings (before the final timing refinements and extra delayed-Reject test).
2. Final focused script-harness run: 7 passed in 101.72 seconds. It covers Start-once Reject and Approve, Observe manual navigation/Resume, terminal restoration, stale-runtime refresh followed by fresh Demo Start, Demo after restored Observe, and a delayed Reject response racing a replacement task.
3. Final backend/ShadowLock/boundary checks: 17 passed. JavaScript syntax checks and git diff --check passed.
4. The harness executes the repository's real content.js, background.js and assistant.js in installed Chrome against the live services. Only Chrome runtime messaging/storage are bridged. Demo tests click only SHADOW Start and the final decision; no intermediate StreamCove or Resume clicks. API is ACTIVE before approval and after Reject (including refresh); Approve sends exactly one subscription-cancel POST and reaches CANCELLED/COMPLETED.
5. Passing final focused examples: Reject task e78131bd-8fed-4535-824b-59a4579a1ba9; Approve task 0448310c-e1d5-4184-a280-87cf7470a0ff. Compact request/response traces are in task-flow-evidence.json.
6. User-operated unpacked Edge check: user explicitly reported that one Demo Start reached final approval without Resume or any intermediate StreamCove clicks. A direct subscription API read then confirmed ACTIVE. User then reported Reject; task 8681aafc-33b3-40fc-b295-e5d54ed36f84 is Demo/paused with approval 88 rejected, and the subscription API confirmed ACTIVE with cancelled_at=null. A fresh user-operated Demo run then reached final approval automatically, received one Approve click, opened success and displayed COMPLETED. The API confirmed CANCELLED; task 834e0823-6921-4ee9-91f1-c428b7f79f92 is completed, approval 89 approved, and its audit has exactly one approved_and_dispatched final click. Details are in manual-edge-checks.json.

## Limits

Windows Application Control blocked Playwright's bundled Chromium DLL (0x11C7). Installed Chrome launched but did not inject the unpacked extension. The new loaded-extension regression fails when injection is missing; the legacy tests can return successfully in that situation. Therefore their pass count is not evidence of an unpacked-extension flow. No Windows protections were changed. Computer Use was not retried; the user operated Edge manually.

The earlier bare pytest invocation was stopped after yielding no progress output; targeting tests/ completed. Browser runtime reload behavior and Observe navigation/Resume pass in the harness; live Edge stale-tab notice and cross-page Observe/Resume were not manually verified. The user confirmed same-page Observe Resume without 409, then requested completion using the harness.

## Changed source

- extension/content.js: initialization, backend reconciliation, mode continuity, reload recovery, confirmed Resume, pause and rejection lifecycle.
- extension/assistant/assistant.js: single restoration owner, synchronized/locked task mode, backend-confirmed Start mode, reload error UI.
- extension/assistant/assistant.html: Start New Task recovery button.
- extension/background.js: 127.0.0.1:8001, GET_TASK reconciliation, compact API diagnostics.
- backend/main.py: truthful terminal Resume responses, subscription API verification, contextual approval check.
- backend/shadow_lock.py: exact StreamCove intermediate navigation exceptions.
- backend/shadow_navigate.py: task/goal/mode cache isolation.
- tests/test_demo_panel_navigation.py and tests/test_task_recovery.py: focused regressions.

## Run and retry

In separate PowerShell windows:

```powershell
Set-Location 'C:\Users\jaink\Program\Shadow\devhost_lastmoment'
python -m uvicorn main:app --app-dir backend --host 127.0.0.1 --port 8001 --reload
```

```powershell
Set-Location 'C:\Users\jaink\Program\Shadow\devhost_lastmoment'
python -m uvicorn server:app --app-dir streamcove --host 127.0.0.1 --port 8080 --reload
```

Do not launch duplicates if those ports are already serving the project.

Reload SHADOW at edge://extensions, then refresh the StreamCove tab. Use Start New Task if shown, or Abort to leave a deliberately restored paused task. Reset the synthetic subscription to ACTIVE in Demo Controls, return to http://127.0.0.1:8080/static/index.html, choose Demo and click Start once with the cancellation goal. Wait for final approval without Resume or host-page clicks.

If it stalls, the SHADOW service-worker console now logs [SHADOW API] entries with task_id, request_mode, response_mode, action, status, requires_approval and HTTP status. Capture the matching /api/task and /api/navigate Network response bodies with Preserve log enabled.

Run the script harness explicitly:

```powershell
$env:SHADOW_EXTENSION_HARNESS='1'
python -m pytest tests/test_demo_panel_navigation.py tests/test_task_recovery.py -q
```

For a genuine loaded-extension check omit SHADOW_EXTENSION_HARNESS; set SHADOW_TEST_BROWSER to a supported extension-capable Chromium executable if needed. Missing injection is a failure, never a successful cancellation test.

Final targeted Observe recheck: 1 passed in 8.71 seconds, task 6365eac3-1ece-42ee-ba97-0027f49dee70. The strengthened test asserts the Settings gear is highlighted, manually opens /static/account.html, verifies backend and cached status remain paused with Observe preserved and no automatic next request, then resumes, receives a successful highlight response, and returns to paused with no HTTP 409. No Demo production code changed after the successful manual cancellation runs.
