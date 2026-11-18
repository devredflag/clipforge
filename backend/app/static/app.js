"use strict";
// Painel do ClipForge — JS puro, sem dependências. Conversa com /api/* usando o token guardado no navegador.

const $ = (sel, root = document) => root.querySelector(sel);
const el = (tag, attrs = {}, ...kids) => {
  const n = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "class") n.className = v;
    else if (k === "html") n.innerHTML = v;
    else if (k.startsWith("on")) n.addEventListener(k.slice(2), v);
    else if (v !== false && v != null) n.setAttribute(k, v === true ? "" : v);
  }
  for (const kid of kids.flat()) if (kid != null) n.append(kid.nodeType ? kid : document.createTextNode(String(kid)));
  return n;
};

// a janela do app (desktop) abre com ?token=…; guardamos e limpamos a URL para não deixá-lo à mostra
const _urlToken = new URLSearchParams(location.search).get("token");
if (_urlToken) {
  localStorage.setItem("clipforge_token", _urlToken);
  const u = new URL(location.href);
  u.searchParams.delete("token");
  history.replaceState(null, "", u.pathname + (u.search || "") + u.hash);
}
let TOKEN = localStorage.getItem("clipforge_token") || "";
let SETTINGS = null;
let currentTab = "dashboard";
let weekOffset = 0;

async function api(path, opts = {}) {
  const res = await fetch(path, {
    ...opts,
    headers: { "X-API-Key": TOKEN, ...(opts.body ? { "Content-Type": "application/json" } : {}), ...(opts.headers || {}) },
  });
  if (res.status === 401) { askToken(); throw new Error("Token inválido"); }
  if (!res.ok) {
    let detail = res.statusText;
    try { const j = await res.json(); detail = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail); } catch {}
    throw new Error(detail);
  }
  return res.json();
}
const post = (p, body) => api(p, { method: "POST", body: body ? JSON.stringify(body) : undefined });

function toast(msg, bad = false) {
  const t = el("div", { class: bad ? "bad" : "" }, msg);
  $("#toast").append(t);
  setTimeout(() => t.remove(), bad ? 7000 : 3500);
}
const guard = (fn) => async (...a) => { try { await fn(...a); } catch (e) { toast(e.message, true); } };

function askToken() {
  const dlg = $("#tokenDlg");
  if (!dlg.open) { $("#tokenInput").value = ""; dlg.showModal(); }
}
$("#tokenBtn").onclick = askToken;
$("#tokenForm").addEventListener("submit", () => {
  TOKEN = $("#tokenInput").value.trim();
  localStorage.setItem("clipforge_token", TOKEN);
  setTimeout(() => refresh(true), 50);
});

// ---------- rótulos ----------
const STATUS = {
  queued: ["Na fila", "info"], downloading: ["Baixando", "info"], transcribing: ["Transcrevendo", "info"],
  analyzing: ["Escolhendo trechos", "info"], rendering: ["Renderizando", "info"], recording: ["Ao vivo", "live"],
  done: ["Concluído", "ok"], failed: ["Falhou", "bad"], stopped: ["Interrompido", "warn"],
  ready: ["Aguardando", "warn"], approved: ["Aprovado", "ok"], rejected: ["Rejeitado", "bad"],
  scheduled: ["Agendado", "info"], publishing: ["Publicando", "info"], published: ["Publicado", "ok"],
  failed_post: ["Falhou", "bad"], cancelled: ["Cancelado", "warn"],
};
const chip = (status, cls = "") => {
  const [t, c] = STATUS[status] || [status, ""];
  return el("span", { class: `chip ${c} ${cls}` }, t);
};
const PLAT = { youtube: "YouTube Shorts", tiktok: "TikTok" };
const PLAT_SHORT = { youtube: "YouTube", tiktok: "TikTok" };
const partLabel = () => (SETTINGS && SETTINGS.part_label) || "Parte";

const fmtDateTime = (iso) => {
  try { return new Date(iso).toLocaleString("pt-BR", { timeZone: SETTINGS?.timezone, dateStyle: "short", timeStyle: "short" }); }
  catch { return new Date(iso).toLocaleString("pt-BR"); }
};
const fmtTime = (iso) => {
  try { return new Date(iso).toLocaleTimeString("pt-BR", { timeZone: SETTINGS?.timezone, hour: "2-digit", minute: "2-digit" }); }
  catch { return ""; }
};
const nfmt = (n) => (n == null ? "—" : n.toLocaleString("pt-BR"));
const mediaUrl = (path) => `${path}?token=${encodeURIComponent(TOKEN)}`;
const ACTIVE = ["queued", "downloading", "transcribing", "analyzing", "rendering", "recording"];

function emptyState(icon, title, text) {
  return el("div", { class: "empty" }, el("div", { class: "big" }, icon), el("h3", {}, title), el("p", {}, text));
}

// ---------- Painel (avisos + métricas) ----------
const ALERT_ICON = { error: "⛔", warning: "⚠", info: "ℹ", ok: "✓" };
const ALERT_CLS = { error: "bad", warning: "warn", info: "info", ok: "ok" };
const PERF = {
  acima: ["Acima da média", "ok"], media: ["Na média", "info"],
  abaixo: ["Abaixo da média", "warn"], sem_dados: ["Sem métricas", "plain"],
};

async function renderDashboard() {
  const root = $("#tab-dashboard");
  const [alerts, m] = await Promise.all([api("/api/alerts"), api("/api/metrics")]);
  root.replaceChildren();

  // avisos
  root.append(el("div", { class: "section-head" }, el("h2", {}, "Avisos")));
  const al = el("div", { class: "alerts" });
  for (const a of alerts) {
    al.append(el("div", { class: `alert ${ALERT_CLS[a.level] || ""}`, ...(a.tab ? { onclick: () => switchTab(a.tab) } : {}) },
      el("span", { class: "alert-ic" }, ALERT_ICON[a.level] || "•"),
      el("div", {}, el("div", { class: "alert-title" }, a.title), a.detail ? el("div", { class: "alert-detail" }, a.detail) : null)));
  }
  root.append(al);

  // métricas
  root.append(el("div", { class: "section-head" },
    el("h2", {}, `Desempenho · últimos ${m.window_days} dias`),
    el("button", { class: "small", onclick: guard(async () => { toast("Atualizando métricas…"); await post("/api/metrics/refresh"); refresh(true); }) }, "Atualizar agora")));

  const platAvg = Object.entries(m.avg_views_by_platform || {})
    .filter(([, v]) => v != null).map(([p, v]) => `${PLAT_SHORT[p] || p}: ${nfmt(v)}`).join("  ·  ");
  const stat = (label, value, sub) => el("div", { class: "stat" },
    el("div", { class: "stat-val" }, value), el("div", { class: "stat-lbl" }, label), sub ? el("div", { class: "stat-sub" }, sub) : null);
  root.append(el("div", { class: "stats" },
    stat("Publicados no período", nfmt(m.published_count)),
    stat("Média de views", m.avg_views == null ? "—" : nfmt(m.avg_views), platAvg || null),
    stat("Total de views", nfmt(m.total_views)),
    stat("Com métricas", `${m.measured_count}/${m.published_count}`, m.measured_count < m.published_count ? "alguns sem dados ainda" : null)));

  // melhor / pior
  if (m.best) {
    const line = (tag, v) => el("div", { class: "hl" }, el("span", { class: "hl-tag" }, tag),
      el("span", { class: "hl-title" }, `${partLabel()} ${v.idx} — ${v.title}`),
      el("span", { class: "hl-views" }, `${nfmt(v.views)} views`));
    const box = el("div", { class: "card highlights" }, line("Melhor", m.best));
    if (m.worst && m.worst.post_id !== m.best.post_id) box.append(line("Pior", m.worst));
    root.append(box);
  }

  // tabela por vídeo
  root.append(el("div", { class: "section-head" }, el("h2", {}, "Por vídeo")));
  if (!m.videos.length) {
    root.append(emptyState("📊", "Nada publicado ainda", "Quando seus cortes forem ao ar, as views reais de cada um aparecem aqui."));
    return;
  }
  const rows = m.videos.map((v) => el("tr", {},
    el("td", {}, el("div", { class: "cellmain" }, `${partLabel()} ${v.idx} — ${v.title}`),
      el("div", { class: "cellsub" }, PLAT_SHORT[v.platform] || v.platform, " · ", fmtDateTime(v.published_at))),
    el("td", { class: "num" }, v.available ? nfmt(v.views) : el("span", { class: "muted", title: v.note || "" }, "sem dados")),
    el("td", { class: "num" }, v.available ? nfmt(v.likes) : "—"),
    el("td", { class: "num" }, v.available ? nfmt(v.comments) : "—"),
    el("td", {}, (() => { const [t, c] = PERF[v.performance] || ["—", "plain"]; return el("span", { class: `chip ${c}` }, t); })()),
    el("td", {}, v.url ? el("a", { href: v.url, target: "_blank", rel: "noopener" }, "abrir") : "")));
  root.append(el("div", { class: "card tablecard" }, el("table", {},
    el("thead", {}, el("tr", {}, ["Vídeo", "Views", "Curtidas", "Comentários", "Desempenho", ""].map((h) => el("th", {}, h)))),
    el("tbody", {}, rows))));
}

// ---------- Vídeos & lives ----------
function renderSources(list) {
  const root = $("#tab-sources");
  root.replaceChildren();
  if (!list.length) {
    root.append(emptyState("🎬", "Nenhum vídeo ainda", "Cole um link de vídeo ou live do YouTube no campo acima para gerar os primeiros cortes."));
    return;
  }
  for (const s of list) {
    const active = ACTIVE.includes(s.status);
    const [label] = STATUS[s.status] || [s.status];
    const thumb = el("div", { class: "thumb" },
      s.thumbnail ? el("img", { src: s.thumbnail, alt: "", referrerpolicy: "no-referrer", style: "width:100%;height:100%;object-fit:cover;border-radius:10px" })
                  : el("div", { class: "ph" }, "▸"));
    root.append(el("div", { class: "card src" }, thumb,
      el("div", { class: "body" },
        el("h4", { title: s.title || s.url }, s.title || s.url),
        el("div", { class: "meta" }, [s.channel, s.kind === "live" ? "transmissão ao vivo" : "vídeo", `${s.clip_count} corte(s)`].filter(Boolean).join("  ·  ")),
        el("div", { class: "row mt" }, chip(s.status), el("span", { class: "stagetext" }, s.stage_detail || label)),
        active && s.status !== "recording" ? el("div", { class: "bar" }, el("i", { style: `width:${Math.round(s.progress * 100)}%` })) : null,
        s.error ? el("div", { class: "err" }, s.error) : null,
        el("div", { class: "row mt" },
          active ? el("button", { class: "small", onclick: guard(async () => { await post(`/api/sources/${s.id}/stop`); toast(s.status === "recording" ? "Encerrando a live e cortando o restante…" : "Interrompendo…"); refresh(); }) }, s.status === "recording" ? "Encerrar live" : "Parar") : null,
          ["failed", "stopped"].includes(s.status) ? el("button", { class: "small", onclick: guard(async () => { await post(`/api/sources/${s.id}/retry`); refresh(); }) }, "Tentar de novo") : null,
          s.clip_count ? el("button", { class: "small accent", onclick: () => { $("#clipFilter").value = ""; switchTab("clips"); } }, `Ver cortes`) : null,
          el("button", { class: "small danger", onclick: guard(async () => { if (confirm("Remover esta fonte e todos os cortes dela?")) { await api(`/api/sources/${s.id}`, { method: "DELETE" }); refresh(); } }) }, "Remover")))));
  }
}

// ---------- Cortes ----------
function renderClips(list) {
  const grid = $("#clipGrid");
  const f = $("#clipFilter").value;
  const clips = list.filter((c) => !f || c.status === f);
  if (document.activeElement && document.activeElement.classList?.contains("title")) return; // não interrompe edição
  grid.replaceChildren();
  if (!clips.length) {
    grid.append(emptyState("✂", "Nenhum corte nesta visão", f ? "Troque o filtro acima para ver outros cortes." : "Assim que um vídeo terminar de processar, os cortes aparecem aqui."));
    return;
  }
  for (const c of clips) {
    const thumb = el("div", { class: "thumb", onclick: () => c.has_video && openPlayer(c) },
      c.has_video ? null : el("div", { class: "ph" }, "✂"),
      el("span", { class: "badge chip plain" }, `${partLabel()} ${c.idx}`),
      (() => { const q = Math.round(c.score * 100); const cl = c.score >= 0.7 ? "ok" : c.score >= 0.5 ? "warn" : "plain"; return el("span", { class: `score chip ${cl}` }, `${q}%`); })(),
      c.has_video ? el("div", { class: "play" }, el("span", {}, "▶")) : null);
    if (c.has_video) thumb.style.backgroundImage = `url('${mediaUrl(`/api/clips/${c.id}/thumb`)}')`;
    const title = el("input", { class: "title", value: c.title, onchange: guard(async (e) => { await api(`/api/clips/${c.id}`, { method: "PATCH", body: JSON.stringify({ title: e.target.value }) }); toast("Título salvo"); }) });
    grid.append(el("div", { class: "clip" }, thumb,
      el("div", { class: "info" }, title,
        el("div", { class: "subrow" }, chip(c.status), el("span", { class: "muted", style: "font-size:12px" }, `${c.duration}s`)),
        c.reason ? el("div", { class: "reason" }, c.reason) : null,
        c.posts.length ? el("div", { class: "plats" }, c.posts.map((p) => el("span", { class: `chip ${(STATUS[p.status] || ["", ""])[1]}`, title: p.error || "" }, `${PLAT_SHORT[p.platform] || p.platform}`))) : null,
        el("div", { class: "actions" },
          (c.status === "ready" || c.status === "rejected") ? el("button", { class: "small accent", onclick: guard(async () => { await post(`/api/clips/${c.id}/approve`); refresh(); }) }, "Aprovar") : null,
          c.status !== "rejected" ? el("button", { class: "small", onclick: guard(async () => { await post(`/api/clips/${c.id}/reject`); refresh(); }) }, "Rejeitar") : null,
          c.has_video ? el("a", { class: "small", style: "text-decoration:none", href: mediaUrl(`/api/clips/${c.id}/video`), download: "" }, "Baixar") : null,
          el("button", { class: "small danger", onclick: guard(async () => { if (confirm("Excluir este corte?")) { await api(`/api/clips/${c.id}`, { method: "DELETE" }); refresh(); } }) }, "Excluir")))));
  }
}
function openPlayer(c) {
  const v = $("#playerVideo");
  v.src = mediaUrl(`/api/clips/${c.id}/video`);
  $("#player").showModal();
  v.play().catch(() => {});
}
$("#playerClose").onclick = () => { $("#playerVideo").pause(); $("#player").close(); };
$("#clipFilter").onchange = () => refresh();

// ---------- Agenda (calendário semanal) ----------
function startOfWeek(offset) {
  const d = new Date(); d.setHours(0, 0, 0, 0);
  const dow = (d.getDay() + 6) % 7;            // 0 = segunda
  d.setDate(d.getDate() - dow + offset * 7);
  return d;
}
const DOW = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"];

function renderCalendar(posts) {
  const root = $("#tab-queue");
  root.replaceChildren();
  const start = startOfWeek(weekOffset);
  const days = Array.from({ length: 7 }, (_, i) => { const d = new Date(start); d.setDate(start.getDate() + i); return d; });
  const end = new Date(start); end.setDate(start.getDate() + 6);
  const todayKey = new Date().toDateString();

  const rangeLabel = `${start.toLocaleDateString("pt-BR", { day: "2-digit", month: "short" })} – ${end.toLocaleDateString("pt-BR", { day: "2-digit", month: "short" })}`;
  root.append(el("div", { class: "cal-head" },
    el("div", { class: "cal-nav" },
      el("button", { class: "small", onclick: () => { weekOffset--; renderCalendar(posts); } }, "‹"),
      el("button", { class: "small", onclick: () => { weekOffset = 0; refresh(true); } }, "Hoje"),
      el("button", { class: "small", onclick: () => { weekOffset++; renderCalendar(posts); } }, "›")),
    el("div", { class: "cal-range" }, rangeLabel),
    el("div", { class: "cal-legend" },
      el("span", { class: "chip info" }, "Agendado"), el("span", { class: "chip ok" }, "Publicado"), el("span", { class: "chip bad" }, "Falhou"))));

  const byDay = new Map(days.map((d) => [d.toDateString(), []]));
  for (const p of posts) {
    const when = p.status === "published" && p.published_at ? p.published_at : p.scheduled_at;
    const key = new Date(when).toDateString();
    if (byDay.has(key)) byDay.get(key).push({ ...p, when });
  }

  const grid = el("div", { class: "cal-grid" });
  for (const d of days) {
    const key = d.toDateString();
    const items = byDay.get(key).sort((a, b) => a.when.localeCompare(b.when));
    const col = el("div", { class: "cal-col" + (key === todayKey ? " today" : "") },
      el("div", { class: "cal-day" }, el("span", {}, DOW[(d.getDay() + 6) % 7]), el("b", {}, d.getDate())));
    const body = el("div", { class: "cal-body" });
    if (!items.length) body.append(el("div", { class: "cal-empty" }, "—"));
    for (const p of items) {
      const st = (STATUS[p.status] || ["", ""])[1];
      const ev = el("div", { class: `cal-ev ${st}`, title: p.error || "" },
        el("div", { class: "cal-ev-top" }, el("span", { class: "cal-time" }, fmtTime(p.when)), el("span", { class: "cal-plat" }, PLAT_SHORT[p.platform] || p.platform)),
        el("div", { class: "cal-ev-title" }, `${partLabel()} ${p.clip_idx} — ${p.clip_title}`));
      const acts = el("div", { class: "cal-ev-acts" });
      if (p.status === "scheduled") {
        acts.append(el("button", { class: "mini", onclick: guard(async () => { await post(`/api/posts/${p.id}/publish-now`); toast("Publicando…"); refresh(); }) }, "Publicar agora"));
        acts.append(el("button", { class: "mini danger", onclick: guard(async () => { await post(`/api/posts/${p.id}/cancel`); refresh(); }) }, "Cancelar"));
      } else if (p.status === "failed") {
        acts.append(el("button", { class: "mini", onclick: guard(async () => { await post(`/api/posts/${p.id}/retry`); refresh(); }) }, "Reagendar"));
      } else if (p.status === "published" && p.external_url) {
        acts.append(el("a", { class: "mini", href: p.external_url, target: "_blank", rel: "noopener" }, "abrir"));
      }
      if (acts.children.length) ev.append(acts);
      body.append(ev);
    }
    col.append(body);
    grid.append(col);
  }
  root.append(grid);

  const scheduled = posts.filter((p) => p.status === "scheduled").length;
  root.append(el("p", { class: "muted", style: "margin-top:14px" },
    scheduled ? `${scheduled} publicação(ões) agendada(s). Cada plataforma publica 1 corte por horário definido em Configurações.`
              : "Nada agendado. Conecte uma conta em Contas e aprove cortes para preencher a agenda."));
}

// ---------- Contas ----------
function renderAccounts(accs) {
  const root = $("#tab-accounts");
  root.replaceChildren();
  for (const a of accs) {
    const initials = a.platform === "youtube" ? "YT" : "TT";
    root.append(el("div", { class: "card" },
      el("div", { class: "acc-head" },
        el("div", { class: `acc-logo ${a.platform}` }, initials),
        el("div", {}, el("div", { class: "acc-name" }, PLAT[a.platform] || a.platform),
          el("div", { class: "acc-sub" }, a.connected ? `Conectado: ${a.display_name || ""}` : "Não conectado")),
        el("div", { class: "right" },
          a.connected ? el("span", { class: "chip ok" }, "Ativo") : el("span", { class: "chip warn" }, "Pendente"),
          a.connected ? el("button", { class: "small danger", onclick: guard(async () => { await api(`/api/accounts/${a.platform}`, { method: "DELETE" }); refresh(); }) }, "Desconectar") : null,
          el("button", { class: "primary", disabled: !a.configured, onclick: guard(async () => { const r = await post(`/api/auth/${a.platform}/start`); window.open(r.url, "_blank", "noopener"); toast("Conclua o login na nova aba e volte aqui."); }) }, a.connected ? "Reconectar" : "Conectar"))),
      (!a.configured && !a.connected) ? el("p", { class: "acc-note" }, `Para conectar, cadastre as chaves de API de ${PLAT_SHORT[a.platform]} no arquivo .env (veja o README, seção “Conectar YouTube e TikTok”).`) : null,
      !a.connected ? el("p", { class: "acc-note" }, "URL de redirecionamento para cadastrar no portal da plataforma: ", el("code", {}, a.redirect_uri)) : null));
  }
}

// ---------- Configurações ----------
const FIELDS = [
  ["Publicação diária", [
    ["timezone", "text", "Fuso horário", "Ex.: America/Sao_Paulo"],
    ["post_times", "list", "Horários de postagem", "HH:MM separados por vírgula. Cada plataforma publica 1 corte por horário, todo dia."],
    ["platforms", "multi:youtube,tiktok", "Plataformas ativas", ""],
    ["auto_approve", "bool", "Aprovar cortes automaticamente", "Desligado: você revisa cada corte antes de ir para a agenda."],
    ["part_label", "text", "Rótulo da parte", "“Parte” → Parte 1, Parte 2…"],
    ["hashtags", "list", "Hashtags", "Sem #, separadas por vírgula."],
    ["youtube_privacy", "select:public,unlisted,private", "Privacidade no YouTube", "Projetos Google sem auditoria publicam como privado, qualquer que seja a escolha."],
    ["tiktok_mode", "select:direct,inbox", "Modo do TikTok", "direct = publica no perfil · inbox = rascunho no app. Reconecte a conta ao mudar."],
    ["tiktok_privacy", "select:SELF_ONLY,FOLLOWER_OF_CREATOR,MUTUAL_FOLLOW_FRIENDS,PUBLIC_TO_EVERYONE", "Privacidade no TikTok", "Apps sem auditoria do TikTok só aceitam SELF_ONLY."],
  ]],
  ["Cortes", [
    ["clip_min_seconds", "number", "Duração mínima (s)", ""],
    ["clip_max_seconds", "number", "Duração máxima (s)", "Até 59 s para Shorts clássicos; o YouTube aceita até 3 min."],
    ["max_clips_per_source", "number", "Máximo de cortes por vídeo", ""],
    ["min_score", "number", "Nota mínima (0 a 1)", "Mais alto = menos cortes, porém mais fortes."],
    ["layout", "select:blur,fill", "Enquadramento", "blur = vídeo inteiro com fundo desfocado · fill = corta no centro."],
    ["normalize_audio", "bool", "Normalizar volume", ""],
  ]],
  ["Legendas", [
    ["caption_font", "text", "Fonte", "Precisa estar instalada no computador."],
    ["caption_size", "number", "Tamanho", ""],
    ["caption_uppercase", "bool", "Maiúsculas", ""],
    ["caption_color", "text", "Cor (RRGGBB)", ""],
    ["caption_highlight", "text", "Cor da palavra falada (RRGGBB)", ""],
    ["show_part_badge", "bool", "Mostrar selo “Parte N” no vídeo", ""],
  ]],
  ["Transcrição e IA local", [
    ["whisper_model", "select:tiny,base,small,medium,large-v3", "Modelo do Whisper", "small é um bom equilíbrio; maior = mais preciso e mais lento."],
    ["whisper_device", "select:auto,cpu,cuda", "Dispositivo", ""],
    ["whisper_compute", "select:int8,float16,float32", "Precisão", "int8 para CPU; float16 para placa NVIDIA."],
    ["language", "text", "Idioma", "auto, pt, en, es…"],
    ["ollama_enabled", "bool", "Usar IA local (Ollama) para ranquear e titular", "Opcional e gratuito; precisa do Ollama rodando."],
    ["ollama_url", "text", "URL do Ollama", ""],
    ["ollama_model", "text", "Modelo do Ollama", "Ex.: qwen2.5:7b, llama3.1:8b"],
  ]],
  ["Lives", [
    ["live_delay_seconds", "number", "Atraso antes de cortar (s)", "Só corta o que terminou há pelo menos esse tempo — preserva o contexto."],
    ["live_chunk_seconds", "number", "Bloco de transcrição (s)", ""],
    ["live_min_score", "number", "Nota mínima nas lives (0 a 1)", ""],
  ]],
  ["Download", [
    ["max_height", "number", "Resolução máxima", "1080 é suficiente para vídeo vertical."],
    ["cookies_from_browser", "text", "Cookies do navegador", "Ex.: chrome — use se o YouTube pedir login."],
  ]],
];
function renderSettings() {
  const root = $("#tab-settings");
  if (root.contains(document.activeElement) && document.activeElement !== root) return;
  root.replaceChildren();
  const form = el("form", { class: "settings" });
  const inputs = {};
  for (const [group, fields] of FIELDS) {
    const fs = el("fieldset", {}, el("legend", {}, group));
    for (const [key, type, label, help] of fields) {
      const val = SETTINGS[key];
      let input;
      if (type === "bool") input = el("input", { type: "checkbox", checked: !!val });
      else if (type === "number") input = el("input", { type: "number", step: "any", value: val });
      else if (type === "list") input = el("input", { type: "text", value: (val || []).join(", ") });
      else if (type.startsWith("select:")) input = el("select", {}, type.slice(7).split(",").map((o) => el("option", { value: o, selected: o === val }, o)));
      else if (type.startsWith("multi:")) input = el("div", { class: "checks" }, type.slice(6).split(",").map((o) => el("label", {}, el("input", { type: "checkbox", value: o, checked: (val || []).includes(o) }), PLAT_SHORT[o] || o)));
      else input = el("input", { type: "text", value: val });
      inputs[key] = { type, input };
      const control = type === "bool" ? el("label", { class: "switch" }, input, "ativado") : el("div", { class: "control" }, input);
      fs.append(el("div", { class: "field" }, el("label", {}, label, help ? el("small", {}, help) : null), control));
    }
    form.append(fs);
  }
  form.append(el("div", { class: "savebar" }, el("button", { class: "primary", type: "submit" }, "Salvar configurações")));
  form.addEventListener("submit", guard(async (e) => {
    e.preventDefault();
    const out = {};
    for (const [key, { type, input }] of Object.entries(inputs)) {
      if (type === "bool") out[key] = input.checked;
      else if (type === "number") out[key] = Number(input.value);
      else if (type === "list") out[key] = input.value.split(",").map((s) => s.trim()).filter(Boolean);
      else if (type.startsWith("multi:")) out[key] = [...input.querySelectorAll("input:checked")].map((i) => i.value);
      else out[key] = input.value;
    }
    SETTINGS = await api("/api/settings", { method: "PUT", body: JSON.stringify(out) });
    toast("Configurações salvas");
    refresh(true);
  }));
  root.append(form);
}

// ---------- navegação ----------
const VIEWS = {
  dashboard: ["Painel", "Visão geral, avisos e desempenho dos seus cortes."],
  sources: ["Vídeos & lives", "Cole links do YouTube para gerar cortes legendados automaticamente."],
  clips: ["Cortes", "Revise, edite o título, aprove ou rejeite cada corte."],
  queue: ["Agenda", "Calendário das publicações da semana — gerencie o que vai ao ar."],
  accounts: ["Contas", "Conecte YouTube e TikTok para publicar automaticamente."],
  settings: ["Configurações", "Ajuste cortes, legendas, horários e o comportamento das lives."],
};
function switchTab(name) {
  currentTab = name;
  document.querySelectorAll("#tabs button").forEach((b) => b.classList.toggle("active", b.dataset.tab === name));
  document.querySelectorAll(".tab").forEach((t) => t.classList.toggle("active", t.id === `tab-${name}`));
  const [title, sub] = VIEWS[name] || ["", ""];
  $("#viewTitle").textContent = title; $("#viewSub").textContent = sub;
  const onSources = name === "sources";
  $("#addForm").style.display = onSources ? "" : "none";
  $("#addMsg").style.display = onSources ? "" : "none";
  refresh(true);
}
$("#tabs").addEventListener("click", (e) => { const b = e.target.closest("button"); if (b && b.dataset.tab) switchTab(b.dataset.tab); });

// ---------- atualização ----------
let busy = false;
async function refresh(force = false) {
  if (!TOKEN) { askToken(); return; }
  if (busy) return;
  busy = true;
  try {
    if (!SETTINGS) SETTINGS = await api("/api/settings");
    $("#conn").textContent = "online"; $("#conn").className = "chip ok";
    if (currentTab === "dashboard") await renderDashboard();
    else if (currentTab === "sources") renderSources(await api("/api/sources"));
    else if (currentTab === "clips") renderClips(await api("/api/clips"));
    else if (currentTab === "queue") renderCalendar(await api("/api/posts"));
    else if (currentTab === "accounts") { if (force || !$("#tab-accounts").children.length) renderAccounts(await api("/api/accounts")); }
    else if (currentTab === "settings") { if (force || !$("#tab-settings").children.length) renderSettings(); }
  } catch (e) {
    $("#conn").textContent = "offline"; $("#conn").className = "chip bad";
  } finally { busy = false; }
}

$("#startMode").addEventListener("change", () => {
  $("#startAt").hidden = $("#startMode").value !== "at";
  if (!$("#startAt").hidden) $("#startAt").focus();
});

// "1:30:00", "90:00" ou "45" → segundos; null se inválido
function parseTime(s) {
  const parts = s.trim().split(":");
  if (!parts.length || parts.length > 3 || parts.some((p) => !/^\d+$/.test(p))) return null;
  return parts.reduce((acc, p) => acc * 60 + Number(p), 0);
}

$("#addForm").addEventListener("submit", guard(async (e) => {
  e.preventDefault();
  const urls = $("#urls").value.split(/\s+/).map((s) => s.trim()).filter(Boolean);
  const mode = $("#startMode").value;
  const start_at = mode === "start" ? 0 : mode === "at" ? parseTime($("#startAt").value) : null;
  if (mode === "at" && start_at === null) { toast("Informe o ponto de início como hh:mm:ss (ex.: 1:30:00).", true); return; }
  let ok = 0, dup = 0;
  for (const url of urls) {
    try { const r = await post("/api/sources", { url, start_at }); r.duplicate ? dup++ : ok++; }
    catch (err) { toast(`${url}: ${err.message}`, true); }
  }
  $("#urls").value = "";
  const msg = $("#addMsg");
  if (ok || dup) { msg.textContent = `${ok} link(s) enviado(s)${dup ? `, ${dup} já na fila` : ""}. Vídeos são baixados e cortados; lives começam a ser gravadas e cortadas após o atraso configurado.`; msg.classList.add("show"); }
  refresh();
}));

// aceita ?url=... (a extensão pode abrir o painel já com o link)
const initial = new URLSearchParams(location.search).get("url");
if (initial) { $("#urls").value = initial; currentTab = "sources"; }

switchTab(currentTab);
setInterval(() => refresh(), 4000);
