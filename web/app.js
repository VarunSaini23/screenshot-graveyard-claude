"use strict";

const CATS = [
  ["Receipts", "#51CF66", "🧾"], ["OTPs", "#FF6B6B", "🔐"], ["Chats", "#4DABF7", "💬"],
  ["Memes", "#FCC419", "😂"], ["Tickets", "#CC5DE8", "🎫"], ["Shopping", "#FF922B", "🛍️"],
  ["Addresses", "#22B8CF", "📍"], ["Recipes", "#F06595", "🍳"], ["Notes", "#ADB5BD", "📝"],
  ["Photos", "#94D82D", "🖼️"], ["Other", "#868E96", "📦"],
];
const COLOR = Object.fromEntries(CATS.map(([n, c]) => [n, c]));
const ICON = Object.fromEntries(CATS.map(([n, , i]) => [n, i]));

const $ = (s) => document.querySelector(s);
const fmt = (n) => Number(n || 0).toLocaleString("en-US");
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
function bytes(b) {
  b = Number(b || 0);
  if (b >= 1e9) return (b / 1e9).toFixed(2) + " GB";
  if (b >= 1e6) return (b / 1e6).toFixed(1) + " MB";
  if (b >= 1e3) return Math.round(b / 1e3) + " KB";
  return b + " B";
}
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const reduceMotion = matchMedia("(prefers-reduced-motion: reduce)").matches;

async function api(path, opts = {}) {
  let res;
  try {
    res = await fetch(path, { headers: { "Content-Type": "application/json" }, ...opts });
  } catch {
    throw new Error("Can't reach the app. Is the server still running?");
  }
  let data = null;
  try { data = await res.json(); } catch { /* non-JSON */ }
  if (!res.ok) throw new Error((data && (data.detail || data.error)) || "Something went wrong. Please try again.");
  return data;
}

let toastTimer;
function toast(msg, isErr = false) {
  document.querySelectorAll(".toast").forEach((t) => t.remove());
  const t = document.createElement("div");
  t.className = "toast" + (isErr ? " err" : "");
  t.textContent = msg;
  document.body.appendChild(t);
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => t.remove(), isErr ? 6000 : 3500);
}
window.addEventListener("unhandledrejection", (e) => { e.preventDefault(); toast(e.reason?.message || "Something went wrong.", true); });

function show(id) {
  for (const s of ["start", "sorting", "summary", "results"]) $("#" + s).classList.toggle("hidden", s !== id);
  $("#searchBox").classList.toggle("hidden", id !== "results");
}

// count-up tween used for big numbers
function tween(el, to, { dur = 900, format = fmt, from } = {}) {
  const start = from ?? Number(el.dataset.v || 0);
  el.dataset.v = to;
  if (reduceMotion || start === to) { el.textContent = format(to); return; }
  const t0 = performance.now();
  const step = (t) => {
    const k = Math.min(1, (t - t0) / dur);
    const e = 1 - Math.pow(1 - k, 3);
    el.textContent = format(start + (to - start) * e);
    if (k < 1 && el.dataset.v == to) requestAnimationFrame(step);
  };
  requestAnimationFrame(step);
}

/* ------------------------------------------------------------------ status bar */
let status = {};
async function refreshStatus() {
  try { status = await api("/api/status"); } catch { return; }
  const b = $("#claudeBadge");
  const st = status.claude;
  b.classList.toggle("on", st === "on");
  b.classList.toggle("off", st === "off");
  b.querySelector(".txt").textContent = st === "on" ? "Claude: on" : st === "off" ? "Claude: off" : "Claude: checking…";
  b.title = status.claude_detail || "Checking for Claude Code…";
  if (st === "unknown" || st === "checking") setTimeout(refreshStatus, 2500);
}

function initBlur() {
  const el = $("#blurToggle");
  const apply = (on) => {
    document.body.classList.toggle("blur", on);
    el.classList.toggle("active", on);
    el.textContent = on ? "🙈 Privacy blur: on" : "🙈 Privacy blur: off";
    localStorage.setItem("sg-blur", on ? "1" : "0");
  };
  apply(localStorage.getItem("sg-blur") === "1");
  el.addEventListener("click", () => apply(!document.body.classList.contains("blur")));
}

/* ------------------------------------------------------------------ 1. start */
let scanInfo = null;
function initStart() {
  const chips = $("#chips");
  chips.innerHTML = "";
  for (const s of status.suggestions || []) {
    const c = document.createElement("button");
    c.type = "button"; c.className = "chip"; c.textContent = s; c.title = s;
    c.onclick = () => { $("#folder").value = s; scan(); };
    chips.appendChild(c);
  }
  if (status.folder && !$("#folder").value) $("#folder").value = status.folder;
}

async function scan() {
  const folder = $("#folder").value.trim();
  const found = $("#found");
  if (!folder) { found.innerHTML = `<div class="msg-error">Please type or pick a folder first.</div>`; return; }
  const btn = $("#scanBtn");
  btn.disabled = true; btn.textContent = "Scanning…";
  found.innerHTML = `<div class="note">Looking for screenshots…</div>`;
  try {
    scanInfo = await api("/api/scan", { method: "POST", body: JSON.stringify({ folder }) });
    if (!scanInfo.count) {
      found.innerHTML = `<div class="msg-error">No screenshots found in that folder (PNG, JPG, HEIC or WEBP).</div>`;
      return;
    }
    const again = scanInfo.indexed ? `${fmt(scanInfo.indexed)} already sorted before, so this will be quicker.` : "Your original files will not be moved or changed.";
    found.innerHTML = `<div class="count">Found ${fmt(scanInfo.count)} screenshots (${bytes(scanInfo.bytes)}).</div>
      <div class="note">${again}</div>
      <button class="btn primary big" id="startBtn">Start sorting</button>`;
    $("#startBtn").onclick = startSort;
  } catch (e) {
    found.innerHTML = `<div class="msg-error">${esc(e.message)}</div>`;
  } finally {
    btn.disabled = false; btn.textContent = "Scan folder";
  }
}

/* ------------------------------------------------------------------ 2. sorting */
const sortState = { counts: {}, done: 0, total: 0, started: 0, pending: [], pendingPos: 0, processed: new Set(), slots: [], idxToSlot: new Map(), flights: 0, es: null, timer: null };

function buildPiles(counts = {}) {
  const box = $("#piles");
  box.innerHTML = "";
  for (const [n, c, i] of CATS) {
    const d = document.createElement("div");
    d.className = "pile" + (counts[n] ? " has" : "");
    d.dataset.cat = n;
    d.style.setProperty("--c", c);
    d.innerHTML = `<span class="ico">${i}</span><span class="name">${n}</span><span class="n" data-v="${counts[n] || 0}">${fmt(counts[n] || 0)}</span>`;
    box.appendChild(d);
  }
}

function buildWall(total, startAt = 0) {
  const wall = $("#wall");
  wall.innerHTML = "";
  sortState.slots = [];
  sortState.idxToSlot.clear();
  sortState.pending = [];
  for (let i = startAt; i < total; i++) sortState.pending.push(i);
  sortState.pendingPos = 0;
  const r = wall.getBoundingClientRect();
  const cols = Math.max(1, Math.floor((r.width - 8 + 10) / (104 + 10)));
  const rows = Math.max(1, Math.ceil((r.height + 10) / (136 + 10)));
  const n = Math.min(cols * rows, 240);
  for (let s = 0; s < n; s++) {
    const t = document.createElement("div");
    t.className = "tile";
    wall.appendChild(t);
    sortState.slots.push({ el: t, idx: null });
    fillSlot(s);
  }
}

function nextPending() {
  const p = sortState.pending;
  while (sortState.pendingPos < p.length) {
    const i = p[sortState.pendingPos++];
    if (!sortState.processed.has(i)) return i;
  }
  return null;
}

function fillSlot(s) {
  const slot = sortState.slots[s];
  if (slot.idx !== null) sortState.idxToSlot.delete(slot.idx);
  const i = nextPending();
  slot.idx = i;
  slot.el.classList.remove("gone");
  slot.el.innerHTML = "";
  if (i === null) { slot.el.classList.add("gone"); return; }
  sortState.idxToSlot.set(i, s);
  const img = new Image();
  img.decoding = "async";
  img.onload = () => img.classList.add("ok");
  img.onerror = () => img.remove();
  img.src = `/api/peek/${i}.webp`;
  slot.el.appendChild(img);
}

function pulsePile(cat) {
  const p = document.querySelector(`.pile[data-cat="${cat}"]`);
  if (!p) return;
  p.classList.remove("pulse"); void p.offsetWidth; p.classList.add("pulse");
}

function setPileCount(cat, n, animate = true) {
  const p = document.querySelector(`.pile[data-cat="${cat}"]`);
  if (!p) return;
  const el = p.querySelector(".n");
  if (animate) tween(el, n, { dur: 300 }); else { el.dataset.v = n; el.textContent = fmt(n); }
  p.classList.toggle("has", n > 0);
}

function fly(fromRect, src, cat) {
  const pile = document.querySelector(`.pile[data-cat="${cat}"]`);
  if (!pile || reduceMotion) { pulsePile(cat); return; }
  const to = pile.getBoundingClientRect();
  const img = document.createElement("img");
  img.className = "flyer";
  img.src = src;
  img.style.left = fromRect.left + "px";
  img.style.top = fromRect.top + "px";
  img.style.width = fromRect.width + "px";
  img.style.height = fromRect.height + "px";
  document.body.appendChild(img);
  const dx = to.left + 40 - fromRect.left - fromRect.width / 2;
  const dy = to.top + to.height / 2 - fromRect.top - fromRect.height / 2;
  const lift = -Math.min(160, 60 + Math.abs(dx) * 0.18);
  sortState.flights++;
  const anim = img.animate([
    { transform: "translate(0,0) scale(1) rotate(0deg)", opacity: 1 },
    { transform: `translate(${dx * 0.5}px, ${dy * 0.5 + lift}px) scale(0.75) rotate(${dx > 0 ? 8 : -8}deg)`, opacity: 1, offset: 0.5 },
    { transform: `translate(${dx}px, ${dy}px) scale(0.22) rotate(0deg)`, opacity: 0.2 },
  ], { duration: 540, easing: "cubic-bezier(.45,0,.55,1)" });
  anim.onfinish = () => { img.remove(); sortState.flights--; pulsePile(cat); };
}

function onItem(ev, budget) {
  sortState.processed.add(ev.i);
  sortState.counts[ev.category] = (sortState.counts[ev.category] || 0) + 1;
  const s = sortState.idxToSlot.get(ev.i);
  if (s !== undefined) {
    const slot = sortState.slots[s];
    const img = slot.el.querySelector("img");
    if (budget.left > 0 && img && img.classList.contains("ok") && sortState.flights < 18) {
      budget.left--;
      fly(slot.el.getBoundingClientRect(), img.src, ev.category);
    } else {
      pulsePile(ev.category);
    }
    slot.el.classList.add("gone");
    sortState.idxToSlot.delete(ev.i);
    slot.idx = null;
    setTimeout(() => fillSlot(s), 380);
  } else if (ev.thumb && budget.left > 0 && sortState.flights < 18 && Math.random() < 0.2) {
    // not on the wall: sample a few to fly from a random tile so the motion never stops
    budget.left--;
    const slot = sortState.slots[Math.floor(Math.random() * sortState.slots.length)];
    if (slot) fly(slot.el.getBoundingClientRect(), ev.thumb, ev.category);
  }
}

function updateCounter(done, total) {
  sortState.done = done; sortState.total = total;
  tween($("#cDone"), done, { dur: 250 });
  $("#cTotal").textContent = fmt(total);
  $("#barFill").style.width = total ? (100 * done / total).toFixed(2) + "%" : "0%";
}

function tick() {
  const sec = Math.floor((Date.now() - sortState.started) / 1000);
  $("#elapsed").textContent = `${Math.floor(sec / 60)}:${String(sec % 60).padStart(2, "0")}`;
  const rate = sec > 2 ? sortState.newDone / sec : 0;
  $("#rate").textContent = rate >= 0.1 ? `${rate.toFixed(1)} / sec` : "";
}

async function startSort() {
  try {
    const r = await api("/api/sort", { method: "POST" });
    openSorting({ total: r.total, done: 0, counts: {}, elapsed: 0 });
  } catch (e) { toast(e.message, true); }
}

function openSorting(snap) {
  show("sorting");
  sortState.counts = { ...(snap.counts || {}) };
  sortState.processed = new Set();
  sortState.started = Date.now() - (snap.elapsed || 0) * 1000;
  sortState.newDone = 0;
  buildPiles(sortState.counts);
  $("#phase").textContent = snap.text || "Reading text inside your screenshots…";
  updateCounter(snap.done || 0, snap.total || 0);
  requestAnimationFrame(() => buildWall(snap.total || 0, snap.done || 0));
  clearInterval(sortState.timer);
  sortState.timer = setInterval(tick, 500);
  listen();
}

function listen() {
  if (sortState.es) sortState.es.close();
  const es = new EventSource("/api/progress");
  sortState.es = es;
  let ended = false;
  es.onmessage = (m) => {
    const msg = JSON.parse(m.data);
    if (msg.type === "snapshot") {
      if (msg.state !== "running" && msg.state !== "idle") { ended = true; es.close(); finishSort(msg); }
      return;
    }
    if (msg.type !== "batch") return;
    const items = msg.events.filter((e) => e.type === "item");
    // sample: keep the motion readable when many items land at once
    const budget = { left: items.length > 10 ? 4 : items.length > 4 ? 3 : items.length };
    for (const ev of msg.events) {
      if (ev.type === "item") { onItem(ev, budget); sortState.newDone++; }
      else if (ev.type === "cached") {
        sortState.counts = { ...ev.counts };
        for (const [n] of CATS) setPileCount(n, sortState.counts[n] || 0);
        for (const i of ev.idx || []) sortState.processed.add(i);
        sortState.slots.forEach((slot, s) => {
          if (slot.idx !== null && sortState.processed.has(slot.idx)) {
            slot.el.classList.add("gone");
            sortState.idxToSlot.delete(slot.idx);
            slot.idx = null;
            setTimeout(() => fillSlot(s), 300 + Math.random() * 500);
          }
        });
        $("#phase").textContent = `${fmt(ev.n)} screenshots were already sorted. Reading the new ones…`;
      } else if (ev.type === "phase") $("#phase").textContent = ev.text;
      else if (ev.type === "reclass") {
        sortState.counts = { ...ev.counts };
        for (const [n] of CATS) { setPileCount(n, sortState.counts[n] || 0); }
        pulsePile("Other");
      } else if (ev.type === "end") { ended = true; es.close(); finishSort(ev); }
    }
    for (const [n] of CATS) {
      const p = document.querySelector(`.pile[data-cat="${n}"] .n`);
      if (p && Number(p.dataset.v) !== (sortState.counts[n] || 0)) setPileCount(n, sortState.counts[n] || 0);
    }
    updateCounter(msg.done, msg.total);
  };
  es.onerror = () => {
    if (ended) return;
    es.close();
    setTimeout(async () => {
      try {
        const st = await api("/api/status");
        if (st.job === "running") listen();
        else if (st.sorted) finishSort({ state: "done" });
        else { toast("Lost connection to the sorter. Please scan again.", true); show("start"); }
      } catch (e) { toast(e.message, true); setTimeout(listen, 2000); }
    }, 800);
  };
}

async function finishSort(ev) {
  clearInterval(sortState.timer);
  if (ev.state === "error") { toast(ev.error || "Sorting stopped unexpectedly.", true); show("start"); return; }
  if (ev.state === "cancelled") { toast("Sorting stopped. Everything sorted so far is saved."); show("start"); return; }
  if (ev.total) updateCounter(ev.total, ev.total);
  $("#phase").textContent = "All sorted!";
  await sleep(700);
  openSummary();
}

/* ------------------------------------------------------------------ 3. summary */
let summary = null;
async function loadSummary() { summary = await api("/api/summary"); return summary; }

function fallbackLines(s) {
  const out = [];
  if (s.otps) out.push(`${fmt(s.otps)} OTPs. Not one of them still works.`);
  if (s.counts.Receipts) out.push(`${fmt(s.counts.Receipts)} receipts. Your accountant would be proud.`);
  if (s.counts.Memes) out.push(`${fmt(s.counts.Memes)} memes saved "for later". Later is now.`);
  if (s.dupes) out.push(`${fmt(s.dupes)} screenshots you took twice, just to be sure.`);
  return out.slice(0, 3);
}

async function openSummary() {
  let s;
  try { s = await loadSummary(); } catch (e) { toast(e.message, true); show("start"); return; }
  show("summary");
  $("#sumTitle").textContent = `${fmt(s.total)} screenshots sorted.`;
  $("#sumLead").textContent = `${bytes(s.bytes)} of screenshots, now in ${Object.values(s.counts).filter(Boolean).length} neat piles.`;
  const cards = [
    { v: s.otps, t: "OTP screenshots.", s: "Useful: 0.", c: COLOR.OTPs },
    { v: s.dupes, t: "duplicates.", s: "We keep the newest copy of each.", c: "#FFA94D" },
    { v: s.junk_bytes, t: "you can free.", s: `${fmt(s.junk)} junk screenshots in total.`, c: "#51CF66", isBytes: true },
  ];
  $("#stats").innerHTML = cards.map((c, i) => `<div class="stat glass" style="animation-delay:${i * 160}ms">
    <div class="v" style="color:${c.c}" data-v="0">0</div><div class="t">${c.t}</div><div class="s">${c.s}</div></div>`).join("");
  document.querySelectorAll(".stat").forEach((el, i) => {
    el.classList.add("in");
    const c = cards[i];
    setTimeout(() => tween(el.querySelector(".v"), c.v, { dur: 1100, from: 0, format: c.isBytes ? bytes : fmt }), i * 160);
  });
  const lines = (s.witty && s.witty.length ? s.witty : fallbackLines(s));
  $("#witty").innerHTML = lines.map((l) => `<div>“${esc(l)}”</div>`).join("") +
    (s.witty && s.witty.length ? `<div class="who">Written by Claude from your counts only.</div>` : "");
  $("#freed").textContent = "";
  const tb = $("#sumTrash");
  tb.disabled = !s.junk;
  tb.textContent = s.junk ? `Move ${fmt(s.junk)} junk screenshots to Trash` : "No junk to clear 🎉";
  $("#junkStrip").innerHTML = "";
  if (s.junk) {
    try {
      const r = await api("/api/items?view=junk&page=0");
      $("#junkStrip").innerHTML = r.items.slice(0, 26).map((it) => `<img src="/thumbs/${it.id}.webp" alt="" loading="lazy" onerror="this.remove()">`).join("");
    } catch { /* optional preview */ }
  }
}

function confirmTrash(s) {
  return new Promise((resolve) => {
    const root = $("#overlayRoot");
    root.innerHTML = `<div class="overlay"><div class="dialog glass" role="dialog" aria-modal="true">
      <h3>Move ${fmt(s.junk)} junk screenshots to Trash?</h3>
      <ul>
        <li><span>🔐 OTP screenshots</span><b>${fmt(s.otps)}</b></li>
        <li><span>👯 Duplicates (newest copy kept)</span><b>${fmt(s.dupes)}</b></li>
        <li><span>📦 Old, almost-empty screenshots (1+ year)</span><b>${fmt(s.old_other)}</b></li>
      </ul>
      <p>Some screenshots can be in more than one group; each is moved once. Total: <b>${bytes(s.junk_bytes)}</b>.</p>
      <p>Your original files are not touched. Copies go to <b>${esc(s.output)}${status.platform === "Windows" ? "\\" : "/"}_Trash</b> so you can check them before deleting the originals yourself.</p>
      <div class="btns"><button class="btn" id="dlgNo">Cancel</button><button class="btn danger" id="dlgYes">Move to Trash</button></div>
    </div></div>`;
    const done = (v) => { root.innerHTML = ""; resolve(v); };
    $("#dlgNo").onclick = () => done(false);
    $("#dlgYes").onclick = () => done(true);
    root.querySelector(".overlay").onclick = (e) => { if (e.target.classList.contains("overlay")) done(false); };
    $("#dlgYes").focus();
  });
}

async function doTrash(fromSummary) {
  let s;
  try { s = await loadSummary(); } catch (e) { toast(e.message, true); return; }
  if (!s.junk) { toast("No junk left to clear."); return; }
  if (!(await confirmTrash(s))) return;
  const btns = [$("#sumTrash"), $("#trashBtn")];
  btns.forEach((b) => { b.disabled = true; });
  try {
    const r = await api("/api/trash-junk", { method: "POST" });
    if (fromSummary) {
      const imgs = [...document.querySelectorAll("#junkStrip img")];
      imgs.forEach((img, i) => {
        img.animate([
          { transform: "translateY(0) rotate(0)", opacity: 1 },
          { transform: `translateY(${180 + Math.random() * 120}px) rotate(${(Math.random() - 0.5) * 50}deg)`, opacity: 0 },
        ], { duration: 900, delay: i * 35, easing: "cubic-bezier(.5,0,.9,.4)", fill: "forwards" });
      });
      const f = $("#freed");
      f.innerHTML = `<span id="freedN">0 B</span> freed. Moved ${fmt(r.moved)} copies to _Trash.`;
      tween($("#freedN"), r.freed, { dur: 1500, from: 0, format: bytes });
      $("#sumTrash").textContent = "Junk moved to Trash ✓";
    } else {
      toast(`Moved ${fmt(r.moved)} junk copies to _Trash (${bytes(r.freed)}). Originals untouched.`);
      document.querySelectorAll(".item").forEach((el) => { if (r.ids.includes(Number(el.dataset.id))) el.style.opacity = "0"; });
      await sleep(400);
      await refreshResults();
    }
    if (r.failed.length) toast(`${r.failed.length} files couldn't be copied.`, true);
  } catch (e) {
    toast(e.message, true);
    btns.forEach((b) => { b.disabled = false; });
  }
}

/* ------------------------------------------------------------------ 4. results */
const view = { category: "", view: "", q: "", page: 0, pages: 0, loading: false, token: 0 };

async function openResults() {
  show("results");
  view.category = ""; view.view = ""; view.q = ""; $("#q").value = "";
  await refreshResults();
}

async function refreshResults() {
  let s;
  try { s = await loadSummary(); } catch (e) { toast(e.message, true); return; }
  renderSidebar(s);
  renderCards(s);
  $("#trashBtn").disabled = !s.junk;
  $("#trashBtn").textContent = s.junk ? `Move ${fmt(s.junk)} junk to Trash` : "No junk left";
  await loadGrid(true);
}

function renderCards(s) {
  const totalShown = Object.values(s.counts).reduce((a, b) => a + b, 0);
  $("#cards").innerHTML = [
    ["Screenshots", fmt(totalShown)], ["Total size", bytes(s.bytes)],
    ["Junk", fmt(s.junk)], ["You can free", bytes(s.junk_bytes)],
  ].map(([k, v]) => `<div class="card glass"><div class="k">${k}</div><div class="v">${v}</div></div>`).join("");
}

function renderSidebar(s) {
  const total = Object.values(s.counts).reduce((a, b) => a + b, 0);
  const item = (lbl, cnt, color, data, active) =>
    `<button class="side-item${active ? " active" : ""}" ${data} style="--c:${color}"><span class="dot"></span><span class="lbl">${lbl}</span><span class="cnt">${fmt(cnt)}</span></button>`;
  let h = `<div class="side-h">Piles</div>` + item("All screenshots", total, "#8B7CFF", `data-cat="" data-view=""`, !view.category && !view.view);
  for (const [n, c, i] of CATS) {
    if (!s.counts[n] && n !== "Other") continue;
    h += item(`${i}&nbsp; ${n}`, s.counts[n], c, `data-cat="${n}" data-view=""`, view.category === n && !view.view);
  }
  h += `<div class="side-h">Clean up</div>`;
  h += item("👯&nbsp; Duplicates", s.dupes, "#FFA94D", `data-cat="" data-view="duplicates"`, view.view === "duplicates");
  h += item("🗑️&nbsp; Junk", s.junk, "#FF6B6B", `data-cat="" data-view="junk"`, view.view === "junk");
  if (s.trashed) h += item("📥&nbsp; In _Trash", s.trashed, "#495057", `data-cat="" data-view="trash"`, view.view === "trash");
  $("#sidebar").innerHTML = h;
  $("#sidebar").querySelectorAll(".side-item").forEach((b) => b.onclick = () => {
    view.category = b.dataset.cat; view.view = b.dataset.view;
    $("#sidebar").querySelectorAll(".side-item").forEach((x) => x.classList.toggle("active", x === b));
    loadGrid(true);
  });
}

function highlightSnippet(s) {
  return esc(s).replace(/\[\[/g, "<mark>").replace(/\]\]/g, "</mark>");
}

function gridTitle() {
  const t = view.view === "duplicates" ? "Duplicates" : view.view === "junk" ? "Junk" : view.view === "trash" ? "Moved to _Trash"
    : view.category ? view.category : "All screenshots";
  return view.q ? `“${view.q}” in ${t.toLowerCase() === "all screenshots" ? "all screenshots" : t}` : t;
}

async function loadGrid(reset) {
  if (reset) { view.page = 0; view.pages = 1; $("#grid").innerHTML = ""; $("#gridScroll").scrollTop = 0; }
  if (view.loading || view.page >= view.pages) return;
  view.loading = true;
  const token = ++view.token;
  const p = new URLSearchParams({ category: view.category, view: view.view, q: view.q, page: view.page });
  try {
    const r = await api("/api/items?" + p);
    if (token !== view.token) return;
    view.pages = r.pages;
    $("#gridTitle").textContent = gridTitle();
    $("#gridCount").textContent = `${fmt(r.total)} screenshot${r.total === 1 ? "" : "s"}`;
    const grid = $("#grid");
    if (!r.total) {
      grid.innerHTML = `<div class="empty"><div class="e">${view.q ? "🔍" : "✨"}</div>${view.q ? "No screenshots contain that text." : "Nothing here."}</div>`;
    }
    const frag = document.createDocumentFragment();
    for (const it of r.items) frag.appendChild(itemCard(it));
    grid.appendChild(frag);
    view.page++;
  } catch (e) {
    if (token === view.token) toast(e.message, true);
  } finally {
    if (token === view.token) view.loading = false;
  }
  if (token === view.token && view.page < view.pages) {
    const sen = $("#sentinel").getBoundingClientRect();
    if (sen.top < window.innerHeight + 400) loadGrid(false);
  }
}

function itemCard(it) {
  const d = document.createElement("div");
  d.className = "item";
  d.dataset.id = it.id;
  const c = COLOR[it.category] || COLOR.Other;
  d.style.setProperty("--c", c);
  d.title = `${it.category} · ${it.reason || ""}`;
  const ratio = it.width && it.height ? Math.min(2.4, Math.max(0.4, it.height / it.width)) : 1.6;
  const label = it.title || it.name;
  const dupTag = it.dup_of ? `<span class="tag tag2">Duplicate</span>` : "";
  d.innerHTML = `<div class="thumb" style="aspect-ratio:1/${ratio.toFixed(3)}"><img loading="lazy" decoding="async" src="/thumbs/${it.id}.webp" alt=""></div>
    <span class="tag">${ICON[it.category] || ""} ${esc(it.category)}</span>${dupTag}
    <div class="cap"><div class="ttl">${esc(label)}</div>${it.snippet ? `<div class="snip">${highlightSnippet(it.snippet)}</div>` : ""}</div>`;
  const img = d.querySelector("img");
  img.onerror = () => { img.replaceWith(Object.assign(document.createElement("div"), { className: "empty", textContent: "Preview unavailable" })); };
  d.onclick = () => openLightbox(it.id);
  return d;
}

function highlightText(text, q) {
  const safe = esc(text || "");
  const words = (q || "").match(/[\p{L}\p{N}₹]+/gu);
  if (!words) return safe;
  const re = new RegExp(`(${words.map((w) => w.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("|")})`, "giu");
  return safe.replace(re, "<mark>$1</mark>");
}

async function openLightbox(id) {
  let it;
  try { it = await api(`/api/item/${id}`); } catch (e) { toast(e.message, true); return; }
  const c = COLOR[it.category] || COLOR.Other;
  const when = new Date(it.mtime * 1000).toLocaleString("en-US", { dateStyle: "medium", timeStyle: "short" });
  const root = $("#overlayRoot");
  root.innerHTML = `<div class="overlay"><button class="btn small close" id="lbClose">Close ✕</button>
    <div class="lightbox glass" role="dialog" aria-modal="true">
      <div class="lb-img"><img src="/image/${it.id}" alt="${esc(it.name)}" class="thumb-full"></div>
      <div class="lb-side">
        <div><span class="pill" style="--c:${c}">${ICON[it.category] || ""} ${esc(it.category)}</span></div>
        <h3>${esc(it.title || it.name)}</h3>
        <div class="row">Why: ${esc(it.reason || "–")}${it.confidence ? ` · ${(it.confidence * 100).toFixed(0)}% sure` : ""}</div>
        ${it.dup_of ? `<div class="row">Duplicate of a newer screenshot (it will be moved to _Trash with the junk).</div>` : ""}
        <div class="row">${esc(it.path)}</div>
        <div class="row">${bytes(it.size)} · ${it.width || "?"}×${it.height || "?"} · ${when}</div>
        <div class="side-h" style="padding:6px 0 0">Text found in this screenshot</div>
        <div class="ocr">${it.ocr ? highlightText(it.ocr, view.q) : "<i>No text found.</i>"}</div>
      </div>
    </div></div>`;
  const imgEl = root.querySelector(".lb-img img");
  imgEl.onerror = () => { imgEl.replaceWith(Object.assign(document.createElement("div"), { className: "empty", textContent: "This image can't be displayed." })); };
  if (document.body.classList.contains("blur")) imgEl.style.filter = "blur(6px)";
  const close = () => { root.innerHTML = ""; document.removeEventListener("keydown", onKey); };
  const onKey = (e) => { if (e.key === "Escape") close(); };
  document.addEventListener("keydown", onKey);
  $("#lbClose").onclick = close;
  root.querySelector(".overlay").onclick = (e) => { if (e.target.classList.contains("overlay")) close(); };
  const m = root.querySelector(".ocr mark");
  if (m) m.scrollIntoView({ block: "center" });
}

async function doExport() {
  const b = $("#exportBtn");
  b.disabled = true; b.textContent = "Exporting…";
  try {
    const r = await api("/api/export", { method: "POST" });
    toast(`Copied ${fmt(r.copied)} screenshots into sorted folders${r.skipped ? ` (${fmt(r.skipped)} were already there)` : ""}. Originals untouched.`);
    if (r.failed.length) toast(`${r.failed.length} files couldn't be copied.`, true);
  } catch (e) { toast(e.message, true); }
  finally { b.disabled = false; b.textContent = "Export sorted folders"; }
}

async function openOutput() {
  try {
    const r = await api("/api/open-output", { method: "POST" });
    toast(`Opened ${r.path}`);
  } catch (e) { toast(e.message, true); }
}

/* ------------------------------------------------------------------ boot */
let searchTimer;
async function boot() {
  initBlur();
  await refreshStatus();
  initStart();
  $("#scanForm").addEventListener("submit", (e) => { e.preventDefault(); scan(); });
  $("#cancelBtn").onclick = async () => { try { await api("/api/cancel", { method: "POST" }); $("#phase").textContent = "Stopping…"; } catch (e) { toast(e.message, true); } };
  $("#sumTrash").onclick = () => doTrash(true);
  $("#sumResults").onclick = openResults;
  $("#trashBtn").onclick = () => doTrash(false);
  $("#exportBtn").onclick = doExport;
  $("#openBtn").onclick = openOutput;
  $("#newBtn").onclick = () => { $("#found").innerHTML = ""; show("start"); initStart(); };
  $("#q").addEventListener("input", () => {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(() => {
      view.q = $("#q").value.trim();
      if (view.q && (view.category || view.view)) {
        view.category = ""; view.view = "";
        $("#sidebar").querySelectorAll(".side-item").forEach((x, i) => x.classList.toggle("active", i === 0));
      }
      loadGrid(true);
    }, 140);
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "/" && !$("#results").classList.contains("hidden") && document.activeElement !== $("#q")) { e.preventDefault(); $("#q").focus(); }
  });
  new IntersectionObserver((es) => { if (es.some((e) => e.isIntersecting)) loadGrid(false); }, { root: $("#gridScroll"), rootMargin: "600px" })
    .observe($("#sentinel"));

  if (status.job === "running") {
    try {
      const st = await new Promise((resolve, reject) => {
        const es = new EventSource("/api/progress");
        es.onmessage = (m) => { es.close(); resolve(JSON.parse(m.data)); };
        es.onerror = () => { es.close(); reject(new Error("Can't reach the sorter.")); };
      });
      openSorting(st);
      return;
    } catch (e) { toast(e.message, true); }
  }
  if (status.sorted && status.folder) { await openResults(); return; }
  show("start");
}

boot();
