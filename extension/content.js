// Injeta o botão "✂ Cortar" nas páginas de vídeo/live do YouTube (que é uma SPA: a página muda sem recarregar).
(() => {
  const BTN_ID = "clipforge-btn";

  function toast(text, bad) {
    let box = document.getElementById("clipforge-toast");
    if (!box) { box = document.createElement("div"); box.id = "clipforge-toast"; document.body.append(box); }
    box.textContent = text;
    box.className = bad ? "bad show" : "show";
    clearTimeout(box._t);
    box._t = setTimeout(() => box.classList.remove("show"), 4500);
  }

  async function onClick(ev) {
    ev.preventDefault();
    ev.stopPropagation();
    const btn = ev.currentTarget;
    btn.disabled = true;
    const r = await cfSend(location.href);
    btn.disabled = false;
    if (!r || !r.ok) return toast((r && r.error) || "Falha ao enviar.", true);
    toast(r.duplicate ? "Esse vídeo já está sendo processado no ClipForge." : "Enviado ao ClipForge! Acompanhe no painel.");
  }

  function ensureButton() {
    const onWatch = !!cfNormalizeUrl(location.href);
    const existing = document.getElementById(BTN_ID);
    if (!onWatch) { if (existing) existing.remove(); return; }
    if (existing && document.contains(existing)) return;
    // contêiner de ações abaixo do título (layout atual e mobile)
    const host = document.querySelector("ytd-watch-metadata #top-level-buttons-computed, ytd-watch-metadata #actions, #actions-inner, .slim-video-action-bar-actions");
    if (!host) return;
    const btn = document.createElement("button");
    btn.id = BTN_ID;
    btn.type = "button";
    btn.textContent = "✂ Cortar com ClipForge";
    btn.title = "Gerar cortes legendados deste vídeo";
    btn.addEventListener("click", onClick);
    host.prepend(btn);
  }

  const obs = new MutationObserver(() => ensureButton());
  obs.observe(document.documentElement, { childList: true, subtree: true });
  window.addEventListener("yt-navigate-finish", ensureButton);
  ensureButton();
})();
