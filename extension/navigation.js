// Ordinary-site guidance. Demo's execution and approval remain in content.js.
(() => {
  "use strict";
  class ShadowPageGuidance {
    constructor(api) {
      this.api = api;
      this.waiting = null;
      this.epoch = 0;
      this.continuing = false;
      document.addEventListener("click", event => {
        const state = this.waiting;
        if (!event.isTrusted || !state || event.target.closest?.(".shadow-guide-box")) return;
        const control = document.querySelector(`[data-shadow-id="${CSS.escape(state.response.action.element_id)}"]`);
        if (control && (event.target === control || control.contains(event.target))) this.followClick(state);
      }, true);
    }

    text(value) {
      return String(value || "").replace(/\s+/g, " ").trim().slice(0, 120);
    }

    visible(node) {
      if (!node) return false;
      const style = getComputedStyle(node);
      return style.display !== "none" && style.visibility !== "hidden" && style.opacity !== "0";
    }

    nodeLabel(node) {
      return this.text(node?.getAttribute("aria-label") || node?.getAttribute("aria-labelledby") ||
        node?.innerText || node?.textContent || node?.id || node?.tagName);
    }

    signature() {
      const snapshot = this.api.snapshot();
      // Guide keeps its existing broad continuation signal because the user,
      // not Observe, made the click. The stricter signal is Observe-only.
      if (this.api.mode() !== "observe") {
        return JSON.stringify([location.href, snapshot.elements.map(el =>
          [el.shadow_id, el.tag, el.text, el.accessible_name, el.href, el.value, el.checked,
            el.enabled, el.role, el.controls, el.expanded, el.has_popup, el.menu_context])]);
      }
      // Framework re-renders, regenerated data-shadow-id values, and unrelated
      // feed updates are not navigation progress. Observe advances only when a
      // URL, page heading, menu, or dialog changes.
      const labels = selector => [...document.querySelectorAll(selector)]
        .filter(node => this.visible(node)).map(node => this.nodeLabel(node)).sort();
      const heading = [...document.querySelectorAll('h1, h2, h3, [role="heading"]')]
        .find(node => this.visible(node));
      const expanded = [...document.querySelectorAll('[aria-expanded="true"]')]
        .filter(node => this.visible(node)).map(node => this.nodeLabel(node)).sort();
      return JSON.stringify([location.href, this.nodeLabel(heading),
        labels('dialog[open], [role="dialog"], [role="alertdialog"], [aria-modal="true"]'),
        labels('[role="menu"], [role="listbox"]'), expanded,
        labels('details[open] > summary')]);
    }

    observeAttemptKey(response) {
      const target = this.target(response);
      if (!target) return null;
      const identity = [target.tag, target.type, target.role, target.href,
        target.accessible_name || target.text || target.value, target.controls,
        target.surrounding_heading, target.context_label].map(value => this.text(value));
      return JSON.stringify([this.signature(), identity]);
    }

    observeAttempts(taskId) {
      try {
        const saved = JSON.parse(sessionStorage.getItem("shadow_observe_attempts") || "null");
        if (saved?.taskId === taskId && Array.isArray(saved.keys)) return new Set(saved.keys);
      } catch {}
      return new Set();
    }

    saveObserveAttempts(taskId, attempts) {
      sessionStorage.setItem("shadow_observe_attempts", JSON.stringify({taskId, keys: [...attempts]}));
    }

    observeAttemptCount(attempts, context) {
      return [...attempts].filter(key => {
        try { return JSON.parse(key)?.[0] === context; } catch { return false; }
      }).length;
    }

    async pauseObserve(response, taskId, epoch, guidance) {
      const update = await this.api.send({type: "UPDATE_TASK_STATUS", task_id: taskId, status: "paused"});
      if (epoch === this.epoch && taskId === this.api.task() && update?.status === "paused") {
        await this.show({...response, reversible: false, guidance});
      }
    }

    reset(reason) {
      this.epoch++;
      this.userPaused = reason === "user_pause";
      this.waiting = null;
      sessionStorage.removeItem("shadow_navigation_intent");
      sessionStorage.removeItem("shadow_observe_attempts");
      this.api.clear();
    }

    async preserveUserPause(taskId) {
      if (!this.userPaused || this.api.task() !== taskId) return;
      await this.api.send({type: "UPDATE_TASK_STATUS", task_id: taskId, status: "paused"});
      if (this.userPaused && this.api.task() === taskId) {
        await this.api.storage.set({active_running: false, active_status: "paused", active_paused_reason: "user_pause"});
      }
    }

    intent(taskId) {
      try {
        const intent = JSON.parse(sessionStorage.getItem("shadow_navigation_intent") || "null");
        return intent?.taskId === taskId && intent.url !== location.href;
      } catch { return false; }
    }

    target(response) {
      return this.api.snapshot().elements.find(el => el.shadow_id === response.action.element_id);
    }

    matches(response) {
      const current = this.target(response), expected = response.navigation_target;
      if (!current || !expected) return false;
      return ["tag", "type", "text", "accessible_name", "href", "in_form", "role", "controls", "expanded", "has_popup", "menu_context"]
        .every(key => (current[key] ?? null) === (expected[key] ?? null));
    }

    changedReview(response) {
      const current = this.target(response);
      const label = current?.accessible_name || current?.text || "This control";
      const guidance = /\b(cancel|cancellation|unsubscribe|end membership)\b/i.test(label)
        ? "Review cancellation." : `${label}? Review on page.`;
      return {...response, reversible: false, guidance,
        action: {...response.action, element_text: label}};
    }

    async changed(before, epoch, taskId) {
      const deadline = Date.now() + 12000;
      let latest = before, stableSince = 0;
      while (Date.now() < deadline && this.epoch === epoch && this.api.task() === taskId) {
        await new Promise(resolve => setTimeout(resolve, 100));
        const current = this.signature();
        if (current !== before) {
          if (current !== latest) { latest = current; stableSince = Date.now(); }
          else if (Date.now() - stableSince >= 500) {
            return this.epoch === epoch && this.api.task() === taskId;
          }
        }
      }
      return false;
    }

    async show(response) {
      const taskId = this.api.task(), epoch = this.epoch;
      if (response.reversible && !this.matches(response)) response = this.changedReview(response);
      const reason = response.reversible ? "guide_step" : "review_on_page";
      await this.api.storage.set({active_task_id: taskId, active_running: false,
        active_status: "paused", active_mode: this.api.mode(), active_paused_reason: reason});
      if (this.api.task() !== taskId || this.epoch !== epoch) {
        await this.preserveUserPause(taskId);
        return;
      }
      this.api.highlight(response.action.element_id, response.guidance);
      const state = {taskId, epoch, response, clicked: false, before: this.signature()};
      this.waiting = state;
      if (this.api.mode() === "guide") {
        const badge = document.querySelector(".shadow-guidance-badge");
        if (badge) {
          const box = document.createElement("button");
          box.type = "button";
          box.className = "shadow-guidance-badge shadow-guide-box";
          box.textContent = response.guidance;
          box.style.cssText = badge.style.cssText;
          box.style.setProperty("pointer-events", "auto", "important");
          box.style.setProperty("cursor", "pointer", "important");
          box.style.setProperty("max-width", "calc(100vw - 24px)", "important");
          box.style.setProperty("overflow", "hidden", "important");
          box.style.setProperty("text-overflow", "ellipsis", "important");
          box.addEventListener("click", event => {
            if (!event.isTrusted || state.clicked || this.waiting !== state) return;
            if (response.reversible) {
              if (!this.matches(response)) {
                state.clicked = true;
                this.show(this.changedReview(response)).catch(error => this.api.fail(error));
                return;
              }
              this.followClick(state);
              box.disabled = true;
              this.api.execute({...response.action, action: "click"});
            } else {
              // Review boxes never submit a consequential or unknown control.
              document.querySelector(`[data-shadow-id="${CSS.escape(response.action.element_id)}"]`)?.focus();
            }
          });
          badge.replaceWith(box);
        }
      }
      this.api.post({source: "SHADOW_CONTENT", type: "GUIDANCE_WAITING", guidance: response.guidance,
        action: response.action, mode: this.api.mode(), reversible: response.reversible});
    }

    followClick(state) {
      if (state.clicked || this.waiting !== state || state.epoch !== this.epoch) return;
      state.clicked = true;
      // Synchronous marker survives a normal link navigation before Chrome's
      // asynchronous storage callbacks complete. Only this tab owns the intent.
      sessionStorage.setItem("shadow_navigation_intent", JSON.stringify({taskId: state.taskId, url: location.href}));
      this.continueAfterClick(state).catch(error => this.api.fail(error));
    }

    async continueAfterClick(state) {
      if (this.continuing) return;
      this.continuing = true;
      try {
        if (!await this.changed(state.before, state.epoch, state.taskId)) {
          if (this.waiting === state) {
            state.clicked = false;
            document.querySelector(".shadow-guide-box")?.removeAttribute("disabled");
          }
          return;
        }
        if (this.waiting !== state) return;
        const result = await this.api.send({type: "UPDATE_TASK_STATUS", task_id: state.taskId, status: "active"});
        if (state.epoch !== this.epoch || this.api.task() !== state.taskId) {
          await this.preserveUserPause(state.taskId);
          return;
        }
        if (result?.status !== "active" || result.error) throw new Error(result?.error || "Task cannot continue. Start New Task.");
        await this.api.storage.set({active_running: true, active_status: "active", active_paused_reason: null});
        if (state.epoch !== this.epoch || this.api.task() !== state.taskId) {
          await this.preserveUserPause(state.taskId);
          return;
        }
        this.waiting = null;
        sessionStorage.removeItem("shadow_navigation_intent");
        this.api.clear();
        this.api.run();
      } finally { this.continuing = false; }
    }

    async navigate(response) {
      const taskId = this.api.task(), epoch = this.epoch, before = this.signature();
      if (!this.matches(response)) {
        const paused = await this.api.send({type: "UPDATE_TASK_STATUS", task_id: taskId, status: "paused"});
        if (epoch === this.epoch && taskId === this.api.task() && paused?.status === "paused") await this.show(this.changedReview(response));
        return false;
      }
      const observe = this.api.mode() === "observe";
      const context = observe && this.signature();
      const attemptKey = observe && this.observeAttemptKey(response);
      const attempts = observe ? this.observeAttempts(taskId) : null;
      if (observe && attemptKey && attempts.has(attemptKey)) {
        await this.pauseObserve(response, taskId, epoch,
          response.stalled_guidance || "That control was already tried without advancing.");
        return false;
      }
      if (observe && attemptKey) {
        attempts.add(attemptKey);
        this.saveObserveAttempts(taskId, attempts);
      }
      const result = this.api.execute(response.action);
      if (result?.error) throw new Error(result.error);
      this.api.post({source: "SHADOW_CONTENT", type: "ACTION_TAKEN", action: response.action,
        result, guidance: response.guidance, mode: this.api.mode(), detections: response.detections});
      if (await this.changed(before, epoch, taskId)) return true;
      if (epoch !== this.epoch || taskId !== this.api.task()) return false;
      if (observe && this.observeAttemptCount(attempts, context) < 2) {
        // Keep the loop active for exactly one alternate reversible plan. The
        // next response is checked against the stable attempted-control key.
        return true;
      }
      if (observe) {
        await this.pauseObserve(response, taskId, epoch,
          response.stalled_guidance || "This control did not advance the page.");
        return false;
      }
      const update = await this.api.send({type: "UPDATE_TASK_STATUS", task_id: taskId, status: "paused"});
      if (epoch === this.epoch && taskId === this.api.task() && update?.status === "paused") await this.show({...response, reversible: false,
        guidance: response.stalled_guidance || `${response.action.element_text || "This control"}? Review on page.`});
      return false;
    }
  }
  globalThis.ShadowPageGuidance = ShadowPageGuidance;
})();
