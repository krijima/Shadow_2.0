// SHADOW Popup Script — Manifest V3 ActiveTab Activation

const siteHost      = document.getElementById("siteHost");
const statusDot     = document.getElementById("statusDot");
const statusText    = document.getElementById("statusText");
const actionBtn     = document.getElementById("actionBtn");
const actionBtnText = document.getElementById("actionBtnText");
const infoText      = document.getElementById("infoText");
const siteScripts = ['terminal_audit.js', 'pocketfm.js', 'navigation.js', 'content.js'];

async function installSiteScripts(tabId, hostname, sitePattern) {
  if (!["localhost", "127.0.0.1"].includes(hostname)) {
    const scriptId = `shadow-${sitePattern.replace(/[^a-z0-9]/gi, "-")}`;
    const registration = {id: scriptId, matches: [sitePattern], js: siteScripts,
      runAt: 'document_idle', persistAcrossSessions: true};
    const existing = await chrome.scripting.getRegisteredContentScripts({ids: [scriptId]});
    if (existing.length) await chrome.scripting.updateContentScripts([registration]);
    else await chrome.scripting.registerContentScripts([registration]);
  }
  await chrome.scripting.executeScript({target: {tabId}, files: siteScripts});
}

function isRestrictedUrl(url) {
  if (!url) return true;
  const restrictedProtocols = [
    "chrome:",
    "chrome-extension:",
    "devtools:",
    "edge:",
    "about:",
    "view-source:",
    "data:",
    "blob:"
  ];
  return restrictedProtocols.some(proto => url.startsWith(proto)) || url.includes("chromewebstore.google.com");
}

async function initPopup() {
  try {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (!tab || !tab.id) {
      setRestrictedState("No active tab detected");
      return;
    }

    const rawUrl = tab.url || "";
    if (isRestrictedUrl(rawUrl)) {
      setRestrictedState("Internal Browser Page", "Chrome security policies prevent extensions from executing on internal system and webstore URLs.");
      return;
    }

    let parsedUrl;
    try {
      parsedUrl = new URL(rawUrl);
    } catch (e) {
      setRestrictedState("Invalid URL", "Could not parse current page URL.");
      return;
    }

    const hostname = parsedUrl.hostname;
    const isLocal = hostname === "localhost" || hostname === "127.0.0.1";
    siteHost.textContent = isLocal ? `Localhost (${parsedUrl.port || "8080"}) — StreamCove` : hostname;

    // Check if content script is already injected
    let isAlive = false;
    try {
      const pingResp = await chrome.tabs.sendMessage(tab.id, { type: "PING" });
      if (pingResp && pingResp.alive) {
        isAlive = true;
      }
    } catch (e) {
      isAlive = false;
    }

    if (isAlive) {
      setActiveState(tab.id, hostname, `${parsedUrl.protocol}//${parsedUrl.hostname}/*`);
    } else {
      setReadyToActivateState(tab.id, hostname, `${parsedUrl.protocol}//${parsedUrl.hostname}/*`);
    }

  } catch (err) {
    setRestrictedState("Error", err.message || String(err));
  }
}

function setActiveState(tabId, hostname, sitePattern) {
  statusDot.className = "status-dot";
  statusText.textContent = "SHADOW is active on this tab";
  actionBtn.disabled = false;
  actionBtnText.textContent = "Open / Focus Assistant";
  infoText.textContent = `Active on ${hostname}. Operating under safe observation & defense boundaries.`;

  actionBtn.onclick = async () => {
    try {
      // Upgrade older saved registrations and already-open tabs too. The
      // content controller's installation guard prevents duplicate listeners.
      await installSiteScripts(tabId, hostname, sitePattern);
      await chrome.tabs.sendMessage(tabId, { type: "FOCUS_ASSISTANT" });
      window.close();
    } catch (e) {
      // In case content script reloaded
      window.close();
    }
  };
}

function setReadyToActivateState(tabId, hostname, sitePattern) {
  statusDot.className = "status-dot inactive";
  statusText.textContent = "Ready to inspect this site";
  actionBtn.disabled = false;
  actionBtnText.textContent = `Activate SHADOW on ${hostname}`;
  infoText.textContent = "Allow this site so SHADOW can follow its pages. Private form values are not read.";

  actionBtn.onclick = async () => {
    actionBtn.disabled = true;
    actionBtnText.textContent = "Activating SHADOW…";

    try {
      // Request only the selected site, directly from the activation gesture.
      if (!["localhost", "127.0.0.1"].includes(hostname)) {
        const granted = await chrome.permissions.request({origins: [sitePattern]});
        if (!granted) {
          statusText.textContent = "Site access was not granted";
          actionBtn.disabled = false;
          actionBtnText.textContent = "Allow this site";
          return;
        }
      }
      await installSiteScripts(tabId, hostname, sitePattern);

      // 2. Record permitted domain in storage & backend
      const stored = await chrome.storage.local.get(["permitted_domains"]);
      const permitted = new Set(stored.permitted_domains || []);
      permitted.add(hostname);
      await chrome.storage.local.set({ permitted_domains: Array.from(permitted) });

      try {
        await chrome.runtime.sendMessage({
          type: "PERMIT_DOMAIN",
          domain: hostname
        });
      } catch (e) {}

      // 3. Small delay for injection, then focus assistant
      setTimeout(async () => {
        try {
          await chrome.tabs.sendMessage(tabId, { type: "FOCUS_ASSISTANT" });
        } catch (e) {}
        window.close();
      }, 500);

    } catch (err) {
      statusDot.className = "status-dot error";
      statusText.textContent = "Activation failed";
      actionBtn.disabled = false;
      actionBtnText.textContent = "Retry Activation";
      infoText.textContent = `Could not inject assistant: ${err.message || String(err)}`;
    }
  };
}

function setRestrictedState(title, message) {
  siteHost.textContent = title;
  statusDot.className = "status-dot error";
  statusText.textContent = "Restricted URL";
  actionBtn.disabled = true;
  actionBtnText.textContent = "Cannot Run on This Page";
  infoText.textContent = message || "SHADOW only runs on standard web pages (HTTP/HTTPS) and localhost.";
}

document.addEventListener("DOMContentLoaded", initPopup);
