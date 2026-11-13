# Terminal Audit Summary Design

## Intent

Show a concise, trustworthy audit summary whenever a SHADOW task reaches a terminal outcome in Observe, Guide, or Demo mode, with one-click access to the existing full ShadowTrail report.

## Goals

- Render the same audit-summary card for completed, halted, failed, and cancelled task outcomes.
- Include outcome, mode, completed-step count, dark-pattern count, and approval count when available.
- Keep the existing full report available through `/api/evidence/{task_id}/html`.
- Preserve the current completion and retry/start-new-task controls.

## Non-goals

- Do not change task-policy decisions, backend report generation, or browser navigation behavior.
- Do not automatically open a new tab or download a report.

## Approaches considered

1. Open the existing report automatically. This makes the report prominent but disrupts the current task experience.
2. Show an embedded summary with a full-report button. Selected because it keeps the result visible in the assistant while leaving navigation in the user's control.

## Design

`extension/content.js` will attach terminal task metadata to every terminal assistant message. `extension/assistant/assistant.js` will normalize that metadata into one renderer shared by success and error views. `assistant.html` and `assistant.css` will add the shared audit-summary card and report action. The report action will be enabled only when a task id is available.

## Verification

Unit-level browser tests will dispatch terminal messages for Observe, Guide, and Demo and assert that the correct summary values and `/api/evidence/{task_id}/html` action are rendered. Existing suite failures caused by the locally occupied port 8080 are documented separately.
