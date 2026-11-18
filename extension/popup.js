const $ = (id) => document.getElementById(id);

function say(text, ok) {
  const m = $("msg");
  m.textContent = text;
  m.className = "msg " + (ok ? "ok" : "bad");
}

async function checkHealth() {
  const r = await chrome.runtime.sendMessage({ type: "health" });
  $("status").textContent = r && r.ok ? "online" : "offline";
  $("status").className = "chip " + (r && r.ok ? "ok" : "bad");
}

async function sendMany(urls) {
  let sent = 0, dup = 0, last = "";
  for (const u of urls) {
    const r = await cfSend(u);
    if (r && r.ok) { r.duplicate ? dup++ : sent++; }
    else last = (r && r.error) || "Falha ao enviar.";
  }
  if (last) return say(last, false);
  say(`${sent} enviado(s)${dup ? `, ${dup} já estava(m) na fila` : ""}. Acompanhe no painel.`, true);
}

(async () => {
  const cfg = await cfGetConfig();
  $("serverUrl").value = cfg.serverUrl;
  $("token").value = cfg.token;
  if (!cfg.token) { $("cfg").hidden = false; say("Cole o token da API para começar.", false); }
  checkHealth();

  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  const current = tab && cfNormalizeUrl(tab.url || "");
  if (current) {
    $("current").hidden = false;
    $("currentUrl").textContent = (tab.title || "").replace(/ - YouTube$/, "") || current;
    $("sendCurrent").onclick = async () => { $("sendCurrent").disabled = true; await sendMany([current]); $("sendCurrent").disabled = false; };
  }

  $("sendLinks").onclick = async () => {
    const urls = $("links").value.split(/\s+/).filter(Boolean);
    if (!urls.length) return say("Cole ao menos um link.", false);
    $("sendLinks").disabled = true;
    await sendMany(urls);
    $("sendLinks").disabled = false;
    $("links").value = "";
  };

  $("openPanel").onclick = async (e) => {
    e.preventDefault();
    const c = await cfGetConfig();
    chrome.tabs.create({ url: c.serverUrl });
  };
  $("toggleCfg").onclick = (e) => { e.preventDefault(); $("cfg").hidden = !$("cfg").hidden; };

  $("save").onclick = async () => {
    let server = $("serverUrl").value.trim().replace(/\/+$/, "") || "http://localhost:8765";
    try { new URL(server); } catch { return say("Endereço inválido.", false); }
    const origin = new URL(server).origin + "/*";
    const isLocal = /^http:\/\/(localhost|127\.0\.0\.1)(:\d+)?$/.test(new URL(server).origin);
    if (!isLocal) {
      const granted = await chrome.permissions.request({ origins: [origin] });
      if (!granted) return say("Sem permissão para acessar esse servidor.", false);
    }
    await chrome.storage.local.set({ serverUrl: server, token: $("token").value.trim() });
    say("Configurações salvas.", true);
    checkHealth();
  };
})();
