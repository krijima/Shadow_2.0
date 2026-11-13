// SHADOW Extension — Content Script
// Injected on http://localhost/* pages

(function () {
  "use strict";
  // Registered scripts and popup activation may arrive together.
  if (globalThis.__shadowContentInstalled) return;
  globalThis.__shadowContentInstalled = true;

  // ─── State ───────────────────────────────────────────────────────────────────
  let running = false;
  let isLoopActive = false;
  let taskId = null;
  let currentApprovalId = null;
  let shadowIndex = 0;
  let assistantFrame = null;
  let currentMode = "observe";
  let ownerTabId = null;
  let runtimeInvalidated = false;

  function extensionReloaded() {
    if (runtimeInvalidated) return;
    runtimeInvalidated = true;
    running = false;
    sessionStorage.setItem("shadow_extension_reloaded", taskId || "none");
    const message = "Extension reloaded. Refresh this page and start again";
    // The old extension iframe may itself be unloaded by Chrome on reload.
    const notice = document.createElement("div");
    notice.id = "shadow-runtime-notice";
    notice.setAttribute("role", "alert");
    notice.textContent = message;
    notice.style.cssText = "position:fixed;bottom:12px;right:24px;z-index:2147483647;background:#161b2b;color:white;padding:16px;border:2px solid #f59e0b;border-radius:8px;font:14px sans-serif";
    document.body.appendChild(notice);
    postToAssistant({ source: "SHADOW_CONTENT", type: "EXTENSION_RELOADED", error: message });
  }

  async function runtimeMessage(message) {
    try {
      if (runtimeInvalidated || !chrome.runtime.id) throw new Error("Extension context invalidated");
      return await chrome.runtime.sendMessage(message);
    } catch (error) {
      if (/extension context invalidated/i.test(error.message || "")) extensionReloaded();
      throw error;
    }
  }

  function isStreamCoveOrigin(urlStr) {
    try {
      const parsed = new URL(urlStr || window.location.href);
      const host = parsed.hostname.toLowerCase();
      const port = parsed.port;
      if ((host === "localhost" || host === "127.0.0.1") && (port === "8080" || port === "8081")) {
        return true;
      }
    } catch (e) {}
    return false;
  }

  // ─── Visual Highlighting (Phase 3 Feature) ──────────────────────────────────
  function injectHighlightStyles() {
    if (document.getElementById("shadow-highlight-styles")) return;
    const style = document.createElement("style");
    style.id = "shadow-highlight-styles";
    style.textContent = `
      .shadow-dp-highlight {
        outline: 2px dashed #f59e0b !important;
        outline-offset: 3px !important;
        box-shadow: 0 0 14px rgba(245, 158, 11, 0.45) !important;
        transition: outline 0.3s ease, box-shadow 0.3s ease !important;
        border-radius: 4px;
      }
      .shadow-dp-highlight-critical {
        outline: 2px dashed #ef4444 !important;
        outline-offset: 3px !important;
        box-shadow: 0 0 16px rgba(239, 68, 68, 0.5) !important;
        transition: outline 0.3s ease, box-shadow 0.3s ease !important;
        border-radius: 4px;
      }
      .shadow-dp-badge {
        position: absolute !important;
        pointer-events: none !important;
        user-select: none !important;
        z-index: 999990 !important;
        background: #0f1322 !important;
        color: #fbbf24 !important;
        border: 1px solid rgba(245, 158, 11, 0.7) !important;
        padding: 3px 8px !important;
        border-radius: 4px !important;
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif !important;
        font-size: 11px !important;
        font-weight: 700 !important;
        letter-spacing: 0.3px !important;
        box-shadow: 0 4px 14px rgba(0, 0, 0, 0.6) !important;
        display: inline-flex !important;
        align-items: center !important;
        gap: 5px !important;
        line-height: 1 !important;
        white-space: nowrap !important;
        transition: opacity 0.2s ease !important;
      }
      .shadow-dp-badge.critical {
        color: #f87171 !important;
        border-color: rgba(239, 68, 68, 0.7) !important;
      }
      .shadow-dp-focus-pulse {
        animation: shadowPulseHighlight 2s ease-in-out !important;
      }
      .shadow-guidance-target {
        outline: 3px solid #8b5cf6 !important;
        outline-offset: 4px !important;
        box-shadow: 0 0 20px rgba(139, 92, 246, 0.75), 0 0 35px rgba(99, 102, 241, 0.4) !important;
        animation: shadowGuidancePulse 1.8s infinite ease-in-out !important;
        border-radius: 6px !important;
      }
      .shadow-guidance-badge {
        position: absolute !important;
        pointer-events: none !important;
        user-select: none !important;
        z-index: 999990 !important;
        background: #0f1322 !important;
        color: #c4b5fd !important;
        border: 1px solid rgba(139, 92, 246, 0.8) !important;
        padding: 3px 8px !important;
        border-radius: 4px !important;
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif !important;
        font-size: 11px !important;
        font-weight: 700 !important;
        letter-spacing: 0.3px !important;
        box-shadow: 0 4px 14px rgba(0, 0, 0, 0.6) !important;
        display: inline-flex !important;
        align-items: center !important;
        gap: 5px !important;
        line-height: 1 !important;
        white-space: nowrap !important;
        transition: opacity 0.2s ease !important;
      }
      @keyframes shadowGuidancePulse {
        0%, 100% {
          outline-color: #8b5cf6;
          box-shadow: 0 0 16px rgba(139, 92, 246, 0.65);
        }
        50% {
          outline-color: #a78bfa;
          outline-width: 4px;
          outline-offset: 6px;
          box-shadow: 0 0 30px rgba(167, 139, 250, 0.95);
        }
      }
      @keyframes shadowPulseHighlight {
        0%, 100% {
          outline-color: #f59e0b;
          box-shadow: 0 0 14px rgba(245, 158, 11, 0.45);
        }
        50% {
          outline-color: #fbbf24;
          outline-width: 4px;
          outline-offset: 5px;
          box-shadow: 0 0 28px rgba(245, 158, 11, 0.9);
        }
      }
    `;
    (document.head || document.documentElement).appendChild(style);
  }

  function clearGuidanceHighlights() {
    document.querySelectorAll(".shadow-guidance-target")
      .forEach((el) => el.classList.remove("shadow-guidance-target"));
    document.querySelectorAll(".shadow-guidance-badge").forEach((b) => b.remove());
  }

  function highlightGuidanceTarget(elId, label = "Recommended Action") {
    clearGuidanceHighlights();
    injectHighlightStyles();
    if (!elId) return;
    const el = document.querySelector(`[data-shadow-id="${elId}"]`);
    if (!el || !isVisible(el)) return;

    el.classList.add("shadow-guidance-target");
    try {
      el.scrollIntoView({ behavior: "smooth", block: "center" });
    } catch (e) {}

    const rect = el.getBoundingClientRect();
    const badge = document.createElement("div");
    badge.className = "shadow-guidance-badge";
    badge.setAttribute("data-shadow-guidance-for", elId);
    badge.textContent = label;

    const top = (rect.top + window.scrollY < 26)
      ? (rect.bottom + window.scrollY + 6)
      : (rect.top + window.scrollY - 24);
    const left = Math.max(10, rect.left + window.scrollX);

    badge.style.top = `${top}px`;
    badge.style.left = `${left}px`;
    document.body.appendChild(badge);
  }

  function clearDarkPatternHighlights() {
    clearGuidanceHighlights();
    document.querySelectorAll(".shadow-dp-highlight, .shadow-dp-highlight-critical, .shadow-dp-focus-pulse")
      .forEach((el) => {
        el.classList.remove("shadow-dp-highlight", "shadow-dp-highlight-critical", "shadow-dp-focus-pulse");
      });
    document.querySelectorAll(".shadow-dp-badge").forEach((b) => b.remove());
  }

  function highlightDarkPatterns(detections) {
    clearDarkPatternHighlights();
    injectHighlightStyles();

    if (!detections || !Array.isArray(detections)) return;

    detections.forEach((d) => {
      // Feature 1: Only highlight if detector reliably identified an element
      const elId = d.element_id || (d.element_context && d.element_context.startsWith("element:") ? d.element_context.replace(/^element:/, "").split(" ")[0] : "");
      if (!elId || elId === "page_text") return;

      const el = document.querySelector(`[data-shadow-id="${elId}"]`);
      if (!el || !isVisible(el)) return;

      const isCritical = d.category === "prompt_injection" || d.category === "forced_continuity";
      el.classList.add(isCritical ? "shadow-dp-highlight-critical" : "shadow-dp-highlight");

      // Create floating badge positioned above element
      const rect = el.getBoundingClientRect();
      const badge = document.createElement("div");
      badge.className = `shadow-dp-badge ${isCritical ? "critical" : ""}`;
      badge.setAttribute("data-shadow-badge-for", elId);

      const categoryLabel = d.category ? d.category.replace(/_/g, " ") : "Dark Pattern";
      badge.innerHTML = `<span>${isCritical ? "🚨" : "🛡️"}</span><span>SHADOW: Potential Dark Pattern (${escapeHtml(categoryLabel.toUpperCase())})</span>`;

      // Absolute offset calculation avoiding layout mutation
      const top = (rect.top + window.scrollY < 26)
        ? (rect.bottom + window.scrollY + 6)
        : (rect.top + window.scrollY - 24);
      const left = Math.max(10, rect.left + window.scrollX);

      badge.style.top = `${top}px`;
      badge.style.left = `${left}px`;

      document.body.appendChild(badge);
    });
  }

  function escapeHtml(str) {
    return String(str || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  // Update badge positions on scroll
  window.addEventListener("scroll", () => {
    document.querySelectorAll(".shadow-dp-badge").forEach((badge) => {
      const elId = badge.getAttribute("data-shadow-badge-for");
      if (!elId) return;
      const el = document.querySelector(`[data-shadow-id="${elId}"]`);
      if (!el) return;
      const rect = el.getBoundingClientRect();
      const top = (rect.top + window.scrollY < 26)
        ? (rect.bottom + window.scrollY + 6)
        : (rect.top + window.scrollY - 24);
      const left = Math.max(10, rect.left + window.scrollX);
      badge.style.top = `${top}px`;
      badge.style.left = `${left}px`;
    });

    document.querySelectorAll(".shadow-guidance-badge").forEach((badge) => {
      const elId = badge.getAttribute("data-shadow-guidance-for");
      if (!elId) return;
      const el = document.querySelector(`[data-shadow-id="${elId}"]`);
      if (!el) return;
      const rect = el.getBoundingClientRect();
      const top = (rect.top + window.scrollY < 26)
        ? (rect.bottom + window.scrollY + 6)
        : (rect.top + window.scrollY - 24);
      const left = Math.max(10, rect.left + window.scrollX);
      badge.style.top = `${top}px`;
      badge.style.left = `${left}px`;
    });
  }, { passive: true });

  // ─── Phase 1: Robust Structured Webpage Observer ────────────────────────────

  // Data Minimization: Patterns for sensitive credentials & payment data
  const SENSITIVE_FIELD_REGEX = /(password|passwd|pin|secret|cvv|cvc|card.?num|credit.?card|expire|exp.?date|ssn|token|auth)/i;

  function isSensitiveField(el) {
    if (!el) return false;
    const type = (el.getAttribute("type") || "").toLowerCase();
    if (type === "password") return true;
    const name = el.getAttribute("name") || "";
    const id = el.getAttribute("id") || "";
    const autocomplete = el.getAttribute("autocomplete") || "";
    const ariaLabel = el.getAttribute("aria-label") || "";
    return (
      SENSITIVE_FIELD_REGEX.test(name) ||
      SENSITIVE_FIELD_REGEX.test(id) ||
      SENSITIVE_FIELD_REGEX.test(autocomplete) ||
      SENSITIVE_FIELD_REGEX.test(ariaLabel)
    );
  }

  function getAccessibleName(el) {
    if (!el) return "";
    // 1. aria-labelledby
    const labelledby = el.getAttribute("aria-labelledby");
    if (labelledby) {
      const labelEl = document.getElementById(labelledby);
      if (labelEl) return (labelEl.innerText || "").trim().substring(0, 100);
    }
    // 2. aria-label
    const ariaLabel = el.getAttribute("aria-label");
    if (ariaLabel) return ariaLabel.trim().substring(0, 100);
    // 3. title attribute
    const title = el.getAttribute("title");
    if (title) return title.trim().substring(0, 100);
    // 4. placeholder
    const placeholder = el.getAttribute("placeholder");
    if (placeholder) return placeholder.trim().substring(0, 100);
    // 5. alt attribute for images
    const alt = el.getAttribute("alt");
    if (alt) return alt.trim().substring(0, 100);
    return "";
  }

  function getSurroundingContext(el) {
    if (!el) return { surrounding_heading: "", context_label: "" };
    let contextLabel = "";
    if (el.id) {
      const lbl = document.querySelector(`label[for="${el.id}"]`);
      if (lbl) contextLabel = (lbl.innerText || "").trim().substring(0, 80);
    }
    if (!contextLabel) {
      const parentLabel = el.closest("label");
      if (parentLabel) contextLabel = (parentLabel.innerText || "").trim().substring(0, 80);
    }

    let headingText = "";
    const container = el.closest(".card, .section, article, form, main, [role='region']") || document.body;
    if (container) {
      const headings = container.querySelectorAll("h1, h2, h3, h4, legend");
      for (const h of headings) {
        if (h.compareDocumentPosition(el) & Node.DOCUMENT_POSITION_FOLLOWING) {
          headingText = (h.innerText || "").trim().substring(0, 80);
        }
      }
    }
    return {
      surrounding_heading: headingText,
      context_label: contextLabel,
    };
  }

  function inspectElementVisuals(el) {
    if (!el) return { isVisible: false, reason: "null" };

    // Exclude SHADOW's own injected UI components
    if (el.closest("#shadow-assistant-frame, .shadow-dp-badge, .shadow-guidance-badge, .shadow-guide-box, #shadow-highlight-styles, #shadow-runtime-notice")) {
      return { isVisible: false, reason: "shadow_internal_ui" };
    }

    const style = window.getComputedStyle(el);
    if (style.display === "none") return { isVisible: false, reason: "display_none" };
    if (style.visibility === "hidden" || style.visibility === "collapse") {
      return { isVisible: false, reason: "visibility_hidden" };
    }
    const opacity = parseFloat(style.opacity || "1");
    if (opacity < 0.04) return { isVisible: false, reason: "zero_opacity", opacity };

    // Bounding rectangle check
    const rect = el.getBoundingClientRect();
    if (rect.width <= 1 || rect.height <= 1) {
      return { isVisible: false, reason: "collapsed_dimensions" };
    }

    // Offscreen check
    const isOffscreen = (
      rect.bottom < -200 ||
      rect.top > (window.innerHeight + 4000) ||
      rect.right < -200 ||
      rect.left > (window.innerWidth + 4000)
    );
    if (isOffscreen) {
      return { isVisible: false, reason: "offscreen" };
    }

    const classNames = (el.className || "").toString().toLowerCase();
    const isPrimaryBtn = classNames.includes("btn-primary") || classNames.includes("btn-success") || classNames.includes("btn-danger");
    const isGhostBtn = classNames.includes("btn-ghost") || classNames.includes("link") || classNames.includes("subtle");

    return {
      isVisible: true,
      display: style.display,
      visibility: style.visibility,
      opacity: opacity,
      rect: {
        x: Math.round(rect.x),
        y: Math.round(rect.y),
        width: Math.round(rect.width),
        height: Math.round(rect.height),
      },
      font_size: style.fontSize,
      font_weight: style.fontWeight,
      color: style.color,
      background_color: style.backgroundColor,
      position: style.position,
      z_index: style.zIndex !== "auto" ? parseInt(style.zIndex, 10) : 0,
      area: Math.round(rect.width * rect.height),
      is_primary_prominence: isPrimaryBtn,
      is_ghost_prominence: isGhostBtn,
    };
  }

  function isVisible(el) {
    const inspection = inspectElementVisuals(el);
    return inspection.isVisible;
  }

  function observePage() {
    const selectors = [
      "button",
      "a[href]",
      "input:not([type='hidden'])",
      "select",
      "textarea",
      "h1", "h2", "h3", "h4",
      '[role="button"]',
      '[role="link"]',
      '[role="checkbox"]',
      '[role="radio"]',
      '[role="switch"]',
      '[role="menuitem"]',
      '[role="tab"]',
      '[role="status"]',
      '[role="alert"]',
      '.badge',
      '.btn',
    ];
    const dialogs = [...document.querySelectorAll('dialog[open], [role="dialog"], [aria-modal="true"]')].filter(isVisible);
    const observationRoot = dialogs[dialogs.length - 1] || document;
    const allElements = observationRoot.querySelectorAll(selectors.join(","));

    const elements = [];
    let autoIdx = shadowIndex;

    for (const el of allElements) {
      const visuals = inspectElementVisuals(el);
      if (!visuals.isVisible) continue;

      // Assign stable temporary action ID if missing
      let shadowId = el.getAttribute("data-shadow-id");
      if (!shadowId) {
        shadowId = `shadow-act-${autoIdx++}`;
        el.setAttribute("data-shadow-id", shadowId);
      }

      // Safe Data Minimization: Redact sensitive credentials & payment values
      const sensitive = isSensitiveField(el);
      let val = null;
      if (el.value !== undefined) {
        val = sensitive ? "[REDACTED_SENSITIVE]" : String(el.value).substring(0, 100);
      }

      // Capture checkbox / radio checked state without exposing private text values
      let isChecked = null;
      const elType = (el.getAttribute("type") || "").toLowerCase();
      if (elType === "checkbox" || elType === "radio") {
        isChecked = Boolean(el.checked);
      } else if (el.getAttribute("aria-checked") !== null) {
        isChecked = el.getAttribute("aria-checked") === "true";
      }

      const accessibleName = getAccessibleName(el);
      const surrounding = getSurroundingContext(el);
      const isEnabled = !(el.disabled || el.getAttribute("aria-disabled") === "true");

      // Structured layout & visual prominence object
      elements.push({
        shadow_id: shadowId,
        "data-shadow-id": shadowId,
        tag: el.tagName.toLowerCase(),
        type: elType || null,
        text: (el.innerText || "").trim().substring(0, 100),
        href: el.href || null,
        value: val,
        checked: isChecked,
        visible: true,
        enabled: isEnabled,
        role: el.getAttribute("role") || null,
        accessible_name: accessibleName,
        in_form: Boolean(el.form || el.closest("form")),
        controls: el.getAttribute("aria-controls") || "",
        expanded: el.getAttribute("aria-expanded"),
        has_popup: Boolean(el.getAttribute("aria-haspopup") && el.getAttribute("aria-haspopup") !== "false"),
        menu_context: el.getAttribute("role") === "menuitem" || Boolean(el.closest('[role="menu"]')),
        bounding_rect: visuals.rect,
        computed_style: {
          display: visuals.display,
          visibility: visuals.visibility,
          opacity: visuals.opacity,
          font_size: visuals.font_size,
          font_weight: visuals.font_weight,
          color: visuals.color,
          background_color: visuals.background_color,
          area: visuals.area,
        },
        visual_prominence: {
          is_primary: visuals.is_primary_prominence,
          is_ghost: visuals.is_ghost_prominence,
          area: visuals.area,
        },
        surrounding_heading: surrounding.surrounding_heading,
        context_label: surrounding.context_label,
      });

      // Bounded JSON snapshot: limit to 75 most relevant elements
      if (elements.length >= 75) break;
    }

    shadowIndex = autoIdx;

    return {
      url: location.href,
      navigation_state: {
        readyState: document.readyState,
        title: document.title,
        timestamp: new Date().toISOString(),
      },
      elements,
      elements_count: elements.length,
      page_text: ((observationRoot === document ? document.body : observationRoot).innerText || "").trim().substring(0, 3000),
    };
  }

  // ─── Action Execution ────────────────────────────────────────────────────────
  function executeAction(action) {
    if (action.action === "scroll") {
      window.scrollBy(0, action.value === "down" ? 400 : -400);
      return { result: "scrolled", direction: action.value };
    }

    if (action.action === "read") {
      if (action.element_id) {
        highlightGuidanceTarget(action.element_id, action.reason || "Observed Target Control");
      }
      return {
        result: "read",
        element_id: action.element_id || null,
        text: document.body.innerText.substring(0, 2000),
      };
    }

    if (action.action === "highlight") {
      if (action.element_id) {
        highlightGuidanceTarget(action.element_id, action.reason || "Observed Target Control");
        return { result: "highlighted", element_id: action.element_id };
      }
      return { result: "highlight_skipped", reason: "no element_id" };
    }

    if (action.action === "ask_user") {
      return { result: "ask_user", question: action.reason };
    }

    if (action.action === "stop") {
      return { result: "stop", message: action.reason };
    }

    // Element-based actions
    const el = document.querySelector(
      `[data-shadow-id="${action.element_id}"]`
    );
    if (!el) {
      return { error: "element not found", element_id: action.element_id };
    }

    // Re-validate element state before execution
    const visuals = inspectElementVisuals(el);
    if (!visuals.isVisible) {
      return { error: "Target element is no longer visible on page", element_id: action.element_id };
    }
    const isEnabled = !(el.disabled || el.getAttribute("aria-disabled") === "true");
    if (!isEnabled) {
      return { error: "Target element is currently disabled", element_id: action.element_id };
    }

    if (action.action === "click") {
      el.scrollIntoView({ behavior: "instant", block: "center" });
      el.focus();
      // Dispatch real mouse events and click
      el.dispatchEvent(new MouseEvent("mousedown", { bubbles: true, cancelable: true, view: window }));
      el.dispatchEvent(new MouseEvent("mouseup", { bubbles: true, cancelable: true, view: window }));
      el.click();

      // If anchor tag with href and no onclick handler, ensure link is followed
      if (el.tagName.toLowerCase() === "a" && el.href && !el.getAttribute("onclick")) {
        setTimeout(() => {
          if (location.href !== el.href) {
            window.location.href = el.href;
          }
        }, 500);
      }
      return { result: "clicked", element_id: action.element_id };
    }

    if (action.action === "select") {
      el.value = action.value;
      el.dispatchEvent(new Event("change", { bubbles: true }));
      return { result: "selected", element_id: action.element_id, value: action.value };
    }

    if (action.action === "type") {
      el.focus();
      el.value = action.value;
      el.dispatchEvent(new Event("input", { bubbles: true }));
      el.dispatchEvent(new Event("change", { bubbles: true }));
      return { result: "typed", element_id: action.element_id, value: action.value };
    }

    return { error: `Unknown action: ${action.action}` };
  }

  // ─── Sleep Helper ─────────────────────────────────────────────────────────────
  function sleep(ms) {
    return new Promise((resolve) => setTimeout(resolve, ms));
  }

  // ─── Post to Assistant iframe ─────────────────────────────────────────────────
  function postToAssistant(msg) {
    if (assistantFrame && assistantFrame.contentWindow) {
      assistantFrame.contentWindow.postMessage(msg, "*");
    }
  }

  function controlLabel(action) {
    const el = action.element_id && document.querySelector(`[data-shadow-id="${CSS.escape(action.element_id)}"]`);
    return action.element_text || (el && (getAccessibleName(el) || el.innerText || el.value)) || "This control";
  }

  const pageGuidance = new ShadowPageGuidance({
    snapshot: observePage, execute: executeAction, send: runtimeMessage,
    storage: chrome.storage.local, task: () => taskId, mode: () => currentMode,
    highlight: highlightGuidanceTarget, clear: clearGuidanceHighlights, post: postToAssistant,
    run: () => { running = true; navigationLoop(); },
    fail: error => { running = false; postToAssistant({source: "SHADOW_CONTENT", type: "TASK_FAILED", error: error.message}); }
  });

  // ─── Navigation Loop ──────────────────────────────────────────────────────────
  async function navigationLoop() {
    if (isLoopActive) return;
    isLoopActive = true;
    try {
      while (running) {
        // Enforce Demo Mode boundary in loop
        if (currentMode === "demo" && !isStreamCoveOrigin(location.href)) {
          running = false;
          try {
            await chrome.storage.local.remove(["active_task_id", "active_running", "active_mode"]);
          } catch (e) {}
          clearDarkPatternHighlights();
          postToAssistant({
            source: "SHADOW_CONTENT",
            type: "TASK_HALTED",
            task_id: taskId,
            reason: "Demo Mode is restricted to StreamCove demonstration environment. Task halted on external site.",
          });
          runtimeMessage({
            type: "UPDATE_TASK_STATUS",
            task_id: taskId,
            status: "halted",
          });
          break;
        }

        const snapshot = observePage();

        // Notify assistant of active reasoning
        postToAssistant({
          source: "SHADOW_CONTENT",
          type: "PLANNING_NEXT_STEP",
        });

        let response;
        const requestedTaskId = taskId;
        try {
          response = await runtimeMessage({
            type: "NAVIGATE_REQUEST",
            task_id: taskId,
            page_snapshot: snapshot,
          });
        } catch (err) {
          postToAssistant({
            source: "SHADOW_CONTENT",
            type: "TASK_FAILED",
            error: err.message || String(err),
          });
          running = false;
          break;
        }

        if (requestedTaskId !== taskId) continue;
        if (!response || response.error) {
          const errMsg = response ? response.error : "No response from background";
          const isPausedErr = typeof errMsg === "string" && (
            errMsg.includes("status: paused") ||
            (errMsg.includes("409") && errMsg.toLowerCase().includes("paused"))
          );
          if (isPausedErr) {
            running = false;
            try {
              await chrome.storage.local.set({
                active_running: false,
                active_status: "paused",
              });
            } catch (e) {}
            postToAssistant({
              source: "SHADOW_CONTENT",
              type: "TASK_PAUSED_WAITING",
              task_id: taskId,
              reason: "Task is paused. Waiting for you.",
            });
            break;
          }

          postToAssistant({
            source: "SHADOW_CONTENT",
            type: "TASK_FAILED",
            error: errMsg,
          });
          running = false;
          break;
        }

        if (!running) break; // Pause may have arrived while the planner was running.

        // Feature 1: Highlight detected dark patterns on actual page DOM
        highlightDarkPatterns(response.detections || []);

        // Approval required?
        if (response.requires_approval) {
          currentApprovalId = response.approval_id;
          await chrome.storage.local.set({active_running: false, active_status: "awaiting_approval"});
          const targetElId = (response.action && response.action.element_id) || "";
          if (targetElId) {
            highlightGuidanceTarget(targetElId, response.mode === "guide" ? "Recommended Step" : "Confirmation Required");
          }
          postToAssistant({
            source: "SHADOW_CONTENT",
            type: "APPROVAL_REQUIRED",
            approval_id: response.approval_id,
            action: {...response.action, element_text: controlLabel(response.action)},
            reason: response.reason || "",
            detections: response.detections || [],
            mode: response.mode || (response.action && response.action.mode) || "guide",
          });
          // Pause until approved/rejected from assistant
          running = false;
          break;
        }

        const action = response.action;

        // Handle special terminal/interactive actions
        if (action.action === "ask_user") {
          postToAssistant({
            source: "SHADOW_CONTENT",
            type: "ASK_USER",
            question: action.reason,
            detections: response.detections || [],
          });
          running = false;
          break;
        }

        if (action.action === "stop" || response.status === "halted" || response.blocked) {
          try {
            await chrome.storage.local.remove(["active_task_id", "active_running", "active_mode"]);
          } catch (e) {}
          clearDarkPatternHighlights();
          running = false;

          const isHalted = response.status === "halted" || response.blocked || (action.reason && (action.reason.includes("halted") || action.reason.includes("stalled") || action.reason.includes("budget")));

          if (isHalted) {
            postToAssistant({
              source: "SHADOW_CONTENT",
              type: "TASK_HALTED",
              task_id: taskId,
              reason: action.reason || response.block_reason || "Task halted by safety boundary.",
              detections: response.detections || [],
            });
            runtimeMessage({
              type: "UPDATE_TASK_STATUS",
              task_id: taskId,
              status: "halted",
            });
          } else {
            postToAssistant({
              source: "SHADOW_CONTENT",
              type: "TASK_COMPLETE",
              message: action.reason,
              detections: response.detections || [],
            });
            runtimeMessage({
              type: "UPDATE_TASK_STATUS",
              task_id: taskId,
              status: "completed",
            });
          }
          break;
        }

        if (currentMode !== "demo") {
          if (response.waiting_for_user) {
            running = false;
            await pageGuidance.show(response);
            if (requestedTaskId !== taskId) continue;
            break;
          }
          if (response.reversible) {
            const advanced = await pageGuidance.navigate(response);
            if (requestedTaskId !== taskId) continue;
            if (!advanced) { running = false; break; }
            continue;
          }
          // Unknown non-Demo response: do not dispatch a mutation.
          running = false;
          await runtimeMessage({type: "UPDATE_TASK_STATUS", task_id: taskId, status: "paused"});
          await pageGuidance.show({...response, reversible: false,
            guidance: `${response.action.element_text || "This control"}? Review on page.`});
          break;
        }

        const result = executeAction(action);
        postToAssistant({source: "SHADOW_CONTENT", type: "ACTION_TAKEN",
          action: {...action, element_text: controlLabel(action)}, result,
          detections: response.detections || [], mode: currentMode});

        // Wait before next step
        await sleep(1500);
      }
    } finally {
      isLoopActive = false;
    }
  }

  // ─── Inject Floating Assistant ────────────────────────────────────────────────
  function injectAssistant() {
    if (document.getElementById("shadow-assistant-frame")) return;

    const frame = document.createElement("iframe");
    frame.id = "shadow-assistant-frame";
    frame.src = chrome.runtime.getURL("assistant/assistant.html");
    frame.style.cssText = [
      "position: fixed",
      "bottom: 24px",
      "right: 24px",
      "width: 420px",
      "height: 560px",
      "z-index: 2147483647",
      "border: none",
      "border-radius: 14px",
      "box-shadow: 0 16px 48px rgba(0,0,0,0.65), 0 0 0 1px rgba(255,255,255,0.06)",
      "background: transparent",
      "transition: height 0.25s ease, width 0.25s ease",
      "color-scheme: normal",
    ].join(";");
    frame.allow = "";

    assistantFrame = frame;
    const loaded = new Promise(resolve => frame.addEventListener("load", resolve, {once: true}));
    document.body.appendChild(frame);
    return loaded;
  }

  // ─── Message Listener (from iframe via postMessage) ───────────────────────────
  window.addEventListener("message", async (event) => {
    // Security: only accept messages from chrome-extension origin or same page
    const isExtensionOrigin =
      event.origin.startsWith("chrome-extension://") ||
      event.origin === window.location.origin;
    if (!isExtensionOrigin || event.source !== assistantFrame?.contentWindow) return;

    const msg = event.data;
    if (!msg || msg.source !== "SHADOW_ASSISTANT") return;

    if (runtimeInvalidated) return;
    switch (msg.type) {
      case "CREATE_TASK": {
        let reqMode = msg.mode || "observe";
        if (reqMode === "demo" && !isStreamCoveOrigin(location.href)) {
          reqMode = "guide";
        }
        currentMode = reqMode;
        // Forward to background, relay task_id back to assistant
        let result;
        try { result = await runtimeMessage({
          type: "CREATE_TASK",
          instruction: msg.instruction,
          mode: reqMode,
          url: location.href,
        }); } catch (error) {
          if (runtimeInvalidated) return;
          result = { error: error.message };
        }
        postToAssistant({
          source: "SHADOW_CONTENT",
          type: "TASK_CREATED",
          task_id: result.task_id,
          mode: result.mode || reqMode,
          error: result.error,
        });
        break;
      }

      case "START_TASK": {
        pageGuidance.reset();
        taskId = msg.task_id;
        if (msg.mode) currentMode = msg.mode;
        running = true;
        try {
          await chrome.storage.local.set({
            active_task_id: taskId,
            active_running: true,
            active_status: "active",
            active_mode: currentMode,
            active_owner_tab_id: ownerTabId,
            active_owner_origin: location.origin,
          });
        } catch (e) {}
        navigationLoop();
        break;
      }

      case "PAUSE_TASK": {
        pageGuidance.reset("user_pause");
        running = false;
        try {
          await chrome.storage.local.set({
            active_running: false,
            active_status: "paused",
            active_paused_reason: "user_pause",
          });
        } catch (e) {}
        await runtimeMessage({
          type: "UPDATE_TASK_STATUS",
          task_id: taskId,
          status: "paused",
        });
        break;
      }

      case "RESUME_TASK": {
        pageGuidance.reset();
        // Wait for backend to confirm task is active before requesting next step!
        try {
          const updateRes = await runtimeMessage({
            type: "UPDATE_TASK_STATUS",
            task_id: taskId,
            status: "active",
          });
          if (updateRes && updateRes.status === "active" && !updateRes.error) {
            running = true;
            await chrome.storage.local.set({
              active_running: true,
              active_status: "active",
            });
            postToAssistant({
              source: "SHADOW_CONTENT",
              type: "TASK_RESUMED",
              status: "active",
            });
            navigationLoop();
          } else {
            postToAssistant({
              source: "SHADOW_CONTENT",
              type: "TASK_RESUME_FAILED",
              error: (updateRes && updateRes.error) || "Backend did not confirm active status.",
            });
          }
        } catch (e) {
          if (runtimeInvalidated) return;
          postToAssistant({
            source: "SHADOW_CONTENT",
            type: "TASK_RESUME_FAILED",
            error: e.message || String(e),
          });
        }
        break;
      }

      case "STOP_TASK": {
        pageGuidance.reset();
        running = false;
        taskId = null;
        try {
          await chrome.storage.local.remove([
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
        break;
      }

      case "APPROVE_ACTION": {
        const approvalTaskId = taskId;
        const approveResult = await runtimeMessage({
          type: "APPROVE_ACTION",
          approval_id: currentApprovalId || msg.approval_id,
          approved: msg.approved,
          answer: msg.answer,
        });
        if (approvalTaskId !== taskId) return;
        if (!approveResult || approveResult.error) {
          postToAssistant({source: "SHADOW_CONTENT", type: "TASK_FAILED", error: approveResult?.error || "Approval failed"});
          return;
        }
        currentApprovalId = null;
        clearGuidanceHighlights();
        if (!msg.approved) {
          running = false;
          await chrome.storage.local.set({active_running: false, active_status: "paused", active_paused_reason: "rejected"});
          await runtimeMessage({type: "UPDATE_TASK_STATUS", task_id: approvalTaskId, status: "paused"});
          if (approvalTaskId !== taskId) return;
          postToAssistant({source: "SHADOW_CONTENT", type: "TASK_PAUSED_WAITING", reason: "Action rejected. Subscription remains ACTIVE."});
        }
        if (msg.approved && approveResult && !approveResult.error) {
          try {
            await chrome.storage.local.set({
              active_task_id: taskId,
              active_running: true,
              active_status: "active",
            });
          } catch (e) {}

          // Execute the approved action immediately on the page!
          if (approveResult.element_id || (approveResult.action && approveResult.action.element_id)) {
            const elId = approveResult.element_id || approveResult.action.element_id;
            executeAction({ action: "click", element_id: elId });
          }
          await sleep(1500);
          running = true;
          navigationLoop();
        }
        break;
      }

      case "VIEW_ON_PAGE": {
        // Feature 3: Scroll corresponding element into view and pulse highlight
        if (!msg.element_id) return;
        const targetEl = document.querySelector(`[data-shadow-id="${msg.element_id}"]`);
        if (targetEl) {
          targetEl.scrollIntoView({ behavior: "smooth", block: "center" });
          targetEl.classList.add("shadow-dp-focus-pulse");
          try {
            targetEl.focus({ preventScroll: true });
          } catch (e) {}
          setTimeout(() => {
            targetEl.classList.remove("shadow-dp-focus-pulse");
          }, 2000);
        }
        break;
      }

      case "FOCUS_ASSISTANT": {
        // Already visible — nothing to do
        break;
      }

      case "SET_HEIGHT": {
        if (assistantFrame) {
          assistantFrame.style.height = `${msg.height}px`;
        }
        break;
      }

      case "DRAG_MOVE": {
        if (assistantFrame) {
          const rect = assistantFrame.getBoundingClientRect();
          let newRight = Math.max(10, window.innerWidth - (rect.right + msg.deltaX));
          let newBottom = Math.max(10, window.innerHeight - (rect.bottom + msg.deltaY));
          assistantFrame.style.right = `${newRight}px`;
          assistantFrame.style.bottom = `${newBottom}px`;
        }
        break;
      }
    }
  });

  // ─── Dynamic SPA Route & Mutation Observer ────────────────────────────────────
  let mutationDebounceTimer = null;
  function setupPageMutationObserver() {
    try {
      const observer = new MutationObserver((mutations) => {
        let isRelevant = false;
        for (const m of mutations) {
          if (m.target && m.target.closest && m.target.closest("#shadow-assistant-frame")) {
            continue;
          }
          if (m.addedNodes.length > 0 || m.removedNodes.length > 0) {
            isRelevant = true;
            break;
          }
        }

        if (isRelevant) {
          clearTimeout(mutationDebounceTimer);
          mutationDebounceTimer = setTimeout(() => {
            if (running && !isLoopActive) {
              postToAssistant({
                source: "SHADOW_CONTENT",
                type: "DOM_MUTATION_OBSERVED",
                url: location.href,
              });
            }
          }, 450);
        }
      });

      if (document.body) {
        observer.observe(document.body, { childList: true, subtree: true });
      }

      window.addEventListener("popstate", () => handleSpaNavigation("popstate"));
      window.addEventListener("hashchange", () => handleSpaNavigation("hashchange"));

      const origPushState = history.pushState;
      if (origPushState) {
        history.pushState = function (...args) {
          const ret = origPushState.apply(this, args);
          handleSpaNavigation("pushState");
          return ret;
        };
      }
    } catch (e) {}
  }

  function handleSpaNavigation(source) {
    if (running) {
      postToAssistant({
        source: "SHADOW_CONTENT",
        type: "SPA_NAVIGATION",
        source,
        url: location.href,
      });
    }
  }

  // ─── Init ─────────────────────────────────────────────────────────────────────
  async function init() {
    await injectAssistant();
    setInterval(() => {
      if (!runtimeInvalidated && !chrome.runtime.id) extensionReloaded();
    }, 1000);
    injectHighlightStyles();
    setupPageMutationObserver();
    window.addEventListener("beforeunload", clearDarkPatternHighlights);

    const isStreamCove = isStreamCoveOrigin(location.href);
    const hostContext = () => postToAssistant({
      source: "SHADOW_CONTENT", type: "HOST_CONTEXT", hostname: location.hostname,
      url: location.href, is_streamcove: isStreamCove,
      is_localhost: ["localhost", "127.0.0.1"].includes(location.hostname),
    });
    // One initialization owner: reconcile storage/backend before enabling Start.
    // The iframe never independently restores cached mode or running status.
    try {
      const tabContext = await runtimeMessage({type: "GET_TAB_CONTEXT"});
      ownerTabId = tabContext?.tab_id ?? null;
      const stored = await chrome.storage.local.get([
        "active_task_id", "active_running", "active_status", "active_goal", "active_mode",
        "active_step_count", "active_detections_count", "active_paused_reason",
        "active_owner_tab_id", "active_owner_origin"
      ]);
      if (!stored.active_task_id) { hostContext(); return; }
      if ((stored.active_owner_tab_id != null && stored.active_owner_tab_id !== ownerTabId) ||
          (stored.active_owner_origin && stored.active_owner_origin !== location.origin && stored.active_mode !== "demo")) {
        hostContext();
        return; // Opening another activated page is not consent to move a task.
      }
      taskId = stored.active_task_id;
      const backendTask = await runtimeMessage({type: "GET_TASK", task_id: taskId});
      const reloadedTask = sessionStorage.getItem("shadow_extension_reloaded");
      sessionStorage.removeItem("shadow_extension_reloaded");
      if (reloadedTask === taskId && backendTask && ["active", "paused"].includes(backendTask.status)) {
        await runtimeMessage({type: "UPDATE_TASK_STATUS", task_id: taskId, status: "paused"});
        await chrome.storage.local.remove(["active_task_id", "active_running", "active_status", "active_mode"]);
        hostContext();
        postToAssistant({source: "SHADOW_CONTENT", type: "TASK_FAILED",
          error: "Previous extension session ended. Start New Task to continue."});
        return;
      }
      if (!backendTask || backendTask.error || !["active", "paused"].includes(backendTask.status)) {
        await chrome.storage.local.remove(["active_task_id", "active_running", "active_status", "active_mode"]);
        hostContext();
        postToAssistant({source: "SHADOW_CONTENT", type: "TASK_FAILED",
          error: backendTask?.error || `Restored task is ${backendTask?.status || "unavailable"}. Start New Task to continue.`});
        return;
      }
      currentMode = backendTask.mode || stored.active_mode || "observe";
      if (currentMode === "demo" && !isStreamCove) {
        await chrome.storage.local.remove(["active_task_id", "active_running", "active_status", "active_mode"]);
        await runtimeMessage({type: "UPDATE_TASK_STATUS", task_id: taskId, status: "halted"});
        hostContext();
        postToAssistant({source: "SHADOW_CONTENT", type: "TASK_HALTED", task_id: taskId,
          reason: "Demo Mode is restricted to StreamCove demonstration environment."});
        return;
      }
      const guidanceContinuation = currentMode !== "demo" && stored.active_paused_reason !== "user_pause" &&
        (pageGuidance.intent(taskId) || (currentMode === "guide" && stored.active_paused_reason === "guide_step"));
      if (guidanceContinuation) {
        const resumed = await runtimeMessage({type: "UPDATE_TASK_STATUS", task_id: taskId, status: "active"});
        if (resumed?.status !== "active" || resumed.error) throw new Error(resumed?.error || "Task cannot continue.");
        sessionStorage.removeItem("shadow_navigation_intent");
      }
      const paused = !guidanceContinuation && (stored.active_running === false || stored.active_status === "paused" || backendTask.status === "paused");
      if (paused && backendTask.status !== "paused") {
        await runtimeMessage({type: "UPDATE_TASK_STATUS", task_id: taskId, status: "paused"});
      }
      running = !paused;
      await chrome.storage.local.set({active_mode: currentMode, active_running: running, active_status: paused ? "paused" : "active"});
      hostContext();
      postToAssistant({source: "SHADOW_CONTENT", type: "RESTORE_SESSION", task_id: taskId,
        goal: backendTask.authorized_goal || stored.active_goal, mode: currentMode,
        step_count: stored.active_step_count, detections_count: stored.active_detections_count,
        is_paused: paused, waiting_user: paused});
      if (running) navigationLoop();
    } catch (error) {
      if (!runtimeInvalidated) {
        hostContext();
        postToAssistant({source: "SHADOW_CONTENT", type: "TASK_FAILED", error: error.message});
      }
    }
  }

  if (document.body) {
    init();
  } else {
    document.addEventListener("DOMContentLoaded", init);
  }

  // Also listen for messages from the popup
  if (typeof chrome !== "undefined" && chrome.runtime && chrome.runtime.onMessage) {
    chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
      if (message.type === "PING") {
        sendResponse({ alive: true });
        return false;
      }
      if (message.type === "FOCUS_ASSISTANT") {
        // Show/focus the iframe
        if (assistantFrame) {
          assistantFrame.style.display = "block";
        }
        sendResponse({ ok: true });
        return false;
      }
      if (message.type === "DEACTIVATE_SHADOW") {
        clearDarkPatternHighlights();
        if (assistantFrame) {
          assistantFrame.remove();
          assistantFrame = null;
        }
        sendResponse({ ok: true });
        return false;
      }
    });
  }
})();
