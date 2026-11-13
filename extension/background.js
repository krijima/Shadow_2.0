// SHADOW Extension — Background Service Worker (Manifest V3)
// Communicates between content script and FastAPI backend API

const BACKEND_URL = "http://127.0.0.1:8001";

async function fetchBackend(method, path, body) {
  try {
    const options = {
      method,
      headers: { "Content-Type": "application/json" },
    };
    if (body !== undefined) {
      options.body = JSON.stringify(body);
    }
    const response = await fetch(`${BACKEND_URL}${path}`, options);
    if (!response.ok) {
      const text = await response.text();
      console.warn("[SHADOW API]", { method, path, task_id: body?.task_id, http_status: response.status, response: text });
      return { error: `HTTP ${response.status}: ${text}` };
    }
    const data = await response.json();
    console.info("[SHADOW API]", { method, path, task_id: body?.task_id || data.task_id,
      request_mode: body?.mode, response_mode: data.mode, status: data.status,
      action: data.action?.action, requires_approval: data.requires_approval, http_status: response.status });
    return data;
  } catch (err) {
    return { error: `Backend connection error: ${err.message || String(err)}. Ensure backend is running on ${BACKEND_URL}` };
  }
}

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  const { type } = message;

  if (type === "GET_TAB_CONTEXT") {
    sendResponse({tab_id: sender.tab?.id ?? null});
    return false;
  }

  if (type === "NAVIGATE_REQUEST") {
    // Forward page snapshot to backend for AI navigation
    fetchBackend("POST", "/api/navigate", {
      task_id: message.task_id,
      page_snapshot: message.page_snapshot,
    }).then(sendResponse);
    return true; // async
  }

  if (type === "CREATE_TASK") {
    fetchBackend("POST", "/api/task", {
      instruction: message.instruction,
      mode: message.mode || "observe",
      url: message.url,
    }).then(sendResponse);
    return true;
  }

  if (type === "UPDATE_TASK_STATUS") {
    fetchBackend("PATCH", `/api/task/${message.task_id}/status`, {
      status: message.status,
    }).then(sendResponse);
    return true;
  }

  if (type === "GET_TASK") {
    fetchBackend("GET", `/api/task/${message.task_id}`).then(sendResponse);
    return true;
  }

  if (type === "APPROVE_ACTION") {
    fetchBackend("POST", `/api/approve/${message.approval_id}`, {
      approved: message.approved,
      answer: message.answer,
    }).then(sendResponse);
    return true;
  }

  if (type === "PERMIT_DOMAIN") {
    fetchBackend("POST", "/api/permissions/permit", {
      domain: message.domain
    }).then(sendResponse);
    return true;
  }

  if (type === "GET_EVIDENCE") {
    fetchBackend("GET", `/api/evidence/${message.task_id}`).then(sendResponse);
    return true;
  }

  if (type === "ACTIVATE_TAB") {
    const tabId = message.tab_id || (sender.tab && sender.tab.id);
    if (!tabId) {
      sendResponse({ error: "Missing tab_id for activation" });
      return false;
    }

    chrome.scripting.executeScript({
      target: { tabId },
      files: ["navigation.js", "content.js"]
    }).then(() => {
      sendResponse({ ok: true, tab_id: tabId });
    }).catch(err => {
      sendResponse({ error: err.message || String(err) });
    });
    return true;
  }

  // Unknown message type
  sendResponse({ error: `Unknown message type: ${type}` });
  return false;
});
