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
  for (const kid of kids.flat()) if (kid != null && kid !== false) n.append(kid.nodeType ? kid : document.createTextNode(String(kid)));
  return n;
};

// ---------- ícones (traço, estilo Lucide) ----------
const SVG = (inner, fill = false) =>
  `<svg viewBox="0 0 24 24" fill="${fill ? "currentColor" : "none"}" stroke="${fill ? "none" : "currentColor"}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${inner}</svg>`;
const ICONS = {
  home: SVG('<path d="M3 10.5 12 3l9 7.5"/><path d="M5 9.5V21h14V9.5"/>'),
  video: SVG('<rect x="3" y="5" width="18" height="14" rx="2"/><path d="m10 9 5 3-5 3z"/>'),
  scissors: SVG('<circle cx="6" cy="6" r="3"/><circle cx="6" cy="18" r="3"/><path d="M20 4 8.1 15.9M14.5 14.5 20 20M8.1 8.1 12 12"/>'),
  calendar: SVG('<rect x="3" y="4" width="18" height="18" rx="2"/><path d="M16 2v4M8 2v4M3 10h18"/>'),
  layers: SVG('<path d="m12 2 10 5-10 5L2 7z"/><path d="m2 12 10 5 10-5"/><path d="m2 17 10 5 10-5"/>'),
  gear: SVG('<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1A1.7 1.7 0 0 0 9 19.4a1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1A1.7 1.7 0 0 0 4.7 15a1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1A1.7 1.7 0 0 0 4.6 9a1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1A1.7 1.7 0 0 0 9 4.7a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8 1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z"/>'),
  key: SVG('<circle cx="7.5" cy="15.5" r="4.5"/><path d="m10.7 12.3 9.3-9.3M17 6l3 3M14 9l2 2"/>'),
  youtube: '<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="1.5" y="5" width="21" height="14" rx="4" fill="currentColor"/><path d="m10 9 5.2 3-5.2 3z" fill="#fff"/></svg>',
  tiktok: SVG('<path d="M16.6 3c.4 2.3 1.9 3.9 4.4 4.1v3.1c-1.6.1-3.1-.4-4.4-1.3v6.4c0 3.5-2.6 5.7-5.7 5.7a5.6 5.6 0 0 1-5.6-5.6c0-3.4 3-6 6.6-5.5v3.2c-1.7-.4-3.4.6-3.4 2.3 0 1.4 1.1 2.4 2.4 2.4 1.5 0 2.5-1 2.5-2.8V3z"/>', true),
  sparkles: SVG('<path d="M12 3l1.8 4.7 4.7 1.8-4.7 1.8L12 16l-1.8-4.7-4.7-1.8 4.7-1.8z"/><path d="M19 15l.8 2.2 2.2.8-2.2.8L19 21l-.8-2.2-2.2-.8 2.2-.8z"/>'),
  upload: SVG('<path d="M16 16.5h1.5a4.5 4.5 0 0 0 .4-9A6 6 0 0 0 6.3 9 4 4 0 0 0 6.5 16.5H8"/><path d="M12 12v9M8.5 15.5 12 12l3.5 3.5"/>'),
  file: SVG('<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6"/>'),
  search: SVG('<circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/>'),
  bolt: SVG('<path d="M13 2 4 14h7l-1 8 9-12h-7z"/>'),
  refresh: SVG('<path d="M21 12a9 9 0 0 1-15.5 6.3L3 16"/><path d="M3 12A9 9 0 0 1 18.5 5.7L21 8"/><path d="M21 3v5h-5M3 21v-5h5"/>'),
  eye: SVG('<path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/>'),
  film: SVG('<rect x="3" y="3" width="18" height="18" rx="2"/><path d="M7 3v18M17 3v18M3 8h4M3 16h4M17 8h4M17 16h4M3 12h18"/>'),
  chart: SVG('<path d="M5 20v-6M10 20V9M15 20v-9M20 20V4"/>'),
  trophy: SVG('<path d="M8 21h8M12 17v4M7 4h10v5a5 5 0 0 1-10 0z"/><path d="M17 5h3v2a3 3 0 0 1-3 3M7 5H4v2a3 3 0 0 0 3 3"/>'),
  trendDown: SVG('<path d="m22 17-8.5-8.5-5 5L2 7"/><path d="M16 17h6v-6"/>'),
  play: SVG('<path d="M7 4v16l13-8z"/>', true),
  clock: SVG('<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>'),
  check: SVG('<path d="m5 12 5 5L20 7"/>'),
  checkCircle: SVG('<circle cx="12" cy="12" r="9"/><path d="m8 12 3 3 5-6"/>'),
  x: SVG('<path d="M18 6 6 18M6 6l12 12"/>'),
  pencil: SVG('<path d="M17 3a2.8 2.8 0 0 1 4 4L7.5 20.5 2 22l1.5-5.5z"/>'),
  trash: SVG('<path d="M3 6h18M8 6V4h8v2M19 6l-1 14H6L5 6"/>'),
  stop: SVG('<rect x="6" y="6" width="12" height="12" rx="1.5"/>', true),
  alert: SVG('<path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z"/><path d="M12 9v4M12 17h.01"/>'),
  info: SVG('<circle cx="12" cy="12" r="9"/><path d="M12 16v-4M12 8h.01"/>'),
  radio: SVG('<circle cx="12" cy="12" r="2"/><path d="M16.2 7.8a6 6 0 0 1 0 8.4M7.8 16.2a6 6 0 0 1 0-8.4M19.1 4.9a10 10 0 0 1 0 14.2M4.9 19.1a10 10 0 0 1 0-14.2"/>'),
  type: SVG('<path d="M4 7V4h16v3M9 20h6M12 4v16"/>'),
  download: SVG('<path d="M12 3v12M7 10l5 5 5-5M5 21h14"/>'),
  copy: SVG('<rect x="9" y="9" width="12" height="12" rx="2"/><path d="M5 15H4a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1h10a1 1 0 0 1 1 1v1"/>'),
  external: SVG('<path d="M15 3h6v6M10 14 21 3M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/>'),
  save: SVG('<path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z"/><path d="M17 21v-8H7v8M7 3v5h8"/>'),
  plus: SVG('<path d="M12 5v14M5 12h14"/>'),
  chevL: SVG('<path d="m15 18-6-6 6-6"/>'),
  chevR: SVG('<path d="m9 18 6-6-6-6"/>'),
  user: SVG('<circle cx="12" cy="8" r="4"/><path d="M4 21a8 8 0 0 1 16 0"/>'),
};
const icon = (name, cls = "") => el("span", { class: `ic ${cls}`, html: ICONS[name] || "" });
document.querySelectorAll("[data-icon]").forEach((n) => { n.innerHTML = ICONS[n.dataset.icon] || ""; });

// ---------- token ----------
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
let PERIOD = 30;
let lastDash = 0;
let clipSourceSel = "";

async function api(path, opts = {}) {
  const res = await fetch(path, {
    ...opts,
    headers: { "X-API-Key": TOKEN, ...(opts.body ? { "Content-Type": "application/json" } : {}), ...(opts.headers || {}) },
  });
  if (res.status === 401) { askToken(); throw new Error("Token inválido"); }
  if (!res.ok) {
    let detail = res.statusText;
    try { const j = await res.json(); detail = typeof j.detail === "string" ? j.detail : (j.detail?.[0]?.msg || JSON.stringify(j.detail)); } catch {}
    throw new Error(detail);
  }
  return res.json();
}
const post = (p, body) => api(p, { method: "POST", body: body ? JSON.stringify(body) : undefined });
const putSettings = async (patch) => { SETTINGS = await api("/api/settings", { method: "PUT", body: JSON.stringify(patch) }); return SETTINGS; };

function toast(msg, bad = false) {
  const t = el("div", { class: bad ? "bad" : "" }, msg);
  $("#toast").append(t);
  setTimeout(() => t.remove(), bad ? 7000 : 4000);
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

// ---------- rótulos e formatos ----------
const STATUS = {
  queued: ["Na fila", "warn"], downloading: ["Baixando", "info"], transcribing: ["Transcrevendo", "info"],
  analyzing: ["Escolhendo trechos", "info"], rendering: ["Renderizando", "info"], recording: ["Ao vivo", "live"],
  done: ["Concluído", "ok"], failed: ["Falhou", "bad"], stopped: ["Interrompido", "warn"],
  ready: ["Aguardando aprovação", "warn"], approved: ["Aprovado", "ok"], rejected: ["Rejeitado", "bad"],
  scheduled: ["Agendado", "info"], publishing: ["Publicando", "info"], published: ["Publicado", "ok"], cancelled: ["Cancelado", "warn"],
};
const chip = (status) => { const [t, c] = STATUS[status] || [status, ""]; return el("span", { class: `chip dot ${c}` }, t); };
const PLAT = { youtube: "YouTube Shorts", tiktok: "TikTok" };
const PLAT_SHORT = { youtube: "YouTube", tiktok: "TikTok" };
const platChip = (p, status) => el("span", { class: `plat ${p}${status ? ` st-${status}` : ""}`, title: status ? (STATUS[status] || [status])[0] : "" }, icon(p), PLAT_SHORT[p] || p);
const partLabel = () => (SETTINGS && SETTINGS.part_label) || "Parte";

const tzOpt = () => (SETTINGS?.timezone ? { timeZone: SETTINGS.timezone } : {});
const fmtDateTime = (iso) => {
  try { return new Date(iso).toLocaleString("pt-BR", { ...tzOpt(), day: "2-digit", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" }); }
  catch { return new Date(iso).toLocaleString("pt-BR"); }
};
const fmtTime = (iso) => {
  try { return new Date(iso).toLocaleTimeString("pt-BR", { ...tzOpt(), hour: "2-digit", minute: "2-digit" }); }
  catch { return ""; }
};
const nfmt = (n) => (n == null ? "—" : Number(n).toLocaleString("pt-BR"));
const fmtDur = (s) => {
  if (s == null || isNaN(s)) return "";
  s = Math.round(s);
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), sec = s % 60;
  const p = (n) => String(n).padStart(2, "0");
  return h ? `${h}:${p(m)}:${p(sec)}` : `${p(m)}:${p(sec)}`;
};
const fmtBytes = (b) => {
  if (!b) return "0 MB";
  const u = ["B", "KB", "MB", "GB", "TB"]; let i = 0;
  while (b >= 1024 && i < u.length - 1) { b /= 1024; i++; }
  return `${b.toLocaleString("pt-BR", { maximumFractionDigits: i >= 3 ? 1 : 0 })} ${u[i]}`;
};
const mediaUrl = (path) => `${path}?token=${encodeURIComponent(TOKEN)}`;
const ACTIVE = ["queued", "downloading", "transcribing", "analyzing", "rendering", "recording"];
const dayKey = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;

function emptyState(ic, title, text) {
  return el("div", { class: "empty" }, icon(ic, "big"), el("h3", {}, title), el("p", {}, text));
}
function setTopActions(...nodes) { $("#topActions").replaceChildren(...nodes); }

// ---------- Painel ----------
const ALERT = { error: ["alert", "bad"], warning: ["alert", "warn"], info: ["info", ""], ok: ["checkCircle", ""] };
const PERF = {
  acima: ["Acima da média", "ok"], media: ["Na média", "accent"],
  abaixo: ["Abaixo da média", "bad"], sem_dados: ["Sem métricas", ""],
};

function delta(cur, prev) {
  if (cur == null || !prev) return null;
  const pct = Math.round(((cur - prev) / prev) * 100);
  return el("span", { class: `delta ${pct >= 0 ? "up" : "down"}` }, `${pct >= 0 ? "↑ +" : "↓ "}${pct}%`);
}

async function renderDashboard() {
  const root = $("#tab-dashboard");
  const [alerts, m, m2, ready, scheduled] = await Promise.all([
    api("/api/alerts"), api(`/api/metrics?window_days=${PERIOD}`), api(`/api/metrics?window_days=${PERIOD * 2}`),
    api("/api/clips?status=ready"), api("/api/posts?status=scheduled"),
  ]);
  const kids = [];

  // destaques + avisos do sistema
  const banners = el("div", { class: "banners" });
  const banner = (ic, title, sub, linkText, tab, cls = "") => el("div", { class: `banner ${cls}` }, icon(ic),
    el("div", {}, el("b", {}, title), sub ? el("span", { class: "muted" }, sub) : null),
    tab ? el("button", { class: "link", onclick: () => { if (tab === "clips") $("#clipFilter").value = "ready"; switchTab(tab); } }, `${linkText} →`) : null);
  if (ready.length) banners.append(banner("bolt", `${ready.length} corte(s) prontos para publicar`, "Cortes finalizados aguardando sua aprovação.", "Ver cortes", "clips"));
  const today = dayKey(new Date());
  const todayCount = scheduled.filter((p) => dayKey(new Date(p.scheduled_at)) === today).length;
  if (todayCount) banners.append(banner("calendar", `${todayCount} publicação(ões) na agenda hoje`, "Seus vídeos serão publicados automaticamente.", "Ver agenda", "queue"));
  for (const a of alerts) {
    const [ic, cls] = ALERT[a.level] || ["info", ""];
    banners.append(banner(ic, a.title, a.detail, "Abrir", a.tab, cls));
  }
  if (banners.children.length) kids.push(banners);

  // indicadores, comparados ao período anterior de mesmo tamanho
  const prev = { pub: m2.published_count - m.published_count, total: m2.total_views - m.total_views, measured: m2.measured_count - m.measured_count };
  const prevAvg = prev.measured ? prev.total / prev.measured : null;
  const kpi = (ic, label, value, d, sub, title) => el("div", { class: "kpi", title: title || "" },
    el("div", { class: "kpi-head" }, icon(ic), label), el("div", { class: "kpi-val" }, value, d), el("div", { class: "kpi-sub" }, sub));
  const pctMeasured = m.published_count ? Math.round((m.measured_count / m.published_count) * 100) : 0;
  kids.push(el("div", { class: "kpis" },
    kpi("film", "Publicados", nfmt(m.published_count), delta(m.published_count, prev.pub), `vs. ${PERIOD} dias anteriores`),
    kpi("eye", "Média de views", m.avg_views == null ? "—" : nfmt(m.avg_views), delta(m.avg_views, prevAvg), "por vídeo publicado"),
    kpi("chart", "Total de views", nfmt(m.total_views), delta(m.total_views, prev.total), "no período"),
    kpi("chart", "Vídeos com métricas", nfmt(m.measured_count), null, `${pctMeasured}% do total`,
      "Nem toda conta fornece métricas (ex.: TikTok sem permissão de leitura).")));

  // gráfico + melhores/piores
  const chartBox = el("div", { class: "chart" });
  const measured = m.videos.filter((v) => v.available && v.views != null);
  const chartCard = el("div", { class: "card" },
    el("div", { class: "chart-head" },
      el("div", {}, el("div", { class: "card-title" }, `Desempenho (últimos ${PERIOD} dias)`),
        el("div", { class: "card-sub" }, "Views dos cortes, somadas pelo dia em que foram publicados.")),
      el("span", { class: "pill" }, icon("eye"), `${nfmt(m.total_views)} views`, delta(m.total_views, prev.total))),
    measured.length ? chartBox : emptyState("chart", "Sem views ainda", "Quando seus cortes publicados tiverem métricas, a evolução aparece aqui."));

  const rankList = (items, cls) => items.map((v, i) => el("div", { class: "rank-row" },
    el("span", { class: "n" }, i + 1), el("span", { class: "t", title: v.title }, `${partLabel()} ${v.idx} — ${v.title}`),
    el("span", { class: `v ${cls}` }, `${nfmt(v.views)} views`)));
  const sorted = [...measured].sort((a, b) => b.views - a.views);
  const rank = el("div", { class: "card rank" },
    el("div", { class: "card-title" }, "Melhores e piores cortes"), el("div", { class: "card-sub" }, "Com base em views no período selecionado."));
  if (!sorted.length) rank.append(el("p", { class: "muted" }, "Ainda sem cortes com métricas."));
  else {
    rank.append(el("h4", {}, icon("trophy"), "Melhores cortes"), ...rankList(sorted.slice(0, 3), "good"));
    if (sorted.length > 3) rank.append(el("h4", {}, icon("trendDown"), "Piores cortes"), ...rankList(sorted.slice(-3).reverse(), "poor"));
  }
  kids.push(el("div", { class: "dash-row" }, chartCard, rank));

  // vídeos recentes
  const table = el("div", { class: "card tablecard", style: "margin-top:14px" },
    el("div", { class: "card-head" }, el("div", {}, el("div", { class: "card-title" }, "Vídeos recentes"),
      el("div", { class: "card-sub" }, "Seus últimos cortes publicados e o desempenho de cada um.")),
      el("button", { class: "small", onclick: guard(async () => { toast("Atualizando métricas…"); await post("/api/metrics/refresh"); lastDash = 0; refresh(true); }) }, icon("refresh"), "Atualizar métricas")));
  if (!m.videos.length) table.append(el("div", { style: "padding:0 20px 20px" }, emptyState("film", "Nada publicado ainda", "Quando seus cortes forem ao ar, as views reais de cada um aparecem aqui.")));
  else table.append(el("div", { class: "table-wrap" }, el("table", {},
    el("thead", {}, el("tr", {}, ["Vídeo / Corte", "Plataforma", "Publicado em", "Views", "Curtidas", "Comentários", "Status", ""].map((h) => el("th", {}, h)))),
    el("tbody", {}, m.videos.slice(0, 10).map((v) => {
      const [t, c] = PERF[v.performance] || ["—", ""];
      return el("tr", {},
        el("td", {}, el("div", { class: "cellmain" }, `${partLabel()} ${v.idx} — ${v.title}`)),
        el("td", {}, platChip(v.platform)),
        el("td", {}, fmtDateTime(v.published_at)),
        el("td", { class: "num" }, v.available ? nfmt(v.views) : el("span", { class: "muted", title: v.note || "" }, "sem dados")),
        el("td", { class: "num" }, v.available ? nfmt(v.likes) : "—"),
        el("td", { class: "num" }, v.available ? nfmt(v.comments) : "—"),
        el("td", {}, el("span", { class: `chip ${c}` }, icon("chart"), t)),
        el("td", {}, v.url ? el("a", { href: v.url, target: "_blank", rel: "noopener", title: "Abrir na plataforma" }, icon("external")) : ""));
    })))));
  kids.push(table);

  root.replaceChildren(...kids);
  if (measured.length) drawChart(chartBox, dailyViews(measured));
}

function dailyViews(videos) {
  const end = new Date(); end.setHours(0, 0, 0, 0);
  const days = Array.from({ length: PERIOD }, (_, i) => { const d = new Date(end); d.setDate(end.getDate() - (PERIOD - 1 - i)); return d; });
  const sums = new Map(days.map((d) => [dayKey(d), 0]));
  for (const v of videos) { const k = dayKey(new Date(v.published_at)); if (sums.has(k)) sums.set(k, sums.get(k) + v.views); }
  return days.map((d) => ({ date: d, value: sums.get(dayKey(d)) }));
}

function niceMax(v) {
  if (v <= 0) return 1;
  const p = 10 ** Math.floor(Math.log10(v));
  return [1, 2, 2.5, 5, 10].map((k) => k * p).find((x) => x >= v);
}

// gráfico de área com cruz de leitura (hover) — SVG puro
function drawChart(box, pts) {
  const W = Math.max(320, box.clientWidth || 700), H = 240, L = 54, R = 12, T = 10, B = 26;
  const max = niceMax(Math.max(...pts.map((p) => p.value)));
  const n = pts.length;
  const x = (i) => L + (n === 1 ? (W - L - R) / 2 : (i * (W - L - R)) / (n - 1));
  const y = (v) => T + (1 - v / max) * (H - T - B);
  const NS = "http://www.w3.org/2000/svg";
  const s = (tag, attrs) => { const e = document.createElementNS(NS, tag); for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v); return e; };
  const svg = s("svg", { viewBox: `0 0 ${W} ${H}`, width: W, height: H, role: "img",
    "aria-label": `Views por dia: total ${nfmt(pts.reduce((a, p) => a + p.value, 0))}` });
  const defs = s("defs", {});
  const grad = s("linearGradient", { id: "areaGrad", x1: 0, y1: 0, x2: 0, y2: 1 });
  grad.append(s("stop", { offset: "0", "stop-color": "#FFC928", "stop-opacity": ".45" }), s("stop", { offset: "1", "stop-color": "#FFC928", "stop-opacity": "0" }));
  defs.append(grad); svg.append(defs);
  for (let i = 0; i <= 4; i++) {
    const v = (max * i) / 4, yy = y(v);
    svg.append(s("line", { x1: L, x2: W - R, y1: yy, y2: yy, class: "grid-line" }));
    const t = s("text", { x: L - 8, y: yy + 4, "text-anchor": "end", class: "axis-label" }); t.textContent = nfmt(Math.round(v)); svg.append(t);
  }
  const step = Math.max(1, Math.ceil(n / 9));
  pts.forEach((p, i) => {
    if (i % step) return;
    const t = s("text", { x: x(i), y: H - 6, "text-anchor": "middle", class: "axis-label" });
    t.textContent = p.date.toLocaleDateString("pt-BR", { day: "numeric", month: "short" }).replace(".", ""); svg.append(t);
  });
  const line = pts.map((p, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(p.value).toFixed(1)}`).join("");
  svg.append(s("path", { d: `${line}L${x(n - 1)},${y(0)}L${x(0)},${y(0)}Z`, fill: "url(#areaGrad)" }));
  svg.append(s("path", { d: line, fill: "none", stroke: "#FFC928", "stroke-width": 2, "stroke-linejoin": "round" }));
  pts.forEach((p, i) => { if (p.value) svg.append(s("circle", { cx: x(i), cy: y(p.value), r: 4, fill: "#FFC928", stroke: "#111317", "stroke-width": 2 })); });
  const cross = s("line", { y1: T, y2: H - B, stroke: "#9ca3af", "stroke-width": 1, visibility: "hidden" });
  const dot = s("circle", { r: 5, fill: "#FFC928", stroke: "#fff", "stroke-width": 2, visibility: "hidden" });
  const hit = s("rect", { x: L, y: T, width: W - L - R, height: H - T - B, fill: "transparent" });
  svg.append(cross, dot, hit);
  const tip = el("div", { class: "tip", hidden: true });
  hit.addEventListener("mousemove", (e) => {
    const r = svg.getBoundingClientRect();
    const px = ((e.clientX - r.left) / r.width) * W;
    const i = Math.max(0, Math.min(n - 1, Math.round(((px - L) / (W - L - R)) * (n - 1))));
    const p = pts[i];
    cross.setAttribute("x1", x(i)); cross.setAttribute("x2", x(i)); cross.setAttribute("visibility", "visible");
    dot.setAttribute("cx", x(i)); dot.setAttribute("cy", y(p.value)); dot.setAttribute("visibility", "visible");
    tip.hidden = false;
    tip.style.left = `${(x(i) / W) * 100}%`; tip.style.top = `${(y(p.value) / H) * 100}%`;
    tip.replaceChildren(el("b", {}, `${nfmt(p.value)} views`), el("div", { class: "muted" }, p.date.toLocaleDateString("pt-BR", { weekday: "short", day: "2-digit", month: "short" })));
  });
  hit.addEventListener("mouseleave", () => { cross.setAttribute("visibility", "hidden"); dot.setAttribute("visibility", "hidden"); tip.hidden = true; });
  box.replaceChildren(svg, tip);
}

// ---------- Vídeos & lives ----------
function sourceState(s) {
  const pct = Math.round((s.progress || 0) * 100);
  if (s.status === "recording") return el("div", { class: "state live" }, el("div", { class: "state-head" }, el("span", { class: "chip live" }, "Gravando ao vivo")), el("small", {}, s.stage_detail || "Cortando conforme a live acontece"));
  if (s.status === "queued") return el("div", { class: "state warn" }, el("div", { class: "state-head" }, el("span", { style: "display:flex;gap:7px;align-items:center" }, icon("clock"), "Na fila")), el("small", {}, s.stage_detail || "Aguardando processamento…"));
  if (ACTIVE.includes(s.status)) return el("div", { class: "state run" },
    el("div", { class: "state-head" }, el("span", { style: "display:flex;gap:7px;align-items:center" }, icon("refresh", "spin"), "Processando…"), el("span", {}, `${pct}%`)),
    el("span", { class: "bar" }, el("i", { style: `width:${pct}%` })), el("small", {}, s.stage_detail || (STATUS[s.status] || [s.status])[0]));
  if (s.status === "done") return el("div", { class: "state ok" }, el("div", { class: "state-head" }, el("span", { style: "display:flex;gap:7px;align-items:center" }, icon("checkCircle"), "Concluído")), el("small", {}, s.stage_detail || "Cortes gerados com sucesso."));
  if (s.status === "failed") return el("div", { class: "state bad" }, el("div", { class: "state-head" }, el("span", { style: "display:flex;gap:7px;align-items:center" }, icon("alert"), "Falhou")), el("small", {}, "Veja o erro abaixo."));
  return el("div", { class: "state warn" }, el("div", { class: "state-head" }, el("span", { style: "display:flex;gap:7px;align-items:center" }, icon("stop"), "Interrompido")), el("small", {}, s.stage_detail || ""));
}

function renderSources(list) {
  const root = $("#sourceList");
  if (!list.length) {
    root.replaceChildren(emptyState("video", "Nenhum vídeo ainda", "Cole um link de vídeo ou live do YouTube acima, ou envie um arquivo do seu computador."));
    return;
  }
  root.replaceChildren(...list.map((s) => {
    const active = ACTIVE.includes(s.status);
    const isUpload = (s.url || "").startsWith("upload://");
    const thumb = el("div", { class: "thumb" }, s.thumbnail ? null : el("div", { class: "ph" }, icon(isUpload ? "file" : "video")),
      s.duration ? el("span", { class: "dur" }, fmtDur(s.duration)) : null);
    if (s.thumbnail) thumb.style.backgroundImage = `url('${s.thumbnail}')`;
    const kind = s.kind === "live" ? "Transmissão ao vivo" : isUpload ? "Arquivo enviado" : "Vídeo do YouTube";
    const startInfo = s.start_at === 0 ? " · desde o início" : s.start_at ? ` · a partir de ${fmtDur(s.start_at)}` : "";
    return el("div", { class: "src" }, thumb,
      el("div", {},
        el("h4", { title: s.title || s.url }, s.title || s.url),
        el("div", { class: "meta" }, icon(s.kind === "live" ? "radio" : isUpload ? "file" : "youtube"), s.channel || kind),
        (s.channel && s.channel !== kind) || startInfo ? el("div", { class: "meta" }, kind + startInfo) : null),
      sourceState(s),
      el("div", { class: "count" }, el("small", {}, icon("scissors"), "Cortes gerados"), el("b", {}, `${s.clip_count} corte${s.clip_count === 1 ? "" : "s"}`),
        el("small", { title: "Vídeo original/gravação + cortes, no seu disco" }, `Ocupa ${fmtBytes((s.original_bytes || 0) + (s.clips_bytes || 0))}`)),
      el("div", { class: "acts" },
        active ? el("button", { class: "ghost", onclick: guard(async () => { await post(`/api/sources/${s.id}/stop`); toast(s.status === "recording" ? "Encerrando a live e cortando o restante…" : "Interrompendo…"); refresh(); }) }, icon("stop"), s.status === "recording" ? "Encerrar live" : "Parar") : null,
        ["failed", "stopped"].includes(s.status) ? el("button", { class: "ghost", onclick: guard(async () => { await post(`/api/sources/${s.id}/retry`); refresh(); }) }, icon("refresh"), "Tentar de novo") : null,
        s.clip_count ? el("button", { class: "primary", onclick: () => { clipSourceSel = String(s.id); $("#clipFilter").value = ""; switchTab("clips"); } }, icon("play"), "Ver cortes") : null,
        !active && s.original_bytes > 0 ? el("button", { class: "ghost", title: "Apaga o vídeo original / gravação da live. Os cortes continuam.", onclick: guard(async () => {
          const extra = isUpload ? " O arquivo enviado não poderá ser reprocessado." : "";
          if (!confirm(`Apagar o vídeo original/gravação (${fmtBytes(s.original_bytes)})? Os ${s.clip_count} corte(s) continuam salvos.${extra}`)) return;
          const r = await post(`/api/sources/${s.id}/free-space`); toast(`${fmtBytes(r.freed_bytes)} liberados.`); refresh();
        }) }, `Liberar ${fmtBytes(s.original_bytes)}`) : null,
        el("button", { class: "iconbtn", title: "Remover vídeo e todos os cortes", "aria-label": "Remover vídeo e todos os cortes", onclick: guard(async () => { if (confirm(`Remover este vídeo e todos os ${s.clip_count} corte(s)? Libera ${fmtBytes((s.original_bytes || 0) + (s.clips_bytes || 0))}.`)) { await api(`/api/sources/${s.id}`, { method: "DELETE" }); refresh(); } }) }, icon("trash"))),
      s.error ? el("div", { class: "err" }, s.error) : null);
  }));
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
  if (!urls.length) { toast("Cole um link do YouTube.", true); return; }
  const mode = $("#startMode").value;
  const start_at = mode === "start" ? 0 : mode === "at" ? parseTime($("#startAt").value) : null;
  if (mode === "at" && start_at === null) { toast("Informe o ponto de início como hh:mm:ss (ex.: 1:30:00).", true); return; }
  let ok = 0, dup = 0;
  for (const url of urls) {
    try { const r = await post("/api/sources", { url, start_at }); r.duplicate ? dup++ : ok++; }
    catch (err) { toast(`${url}: ${err.message}`, true); }
  }
  $("#urls").value = "";
  if (ok || dup) $("#addMsg").textContent = `${ok} link(s) enviado(s)${dup ? `, ${dup} já na fila` : ""}. Vídeos são baixados e cortados; lives começam a ser gravadas e cortadas após o atraso configurado.`;
  refresh();
}));

// envio de arquivo (arrastar e soltar ou clicar)
function uploadFile(file) {
  if (!file) return;
  const okExt = /\.(mp4|mov|mkv|webm|avi|m4v)$/i.test(file.name);
  if (!okExt) { toast("Envie um vídeo MP4, MOV, MKV, WEBM ou AVI.", true); return; }
  if (file.size > 10 * 1024 ** 3) { toast("Arquivo maior que 10 GB.", true); return; }
  const bar = $("#uploadBar"), fill = bar.firstElementChild;
  bar.hidden = false; fill.style.width = "0%";
  const xhr = new XMLHttpRequest();
  xhr.open("POST", "/api/sources/upload");
  xhr.setRequestHeader("X-API-Key", TOKEN);
  xhr.upload.onprogress = (e) => { if (e.lengthComputable) fill.style.width = `${Math.round((e.loaded / e.total) * 100)}%`; };
  xhr.onload = () => {
    bar.hidden = true;
    if (xhr.status === 200) { toast(`“${file.name}” enviado. Os cortes começam a ser gerados.`); refresh(); return; }
    let msg = `Falha no envio (${xhr.status})`;
    try { msg = JSON.parse(xhr.responseText).detail || msg; } catch {}
    toast(msg, true);
  };
  xhr.onerror = () => { bar.hidden = true; toast("Falha de conexão durante o envio.", true); };
  const fd = new FormData(); fd.append("file", file);
  xhr.send(fd);
  toast(`Enviando “${file.name}”…`);
}
const dz = $("#dropzone");
$("#fileInput").addEventListener("change", (e) => { uploadFile(e.target.files[0]); e.target.value = ""; });
dz.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); $("#fileInput").click(); } });
["dragenter", "dragover"].forEach((t) => dz.addEventListener(t, (e) => { e.preventDefault(); dz.classList.add("over"); }));
["dragleave", "drop"].forEach((t) => dz.addEventListener(t, (e) => { e.preventDefault(); dz.classList.remove("over"); }));
dz.addEventListener("drop", (e) => uploadFile(e.dataTransfer.files[0]));

// ---------- Cortes ----------
function renderClips(list, sources) {
  const srcSel = $("#clipSource");
  if (clipSourceSel && srcSel.value !== clipSourceSel) srcSel.dataset.want = clipSourceSel;
  const want = srcSel.dataset.want || srcSel.value;
  srcSel.replaceChildren(el("option", { value: "" }, "Origem: Todas"),
    ...sources.filter((s) => s.clip_count).map((s) => el("option", { value: String(s.id) }, (s.title || s.url).slice(0, 60))));
  srcSel.value = want; delete srcSel.dataset.want; clipSourceSel = "";

  const f = $("#clipFilter").value, q = $("#clipSearch").value.trim().toLowerCase(), days = Number($("#clipPeriod").value || 0), src = srcSel.value;
  let since = 0;
  if (days === 1) { const d = new Date(); d.setHours(0, 0, 0, 0); since = d.getTime(); }
  else if (days) since = Date.now() - days * 86400000;
  const clips = list.filter((c) => (!f || c.status === f) && (!src || String(c.source_id) === src)
    && (!since || new Date(c.created_at).getTime() >= since)
    && (!q || `${c.title} ${c.description} ${c.reason}`.toLowerCase().includes(q)));
  $("#clipCount").textContent = `${clips.length} corte${clips.length === 1 ? "" : "s"} encontrado${clips.length === 1 ? "" : "s"}`;

  const grid = $("#clipGrid");
  if ($("#editDlg").open) return; // não atrapalha a edição
  if (!clips.length) {
    grid.replaceChildren(emptyState("scissors", "Nenhum corte nesta visão", f || q || src || days ? "Troque os filtros acima para ver outros cortes." : "Assim que um vídeo terminar de processar, os cortes aparecem aqui."));
    return;
  }
  grid.replaceChildren(...clips.map((c) => {
    const thumb = el("div", { class: `thumb${c.has_video ? " has" : ""}`, onclick: () => c.has_video && openPlayer(c), title: c.has_video ? "Assistir" : "" },
      el("span", { class: "tag part" }, `${partLabel()} ${c.idx}`),
      el("span", { class: "tag score" }, icon("bolt"), `Score: ${Math.round(c.score * 100)}`),
      el("span", { class: "tag dur" }, icon("clock"), fmtDur(c.duration)),
      c.has_video ? el("span", { class: "play" }, icon("play")) : null);
    if (c.has_video) thumb.style.backgroundImage = `url('${mediaUrl(`/api/clips/${c.id}/thumb`)}')`;
    const canApprove = c.status === "ready" || c.status === "rejected";
    return el("div", { class: "clip" }, thumb,
      el("div", { class: "info" },
        el("h4", {}, c.title),
        (c.description || c.reason) ? el("div", { class: "desc" }, c.description || c.reason) : null,
        el("div", { class: "status-line" }, chip(c.status),
          // um selo por plataforma, com o status do post mais recente dela
          el("div", { class: "plats" }, [...new Map([...c.posts].sort((a, b) => a.id - b.id).map((p) => [p.platform, p])).values()]
            .map((p) => platChip(p.platform, p.status)))),
        c.error ? el("div", { class: "err" }, c.error) : null,
        el("div", { class: "actions" },
          canApprove ? el("button", { class: "small accent", onclick: guard(async () => { await post(`/api/clips/${c.id}/approve`); toast("Corte aprovado — entra na agenda."); refresh(); }) }, icon("check"), "Aprovar")
                     : el("button", { class: "small", disabled: true }, icon("check"), c.status === "approved" ? "Aprovado" : "Aprovar"),
          el("button", { class: "small", onclick: () => openEdit(c) }, icon("pencil"), "Editar"),
          el("button", { class: "small danger", disabled: c.status === "rejected", onclick: guard(async () => { await post(`/api/clips/${c.id}/reject`); refresh(); }) }, icon("x"), "Rejeitar")),
        el("div", { class: "more" },
          c.has_video ? el("a", { href: mediaUrl(`/api/clips/${c.id}/video`), download: "" }, "Baixar vídeo") : null,
          el("button", { class: "del", onclick: guard(async () => { if (confirm("Excluir este corte? O vídeo dele é apagado do disco.")) { await api(`/api/clips/${c.id}`, { method: "DELETE" }); refresh(); } }) }, icon("trash"), "Excluir corte"))));
  }));
}
function openPlayer(c) {
  const v = $("#playerVideo");
  v.src = mediaUrl(`/api/clips/${c.id}/video`);
  $("#player").showModal();
  v.play().catch(() => {});
}
$("#playerClose").onclick = () => { $("#playerVideo").pause(); $("#player").close(); };
let editing = null;
function openEdit(c) {
  editing = c;
  $("#editTitle").value = c.title; $("#editDesc").value = c.description || "";
  $("#editDlg").showModal();
}
$("#editCancel").onclick = () => $("#editDlg").close();
$("#editForm").addEventListener("submit", guard(async () => {
  if (!editing) return;
  await api(`/api/clips/${editing.id}`, { method: "PATCH", body: JSON.stringify({ title: $("#editTitle").value, description: $("#editDesc").value }) });
  toast("Corte atualizado"); editing = null; refresh();
}));
["#clipFilter", "#clipPeriod", "#clipSource"].forEach((s) => { $(s).onchange = () => refresh(); });
$("#clipSearch").addEventListener("input", () => refresh());

// ---------- Agenda ----------
function startOfWeek(offset) {
  const d = new Date(); d.setHours(0, 0, 0, 0);
  d.setDate(d.getDate() - ((d.getDay() + 6) % 7) + offset * 7); // segunda-feira
  return d;
}
const DOW = ["Seg.", "Ter.", "Qua.", "Qui.", "Sex.", "Sáb.", "Dom."];
const DOT = { scheduled: "", publishing: "", published: "ok", failed: "bad" };

function renderCalendar(posts) {
  const root = $("#tab-queue");
  const start = startOfWeek(weekOffset);
  const days = Array.from({ length: 7 }, (_, i) => { const d = new Date(start); d.setDate(start.getDate() + i); return d; });
  const end = days[6];
  const todayKey = dayKey(new Date());
  const fmtD = (d) => d.toLocaleDateString("pt-BR", { day: "numeric", month: "short" });

  const head = el("div", { class: "cal-head" },
    el("div", { class: "cal-nav" },
      el("button", { class: "ghost", "aria-label": "Semana anterior", onclick: () => { weekOffset--; renderCalendar(posts); } }, icon("chevL")),
      el("button", { class: "ghost", onclick: () => { weekOffset = 0; refresh(true); } }, "Hoje"),
      el("button", { class: "ghost", "aria-label": "Próxima semana", onclick: () => { weekOffset++; renderCalendar(posts); } }, icon("chevR"))),
    el("div", { class: "cal-range" }, icon("calendar"), `${fmtD(start)} – ${fmtD(end)} ${end.getFullYear()}`),
    el("div", { class: "cal-legend" },
      el("span", {}, el("i", { class: "dotc" }), "Agendado"), el("span", {}, el("i", { class: "dotc ok" }), "Publicado"), el("span", {}, el("i", { class: "dotc bad" }), "Falhou")));

  const byDay = new Map(days.map((d) => [dayKey(d), []]));
  for (const p of posts) {
    const when = p.status === "published" && p.published_at ? p.published_at : p.scheduled_at;
    const k = dayKey(new Date(when));
    if (byDay.has(k)) byDay.get(k).push({ ...p, when });
  }
  const grid = el("div", { class: "cal-grid" }, days.map((d, i) => {
    const k = dayKey(d);
    const items = byDay.get(k).sort((a, b) => a.when.localeCompare(b.when));
    return el("div", { class: `cal-col${k === todayKey ? " today" : ""}` },
      el("div", { class: "cal-day" }, el("b", {}, DOW[i]), el("span", {}, fmtD(d))),
      el("div", { class: "cal-body" }, items.map((p) => {
        const acts = el("div", { class: "cal-ev-acts" });
        if (p.status === "scheduled") acts.append(
          el("button", { class: "mini accent", onclick: guard(async () => { await post(`/api/posts/${p.id}/publish-now`); toast("Publicando…"); refresh(); }) }, icon("play"), "Publicar"),
          el("button", { class: "mini", onclick: guard(async () => { await post(`/api/posts/${p.id}/cancel`); refresh(); }) }, "Cancelar"));
        else if (p.status === "failed") acts.append(
          el("span", { class: "mini-state bad", title: p.error || "" }, icon("x"), "Falhou"),
          el("button", { class: "mini", onclick: guard(async () => { await post(`/api/posts/${p.id}/retry`); refresh(); }) }, "Reagendar"));
        else if (p.status === "published") {
          acts.append(el("span", { class: "mini-state ok" }, icon("check"), "Publicado"));
          if (p.external_url) acts.append(el("a", { class: "mini", href: p.external_url, target: "_blank", rel: "noopener" }, "Abrir"));
        }
        else acts.append(chip(p.status));
        return el("div", { class: "cal-ev", title: p.error || "" },
          el("div", { class: "cal-ev-top" }, el("i", { class: `dotc ${DOT[p.status] || ""}` }), fmtTime(p.when)),
          platChip(p.platform),
          el("div", { class: "cal-ev-title" }, `${partLabel()} ${p.clip_idx} — ${p.clip_title}`), acts);
      })));
  }));
  const scheduled = posts.filter((p) => p.status === "scheduled").length;
  root.replaceChildren(head, grid, el("p", { class: "muted cal-note" },
    scheduled ? `${scheduled} publicação(ões) agendada(s). Cada plataforma publica 1 corte por horário definido em Configurações.`
              : "Nada agendado. Conecte uma conta em Contas e aprove cortes para preencher a agenda."));
}

// ---------- Contas ----------
const GUIDES = {
  youtube: {
    desc: "Publicação de cortes em formato Shorts no YouTube.",
    idLabel: "ID do cliente", secretLabel: "Chave secreta do cliente",
    steps: (uri) => [
      ["Abra o ", el("a", { href: "https://console.cloud.google.com/apis/library/youtube.googleapis.com", target: "_blank", rel: "noopener" }, "Google Cloud Console"), " (crie um projeto se ele pedir) e clique em ", el("b", {}, "Ativar"), " na YouTube Data API v3."],
      ["Em ", el("a", { href: "https://console.cloud.google.com/apis/credentials/consent", target: "_blank", rel: "noopener" }, "Tela de consentimento OAuth"), ", escolha ", el("b", {}, "Externo"), ", dê um nome ao app e adicione o seu e-mail em ", el("b", {}, "Usuários de teste"), "."],
      ["Em ", el("a", { href: "https://console.cloud.google.com/apis/credentials", target: "_blank", rel: "noopener" }, "Credenciais"), " → Criar credenciais → ", el("b", {}, "ID do cliente OAuth"), " → tipo ", el("b", {}, "Aplicativo da Web"), ". Em “URIs de redirecionamento autorizados”, cole:", copyRow(uri)],
      ["Copie o ", el("b", {}, "ID do cliente"), " e a ", el("b", {}, "Chave secreta"), " que aparecerem e cole abaixo. Depois é só clicar em Conectar."],
    ],
  },
  tiktok: {
    desc: "Publicação de cortes no TikTok.",
    idLabel: "Client key", secretLabel: "Client secret", askRedirect: true,
    steps: (uri) => [
      ["Crie um app em ", el("a", { href: "https://developers.tiktok.com/apps", target: "_blank", rel: "noopener" }, "TikTok for Developers"), " e adicione os produtos ", el("b", {}, "Login Kit"), " e ", el("b", {}, "Content Posting API"), "."],
      ["O TikTok só aceita endereço de retorno ", el("b", {}, "HTTPS"), ". Abra um túnel para o ClipForge (ex.: ", el("code", {}, "cloudflared tunnel --url http://localhost:8765"), ") e use o endereço https gerado + ", el("code", {}, "/auth/tiktok/callback"), ". Endereço atual:", copyRow(uri)],
      ["Cadastre esse endereço em ", el("b", {}, "Redirect URI"), " no portal do TikTok e copie o ", el("b", {}, "Client key"), " e o ", el("b", {}, "Client secret"), " para os campos abaixo."],
    ],
  },
};

function copyRow(text) {
  const inp = el("input", { type: "text", value: text, readonly: true, "aria-label": "Endereço de retorno", onfocus: (e) => e.target.select() });
  return el("div", { class: "copyrow" }, inp, el("button", { type: "button", class: "small", onclick: guard(async () => { await navigator.clipboard.writeText(text); toast("Copiado"); }) }, icon("copy"), "Copiar"));
}

async function connect(platform) {
  await post(`/api/auth/${platform}/start?open_browser=true`);
  toast(`Abrimos o login do ${PLAT_SHORT[platform]} no seu navegador. Autorize o acesso — a conta aparece aqui sozinha.`);
  const before = (await api("/api/accounts")).find((a) => a.platform === platform)?.connected_at;
  const deadline = Date.now() + 5 * 60000;
  const tick = async () => {
    if (Date.now() > deadline) return;
    const accs = await api("/api/accounts").catch(() => null);
    const a = accs?.find((x) => x.platform === platform);
    if (a?.connected && a.connected_at !== before) {
      toast(`${PLAT_SHORT[platform]} conectado: ${a.display_name || ""}`);
      if (currentTab === "accounts") renderAccounts(accs);
      return;
    }
    setTimeout(tick, 3000);
  };
  setTimeout(tick, 3000);
}

function setupPanel(a) {
  const g = GUIDES[a.platform];
  const id = el("input", { type: "text", autocomplete: "off", placeholder: g.idLabel, "aria-label": g.idLabel });
  const secret = el("input", { type: "password", autocomplete: "off", placeholder: g.secretLabel, "aria-label": g.secretLabel });
  const redir = g.askRedirect ? el("input", { type: "url", placeholder: "https://seu-tunel.trycloudflare.com/auth/tiktok/callback", value: a.redirect_uri.startsWith("https://") ? a.redirect_uri : "", "aria-label": "Endereço de retorno (HTTPS)" }) : null;
  const save = el("button", { class: "primary", type: "submit" }, icon("save"), "Salvar chaves");
  const form = el("form", { class: "cred" },
    el("div", {}, el("label", {}, g.idLabel), id), el("div", {}, el("label", {}, g.secretLabel), secret), save,
    redir ? el("div", { class: "full" }, el("label", {}, "Endereço de retorno HTTPS (Redirect URI)"), redir) : null);
  form.addEventListener("submit", guard(async (e) => {
    e.preventDefault();
    await post(`/api/accounts/${a.platform}/credentials`, { client_id: id.value, client_secret: secret.value, redirect_uri: redir ? redir.value || null : null });
    toast("Chaves salvas. Agora clique em Conectar.");
    renderAccounts(await api("/api/accounts"));
  }));
  return el("div", { class: "setup" },
    el("h4", {}, a.configured ? `Trocar as chaves do ${PLAT_SHORT[a.platform]}` : `Configure o ${PLAT_SHORT[a.platform]} em poucos passos`),
    el("div", { class: "muted", style: "font-size:13px" }, "Feito uma vez só. As chaves ficam guardadas apenas neste computador (arquivo .env ao lado do ClipForge)."),
    el("ol", { class: "steps" }, g.steps(a.redirect_uri).map((parts) => el("li", {}, el("div", {}, ...parts)))),
    form);
}

function renderAccounts(accs) {
  const root = $("#tab-accounts");
  const cards = accs.map((a) => {
    const g = GUIDES[a.platform] || { desc: "" };
    const setup = setupPanel(a);
    setup.hidden = a.configured || a.connected;
    const name = a.display_name || PLAT_SHORT[a.platform];
    const row = a.connected
      ? el("div", { class: "acc-row" },
          el("div", { class: "avatar" }, (name[0] || "?").toUpperCase()),
          el("div", { class: "acc-who" }, el("b", {}, name), el("span", {}, PLAT[a.platform])),
          el("span", { class: "chip ok" }, icon("check"), "Conectado"),
          a.connected_at ? el("div", { class: "acc-sync" }, icon("refresh"), el("div", {}, "Conectado em:", el("b", {}, fmtDateTime(a.connected_at)))) : null,
          el("div", { class: "right" },
            el("button", { class: "ghost", onclick: guard(async () => { if (confirm(`Desconectar ${PLAT_SHORT[a.platform]}? Os agendamentos dessa plataforma param de ser publicados.`)) { await api(`/api/accounts/${a.platform}`, { method: "DELETE" }); renderAccounts(await api("/api/accounts")); } }) }, "Desconectar"),
            el("button", { class: "primary", onclick: guard(() => connect(a.platform)) }, icon("refresh"), "Reconectar")))
      : el("div", { class: "acc-row" },
          el("div", { class: "avatar" }, icon("user")),
          el("div", { class: "acc-who" }, el("b", {}, "Nenhuma conta conectada"), el("span", {}, a.configured ? "Chaves configuradas — falta só entrar na conta." : "Configure as chaves abaixo para conectar.")),
          el("span", { class: "chip warn" }, "Pendente"),
          el("div", { class: "right" },
            a.configured ? el("button", { class: "ghost", onclick: () => { setup.hidden = !setup.hidden; } }, icon("key"), "Trocar chaves") : null,
            el("button", { class: "primary", disabled: !a.configured, title: a.configured ? "" : "Salve as chaves primeiro", onclick: guard(() => connect(a.platform)) }, icon("plus"), "Conectar")));
    return el("div", { class: "card acc", "data-platform": a.platform },
      el("div", { class: "acc-top" }, el("div", { class: `acc-logo ${a.platform}` }, icon(a.platform)), el("div", { class: "sep" }),
        el("div", {}, el("div", { class: "acc-name" }, PLAT[a.platform] || a.platform), el("div", { class: "acc-desc" }, g.desc))),
      row, setup);
  });

  const toggle = (checked, onchange, label) => el("label", { class: "toggle" }, el("input", { type: "checkbox", checked, "aria-label": label, onchange }), el("i"));
  const perm = (ic, title, sub, checked, onchange) => el("div", { class: "perm" }, icon(ic),
    el("div", {}, el("b", {}, title), el("span", {}, sub)), toggle(checked, onchange, title));
  const setPlat = (p) => guard(async (e) => {
    const cur = new Set(SETTINGS.platforms || []);
    e.target.checked ? cur.add(p) : cur.delete(p);
    await putSettings({ platforms: [...cur] }); toast("Preferência salva");
  });
  root.replaceChildren(...cards,
    el("div", { class: "info-box" }, icon("info"),
      el("div", {}, el("b", {}, "Publicação automática de cortes"),
        el("p", {}, "Com as contas conectadas, o ClipForge publica os cortes nos horários da Agenda, de acordo com as suas preferências.")),
      el("ul", {}, ["Publicar vídeos (Shorts / TikTok)", "Título, descrição e hashtags", "Status e métricas básicas dos vídeos"].map((t) => el("li", {}, icon("check"), t)))),
    el("div", { class: "section-head" }, el("div", {}, el("h2", {}, "Permissões de publicação"), el("p", { class: "muted" }, "Defina como o ClipForge pode publicar nos seus canais conectados."))),
    el("div", { class: "card" },
      perm("bolt", "Publicar cortes automaticamente", "Cortes prontos entram direto na agenda, sem esperar sua aprovação.", !!SETTINGS.auto_approve,
        guard(async (e) => { await putSettings({ auto_approve: e.target.checked }); toast("Preferência salva"); })),
      perm("youtube", "Publicar no YouTube", "Inclui o YouTube Shorts na agenda de publicação.", (SETTINGS.platforms || []).includes("youtube"), setPlat("youtube")),
      perm("tiktok", "Publicar no TikTok", "Inclui o TikTok na agenda de publicação.", (SETTINGS.platforms || []).includes("tiktok"), setPlat("tiktok"))));
}

// ---------- Configurações ----------
const TZ = [["America/Sao_Paulo", "(UTC−03:00) Brasília"], ["America/Manaus", "(UTC−04:00) Manaus"], ["America/Rio_Branco", "(UTC−05:00) Rio Branco"],
  ["America/Noronha", "(UTC−02:00) Fernando de Noronha"], ["Europe/Lisbon", "Lisboa"], ["America/New_York", "Nova York"], ["UTC", "UTC"]];
const SET_GROUPS = [
  ["Publicação", "calendar", "Defina quando, onde e como os conteúdos serão publicados.", [
    ["timezone", "select", "Fuso horário", "", TZ],
    ["post_times", "times", "Horários de publicação", "Cada plataforma publica 1 corte por horário, todo dia."],
    ["platforms", "platforms", "Plataformas de publicação"],
    ["auto_approve", "toggle", "Aprovação automática", "Publica os cortes automaticamente, sem revisão manual."],
  ], [
    ["part_label", "text", "Rótulo da parte", "“Parte” → Parte 1, Parte 2…"],
    ["hashtags", "list", "Hashtags", "Sem #, separadas por vírgula."],
    ["youtube_privacy", "select", "Privacidade no YouTube", "Projetos Google sem auditoria publicam como privado.", [["public", "Público"], ["unlisted", "Não listado"], ["private", "Privado"]]],
    ["tiktok_mode", "select", "Modo do TikTok", "Reconecte a conta ao mudar.", [["direct", "Publicar no perfil"], ["inbox", "Rascunho no app"]]],
    ["tiktok_privacy", "select", "Privacidade no TikTok", "Apps sem auditoria do TikTok só aceitam “Só eu”.", [["SELF_ONLY", "Só eu"], ["FOLLOWER_OF_CREATOR", "Seguidores"], ["MUTUAL_FOLLOW_FRIENDS", "Amigos"], ["PUBLIC_TO_EVERYONE", "Todos"]]],
  ]],
  ["Cortes", "scissors", "Configure como os cortes serão gerados e selecionados.", [
    ["clip_min_seconds", "number", "Duração mínima do corte", "em segundos"],
    ["clip_max_seconds", "number", "Duração máxima do corte", "em segundos (até 59 s para Shorts clássicos)"],
    ["max_clips_per_source", "number", "Máximo de cortes por vídeo"],
    ["min_score", "score", "Pontuação mínima (score)", "Mais alto = menos cortes, porém mais fortes."],
    ["layout", "select", "Enquadramento (vertical 9:16)", "", [["blur", "Vídeo inteiro + fundo desfocado"], ["fill", "Preencher (corta no centro)"]]],
    ["normalize_audio", "toggle", "Normalizar volume"],
  ]],
  ["Legendas", "type", "Personalize o estilo das legendas geradas nos cortes.", [
    ["caption_font", "font", "Fonte", "Precisa estar instalada no computador."],
    ["caption_size", "number", "Tamanho", "em pixels"],
    ["caption_uppercase", "toggle", "Texto em MAIÚSCULAS"],
    ["caption_color", "color", "Cor do texto"],
    ["caption_highlight", "color", "Cor do destaque", "Palavra sendo falada."],
    ["show_part_badge", "toggle", "Mostrar selo “Parte N” no vídeo"],
  ]],
  ["Transcrição com IA", "sparkles", "Configure o modelo e os parâmetros da transcrição.", [
    ["whisper_model", "select", "Modelo de transcrição", "Maior = mais preciso e mais lento.", [["tiny", "Tiny (mais rápido)"], ["base", "Base"], ["small", "Small (recomendado)"], ["medium", "Medium"], ["large-v3", "Large v3 (mais preciso)"]]],
    ["whisper_device", "select", "Dispositivo", "", [["auto", "Automático (GPU se disponível)"], ["cpu", "CPU"], ["cuda", "Placa NVIDIA (CUDA)"]]],
    ["whisper_compute", "select", "Precisão", "", [["int8", "Normal — int8 (CPU)"], ["float16", "Alta — float16 (NVIDIA)"], ["float32", "Máxima — float32"]]],
    ["language", "select", "Idioma da transcrição", "", [["auto", "Detectar automaticamente"], ["pt", "Português"], ["en", "Inglês"], ["es", "Espanhol"]]],
  ], [
    ["ollama_enabled", "toggle", "Usar IA local (Ollama) para ranquear e titular", "Opcional e gratuito; precisa do Ollama rodando."],
    ["ollama_url", "text", "URL do Ollama"],
    ["ollama_model", "text", "Modelo do Ollama", "Ex.: qwen2.5:7b, llama3.1:8b"],
  ]],
  ["Lives", "radio", "Defina como as lives serão tratadas e transcritas.", [
    ["live_delay_seconds", "number", "Atraso antes de cortar", "segundos — só corta o que terminou há pelo menos esse tempo"],
    ["live_chunk_seconds", "number", "Bloco de transcrição", "segundos de live por bloco"],
    ["live_min_score", "score", "Pontuação mínima nas lives"],
  ]],
  ["Download", "download", "Configure a qualidade dos downloads e o uso de cookies do navegador.", [
    ["max_height", "select", "Resolução do download", "", [["720", "720p (HD)"], ["1080", "1080p (Full HD)"], ["1440", "1440p (2K)"], ["2160", "2160p (4K)"]], true],
    ["cookies_from_browser", "cookies", "Usar cookies do navegador", "Para lives de membros, não listadas ou quando o YouTube pedir login."],
  ]],
];

function fieldControl(key, type, label, opts, numeric) {
  const val = SETTINGS[key];
  const tog = (checked) => { const i = el("input", { type: "checkbox", checked, "aria-label": label }); return [el("label", { class: "toggle" }, i, el("i")), i]; };
  if (type === "toggle") { const [n, i] = tog(!!val); return { node: n, get: () => i.checked, row: "tog" }; }
  if (type === "number") { const i = el("input", { type: "number", step: "any", min: 0, value: val, "aria-label": label }); return { node: i, get: () => Number(i.value) }; }
  if (type === "score") {
    const i = el("input", { type: "number", min: 0, max: 100, step: 1, value: Math.round((val || 0) * 100), "aria-label": label });
    return { node: el("div", { class: "colorpick" }, i, el("span", { class: "muted" }, "/ 100")), get: () => Math.max(0, Math.min(100, Number(i.value))) / 100 };
  }
  if (type === "list") { const i = el("input", { type: "text", value: (val || []).join(", "), "aria-label": label }); return { node: i, get: () => i.value.split(",").map((s) => s.trim().replace(/^#/, "")).filter(Boolean) }; }
  if (type === "select") {
    const options = [...opts];
    if (!options.some(([v]) => v === String(val))) options.push([String(val), String(val)]);
    const s = el("select", { "aria-label": label }, options.map(([v, t]) => el("option", { value: v, selected: v === String(val) }, t)));
    return { node: s, get: () => (numeric ? Number(s.value) : s.value) };
  }
  if (type === "font") {
    const i = el("input", { type: "text", value: val, list: "fontList", "aria-label": label });
    const dl = el("datalist", { id: "fontList" }, ["Arial", "Arial Black", "Segoe UI", "Impact", "Verdana", "Montserrat", "Inter", "Roboto"].map((f) => el("option", { value: f })));
    return { node: el("div", {}, i, dl), get: () => i.value.trim() };
  }
  if (type === "color") {
    const hex = /^[0-9a-fA-F]{6}$/.test(val || "") ? val : "FFFFFF";
    const pick = el("input", { type: "color", value: `#${hex}`, "aria-label": label });
    const txt = el("input", { type: "text", value: `#${hex.toUpperCase()}`, maxlength: 7, "aria-label": `${label} (hex)` });
    pick.oninput = () => { txt.value = pick.value.toUpperCase(); };
    txt.oninput = () => { if (/^#?[0-9a-fA-F]{6}$/.test(txt.value)) pick.value = `#${txt.value.replace("#", "")}`; };
    return { node: el("div", { class: "colorpick" }, pick, txt), get: () => pick.value.replace("#", "").toUpperCase() };
  }
  if (type === "times") {
    let times = [...(val || [])];
    const wrap = el("div", { class: "times" });
    const add = el("input", { type: "time", "aria-label": "Novo horário" });
    const draw = () => wrap.replaceChildren(
      ...times.map((t) => el("span", { class: "time-chip" }, t, el("button", { type: "button", "aria-label": `Remover ${t}`, onclick: () => { times = times.filter((x) => x !== t); draw(); } }, "×"))),
      add, el("button", { type: "button", class: "small", onclick: () => { if (add.value && !times.includes(add.value)) { times = [...times, add.value].sort(); add.value = ""; draw(); } } }, icon("plus"), "Adicionar horário"));
    draw();
    return { node: wrap, get: () => times, row: "block" };
  }
  if (type === "platforms") {
    const boxes = ["youtube", "tiktok"].map((p) => { const [n, i] = tog((val || []).includes(p)); i.value = p; return [p, n, i]; });
    return { node: el("div", { class: "plat-toggles" }, boxes.map(([p, n]) => el("div", { class: "plat-toggle" }, icon(p, p), PLAT_SHORT[p], n))),
      get: () => boxes.filter(([, , i]) => i.checked).map(([p]) => p), row: "block" };
  }
  if (type === "cookies") {
    const [n, i] = tog(!!val);
    const s = el("select", { "aria-label": "Navegador", style: "width:auto" }, ["chrome", "edge", "firefox", "brave", "opera"].map((b) => el("option", { value: b, selected: b === val }, b[0].toUpperCase() + b.slice(1))));
    s.hidden = !val; i.onchange = () => { s.hidden = !i.checked; };
    return { node: el("div", { class: "colorpick" }, s, n), get: () => (i.checked ? s.value : "") };
  }
  const i = el("input", { type: "text", value: val ?? "", "aria-label": label });
  return { node: i, get: () => i.value.trim() };
}

function renderSettings() {
  const root = $("#tab-settings");
  if (root.contains(document.activeElement) && document.activeElement !== root) return;
  const getters = {};
  const rows = (fields) => fields.map(([key, type, label, help, opts, numeric]) => {
    const f = fieldControl(key, type, label, opts, numeric);
    getters[key] = f.get;
    const lbl = el("label", {}, label, help ? el("small", {}, help) : null);
    if (f.row === "block") return el("div", { style: "padding:9px 0" }, el("div", { class: "frow", style: "padding:0 0 8px" }, lbl), f.node);
    return el("div", { class: `frow${f.row === "tog" ? " tog" : ""}` }, lbl, f.node);
  });
  const grid = el("div", { class: "set-grid" }, SET_GROUPS.map(([title, ic, sub, fields, adv]) => el("div", { class: "card set-card" },
    el("h3", {}, icon(ic), title), el("p", {}, sub), ...rows(fields),
    adv ? el("details", { class: "adv" }, el("summary", {}, "Opções avançadas"), ...rows(adv)) : null)));
  const form = el("form", {}, grid,
    el("div", { class: "savebar" }, el("span", { class: "muted" }, icon("info"), "Suas preferências serão aplicadas em todo o ClipForge."),
      el("button", { class: "primary", type: "submit" }, icon("save"), "Salvar alterações")));
  form.addEventListener("submit", guard(async (e) => {
    e.preventDefault();
    const out = Object.fromEntries(Object.entries(getters).map(([k, g]) => [k, g()]));
    await putSettings(out);
    toast("Configurações salvas");
    renderSettings();
  }));
  root.replaceChildren(form);
}

// ---------- navegação ----------
const VIEWS = {
  dashboard: ["Painel", "Visão geral dos seus cortes, publicações e desempenho nas redes sociais."],
  sources: ["Vídeos & lives", "Adicione o link de um vídeo ou live do YouTube, ou envie um arquivo, e gere cortes automaticamente com IA."],
  clips: ["Cortes", "Revise, edite o título e aprove os melhores momentos."],
  queue: ["Agenda", "Calendário semanal de publicações dos seus cortes."],
  accounts: ["Contas conectadas", "Gerencie os canais usados para publicar seus cortes."],
  settings: ["Configurações", "Personalize o ClipForge: publicação, cortes, legendas, transcrição, lives e downloads."],
};

function topActionsFor(name) {
  if (name === "dashboard") {
    const sel = el("select", { "aria-label": "Período", onchange: (e) => { PERIOD = Number(e.target.value); lastDash = 0; refresh(true); } },
      [[7, "Últimos 7 dias"], [30, "Últimos 30 dias"], [90, "Últimos 90 dias"]].map(([v, t]) => el("option", { value: v, selected: v === PERIOD }, t)));
    return [sel, el("button", { class: "primary", onclick: guard(async () => { await post("/api/metrics/refresh"); lastDash = 0; await refresh(true); toast("Painel atualizado"); }) }, icon("refresh"), "Atualizar")];
  }
  if (name === "clips") return [el("button", { class: "primary", onclick: () => switchTab("sources") }, icon("sparkles"), "Gerar cortes")];
  if (name === "queue") return [el("button", { class: "primary", onclick: () => { $("#clipFilter").value = "ready"; switchTab("clips"); toast("Aprove um corte: ele entra na agenda no próximo horário livre de cada plataforma."); } }, icon("calendar"), "Agendar publicação")];
  if (name === "accounts") return [el("button", { class: "primary", onclick: () => {
    const card = document.querySelector("#tab-accounts .acc .setup[hidden]")?.closest(".acc") || document.querySelector("#tab-accounts .acc");
    const setup = card?.querySelector(".setup"); if (setup) setup.hidden = false;
    card?.scrollIntoView({ behavior: "smooth", block: "start" });
  } }, icon("plus"), "Conectar conta")];
  return [];
}

function switchTab(name) {
  currentTab = name;
  document.querySelectorAll("#tabs button").forEach((b) => b.classList.toggle("active", b.dataset.tab === name));
  document.querySelectorAll(".tab").forEach((t) => t.classList.toggle("active", t.id === `tab-${name}`));
  const [title, sub] = VIEWS[name] || ["", ""];
  $("#viewTitle").textContent = title; $("#viewSub").textContent = sub;
  setTopActions(...topActionsFor(name));
  if (name === "dashboard") lastDash = 0;
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
    $("#conn").textContent = "online"; $("#conn").className = "chip dot ok";
    if (currentTab === "dashboard") { if (force || Date.now() - lastDash > 30000) { await renderDashboard(); lastDash = Date.now(); } }
    else if (currentTab === "sources") renderSources(await api("/api/sources"));
    else if (currentTab === "clips") { const [c, s] = await Promise.all([api("/api/clips"), api("/api/sources")]); renderClips(c, s); }
    else if (currentTab === "queue") renderCalendar(await api("/api/posts"));
    else if (currentTab === "accounts") { if (force || !$("#tab-accounts").children.length) renderAccounts(await api("/api/accounts")); }
    else if (currentTab === "settings") { if (force || !$("#tab-settings").children.length) renderSettings(); }
  } catch (e) {
    $("#conn").textContent = "offline"; $("#conn").className = "chip dot bad";
    if (force) toast(e.message, true);
  } finally { busy = false; }
}

// aceita ?url=... (a extensão pode abrir o painel já com o link)
const initial = new URLSearchParams(location.search).get("url");
if (initial) { $("#urls").value = initial; currentTab = "sources"; }

switchTab(currentTab);
setInterval(() => refresh(), 4000);
