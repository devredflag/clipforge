// Utilidades compartilhadas (service worker, popup e content script).
const CF_DEFAULTS = { serverUrl: "http://localhost:8765", token: "" };

/** Reduz qualquer link do YouTube ao formato canônico https://www.youtube.com/watch?v=ID. Retorna null se não for vídeo/live. */
function cfNormalizeUrl(raw) {
  let u;
  try { u = new URL(String(raw).trim()); } catch { return null; }
  const host = u.hostname.replace(/^(www|m|music)\./, "");
  let id = null;
  if (host === "youtu.be") id = u.pathname.slice(1).split("/")[0];
  else if (host === "youtube.com") {
    if (u.pathname === "/watch") id = u.searchParams.get("v");
    else {
      const m = u.pathname.match(/^\/(?:live|shorts|embed)\/([\w-]{6,})/);
      if (m) id = m[1];
    }
  }
  return id && /^[\w-]{6,}$/.test(id) ? `https://www.youtube.com/watch?v=${id}` : null;
}

async function cfGetConfig() {
  const stored = await chrome.storage.local.get(CF_DEFAULTS);
  return { serverUrl: String(stored.serverUrl || CF_DEFAULTS.serverUrl).replace(/\/+$/, ""), token: stored.token || "" };
}

/** Pede ao service worker para enviar o link (assim o fetch não sofre restrições de CORS da página). */
function cfSend(url) {
  return chrome.runtime.sendMessage({ type: "send", url });
}
