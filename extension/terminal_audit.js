// Shared terminal-message contract for the content script and audit UI.
(function (root) {
  "use strict";

  const statusByType = Object.freeze({
    TASK_COMPLETE: "completed",
    TASK_HALTED: "halted",
    TASK_FAILED: "failed",
    TASK_CANCELLED: "cancelled",
  });

  function createTerminalMessage(type, taskId, mode, details = {}) {
    return {
      source: "SHADOW_CONTENT",
      ...details,
      type,
      task_id: taskId || null,
      mode: mode || "observe",
      status: statusByType[type] || "failed",
      detections: Array.isArray(details.detections) ? details.detections : [],
    };
  }

  root.ShadowTerminalAudit = { createTerminalMessage };
})(globalThis);
