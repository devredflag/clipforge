importScripts("common.js");

async function callApi(path, options = {}) {
  const { serverUrl, token } = await cfGetConfig();
  if (!token) return { ok: false, error: "Cole o token da API nas configurações da extensão (ícone → Configurações)." };
  try {
    const res = await fetch(serverUrl + path, {
      ...options,
      headers: { "X-API-Key": token, ...(options.body ? { "Content-Type": "application/json" } : {}) },
    });
    let data = null;
    try { data = await res.json(); } catch { /* corpo vazio */ }
    if (!res.ok) {
      const detail = data && data.detail ? (typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail)) : res.statusText;
      return { ok: false, error: res.status === 401 ? "Token inválido. Confira o arquivo data/api_token.txt." : detail };
    }
    return { ok: true, data };
  } catch (e) {
    return { ok: false, error: `Não consegui falar com o ClipForge em ${serverUrl}. O servidor está rodando? (python -m app)` };
  }
}

async function sendVideo(rawUrl) {
  const url = cfNormalizeUrl(rawUrl);
  if (!url) return { ok: false, error: "Esse link não é de um vídeo ou live do YouTube." };
  const r = await callApi("/api/sources", { method: "POST", body: JSON.stringify({ url }) });
  if (r.ok) r.duplicate = !!(r.data && r.data.duplicate);
  return r;
}

chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  if (msg.type === "send") { sendVideo(msg.url).then(sendResponse); return true; }
  if (msg.type === "health") {
    cfGetConfig().then(async ({ serverUrl }) => {
      try { const r = await fetch(serverUrl + "/api/health"); sendResponse({ ok: r.ok }); }
      catch { sendResponse({ ok: false }); }
    });
    return true;
  }
  if (msg.type === "badge") { chrome.action.setBadgeText({ text: msg.text || "" }); }
  return false;
});

chrome.runtime.onInstalled.addListener(() => {
  chrome.contextMenus.create({
    id: "clipforge-send", title: "Cortar com ClipForge", contexts: ["link", "page"],
    documentUrlPatterns: ["https://www.youtube.com/*", "https://m.youtube.com/*"],
  });
});

chrome.contextMenus.onClicked.addListener(async (info, tab) => {
  if (info.menuItemId !== "clipforge-send") return;
  const r = await sendVideo(info.linkUrl || info.pageUrl || (tab && tab.url) || "");
  chrome.action.setBadgeBackgroundColor({ color: r.ok ? "#16a34a" : "#dc2626" });
  chrome.action.setBadgeText({ text: r.ok ? "✓" : "!" });
  setTimeout(() => chrome.action.setBadgeText({ text: "" }), 3000);
});
