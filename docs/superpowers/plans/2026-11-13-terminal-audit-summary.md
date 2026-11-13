# Terminal Audit Summary Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show an in-assistant audit summary and full-report action for every terminal task outcome in Observe, Guide, and Demo.

**Architecture:** The content script is the terminal-state producer and will include mode, task id, status, action/detection data in completion, halt, and failure messages. The assistant iframe will render a mode-independent audit card from that normalized message data and delegate opening the full HTML report to the parent frame.

**Tech Stack:** Chrome extension JavaScript, HTML/CSS, Playwright/Pytest browser harness, existing FastAPI ShadowTrail endpoint.

**Spec:** `docs/superpowers/specs/2026-11-13-terminal-audit-summary-design.md`

## Global Constraints

- Do not alter policy, task status transitions, or report-generation endpoint contracts.
- Support Observe, Guide, and Demo terminal outcomes.
- Preserve existing success, halt, retry, and start-new-task behavior.

## Review Focus

- Terminal messages missing optional action or detection arrays render a zero-count summary without JavaScript errors.
- Halted and failed outcomes show the same audit action as completed outcomes.
- A stale or missing task id disables the full-report action rather than opening an invalid URL.
- The summary reflects the selected operating mode, not a planner-provided mode.
- Rendering untrusted completion/reason text remains escaped.

### Task 1: Produce normalized terminal audit metadata

**Files:**
- Modify: `extension/content.js: navigationLoop terminal and failure branches`
- Test: `tests/test_terminal_audit_summary.py`

**Interfaces:**
- Produces iframe messages with `task_id`, `mode`, `status`, `detections`, and terminal reason/message.

- [ ] **Step 1: Write failing terminal-message tests**

Cover completed Demo, halted Guide, and failed Observe messages; assert each includes task id, mode, terminal status, and a detection array.

- [ ] **Step 2: Run the focused test to verify it fails**

Run: `python -m pytest tests/test_terminal_audit_summary.py -q`

- [ ] **Step 3: Add terminal metadata in `extension/content.js`**

Send the active `taskId` and `currentMode` with each terminal message and preserve backend status/reason data where available.

- [ ] **Step 4: Run the focused test to verify it passes**

Run: `python -m pytest tests/test_terminal_audit_summary.py -q`

### Task 2: Render the shared audit summary and report action

**Files:**
- Modify: `extension/assistant/assistant.html: completion and error sections`
- Modify: `extension/assistant/assistant.css: audit-summary styles`
- Modify: `extension/assistant/assistant.js: terminal-state renderer and report action`
- Test: `tests/test_terminal_audit_summary.py`

**Interfaces:**
- Consumes: terminal message metadata from Task 1.
- Produces: an accessible audit card and report action using `/api/evidence/{task_id}/html`.

- [ ] **Step 1: Extend failing browser tests**

Assert all three modes render outcome, mode, steps, detections, and the correct report URL; assert missing task id disables the action.

- [ ] **Step 2: Run the focused test to verify it fails**

Run: `python -m pytest tests/test_terminal_audit_summary.py -q`

- [ ] **Step 3: Implement a shared `renderTerminalAudit` renderer**

Use DOM APIs and existing `escapeHtml`; reuse it from completion, halt, and failure event handlers.

- [ ] **Step 4: Add the audit card markup and styles**

Keep the existing completion and error layouts intact while placing the summary before their primary actions.

- [ ] **Step 5: Run focused tests to verify they pass**

Run: `python -m pytest tests/test_terminal_audit_summary.py -q`

### Task 3: Verify regression safety

**Files:**
- Test: `tests/test_terminal_audit_summary.py`

- [ ] **Step 1: Run JavaScript syntax checks**

Run: `node --check extension/content.js; node --check extension/assistant/assistant.js`

- [ ] **Step 2: Run focused audit tests**

Run: `python -m pytest tests/test_terminal_audit_summary.py -q`

- [ ] **Step 3: Run the complete suite and report environmental failures**

Run: `python -m pytest -q`

## Self-review

- Spec coverage: Task 1 covers every mode's terminal producer; Task 2 covers the shared UI and full-report link; Task 3 checks focused and broad regression behavior.
- Type consistency: terminal payload fields use the existing `task_id`, `mode`, `status`, and `detections` naming convention.
- Review focus: each listed condition is asserted in the focused browser tests.
- Proportion: the plan defines interfaces, test obligations, and affected files without prescribing implementation bodies.
