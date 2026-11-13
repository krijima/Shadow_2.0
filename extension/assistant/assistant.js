// SHADOW Assistant UI — assistant.js
// Runs inside the iframe; communicates with the parent page via window.parent.postMessage

(function () {
  "use strict";

  // ─── State ───────────────────────────────────────────────────────────────────
  let taskId = null;
  let isRunning = false;
  let isPaused = false;
  let detectionCount = 0;
  let stepCount = 0;
  let currentApprovalId = null;
  let approvalCount = 0;
  let isMinimized = false;

  // ─── DOM References ──────────────────────────────────────────────────────────
  const appContainer         = document.getElementById("app");
  const dragHeader           = document.getElementById("dragHeader");
  const contentArea          = document.getElementById("content");
  const minimizeBtn          = document.getElementById("minimizeBtn");
  const launcherBtn          = document.getElementById('launcherBtn');

  const headerStatusPill     = document.getElementById("headerStatusPill");
  const headerStatusText     = document.getElementById("headerStatusText");

  // Sections
  const taskInputSection     = document.getElementById("taskInputSection");
  const activeTaskSection    = document.getElementById("activeTaskSection");
  const completionSection    = document.getElementById("completionSection");
  const errorSection         = document.getElementById("errorSection");

  // Input elements
  const instructionInput     = document.getElementById("instructionInput");
  const quickTagCancel       = document.getElementById("quickTagCancel");
  const startBtn             = document.getElementById("startBtn");

  // Active task elements
  const goalText             = document.getElementById("goalText");
  const stepCounter          = document.getElementById("stepCounter");
  const timelineList         = document.getElementById("timelineList");
  const pauseBtn             = document.getElementById("pauseBtn");
  const pauseBtnIcon         = document.getElementById("pauseBtnIcon");
  const pauseBtnText         = document.getElementById("pauseBtnText");
  const stopBtn              = document.getElementById("stopBtn");

  // Detections
  const detectionCountEl     = document.getElementById("detectionCount");
  const noDetectionsText     = document.getElementById("noDetectionsText");
  const detectionsList       = document.getElementById("detectionsList");

  // Completion & Error
  const completionMsg        = document.getElementById("completionMsg");
  const evidenceBtn          = document.getElementById("evidenceBtn");
  const newTaskBtn           = document.getElementById("newTaskBtn");
  const errorMsg             = document.getElementById("errorMsg");
  const retryBtn             = document.getElementById("retryBtn");

  // Modals
  const approvalModal        = document.getElementById("approvalModal");
  const approvalTitle        = document.getElementById("approvalTitle");
  const approvalActionDesc   = document.getElementById("approvalActionDesc");
  const approvalReason       = document.getElementById("approvalReason");
  const approveBtn           = document.getElementById("approveBtn");
  const rejectBtn            = document.getElementById("rejectBtn");

  const askUserModal         = document.getElementById("askUserModal");
  const askQuestion          = document.getElementById("askQuestion");
  const askAnswer            = document.getElementById("askAnswer");
  const submitAnswerBtn      = document.getElementById("submitAnswerBtn");

  // Keep the primary actions outside the scrolling cards, including in short
  // windows. Moving existing controls preserves their IDs and event handlers.
  const controlsToolbar = document.querySelector('.controls-toolbar');
  const actionBar = document.createElement('footer');
  actionBar.className = 'action-bar';
  actionBar.setAttribute('aria-label', 'Task actions');
  actionBar.append(startBtn, controlsToolbar);
  appContainer.appendChild(actionBar);
  controlsToolbar.classList.add('hidden');

  // ─── Status Controller ────────────────────────────────────────────────────────
  function setAgentStatus(statusKey, labelText) {
    headerStatusPill.className = "ai-status-pill " + statusKey;
    headerStatusText.textContent = labelText.toUpperCase();
  }

  function showSection(sectionEl) {
    [taskInputSection, activeTaskSection, completionSection, errorSection].forEach(
      (sec) => sec.classList.add("hidden")
    );
    sectionEl.classList.remove("hidden");
    startBtn.classList.toggle('hidden', sectionEl !== taskInputSection);
    controlsToolbar.classList.toggle('hidden', sectionEl !== activeTaskSection);
    actionBar.classList.toggle('hidden', sectionEl !== taskInputSection && sectionEl !== activeTaskSection);
  }

  function pluralize(count, singular, plural = `${singular}S`) {
    return `${count} ${count === 1 ? singular : plural}`;
  }

  function renderTerminalAudit(message, fallbackStatus) {
    const auditTaskId = message.task_id || "";
    const mode = String(message.mode || currentMode || "observe").toUpperCase();
    const status = String(message.status || fallbackStatus || "completed").toUpperCase();
    const detected = Array.isArray(message.detections) ? message.detections.length : detectionCount;
    const approvals = Number.isFinite(message.approval_count) ? message.approval_count : approvalCount;
    const reportUrl = auditTaskId ? `http://localhost:8001/api/evidence/${encodeURIComponent(auditTaskId)}/html` : "";

    document.querySelectorAll("[data-terminal-audit]").forEach(card => {
      card.classList.remove("hidden");
      card.querySelector("[data-audit-status]").textContent = status;
      card.querySelector("[data-audit-mode]").textContent = mode;
      card.querySelector("[data-audit-steps]").textContent = pluralize(stepCount, "STEP");
      card.querySelector("[data-audit-detections]").textContent = pluralize(detected, "PATTERN");
      card.querySelector("[data-audit-approvals]").textContent = pluralize(approvals, "APPROVAL");
    });

    document.querySelectorAll("[data-audit-report-action]").forEach(button => {
      button.disabled = !reportUrl;
      button.dataset.reportUrl = reportUrl;
    });
  }

  function openAuditReport(button) {
    const reportUrl = button.dataset.reportUrl;
    if (reportUrl) window.open(reportUrl, "_blank");
  }

  // ─── Live Timeline Renderer (Phase 2 Feature) ─────────────────────────────────
  function addTimelineEvent({ type, actionTitle, detail, timestamp }) {
    if (currentMode !== "demo") {
      timelineList.replaceChildren();
      detail = "";
    }
    const emptyPlaceholder = timelineList.querySelector(".timeline-empty");
    if (emptyPlaceholder) emptyPlaceholder.remove();

    const timeStr = timestamp || new Date().toLocaleTimeString("en-US", {
      hour12: false,
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit"
    });

    let badgeIcon = "✓";
    let badgeClass = "success";

    if (type === "warning" || type === "detection") {
      badgeIcon = "⚠";
      badgeClass = "warning";
    } else if (type === "blocked") {
      badgeIcon = "🚫";
      badgeClass = "blocked";
    } else if (type === "approval") {
      badgeIcon = "◉";
      badgeClass = "warning";
    } else if (type === "active" || type === "info") {
      badgeIcon = "➜";
      badgeClass = "active";
    }

    const node = document.createElement("div");
    node.className = "timeline-node";
    node.innerHTML = `
      <div class="timeline-badge ${badgeClass}">${badgeIcon}</div>
      <div class="timeline-content">
        <div class="timeline-action">${escapeHtml(actionTitle)}</div>
        <div class="timeline-meta">
          <span>${escapeHtml(detail || "")}</span>
          <span>${timeStr}</span>
        </div>
      </div>
    `;

    timelineList.appendChild(node);
    timelineList.scrollTop = timelineList.scrollHeight;

    // Increment step counter
    stepCount++;
    stepCounter.textContent = `${stepCount} STEPS`;
  }

  // ─── Dark Pattern Detections Renderer (Phase 3 Feature) ─────────────────────
  const seenDetectionKeys = new Set();

  function handleDetections(detections) {
    if (!detections || !detections.length) return;

    noDetectionsText.classList.add("hidden");
    detectionsList.classList.remove("hidden");

    detections.forEach((d) => {
      const category = d.category ? d.category.replace(/_/g, " ") : "Dark Pattern";
      const snippet = (d.visible_text || d.evidence || "").trim();
      const reason = d.reason || "Deceptive pattern detected.";
      const isCritical = d.category === "prompt_injection" || d.category === "forced_continuity";
      const isBlocked = d.category === "prompt_injection" || d.blocked === true;
      
      const elId = d.element_id || (d.element_context && d.element_context.startsWith("element:") ? d.element_context.replace(/^element:/, "").split(" ")[0] : "");
      const cleanElId = (elId && elId !== "page_text") ? elId : "";

      // Deduplication: Avoid duplicate detection cards during navigation
      const dedupKey = `${d.category}|${cleanElId}|${snippet.substring(0, 40)}`;
      if (seenDetectionKeys.has(dedupKey)) {
        return;
      }
      seenDetectionKeys.add(dedupKey);

      detectionCount++;
      detectionCountEl.textContent = String(detectionCount);

      // Feature 2: Structured professional Detection Card
      const card = document.createElement("div");
      card.className = `detection-card ${isCritical ? "critical" : ""}`;

      let cardHtml = `
        <div class="detection-card-header">
          <div class="detection-category">
            <span>${isCritical ? "🚨" : "⚠"}</span>
            <span>${escapeHtml(category.toUpperCase())}</span>
          </div>
          <div class="detection-guard-badge ${isBlocked ? "blocked" : ""}">
            ${isBlocked ? "BLOCKED BY SHADOW" : "GUARDED"}
          </div>
        </div>
      `;

      if (snippet) {
        cardHtml += `<div class="detection-snippet">"${escapeHtml(snippet.substring(0, 180))}${snippet.length > 180 ? "…" : ""}"</div>`;
      }

      cardHtml += `<div class="detection-explanation">${escapeHtml(reason)}</div>`;

      // Feature 3: "View on Page" control when a matching DOM element exists
      if (cleanElId) {
        cardHtml += `
          <div class="detection-actions">
            <button class="btn-view-on-page" type="button" data-element-id="${escapeHtml(cleanElId)}">
              👁 View on Page
            </button>
          </div>
        `;
      }

      card.innerHTML = cardHtml;

      // Wire View on Page button
      const viewBtn = card.querySelector(".btn-view-on-page");
      if (viewBtn) {
        viewBtn.addEventListener("click", (e) => {
          e.stopPropagation();
          const targetId = viewBtn.getAttribute("data-element-id");
          postToParent({
            source: "SHADOW_ASSISTANT",
            type: "VIEW_ON_PAGE",
            element_id: targetId,
          });
        });
      }

      detectionsList.appendChild(card);

      // Add to timeline as a warning event
      addTimelineEvent({
        type: isCritical ? "blocked" : "warning",
        actionTitle: `${isCritical ? "Security Risk Blocked" : "Deceptive pattern detected"}: ${category}`,
        detail: reason.substring(0, 70) + (reason.length > 70 ? "…" : "")
      });
    });
  }

  // ─── HTML Sanitizer ───────────────────────────────────────────────────────────
  function escapeHtml(str) {
    return String(str || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  // ─── Post Message to Parent Frame ─────────────────────────────────────────────
  function postToParent(msg) {
    window.parent.postMessage(msg, "*");
  }

  // Fit the panel to its visible cards instead of leaving a fixed empty tail.
  let sizeFrame = 0, lastPanelHeight = 0;
  function fitPanel() {
    cancelAnimationFrame(sizeFrame);
    sizeFrame = requestAnimationFrame(() => {
      if (isMinimized) return;
      const sections = [...contentArea.children].filter(node => getComputedStyle(node).display !== 'none');
      const style = getComputedStyle(contentArea);
      const borders = appContainer.offsetHeight - appContainer.clientHeight;
      const height = Math.min(640, Math.max(300, Math.ceil(borders + dragHeader.getBoundingClientRect().height + actionBar.getBoundingClientRect().height +
        parseFloat(style.paddingTop) + parseFloat(style.paddingBottom) +
        sections.reduce((sum, node) => sum + node.getBoundingClientRect().height, 0) +
        Math.max(0, sections.length - 1) * parseFloat(style.gap || 0))));
      if (height !== lastPanelHeight) {
        lastPanelHeight = height;
        postToParent({source: 'SHADOW_ASSISTANT', type: 'SET_HEIGHT', height});
      }
    });
  }
  const panelSizeObserver = new ResizeObserver(fitPanel);
  [...contentArea.children, dragHeader, actionBar].forEach(node => panelSizeObserver.observe(node));
  fitPanel();

  // ─── Dragging Support for Floating Assistant ───────────────────────────────────
  let isDragging = false;
  let dragPointerId = null;
  dragHeader.style.touchAction = 'none';
  dragHeader.style.userSelect = 'none';

  dragHeader.addEventListener("pointerdown", (e) => {
    if (e.button !== 0 || e.target.closest("button")) return;
    e.preventDefault();
    isDragging = true;
    dragPointerId = e.pointerId;
    dragHeader.setPointerCapture(e.pointerId);
    postToParent({ source: "SHADOW_ASSISTANT", type: "DRAG_START", screenX: e.screenX, screenY: e.screenY });
  });

  dragHeader.addEventListener("pointermove", (e) => {
    if (!isDragging || e.pointerId !== dragPointerId) return;
    postToParent({ source: "SHADOW_ASSISTANT", type: "DRAG_MOVE", screenX: e.screenX, screenY: e.screenY });
  });

  const finishDrag = () => {
    if (isDragging) {
      isDragging = false;
      const pointerId = dragPointerId;
      dragPointerId = null;
      if (dragHeader.hasPointerCapture(pointerId)) dragHeader.releasePointerCapture(pointerId);
      postToParent({ source: "SHADOW_ASSISTANT", type: "DRAG_END" });
    }
  };
  dragHeader.addEventListener('pointerup', finishDrag);
  dragHeader.addEventListener('pointercancel', finishDrag);
  dragHeader.addEventListener('lostpointercapture', finishDrag);
  window.addEventListener('blur', finishDrag);

  // ─── Button Handlers ──────────────────────────────────────────────────────────

  // Mode & Site State (Phases 5 & 7)
  let currentMode = "observe";
  let isStreamCoveHost = false;
  const siteNameDisplay      = document.getElementById("siteNameDisplay");
  const modeBtnObserve       = document.getElementById("modeBtnObserve");
  const modeBtnGuide         = document.getElementById("modeBtnGuide");
  const modeBtnDemo          = document.getElementById("modeBtnDemo");
  const quickTagCookies      = document.getElementById("quickTagCookies");
  const quickTagAccount      = document.getElementById("quickTagAccount");

  startBtn.disabled = true;
  [modeBtnObserve, modeBtnGuide, modeBtnDemo].forEach(button => { button.disabled = true; });

  function setOperatingMode(mode) {
    if (mode === "demo" && !isStreamCoveHost) {
      return;
    }
    currentMode = mode;
    [modeBtnObserve, modeBtnGuide, modeBtnDemo].forEach(btn => {
      if (!btn) return;
      btn.disabled = Boolean(taskId) || (btn === modeBtnDemo && !isStreamCoveHost);
      if (btn.getAttribute("data-mode") === mode) {
        btn.classList.add("active");
      } else {
        btn.classList.remove("active");
      }
    });
  }

  if (modeBtnObserve) modeBtnObserve.addEventListener("click", () => setOperatingMode("observe"));
  if (modeBtnGuide) modeBtnGuide.addEventListener("click", () => setOperatingMode("guide"));
  if (modeBtnDemo) modeBtnDemo.addEventListener("click", () => setOperatingMode("demo"));

  // Quick preset chips
  if (quickTagCancel) {
    quickTagCancel.addEventListener("click", () => {
      instructionInput.value = "Cancel my subscription. Do not accept discount offers or upgrades.";
      instructionInput.focus();
    });
  }
  if (quickTagCookies) {
    quickTagCookies.addEventListener("click", () => {
      instructionInput.value = "Find the option to reject optional cookies and tracking.";
      instructionInput.focus();
    });
  }
  if (quickTagAccount) {
    quickTagAccount.addEventListener("click", () => {
      instructionInput.value = "Help me navigate to account management and security settings.";
      instructionInput.focus();
    });
  }

  // Start Task
  startBtn.addEventListener("click", () => {
    const instruction = instructionInput.value.trim();
    if (!instruction) {
      instructionInput.focus();
      return;
    }

    seenDetectionKeys.clear();
    goalText.textContent = instruction;
    stepCount = 0;
    detectionCount = 0;
    approvalCount = 0;
    detectionCountEl.textContent = "0";
    detectionsList.innerHTML = "";
    noDetectionsText.classList.remove("hidden");
    detectionsList.classList.add("hidden");
    timelineList.innerHTML = "";

    showSection(activeTaskSection);
    setAgentStatus("navigating", "PLANNING");
    startBtn.disabled = true;

    addTimelineEvent({
      type: "info",
      actionTitle: "Objective locked",
      detail: "ShadowLock verified authorized goal."
    });

    try {
      chrome.storage.local.set({
        active_goal: instruction,
        active_running: true,
        active_step_count: 0,
        active_detections_count: 0
      });
    } catch (e) {}

    postToParent({
      source: "SHADOW_ASSISTANT",
      type: "CREATE_TASK",
      instruction,
      mode: currentMode,
    });
  });

  // Pause / Resume
  pauseBtn.addEventListener("click", () => {
    if (!isPaused) {
      isPaused = true;
      pauseBtnText.textContent = "Resume";
      pauseBtnIcon.textContent = "▶";
      setAgentStatus("paused", "PAUSED");
      addTimelineEvent({
        type: "warning",
        actionTitle: "Agent execution paused",
        detail: "User paused autonomous navigation."
      });
      postToParent({ source: "SHADOW_ASSISTANT", type: "PAUSE_TASK" });
    } else {
      pauseBtn.disabled = true;
      pauseBtnText.textContent = "Resuming...";
      addTimelineEvent({
        type: "info",
        actionTitle: "Resuming agent",
        detail: "Waiting for backend confirmation before proceeding..."
      });
      postToParent({ source: "SHADOW_ASSISTANT", type: "RESUME_TASK" });
    }
  });

  // Abort / Stop
  stopBtn.addEventListener("click", () => {
    isRunning = false;
    isPaused = false;
    if (pauseBtn) pauseBtn.disabled = false;
    postToParent({ source: "SHADOW_ASSISTANT", type: "STOP_TASK" });
    try {
      chrome.storage.local.remove([
        "active_task_id",
        "active_running",
        "active_status",
        "active_paused_reason",
        "active_mode",
        "active_goal",
        "active_step_count",
        "active_detections_count"
      ]);
    } catch (e) {}

    setAgentStatus("idle", "IDLE");
    showSection(taskInputSection);
    instructionInput.value = "";
    startBtn.disabled = false;
    taskId = null;
    setOperatingMode(currentMode);
  });

  // Minimize / Expand
  function setMinimized(minimized) {
    isMinimized = minimized;
    appContainer.classList.toggle('hidden', minimized);
    launcherBtn.classList.toggle('hidden', !minimized);
    postToParent({source: 'SHADOW_ASSISTANT', type: 'SET_PANEL_SIZE', minimized});
    if (!minimized) minimizeBtn.focus();
    if (!minimized) { lastPanelHeight = 0; fitPanel(); }
  }
  minimizeBtn.addEventListener('click', () => setMinimized(true));
  launcherBtn.addEventListener('click', () => setMinimized(false));

  // Approve Consequential Action
  approveBtn.addEventListener("click", () => {
    approvalModal.classList.add("hidden");
    isRunning = true;
    isPaused = false;
    try {
      chrome.storage.local.set({
        active_task_id: taskId,
        active_running: true,
      });
    } catch (e) {}

    postToParent({
      source: "SHADOW_ASSISTANT",
      type: "APPROVE_ACTION",
      approval_id: currentApprovalId,
      approved: true
    });
    addTimelineEvent({
      type: "active",
      actionTitle: "User approved consequential action",
      detail: "Dispatched confirmed cancellation to backend."
    });
    setAgentStatus("navigating", "EXECUTING");
  });

  // Reject Action
  rejectBtn.addEventListener("click", () => {
    approvalModal.classList.add("hidden");
    postToParent({
      source: "SHADOW_ASSISTANT",
      type: "APPROVE_ACTION",
      approval_id: currentApprovalId,
      approved: false
    });
    addTimelineEvent({
      type: "blocked",
      actionTitle: "Action rejected by user",
      detail: "Subscription remains intact and ACTIVE."
    });
    setAgentStatus("paused", "REJECTED");
  });

  // Submit User Clarification
  submitAnswerBtn.addEventListener("click", () => {
    const answer = askAnswer.value.trim();
    if (!answer) { askAnswer.focus(); return; }
    askUserModal.classList.add("hidden");
    askAnswer.value = "";
    postToParent({
      source: "SHADOW_ASSISTANT",
      type: "APPROVE_ACTION",
      approval_id: currentApprovalId,
      approved: true,
      answer
    });
    addTimelineEvent({
      type: "active",
      actionTitle: "User guidance provided",
      detail: `Answer: "${answer}"`
    });
    setAgentStatus("navigating", "NAVIGATING");
  });

  // Evidence Report Button
  document.querySelectorAll("[data-audit-report-action]").forEach(button => {
    button.addEventListener("click", () => openAuditReport(button));
  });

  // Start Another Task
  newTaskBtn.addEventListener("click", () => {
    postToParent({source: "SHADOW_ASSISTANT", type: "STOP_TASK"});
    taskId = null;
    setOperatingMode(currentMode);
    instructionInput.value = "";
    startBtn.disabled = false;
    setAgentStatus("idle", "IDLE");
    showSection(taskInputSection);
  });

  // Retry from Error
  retryBtn.addEventListener("click", () => {
    postToParent({source: "SHADOW_ASSISTANT", type: "STOP_TASK"});
    taskId = null;
    setOperatingMode(currentMode);
    instructionInput.value = "";
    startBtn.disabled = false;
    setAgentStatus("idle", "IDLE");
    showSection(taskInputSection);
  });

  // ─── Incoming Message Listener (From Content Script) ──────────────────────────
  window.addEventListener("message", (event) => {
    const msg = event.data;
    if (!msg || msg.source !== "SHADOW_CONTENT") return;

    switch (msg.type) {
      case 'EXPAND_ASSISTANT': setMinimized(false); break;

      case "HOST_CONTEXT": {
        isStreamCoveHost = Boolean(msg.is_streamcove);
        startBtn.disabled = false;
        modeBtnObserve.disabled = false;
        modeBtnGuide.disabled = false;
        if (siteNameDisplay) {
          siteNameDisplay.textContent = msg.hostname || "External Site";
        }
        if (!msg.is_streamcove) {
          if (modeBtnDemo) {
            modeBtnDemo.disabled = true;
            modeBtnDemo.title = "Demo mode is restricted to StreamCove environment";
            modeBtnDemo.style.opacity = "0.4";
            modeBtnDemo.style.cursor = "not-allowed";
          }
          if (currentMode === "demo") {
            setOperatingMode("observe");
          }
        } else {
          if (modeBtnDemo) {
            modeBtnDemo.disabled = false;
            modeBtnDemo.title = "Autonomous navigation for StreamCove demo environment";
            modeBtnDemo.style.opacity = "1";
            modeBtnDemo.style.cursor = "pointer";
          }
          if (!taskId) setOperatingMode("demo");
        }
        break;
      }

      case "PLANNING_NEXT_STEP": {
        setAgentStatus("navigating", "ANALYZING");
        break;
      }

      case "RESTORE_SESSION": {
        taskId = msg.task_id;
        if (msg.mode) setOperatingMode(msg.mode);
        const isPausedState = Boolean(msg.is_paused);
        isRunning = !isPausedState;
        isPaused = isPausedState;
        if (msg.goal) {
          goalText.textContent = msg.goal;
        }
        if (typeof msg.step_count === "number") {
          stepCount = msg.step_count;
          stepCounter.textContent = `${stepCount} STEPS`;
        }
        if (typeof msg.detections_count === "number") {
          detectionCount = msg.detections_count;
          detectionCountEl.textContent = String(detectionCount);
        }
        showSection(activeTaskSection);
        if (isPausedState) {
          setAgentStatus("paused", currentMode === "observe" ? "OBSERVING" : "PAUSED");
          if (pauseBtn) pauseBtn.disabled = false;
          if (pauseBtnText) pauseBtnText.textContent = "Resume";
          if (pauseBtnIcon) pauseBtnIcon.textContent = "▶";
          addTimelineEvent({
            type: "info",
            actionTitle: "Waiting for you",
            detail: "Waiting for you to review or click Resume."
          });
        } else {
          setAgentStatus("navigating", "NAVIGATING");
          if (pauseBtn) pauseBtn.disabled = false;
          if (pauseBtnText) pauseBtnText.textContent = "Pause";
          if (pauseBtnIcon) pauseBtnIcon.textContent = "⏸";
          addTimelineEvent({
            type: "info",
            actionTitle: "Resuming plan on new view",
            detail: "Scanned DOM elements and continuing autonomous execution."
          });
        }
        break;
      }

      case "TASK_RESUMED": {
        if (pauseBtn) pauseBtn.disabled = false;
        isPaused = false;
        isRunning = true;
        if (pauseBtnText) pauseBtnText.textContent = "Pause";
        if (pauseBtnIcon) pauseBtnIcon.textContent = "⏸";
        setAgentStatus("navigating", "NAVIGATING");
        addTimelineEvent({
          type: "info",
          actionTitle: "Agent resumed",
          detail: "Autonomous navigation restarted."
        });
        break;
      }

      case "TASK_RESUME_FAILED": {
        if (pauseBtn) pauseBtn.disabled = false;
        isPaused = true;
        isRunning = false;
        if (pauseBtnText) pauseBtnText.textContent = "Resume";
        if (pauseBtnIcon) pauseBtnIcon.textContent = "▶";
        setAgentStatus("paused", "PAUSED");
        addTimelineEvent({
          type: "blocked",
          actionTitle: "Resume failed",
          detail: msg.error || "Failed to resume task on backend."
        });
        break;
      }

      case "TASK_PAUSED_WAITING": {
        if (pauseBtn) pauseBtn.disabled = false;
        isPaused = true;
        isRunning = false;
        if (pauseBtnText) pauseBtnText.textContent = "Resume";
        if (pauseBtnIcon) pauseBtnIcon.textContent = "▶";
        setAgentStatus("paused", currentMode === "observe" ? "OBSERVING" : "PAUSED");
        addTimelineEvent({
          type: "info",
          actionTitle: "Waiting for you",
          detail: msg.reason || "Task is paused. Waiting for you to review or click Resume."
        });
        break;
      }

      case "TASK_CREATED": {
        if (msg.error) {
          showError(`Failed to initialize agent task: ${msg.error}`);
          startBtn.disabled = false;
          return;
        }
        taskId = msg.task_id;
        if (msg.mode) setOperatingMode(msg.mode);
        try {
          chrome.storage.local.set({ active_task_id: taskId });
        } catch (e) {}

        addTimelineEvent({
          type: "info",
          actionTitle: "Task initiated",
          detail: "Observing DOM elements and starting planner loop."
        });
        setAgentStatus("navigating", "NAVIGATING");

        postToParent({
          source: "SHADOW_ASSISTANT",
          type: "START_TASK",
          task_id: taskId,
          mode: currentMode
        });
        break;
      }

      case "GUIDANCE_WAITING": {
        isRunning = false;
        isPaused = false; // The Pause button remains an explicit user pause.
        setAgentStatus("paused", msg.reversible ? "GUIDING" : "REVIEW ON PAGE");
        pauseBtn.disabled = false;
        pauseBtnText.textContent = "Pause";
        pauseBtnIcon.textContent = "⏸";
        addTimelineEvent({type: "active", actionTitle: msg.guidance, detail: ""});
        console.info("[SHADOW guidance]", {task_id: taskId, action: msg.action, mode: msg.mode});
        break;
      }

      case "ACTION_TAKEN": {
        const { action, result, detections } = msg;
        isPaused = false;
        isRunning = true;
        pauseBtnText.textContent = "Pause";
        pauseBtnIcon.textContent = "⏸";
        setAgentStatus("navigating", "NAVIGATING");
        const label = action?.element_text || "Next page";
        addTimelineEvent({type: "active", actionTitle: msg.guidance || `Open ${label}.`, detail: ""});
        console.info("[SHADOW action]", {task_id: taskId, action, result, mode: msg.mode});

        if (detections && detections.length) {
          handleDetections(detections);
        }

        try {
          chrome.storage.local.set({
            active_step_count: stepCount,
            active_detections_count: detectionCount
          });
        } catch (e) {}
        break;
      }

      case "APPROVAL_REQUIRED": {
        if (isMinimized) setMinimized(false);
        currentApprovalId = msg.approval_id;
        approvalCount++;
        const isGuideMode = msg.mode === "guide";
        setAgentStatus("approval", isGuideMode ? "GUIDED STEP" : "APPROVAL NEEDED");

        const act = msg.action;
        let desc = act?.element_text || "Review this action";
        approvalActionDesc.textContent = desc;
        approvalReason.textContent = msg.reason || (isGuideMode ? "SHADOW recommends this navigation action. Confirm to proceed." : "ShadowLock requires explicit consent before final cancellation.");

        const modalNotice = document.querySelector("#approvalModal .modal-notice");
        const modalBadge = document.querySelector("#approvalModal .modal-warning-badge");
        if (isGuideMode) {
          if (approvalTitle) approvalTitle.textContent = "Confirm Guided Navigation Step";
          if (modalBadge) modalBadge.textContent = "🎯 GUIDED ACTION APPROVAL";
          if (modalNotice) modalNotice.textContent = "SHADOW identified this next navigation step. Confirm to navigate or skip to stay on current view.";
          approveBtn.innerHTML = "<span>Confirm &amp; Navigate</span>";
          rejectBtn.innerHTML = "<span>Skip Step</span>";
        } else {
          if (approvalTitle) approvalTitle.textContent = "Confirm Subscription Cancellation";
          if (modalBadge) modalBadge.textContent = "⚠ ACTION APPROVAL REQUIRED";
          if (modalNotice) modalNotice.textContent = "ShadowLock has intercepted an irreversible action. This will permanently change your subscription status in the database.";
          approveBtn.innerHTML = "<span>Approve &amp; Execute</span>";
          rejectBtn.innerHTML = "<span>Reject Action</span>";
        }

        if (msg.detections) handleDetections(msg.detections);

        addTimelineEvent({
          type: "approval",
          actionTitle: isGuideMode ? "Guided step proposed" : "Interception: Approval required",
          detail: msg.reason || "Paused for human confirmation before execution."
        });

        approvalModal.classList.remove("hidden");
        break;
      }

      case "ASK_USER": {
        currentApprovalId = null;
        setAgentStatus("approval", "CLARIFICATION");
        askQuestion.textContent = msg.question || "The agent requires clarification to proceed.";
        if (msg.detections) handleDetections(msg.detections);
        askUserModal.classList.remove("hidden");
        break;
      }

      case "TASK_COMPLETE": {
        isRunning = false;
        setAgentStatus("complete", "COMPLETED");
        try {
          chrome.storage.local.remove([
            "active_task_id",
            "active_running",
            "active_goal",
            "active_step_count",
            "active_detections_count"
          ]);
        } catch (e) {}

        document.querySelector(".verified-card")?.classList.toggle("hidden", currentMode !== "demo");
        completionMsg.textContent = currentMode === "demo"
          ? (msg.message || "Subscription was safely cancelled and verified.")
          : "Finished. Review on page.";
        if (msg.detections) handleDetections(msg.detections);

        renderTerminalAudit(msg, "completed");

        addTimelineEvent({
          type: "active",
          actionTitle: "Goal achieved",
          detail: "Verified cancellation in SQLite database."
        });

        showSection(completionSection);
        break;
      }

      case "TASK_HALTED": {
        isRunning = false;
        setAgentStatus("paused", "HALTED");
        try {
          chrome.storage.local.remove([
            "active_task_id",
            "active_running",
            "active_goal",
            "active_step_count",
            "active_detections_count"
          ]);
        } catch (e) {}

        if (msg.detections) handleDetections(msg.detections);

        renderTerminalAudit(msg, "halted");

        addTimelineEvent({
          type: "blocked",
          actionTitle: "Task halted",
          detail: msg.reason || "Navigation stopped by safety boundary."
        });

        showError(`Task Halted: ${msg.reason || "Safety boundary triggered."}`);
        break;
      }

      case "TASK_FAILED": {
        isRunning = false;
        setAgentStatus("failed", "HALTED");
        if (msg.detections) handleDetections(msg.detections);
        renderTerminalAudit(msg, "failed");
        showError(msg.error || "An unknown navigation error occurred.");
        break;
      }

      case "TASK_CANCELLED": {
        isRunning = false;
        setAgentStatus("paused", "CANCELLED");
        if (msg.detections) handleDetections(msg.detections);
        renderTerminalAudit(msg, "cancelled");
        showError(msg.reason || "Task was cancelled before it could continue.");
        break;
      }

      case "EXTENSION_RELOADED": {
        isRunning = false;
        isPaused = true;
        approvalModal.classList.add("hidden");
        askUserModal.classList.add("hidden");
        pauseBtn.disabled = true;
        retryBtn.disabled = true;
        setAgentStatus("failed", "REFRESH REQUIRED");
        showError(msg.error);
        break;
      }
    }
  });

  function showError(text) {
    console.error("[SHADOW stopped]", {task_id: taskId, mode: currentMode, error: text});
    errorMsg.textContent = currentMode === "demo" || /Extension reloaded|Start New Task/.test(text || "")
      ? text : "Couldn’t continue. Review on page.";
    showSection(errorSection);
    startBtn.disabled = false;
  }

})();
