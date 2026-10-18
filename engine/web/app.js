// Roomsmith Studio. No framework, no third-party code. Text is only ever set with textContent,
// never innerHTML, so a photo label or a catalog field cannot become markup or script.
"use strict";

const $ = (s) => document.querySelector(s);
const state = { p: "", r: "", room: null, photo: null, items: [], sel: -1, tool: "line",
                flipSide: "A" };

function h(tag, attrs = {}, ...kids) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "on") for (const [ev, fn] of Object.entries(v)) el.addEventListener(ev, fn);
    else if (k === "class") el.className = v;
    else if (v !== undefined && v !== null && v !== false) el.setAttribute(k, v === true ? "" : v);
  }
  for (const kid of kids.flat()) if (kid !== null && kid !== undefined)
    el.append(kid instanceof Node ? kid : document.createTextNode(String(kid)));
  return el;
}

function toast(msg) {
  const t = $("#toast"); t.textContent = msg; t.classList.add("show");
  clearTimeout(toast.t); toast.t = setTimeout(() => t.classList.remove("show"), 3200);
}

async function api(path, opts = {}) {
  const init = { method: opts.method || "GET", headers: { "X-Roomsmith": "1" },
                 credentials: "same-origin" };
  if (opts.body !== undefined) {
    init.body = opts.raw ? opts.body : JSON.stringify(opts.body);
    if (!opts.raw) init.headers["Content-Type"] = "application/json";
  }
  const res = await fetch(path, init);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || res.statusText);
  return data;
}

const q = (extra = {}) => new URLSearchParams({ p: state.p, r: state.r, ...extra }).toString();
const media = (extra) => `/media?${q(extra)}`;

// ---------------------------------------------------------------- tree

async function loadTree() {
  const { tree, current, home } = await api("/api/tree");
  const box = $("#tree"); box.replaceChildren();
  if (!tree.length) box.append(h("p", { class: "muted" }, "No projects yet. Run: design init house/garage"));
  for (const proj of tree) {
    box.append(h("div", { class: "proj" }, proj.project));
    const rooms = proj.flat ? [{ room: "", head: null, revisions: [] }] : proj.rooms;
    for (const r of rooms) {
      const addr = proj.flat ? proj.project : `${proj.project}/${r.room}`;
      const a = h("a", { on: { click: () => selectRoom(proj.project, r.room) } },
                  proj.flat ? "(single room)" : r.room, r.head ? h("small", {}, r.head) : null);
      if (proj.project === state.p && r.room === state.r) a.classList.add("on");
      box.append(a);
      if (!state.p && addr === current) setTimeout(() => selectRoom(proj.project, r.room));
    }
  }
  $("#where").textContent = home;
}

async function selectRoom(p, r) {
  state.p = p; state.r = r; state.photo = null; $("#annotator").hidden = true;
  await loadTree();
  await loadRoom();
}

async function loadRoom() {
  if (!state.p) return;
  state.room = await api(`/api/room?${q()}`);
  $("#where").textContent = state.r ? `${state.p}/${state.r} @ ${state.room.head}` : state.p;
  renderGrid(); renderRevisions();
}

// ---------------------------------------------------------------- photos

function renderGrid() {
  const g = $("#grid"); g.replaceChildren();
  for (const ph of state.room.photos) {
    g.append(h("div", { class: "card", on: { click: () => openPhoto(ph.name) } },
      h("img", { src: media({ kind: "refs", f: ph.name }), alt: ph.name, loading: "lazy" }),
      h("div", {}, h("span", { title: ph.name }, ph.name),
        h("span", { class: "muted" }, ph.annotations ? `${ph.annotations} notes` : ""))));
  }
}

async function upload(files) {
  if (!state.p) return toast("Choose a room first");
  for (const f of files) {
    try {
      const r = await api(`/api/upload?${q({ name: f.name })}`, { method: "POST", body: f, raw: true });
      toast(`${r.name}: ${r.width}×${r.height}` + (r.stripped ? `, ${r.stripped} bytes of metadata removed` : ""));
    } catch (e) { toast(`${f.name}: ${e.message}`); }
  }
  await loadRoom();
}

// ---------------------------------------------------------------- annotator

async function openPhoto(name) {
  state.photo = name; state.sel = -1;
  const doc = await api(`/api/annotations?${q({ image: name })}`);
  state.items = doc.items || [];
  const img = $("#photo");
  img.onload = () => { sizeCanvas(); draw(); };
  img.src = media({ kind: "refs", f: name });
  $("#annotator").hidden = false; $("#saved").textContent = doc.updated ? `saved ${doc.updated}` : "";
  renderItems();
  $("#annotator").scrollIntoView({ behavior: "smooth" });
}

function sizeCanvas() {
  const img = $("#photo"), c = $("#ink");
  c.width = img.clientWidth * devicePixelRatio; c.height = img.clientHeight * devicePixelRatio;
  c.style.width = img.clientWidth + "px"; c.style.height = img.clientHeight + "px";
}

const COLORS = { line: "#ff5a36", point: "#2fa8ff", rect: "#ffc233", arrow: "#b46cff" };

function draw(preview) {
  const c = $("#ink"), x = c.getContext("2d"), W = c.width, H = c.height;
  x.clearRect(0, 0, W, H);
  const all = preview ? [...state.items, preview] : state.items;
  all.forEach((it, i) => {
    const col = COLORS[it.kind], sel = i === state.sel;
    const [a, b] = [it.pts[0], it.pts[1] || it.pts[0]].map(([u, v]) => [u * W, v * H]);
    x.strokeStyle = col; x.fillStyle = col; x.lineWidth = (sel ? 4 : 2.5) * devicePixelRatio;
    x.beginPath();
    if (it.kind === "point") { x.arc(a[0], a[1], 7 * devicePixelRatio, 0, 7); x.fill(); }
    else if (it.kind === "rect") x.strokeRect(a[0], a[1], b[0] - a[0], b[1] - a[1]);
    else {
      x.moveTo(a[0], a[1]); x.lineTo(b[0], b[1]); x.stroke();
      if (it.kind === "arrow") {
        const ang = Math.atan2(b[1] - a[1], b[0] - a[0]), L = 14 * devicePixelRatio;
        x.beginPath(); x.moveTo(b[0], b[1]);
        x.lineTo(b[0] - L * Math.cos(ang - .4), b[1] - L * Math.sin(ang - .4));
        x.lineTo(b[0] - L * Math.cos(ang + .4), b[1] - L * Math.sin(ang + .4)); x.fill();
      }
    }
    const text = [it.tag, it.length_m ? `${it.length_m} m` : "", it.label].filter(Boolean).join(" · ");
    if (text) {
      x.font = `${12 * devicePixelRatio}px Helvetica, Arial, sans-serif`;
      const tx = (a[0] + b[0]) / 2 + 8, ty = (a[1] + b[1]) / 2 - 8, tw = x.measureText(text).width;
      x.fillStyle = "rgba(0,0,0,.72)"; x.fillRect(tx - 4, ty - 14 * devicePixelRatio, tw + 8, 18 * devicePixelRatio);
      x.fillStyle = "#fff"; x.fillText(text, tx, ty);
    }
  });
}

function pos(ev) {
  const r = $("#ink").getBoundingClientRect();
  return [Math.min(1, Math.max(0, (ev.clientX - r.left) / r.width)),
          Math.min(1, Math.max(0, (ev.clientY - r.top) / r.height))];
}

let drag = null;
function onDown(ev) {
  ev.preventDefault(); $("#ink").setPointerCapture(ev.pointerId);
  const p = pos(ev);
  drag = { kind: state.tool, pts: state.tool === "point" ? [p] : [p, p], label: "" };
  draw(drag);
}
function onMove(ev) { if (drag && drag.pts.length === 2) { drag.pts[1] = pos(ev); draw(drag); } }
function onUp() {
  if (!drag) return;
  const [a, b] = [drag.pts[0], drag.pts[1] || drag.pts[0]];
  if (drag.kind === "point" || Math.hypot(a[0] - b[0], a[1] - b[1]) > 0.01) {
    drag.id = Math.random().toString(36).slice(2, 10);
    state.items.push(drag); state.sel = state.items.length - 1; dirty();
  }
  drag = null; renderItems(); draw();
  const inp = document.querySelector(".item.sel input"); if (inp) inp.focus();
}

function renderItems() {
  const box = $("#items"); box.replaceChildren();
  if (!state.items.length) box.append(h("p", { class: "muted" },
    "Measure: drag along something you have measured, then type its length. ",
    "Tag: click a door or window and give it the tag used in the room model (D1, W1)."));
  state.items.forEach((it, i) => {
    const field = (key, ph, type = "text") => h("input", {
      type, placeholder: ph, value: it[key] ?? "", step: type === "number" ? "0.001" : undefined,
      on: { input: (e) => { it[key] = type === "number" && e.target.value !== "" ? Number(e.target.value) : e.target.value; dirty(); draw(); },
            focus: () => { state.sel = i; draw(); } } });
    box.append(h("div", { class: "item" + (i === state.sel ? " sel" : "") },
      h("header", {}, h("strong", {}, it.kind), h("span", { class: "spacer" }),
        h("button", { on: { click: () => { state.items.splice(i, 1); state.sel = -1; dirty(); renderItems(); draw(); } } }, "Delete")),
      it.kind === "line" ? field("length_m", "measured length, metres", "number") : null,
      it.kind === "point" || it.kind === "rect" ? field("tag", "tag, e.g. D1, W2, RAD") : null,
      field("label", "note")));
  });
}

function dirty() { $("#saved").textContent = "unsaved changes"; }

async function save() {
  try {
    const doc = await api(`/api/annotations?${q({ image: state.photo })}`,
                          { method: "PUT", body: { items: state.items } });
    state.items = doc.items; $("#saved").textContent = `saved ${doc.updated}`;
    renderItems(); draw(); loadRoom();
  } catch (e) { toast(e.message); }
}

// ---------------------------------------------------------------- revisions

function renderRevisions() {
  const box = $("#revlist"); box.replaceChildren();
  const room = state.room;
  if (!room.nested) {
    box.append(h("p", { class: "muted" }, "Single-room projects have no revisions. Start a nested one with: design init <project>/<room>"));
    return;
  }
  for (const r of room.revisions) {
    const isHead = r.id === room.head;
    box.append(h("div", { class: "rev" },
      h("span", { class: "id" }, r.id),
      isHead ? h("span", { class: "badge ok" }, "HEAD") : null,
      h("span", { class: "note" }, r.note || "", r.parent ? h("span", { class: "muted" }, `  ← ${r.parent}`) : null),
      h("span", { class: "muted" }, `${r.renders.length} renders`),
      h("button", { disabled: isHead, on: { click: () => setHead(r.id) } }, "Make HEAD"),
      h("button", { on: { click: () => branch(r.id) } }, "Branch")));
  }
  const ids = room.revisions.map((r) => r.id);
  for (const [sel, pick] of [["#revA", ids[Math.max(0, ids.length - 2)]], ["#revB", ids[ids.length - 1]]]) {
    const s = $(sel), keep = s.value; s.replaceChildren(...ids.map((id) => h("option", { value: id }, id)));
    s.value = ids.includes(keep) ? keep : pick;
  }
  fillFlipFiles();
}

function fillFlipFiles() {
  const by = Object.fromEntries(state.room.revisions.map((r) => [r.id, r]));
  const A = by[$("#revA").value], B = by[$("#revB").value];
  const s = $("#flipfile"), keep = s.value;
  const opts = [];
  if (A && B) {
    for (const kind of ["renders", "drawings"])
      for (const f of A[kind]) if (B[kind].includes(f)) opts.push(`${kind}/${f}`);
  }
  s.replaceChildren(...opts.map((o) => h("option", { value: o }, o)));
  if (opts.includes(keep)) s.value = keep;
  if (!opts.length) s.append(h("option", { value: "" }, "no image in both — render them first"));
  showFlip();
}

function showFlip() {
  const v = $("#flipfile").value, img = $("#flipimg");
  if (!v) { img.removeAttribute("src"); $("#fliplabel").textContent = ""; return; }
  const [kind, f] = v.split("/");
  const rev = state.flipSide === "A" ? $("#revA").value : $("#revB").value;
  img.src = media({ kind, f, rev });
  $("#fliplabel").textContent = `${state.flipSide} · ${rev}`;
}

function flip() { state.flipSide = state.flipSide === "A" ? "B" : "A"; showFlip(); }

async function setHead(rev) {
  try { await api(`/api/head?${q()}`, { method: "POST", body: { rev } }); toast(`HEAD is now ${rev}`); await loadTree(); await loadRoom(); }
  catch (e) { toast(e.message); }
}

async function branch(from) {
  const note = prompt(`New revision from ${from}. What are you trying?`);
  if (note === null) return;
  try {
    const r = await api(`/api/revision?${q()}`, { method: "POST", body: { from, note } });
    toast(`created ${r.id} (HEAD unchanged — make it HEAD to work on it)`); await loadRoom();
  } catch (e) { toast(e.message); }
}

// ---------------------------------------------------------------- catalog

async function loadCatalog() {
  const { items } = await api("/api/catalog");
  const box = $("#cat"); box.replaceChildren();
  if (!items.length) { box.append(h("p", { class: "muted" }, "The catalog is empty. Ask Claude to research an item.")); return; }
  const m = (v) => (typeof v === "number" ? `${Math.round(v * 1000)}` : "?");
  const rows = items.map((it) => {
    const fp = it.footprint || {}, cl = (it.use || {}).clearance || {};
    const v = it.verification.state;
    const badge = v === "verified" ? "ok" : v === "changed" ? "bad" : "warn";
    return h("tr", {},
      h("td", {}, h("strong", {}, it.name || it.id), h("div", { class: "muted" }, it.id)),
      h("td", {}, it.status || ""),
      h("td", {}, `${m(fp.w)} × ${m(fp.d)} × ${m(fp.h)} mm`, fp.source_text ? h("div", { class: "muted" }, fp.source_text) : null),
      h("td", {}, Object.entries(cl).map(([k, val]) => `${k} ${m(val)}`).join(", ")),
      h("td", {}, h("ul", {}, (it.sources || []).map((s) => h("li", {},
        /^https:\/\//.test(s.url || "") ? h("a", { href: s.url, target: "_blank", rel: "noopener noreferrer" }, s.title || s.url) : (s.title || "?"),
        s.confidence ? h("span", { class: "muted" }, ` · ${s.confidence}`) : null)))),
      h("td", {}, h("span", { class: `badge ${badge}` }, v),
        [...it.errors.map((e) => h("div", { class: "badge bad" }, e)), ...it.warnings.map((w) => h("div", { class: "muted" }, "! " + w))],
        v !== "verified" && !it.errors.length ? h("div", {}, h("button", { on: { click: () => verify(it) } }, "I checked these numbers")) : null));
  });
  box.append(h("table", {}, h("thead", {}, h("tr", {}, ["Item", "Status", "Footprint (w × d × h)", "Clearance to use", "Sources", "Verified"].map((t) => h("th", {}, t)))), h("tbody", {}, rows)));
}

async function verify(it) {
  if (!confirm(`Verify ${it.id}? You are confirming its dimensions and sources are right. Any later edit to the file un-verifies it.`)) return;
  try { await api("/api/catalog/verify", { method: "POST", body: { id: it.id } }); toast(`verified ${it.id}`); loadCatalog(); }
  catch (e) { toast(e.message); }
}

// ---------------------------------------------------------------- wiring

document.addEventListener("DOMContentLoaded", () => {
  document.querySelectorAll("header nav button").forEach((b) => b.addEventListener("click", () => {
    document.querySelectorAll("header nav button").forEach((x) => x.classList.toggle("on", x === b));
    document.querySelectorAll(".tab").forEach((t) => t.classList.toggle("on", t.id === b.dataset.tab));
    if (b.dataset.tab === "catalog") loadCatalog();
  }));
  document.querySelectorAll(".toolbar [data-tool]").forEach((b) => b.addEventListener("click", () => {
    state.tool = b.dataset.tool;
    document.querySelectorAll(".toolbar [data-tool]").forEach((x) => x.classList.toggle("on", x === b));
  }));
  const drop = $("#drop");
  $("#file").addEventListener("change", (e) => upload([...e.target.files]));
  drop.addEventListener("dragover", (e) => { e.preventDefault(); drop.classList.add("over"); });
  drop.addEventListener("dragleave", () => drop.classList.remove("over"));
  drop.addEventListener("drop", (e) => { e.preventDefault(); drop.classList.remove("over"); upload([...e.dataTransfer.files]); });
  const ink = $("#ink");
  ink.addEventListener("pointerdown", onDown); ink.addEventListener("pointermove", onMove);
  ink.addEventListener("pointerup", onUp);
  window.addEventListener("resize", () => { if (state.photo) { sizeCanvas(); draw(); } });
  $("#save").addEventListener("click", save);
  $("#close").addEventListener("click", () => { $("#annotator").hidden = true; state.photo = null; });
  $("#revA").addEventListener("change", fillFlipFiles); $("#revB").addEventListener("change", fillFlipFiles);
  $("#flipfile").addEventListener("change", showFlip); $("#flip").addEventListener("click", flip);
  document.addEventListener("keydown", (e) => {
    if (e.code === "Space" && $("#revisions").classList.contains("on") && e.target.tagName !== "INPUT") { e.preventDefault(); flip(); }
  });
  loadTree().catch((e) => toast(e.message));
});
