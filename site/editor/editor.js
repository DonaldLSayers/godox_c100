// The firmware editor: 8 preset slots (palette, S-curve, film, tag, display code), each
// on or off, rnd, the Game Boy Camera mode and its colours, the corner tag and sounds
// with their volume; previewed on nine photos, kept in localStorage,
// and built into a firmware in the browser (firmware.js) from the template.
import { buildFirmware, configErrors, encodeWav, hexToYuv, lumaFix, sha256, slotSamples, tagCells, tagColours, tagWidth, toneCurve, yuvToHex, yuvToRgb } from "./firmware.js";
import { paintColours } from "./films.js";
import { buildLut, cameraFrame, render, renderGb } from "./sim.js";

const STORE = "c100-editor-v2";
// a 3 x 3 grid: streets, natural, close-ups
const PHOTOS = [
  "street_sign", "street_duck", "snail", "hydrangeas", "mimosa", "turtle", "cup", "IMG_0577", "dessert",
].map((f) => `editor/photos/${f}.jpg`);
const noPhotos = () => PHOTOS.map(() => null);
const DEFAULT_SLOTS = [
  "EP6", "6FP", "BW", "endesga32 (32)",
  "db16 + mixes (24)", "sweetie16 (16)", "riso6 + mixes (10)", "nes (32)",
];
const SOUND_PRESETS = { stock: "Stock", mario: "Super Mario" };
const SOUND_LABELS = { shutter: "Shutter", poweron: "Power-on" };
const SEGS = "abcdefg";

// The usual 7-segment letters, one cell each (M and W as well as can be).
const SEG7 = {
  A: "abcefg", B: "abcdefg", C: "adef", D: "bcdeg", E: "adefg", F: "aefg", G: "acdef", H: "bcefg",
  I: "ef", J: "bcde", K: "bcefg", L: "def", M: "abcef", N: "ceg", O: "abcdef", P: "abefg",
  Q: "abcfg", R: "eg", S: "acdfg", T: "defg", U: "bcdef", V: "cde", W: "bcdef", X: "bcefg",
  Y: "bcdfg", Z: "abdeg", 0: "abcdef", 1: "bc", 2: "abdeg", 3: "abcdg", 4: "bcfg", 5: "acdfg",
  6: "acdefg", 7: "abc", 8: "abcdefg", 9: "abcdfg", "-": "g",
};

function autoLcd(tag) {
  const cells = [...tag].map((ch) => SEG7[ch] ?? "");
  while (cells.length < 3) cells.push("");
  return cells.slice(0, 3);
}

const $ = (sel, el = document) => el.querySelector(sel);
const esc = (s) => String(s).replace(/[&<>"]/g, (c) => `&#${c.charCodeAt(0)};`);
const uid = () => Math.random().toString(36).slice(2, 9);
// PostHog (loaded in index.html), if it's there
const track = (event, props) => window.posthog?.capture(`editor_${event}`, props);

let m; // template.json
let library; // library.json: { palettes, films }
let state;
const frames = noPhotos(); // camera-size ImageData per photo
const gbFrames = noPhotos(); // the same at the Game Boy mode's own 8:7 size
const soundCache = {}; // "stock/shutter" -> Uint8Array
const paints = new Map(); // film + colours -> paint colours

// ---- state ----

function slotFrom(item, on) {
  return {
    id: uid(),
    on,
    name: item.name,
    from: item.name,
    tag: item.tag,
    lcd: item.lcd ?? autoLcd(item.tag),
    lcdAuto: !item.lcd || item.lcd.join() === autoLcd(item.tag).join(),
    colours: item.colours.map((c) => [...c]),
    curve: !!item.curve,
    film: item.film,
    sel: 0,
  };
}

function defaultState() {
  const slots = DEFAULT_SLOTS.map((name, i) =>
    slotFrom(library.palettes.find((l) => l.name === name) ?? library.palettes[i], i < 3),
  );
  return {
    slots,
    selected: slots[0].id,
    rnd: true,
    contrast: 0,
    brightness: 0,
    tag: false,
    normal: true,
    gb: { on: true, curve: false, contrast: 0, brightness: 0, sel: 0, from: "Soft grey-green (default)", colours: m.defaults.gb.palette.map((c) => [...c]) },
    gbPreview: false,
    sounds: { on: false, volume: 10, shutter: { src: "stock" }, poweron: { src: "stock" } },
    photos: noPhotos(),
  };
}

function load() {
  try {
    const saved = JSON.parse(localStorage.getItem(STORE));
    if (saved?.slots?.length === m.maxPresets) {
      for (const p of saved.slots) {
        // the S-curve used to be one of the films
        if (p.film === "scurve") Object.assign(p, { film: null, curve: true });
        p.curve = !!p.curve;
      }
      // the preview photos changed: own photos don't carry over
      if (saved.photos?.length !== PHOTOS.length) saved.photos = noPhotos();
      // saved before the Game Boy mode, the corner tag option and the volume
      const fresh = defaultState();
      saved.tag ??= fresh.tag;
      saved.normal ??= fresh.normal;
      saved.contrast ??= 0;
      saved.brightness ??= 0;
      saved.gb ??= fresh.gb;
      // saved with hex colours, before the palette presets and the curve
      if (typeof saved.gb.colours[0] === "string") Object.assign(saved.gb, { colours: saved.gb.colours.map(hexToYuv), from: null });
      saved.gb.curve ??= false;
      saved.gb.contrast ??= 0;
      saved.gb.brightness ??= 0;
      saved.gb.sel ??= 0;
      saved.gbPreview = false;
      saved.sounds.volume ??= fresh.sounds.volume;
      return saved;
    }
  } catch {}
  return defaultState();
}

let saveTimer = 0;
function save() {
  clearTimeout(saveTimer);
  saveTimer = setTimeout(() => {
    try {
      localStorage.setItem(STORE, JSON.stringify(state));
    } catch {
      // full (big uploaded photos): keep the rest
      try {
        localStorage.setItem(STORE, JSON.stringify({ ...state, photos: noPhotos() }));
      } catch {}
    }
  }, 250);
}

const current = () => state.slots.find((p) => p.id === state.selected) ?? state.slots[0];
// what the right-hand panel edits: the selected palette, or the Game Boy mode (4 colours, a curve)
const target = () => (state.gbPreview ? state.gb : current());
const enabled = () => state.slots.filter((p) => p.on);
const film = (p) => library.films.find((f) => f.id === p.film) ?? null;

async function paintOf(p) {
  const key = `${p.film}|${p.curve}|${p.colours.join(" ")}`;
  if (!paints.has(key)) paints.set(key, await paintColours(film(p), p.curve ? library.curve : null, p.colours));
  return paints.get(key);
}

async function config() {
  const on = enabled();
  return {
    presets: await Promise.all(
      on.map(async (p) => ({ tag: p.tag, match: p.colours, paint: await paintOf(p), lcd: p.lcd })),
    ),
    rnd: state.rnd && on.length > 1,
    sounds: state.sounds.on,
    volume: state.sounds.volume,
    tag: state.tag,
    contrast: state.contrast,
    brightness: state.brightness,
    normal: state.normal,
    gb: { on: state.gb.on, curve: state.gb.curve, contrast: state.gb.contrast, brightness: state.gb.brightness, palette: state.gb.colours },
  };
}

function changed({ list = true, palette = false, preview = true } = {}) {
  if (list) renderList();
  if (palette) renderPalette();
  renderHead();
  renderDownload();
  if (preview) schedulePreview();
  save();
}

// ---- 7-segment cells ----

const SEG_RECTS = {
  a: [2, 0, 8, 2], b: [10, 2, 2, 7], c: [10, 11, 2, 7], d: [2, 18, 8, 2],
  e: [0, 11, 2, 7], f: [0, 2, 2, 7], g: [2, 9, 8, 2],
};

function segSvg(segs, cell) {
  const rects = [...SEGS]
    .map((s) => {
      const [x, y, w, h] = SEG_RECTS[s];
      return `<rect class="seg${segs.includes(s) ? " on" : ""}" data-seg="${s}" x="${x}" y="${y}" width="${w}" height="${h}" />`;
    })
    .join("");
  return `<svg class="seg7" data-cell="${cell}" viewBox="-3 -2 18 24" aria-hidden="true">${rects}</svg>`;
}

// The segment nearest the pointer, so the whole display is one big target:
// every point of a cell belongs to one of its segments.
function segAt(e) {
  const svg = e.target.closest?.(".seg7");
  if (!svg) return null;
  const pt = new DOMPoint(e.clientX, e.clientY).matrixTransform(svg.getScreenCTM().inverse());
  let best = null;
  let dist = Infinity;
  for (const [s, [x, y, w, h]] of Object.entries(SEG_RECTS)) {
    const dx = Math.max(x - pt.x, 0, pt.x - (x + w));
    const dy = Math.max(y - pt.y, 0, pt.y - (y + h));
    const d = dx * dx + dy * dy;
    if (d < dist) (dist = d), (best = s);
  }
  return { svg, cell: +svg.dataset.cell, seg: best };
}

function hoverSeg(e) {
  const at = e.type === "mouseleave" ? null : segAt(e);
  for (const r of document.querySelectorAll("#ed-lcd .seg.hover")) r.classList.remove("hover");
  if (at) at.svg.querySelector(`[data-seg="${at.seg}"]`).classList.add("hover");
}

// ---- the slot list ----

async function renderStrips() {
  for (const li of document.querySelectorAll("#ed-list li")) {
    const p = state.slots.find((q) => q.id === li.dataset.id);
    const paint = await paintOf(p);
    const strip = li.querySelector(".ed-strip");
    if (strip) strip.innerHTML = paint.map((c) => `<i style="background:${yuvToHex(c)}"></i>`).join("");
    const tag = li.querySelector(".ed-tagc");
    if (tag) drawTag(tag, p.tag, paint, 3, true);
  }
}

function renderList() {
  const on = enabled().length;
  $("#ed-count").textContent = `${on} of ${m.maxPresets}`;
  $("#ed-list").innerHTML = state.slots
    .map(
      (p) => `
      <li class="${p.id === state.selected && !state.gbPreview ? "sel" : ""} ${p.on ? "" : "off"} ${drag?.id === p.id && drag.moved ? "lifted" : ""}"
          data-id="${p.id}" tabindex="0" aria-current="${p.id === state.selected}">
        <input type="checkbox" class="ed-on" ${p.on ? "checked" : ""} aria-label="Put ${esc(p.tag)} on the camera" />
        <span class="ed-pick">
          ${tagCanvas("ed-tagc", p.tag, 3, true)}
          <span class="ed-name">${esc(p.name)}</span>
          <span class="ed-strip"></span>
        </span>
        <span class="ed-handle" aria-hidden="true" title="Drag to rearrange"><i></i><i></i><i></i></span>
      </li>`,
    )
    .join("");
  renderGbList();
  const rnd = $("#ed-rnd");
  rnd.checked = state.rnd && on > 1;
  rnd.disabled = on < 2;
  renderStrips();
}

function select(id) {
  if (state.selected === id && !state.gbPreview) return;
  state.gbPreview = false;
  state.selected = id;
  changed({ palette: true });
  track("select_palette", { tag: current().tag, name: current().name });
}

function move(id, to) {
  const from = state.slots.findIndex((p) => p.id === id);
  if (to === from || to < 0 || to >= state.slots.length) return false;
  const [p] = state.slots.splice(from, 1);
  state.slots.splice(to, 0, p);
  return true;
}

// Click a row to select it; drag it (or its handle, on touch screens) to move it.
let drag = null;

function listPointerDown(e) {
  const li = e.target.closest("li");
  if (!li || e.target.closest("input") || e.button > 0) return;
  // on touch screens only the handle drags, so the list still scrolls
  const tap = e.pointerType !== "mouse" && !e.target.closest(".ed-handle");
  drag = { id: li.dataset.id, y: e.clientY, moved: false, tap };
  if (tap) return;
  try {
    e.currentTarget.setPointerCapture(e.pointerId);
  } catch {} // a pointer the browser doesn't track: the drag just follows the list's own events
  e.preventDefault();
}

function listPointerMove(e) {
  if (!drag) return;
  if (!drag.moved && Math.abs(e.clientY - drag.y) < 5) return;
  if (drag.tap) return (drag = null);
  if (!drag.moved) {
    drag.moved = true;
    $("#ed-list").classList.add("dragging");
    renderList();
  }
  const rows = [...$("#ed-list").children].filter((li) => li.dataset.id !== drag.id);
  const to = rows.filter((li) => {
    const r = li.getBoundingClientRect();
    return r.top + r.height / 2 < e.clientY;
  }).length;
  if (move(drag.id, to)) renderList();
}

function listPointerUp(e) {
  if (!drag) return;
  const { id, moved } = drag;
  drag = null;
  $("#ed-list").classList.remove("dragging");
  if (moved) {
    changed();
    track("reorder_palette", { via: "drag" });
  } else if (e.type === "pointerup") select(id);
  else renderList();
}

function listChange(e) {
  if (!e.target.matches(".ed-on")) return;
  const p = state.slots.find((q) => q.id === e.target.closest("li").dataset.id);
  p.on = e.target.checked;
  changed();
  track("toggle_palette", { tag: p.tag, on: p.on, palettes: enabled().length });
}

function listKey(e) {
  const li = e.target.closest("li");
  if (!li || e.target.closest("input")) return;
  const i = state.slots.findIndex((p) => p.id === li.dataset.id);
  if (e.key === "Enter" || e.key === " ") {
    e.preventDefault();
    select(li.dataset.id);
  } else if (e.altKey && (e.key === "ArrowUp" || e.key === "ArrowDown")) {
    e.preventDefault();
    if (move(li.dataset.id, i + (e.key === "ArrowUp" ? -1 : 1))) {
      changed();
      $(`#ed-list li[data-id="${li.dataset.id}"]`).focus();
      track("reorder_palette", { via: "keyboard" });
    }
  }
}

// ---- the preview and edit area ----

// The tag as the camera draws it on photos: letters in the paint colours'
// lightest, a one-cell outline in their darkest; `field` pads it on the left
// to the camera's 3-letter field, so a column of tags lines up on the right.
function drawTag(canvas, tag, paint, scale, field) {
  if (!canvas.getContext) return; // the tag option is off: a plain text badge
  const drawable = tag && [...tag].every((ch) => m.font[ch]) && tagWidth(m, tag) <= m.tag.cols;
  const cells = drawable ? tagCells(m, tag, field ? m.tag.cols : undefined) : [];
  canvas.width = cells[0]?.length ?? (field ? m.tag.cols : 1);
  canvas.height = m.tag.rows;
  canvas.style.width = `${canvas.width * scale}px`;
  canvas.style.height = `${canvas.height * scale}px`;
  const ctx = canvas.getContext("2d");
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  const [dark, light] = tagColours(paint).map((i) => yuvToHex(paint[i]));
  cells.forEach((row, y) =>
    row.forEach((v, x) => {
      if (!v) return;
      ctx.fillStyle = v === 1 ? dark : light;
      ctx.fillRect(x, y, 1, 1);
    }),
  );
}

// A tag's canvas at its final size: it's drawn once the preset's paint
// colours are known, which can take a moment (a film to download), and an
// unsized canvas is 300x150 until then.
function tagCanvas(cls, tag, scale, field) {
  if (!state.tag) return `<span class="${cls} ed-tagt" role="img" aria-label="${esc(tag)}">${esc(tag)}</span>`;
  const drawable = tag && [...tag].every((ch) => m.font[ch]) && tagWidth(m, tag) <= m.tag.cols;
  const w = field ? m.tag.cols : drawable ? tagWidth(m, tag) : 1;
  const h = m.tag.rows;
  return `<canvas class="${cls}" role="img" aria-label="${esc(tag)}" width="${w}" height="${h}"
    style="width:${w * scale}px;height:${h * scale}px"></canvas>`;
}

async function renderTagShown() {
  const p = current();
  const paint = await paintOf(p);
  const canvas = $("#ed-tag-shown");
  if (canvas && current() === p) drawTag(canvas, p.tag, paint, 5, false);
}

async function renderHead() {
  if (state.gbPreview) {
    $("#ed-work-head").innerHTML = `<span class="ed-tagt">GB</span>
      <span><strong>Preview and edit this mode</strong> &middot; Game Boy Camera${headCredit(library.gbPalettes, state.gb.from)}</span>`;
    return;
  }
  const p = current();
  const f = film(p);
  $("#ed-work-head").innerHTML = `
    ${tagCanvas("ed-tagc", p.tag, 3, false)}
    <span><strong>Preview and edit this palette</strong> &middot; ${esc(p.name)}${p.curve ? " &middot; S-curve" : ""}${f ? ` &middot; ${esc(f.name)}` : ""}${headCredit(library.palettes, p.from)}</span>`;
  const paint = await paintOf(p);
  const canvas = $("#ed-work-head .ed-tagc");
  if (canvas && current() === p) drawTag(canvas, p.tag, paint, 3, false);
}

function tagProblem(p) {
  if (!p.tag) return "Give it a tag.";
  const bad = [...p.tag].find((ch) => !m.font[ch]);
  if (bad) return `No "${bad}" in the camera's tag font.`;
  if (tagWidth(m, p.tag) > m.tag.cols) return "Too wide for the photo tag (its W is extra wide).";
  if (p.on && enabled().some((q) => q !== p && q.tag === p.tag)) return "Another palette already has this tag.";
  return "";
}

// "Palette: Name by Author · Lospec" for a preset in `list`, or "Custom colours." once its colours were edited.
function creditLine(list, from) {
  const item = list?.find((l) => l.name === from);
  if (!item) return "Custom colours.";
  if (!item.author && !item.url) return ""; // the project's own presets
  const by = item.author ? ` by ${esc(item.author)}` : "";
  const link = item.url ? ` &middot; <a href="${item.url}" target="_blank" rel="noopener">Lospec</a>` : "";
  return `Palette: <strong>${esc(item.name)}</strong>${by}${link}`;
}
const gbCredit = () => creditLine(library.gbPalettes, state.gb.from);
const paletteCredit = (p) => creditLine(library.palettes, p.from);

// " · by Author · Lospec" for the work header, for a preset in `list` (nothing for the project's own or edited ones).
function headCredit(list, from) {
  const item = list?.find((l) => l.name === from);
  if (!item || (!item.author && !item.url)) return "";
  const by = item.author ? ` &middot; by ${esc(item.author)}` : "";
  const link = item.url ? ` &middot; <a href="${item.url}" target="_blank" rel="noopener">Lospec</a>` : "";
  return by + link;
}

function renderPalette() {
  const gbMode = state.gbPreview;
  const p = gbMode ? null : current();
  $("#ed-palette").innerHTML = `
    ${gbMode ? `<p class="note">128&times;112 pixels (photos and video are 512&times;448, 8:7), four shades, the Game Boy Camera's own
      dithering, sharpening and exposure. It comes after rnd in the center button's cycle; the display shows
      <code>Gb</code>. Four colours, dark to light. The look follows <a href="https://github.com/untoxa/gb-photo" target="_blank" rel="noopener">gb-photo</a>
      by Toxa and the Pan Docs reference, through the maths in <a href="https://donaldsayers.com" target="_blank" rel="noopener">Donald Sayers'</a>
      <a href="https://github.com/DonaldLSayers/PixelBoy-ESP32-P4X-EYE" target="_blank" rel="noopener">PixelBoy</a>.</p>` : ""}
    <div class="ed-row">
      <label for="ed-from">Preset</label>
      <select id="ed-from">
        <option value="">Start from&hellip;</option>
        ${(gbMode ? library.gbPalettes ?? [] : library.palettes).map((l, i) => `<option value="${i}">${esc(l.name)}</option>`).join("")}
      </select>
    </div>
    <div class="ed-row ed-credit" id="ed-credit">${gbMode ? gbCredit() : paletteCredit(p)}</div>
    <div class="ed-row">
      <span class="label">Curve</span>
      <label class="ed-check"><input type="checkbox" id="ed-curve" ${(gbMode ? state.gb.curve : p.curve) ? "checked" : ""} /> S-curve: more contrast (as BW)</label>
    </div>
    ${gbMode ? `<div class="ed-row">
      <label for="ed-contrast">Contrast</label>
      <input type="range" id="ed-contrast" min="-50" max="50" step="1" value="${state.gb.contrast}" />
      <output id="ed-contrast-out">${state.gb.contrast}</output>
    </div>
    <div class="ed-row">
      <label for="ed-brightness">Brightness</label>
      <input type="range" id="ed-brightness" min="-50" max="50" step="1" value="${state.gb.brightness}" />
      <output id="ed-brightness-out">${state.gb.brightness}</output>
    </div>` : ""}
    ${gbMode ? "" : `<div class="ed-row">
      <label for="ed-contrast">Contrast</label>
      <input type="range" id="ed-contrast" min="-50" max="50" step="1" value="${state.contrast}" />
      <output id="ed-contrast-out">${state.contrast}</output>
    </div>
    <div class="ed-row">
      <label for="ed-brightness">Brightness</label>
      <input type="range" id="ed-brightness" min="-50" max="50" step="1" value="${state.brightness}" />
      <output id="ed-brightness-out">${state.brightness}</output>
    </div>
    <p class="note">Contrast and brightness are the same for every palette.</p>
    <div class="ed-row">
      <label for="ed-film">Film</label>
      <select id="ed-film">
        <option value="">None</option>
        ${library.films.map((f) => `<option value="${f.id}" ${f.id === p.film ? "selected" : ""}>${esc(f.name)}</option>`).join("")}
      </select>
    </div>
    <div class="ed-row ed-tagrow">
      <label for="ed-tag">Tag</label>
      <input id="ed-tag" value="${esc(p.tag)}" maxlength="3" autocomplete="off" spellcheck="false" />
      ${tagCanvas("ed-tag-shown", p.tag, 5, false).replace("<canvas", '<canvas id="ed-tag-shown" title="The tag as the camera draws it"')}
      <span class="ed-problem" id="ed-tag-problem">${esc(tagProblem(p))}</span>
    </div>
    <div class="ed-row">
      <span class="label">Display</span>
      <span class="ed-lcd" id="ed-lcd">${p.lcd.map((s, i) => segSvg(s, i)).join("")}</span>
      <label class="ed-check"><input type="checkbox" id="ed-lcd-auto" ${p.lcdAuto ? "checked" : ""} /> follow the tag</label>
    </div>`}
    <div class="ed-row ed-colours-head">
      <span class="label">Colours</span>
      <span class="ed-ncol" id="ed-ncol"></span>
    </div>
    <div class="ed-swatches" id="ed-swatches"></div>
    <div class="ed-colour" id="ed-colour">
      <div class="ed-colour-head">
        <span id="ed-colour-name"></span>
        <span>
          <button type="button" id="ed-dupcol">Duplicate</button>
          <button type="button" id="ed-delcol">Remove</button>
        </span>
      </div>
      <div class="ed-sv" id="ed-sv"><canvas width="256" height="128"></canvas><i class="ed-node"></i></div>
      <div class="ed-hue" id="ed-hue"><i class="ed-node"></i></div>
      <div class="ed-hexrow"><label for="ed-hex">Hex</label><input id="ed-hex" maxlength="7" spellcheck="false" autocomplete="off" /></div>
    </div>`;
  renderSwatches();
  pickerFromColour();
  renderTagShown();
}

function renderSwatches() {
  const p = target();
  $("#ed-ncol").textContent = state.gbPreview ? "4 shades" : `${p.colours.length} of ${m.maxColours}`;
  $("#ed-swatches").innerHTML = p.colours
    .map(
      (c, i) => `<button type="button" class="sw${i === p.sel ? " sel" : ""}" data-i="${i}"
        style="--c:${yuvToHex(c)}" aria-label="Colour ${i + 1}" aria-pressed="${i === p.sel}"></button>`,
    )
    .join("");
  $("#ed-dupcol").hidden = $("#ed-delcol").hidden = state.gbPreview; // the Game Boy mode has exactly 4 colours
  $("#ed-dupcol").disabled = p.colours.length >= m.maxColours;
  $("#ed-dupcol").title = p.colours.length >= m.maxColours ? `${m.maxColours} colours is the most` : "";
  $("#ed-delcol").disabled = p.colours.length < 2;
  $("#ed-colour-name").textContent = `Colour ${p.sel + 1}`;
}

// The colour picker: saturation x value field and a hue strip, for the
// selected colour. hsv is kept while dragging, so greys don't lose their hue.
let hsv = [0, 0, 0];

function rgbToHsv([r, g, b]) {
  r /= 255;
  g /= 255;
  b /= 255;
  const max = Math.max(r, g, b);
  const d = max - Math.min(r, g, b);
  const h = d === 0 ? hsv[0] : max === r ? ((g - b) / d + 6) % 6 : max === g ? (b - r) / d + 2 : (r - g) / d + 4;
  return [d === 0 ? hsv[0] : h * 60, max === 0 ? 0 : d / max, max];
}

function hsvToRgb([h, s, v]) {
  const f = (n) => {
    const k = (n + h / 60) % 6;
    return Math.round(255 * (v - v * s * Math.max(0, Math.min(k, 4 - k, 1))));
  };
  return [f(5), f(3), f(1)];
}

function drawSv() {
  const c = $("#ed-sv canvas");
  const ctx = c.getContext("2d");
  ctx.fillStyle = `hsl(${hsv[0]} 100% 50%)`;
  ctx.fillRect(0, 0, c.width, c.height);
  const white = ctx.createLinearGradient(0, 0, c.width, 0);
  white.addColorStop(0, "#fff");
  white.addColorStop(1, "rgb(255 255 255 / 0)");
  ctx.fillStyle = white;
  ctx.fillRect(0, 0, c.width, c.height);
  const black = ctx.createLinearGradient(0, 0, 0, c.height);
  black.addColorStop(0, "rgb(0 0 0 / 0)");
  black.addColorStop(1, "#000");
  ctx.fillStyle = black;
  ctx.fillRect(0, 0, c.width, c.height);
}

function placeNodes(hex) {
  const sv = $("#ed-sv .ed-node");
  sv.style.left = `${hsv[1] * 100}%`;
  sv.style.top = `${(1 - hsv[2]) * 100}%`;
  sv.style.background = hex;
  const hue = $("#ed-hue .ed-node");
  hue.style.left = `${(hsv[0] / 360) * 100}%`;
  hue.style.background = `hsl(${hsv[0]} 100% 50%)`;
}

function pickerFromColour() {
  const p = target();
  const hex = yuvToHex(p.colours[p.sel]);
  hsv = rgbToHsv(yuvToRgb(p.colours[p.sel]));
  drawSv();
  placeNodes(hex);
  $("#ed-hex").value = hex.toUpperCase();
}

function setColour(yuv) {
  const p = target();
  p.colours[p.sel] = yuv;
  const sw = $(`#ed-swatches .sw[data-i="${p.sel}"]`);
  if (sw) sw.style.setProperty("--c", yuvToHex(yuv));
  if (state.gbPreview) {
    p.from = null;
    $("#ed-credit").innerHTML = gbCredit();
    renderGbList();
    return changed({ list: false, preview: true });
  }
  p.from = null;
  $("#ed-credit").innerHTML = paletteCredit(p);
  renderTagShown();
  changed({ list: false, preview: true });
  renderStrips();
}

function pickerFromHsv() {
  const rgb = hsvToRgb(hsv);
  const hex = "#" + rgb.map((x) => x.toString(16).padStart(2, "0")).join("");
  drawSv();
  placeNodes(hex);
  $("#ed-hex").value = hex.toUpperCase();
  setColour(hexToYuv(hex));
}

let picking = null;

function pickerPointer(e) {
  if (e.type === "pointerdown") {
    const area = e.target.closest("#ed-sv, #ed-hue");
    if (!area || e.button > 0) return;
    picking = area.id;
    area.setPointerCapture(e.pointerId);
    e.preventDefault();
  } else if (e.type === "pointerup" || e.type === "pointercancel") {
    if (picking) track("pick_colour", { via: picking === "ed-sv" ? "field" : "hue", hex: $("#ed-hex").value });
    picking = null;
    return;
  }
  if (!picking) return;
  const r = $(`#${picking}`).getBoundingClientRect();
  const x = Math.min(1, Math.max(0, (e.clientX - r.left) / r.width));
  const y = Math.min(1, Math.max(0, (e.clientY - r.top) / r.height));
  if (picking === "ed-sv") hsv = [hsv[0], x, 1 - y];
  else hsv = [Math.min(x * 360, 359.9), hsv[1], hsv[2]];
  pickerFromHsv();
}

function paletteInput(e) {
  if (e.target.id === "ed-contrast" || e.target.id === "ed-brightness") {
    const key = e.target.id.slice(3);
    (state.gbPreview ? state.gb : state)[key] = +e.target.value;
    $(`#${e.target.id}-out`).textContent = e.target.value;
    return changed({ list: false });
  }
  const p = current();
  if (e.target.id === "ed-tag") {
    const caret = e.target.selectionStart;
    p.tag = e.target.value.toUpperCase().slice(0, 3);
    e.target.value = p.tag;
    e.target.setSelectionRange(caret, caret);
    if (p.lcdAuto) {
      p.lcd = autoLcd(p.tag);
      $("#ed-lcd").innerHTML = p.lcd.map((s, i) => segSvg(s, i)).join("");
    }
    $("#ed-tag-problem").textContent = tagProblem(p);
    renderTagShown();
    return changed();
  }
  if (e.target.id === "ed-hex") {
    const v = e.target.value.trim().replace(/^#?/, "#");
    if (/^#[0-9a-f]{6}$/i.test(v)) {
      hsv = rgbToHsv([1, 3, 5].map((i) => parseInt(v.slice(i, i + 2), 16)));
      drawSv();
      placeNodes(v);
      setColour(hexToYuv(v));
    }
  }
}

function paletteChange(e) {
  const p = current();
  if (state.gbPreview && e.target.id === "ed-from" && e.target.value !== "") {
    const item = library.gbPalettes[+e.target.value];
    Object.assign(state.gb, { colours: item.colours.map((h) => hexToYuv("#" + h)), sel: 0, from: item.name });
    track("choose_gb_palette", { palette: item.name });
    return changed({ palette: true });
  }
  if (state.gbPreview && e.target.id === "ed-curve") {
    state.gb.curve = e.target.checked;
    track("toggle_gb_curve", { on: state.gb.curve });
    return changed({ list: false });
  }
  if (e.target.id === "ed-from" && e.target.value !== "") {
    const item = library.palettes[+e.target.value];
    const fresh = slotFrom(item, p.on);
    Object.assign(p, { name: item.name, from: item.name, colours: fresh.colours, curve: fresh.curve, film: item.film, sel: 0 });
    if (!enabled().some((q) => q !== p && q.tag === item.tag)) Object.assign(p, { tag: item.tag, lcd: fresh.lcd, lcdAuto: fresh.lcdAuto });
    track("choose_preset", { preset: item.name });
    return changed({ palette: true });
  }
  if (e.target.id === "ed-film" || e.target.id === "ed-curve") {
    if (e.target.id === "ed-film") {
      p.film = e.target.value || null;
      track("choose_film", { film: film(p)?.name ?? "none" });
    } else {
      p.curve = e.target.checked;
      track("toggle_curve", { on: p.curve });
    }
    renderTagShown();
    renderStrips();
    return changed({ list: false });
  }
  if (e.target.id === "ed-lcd-auto") {
    p.lcdAuto = e.target.checked;
    if (p.lcdAuto) p.lcd = autoLcd(p.tag);
    track("toggle_display_follows_tag", { on: p.lcdAuto });
    return changed({ palette: true, preview: false });
  }
  // typing is tracked once it's done (the input loses focus)
  if (e.target.id === "ed-tag") track("change_tag", { tag: p.tag, problem: tagProblem(p) || null });
  if (e.target.id === "ed-hex") {
    const t = target();
    track("pick_colour", { via: "hex", hex: yuvToHex(t.colours[t.sel]).toUpperCase() });
    pickerFromColour();
  }
}

function paletteClick(e) {
  const p = current();
  const at = e.target.closest("#ed-lcd") && segAt(e);
  if (at) {
    const cur = p.lcd[at.cell];
    p.lcd[at.cell] = [...SEGS].filter((x) => (x === at.seg ? !cur.includes(x) : cur.includes(x))).join("");
    p.lcdAuto = false;
    $("#ed-lcd").innerHTML = p.lcd.map((s, i) => segSvg(s, i)).join("");
    $("#ed-lcd-auto").checked = false;
    hoverSeg(e);
    track("edit_display", { cell: at.cell, segment: at.seg });
    return changed({ list: false, preview: false });
  }
  const sw = e.target.closest(".sw[data-i]");
  if (sw) {
    const t = target();
    t.sel = +sw.dataset.i;
    track("select_colour", { colour: t.sel + 1 });
    renderSwatches();
    pickerFromColour();
    return save();
  }
  if (e.target.closest("#ed-dupcol") || e.target.closest("#ed-delcol")) {
    if (e.target.closest("#ed-dupcol")) {
      p.colours.splice(p.sel + 1, 0, [...p.colours[p.sel]]);
      p.sel++;
    } else {
      p.colours.splice(p.sel, 1);
      p.sel = Math.min(p.sel, p.colours.length - 1);
    }
    track(e.target.closest("#ed-dupcol") ? "duplicate_colour" : "remove_colour", { colours: p.colours.length });
    renderSwatches();
    pickerFromColour();
    renderStrips();
    return changed({ list: false });
  }
}

// ---- preview ----

let previewQueued = false;
function schedulePreview() {
  if (previewQueued) return;
  previewQueued = true;
  requestAnimationFrame(() => {
    previewQueued = false;
    renderPreview();
  });
}

async function renderPreview() {
  const p = current();
  const paint = await paintOf(p);
  if (current() !== p) return;
  const drawable = [...p.tag].every((ch) => m.font[ch]) && tagWidth(m, p.tag) <= m.tag.cols;
  const preset = { tag: state.tag && drawable ? p.tag : "", match: p.colours, paint, ...lumaFix(state.contrast, state.brightness) };
  const lut = buildLut(preset.match, m.wy);
  const gb = state.gb.colours.map(yuvToRgb);
  const gbCurve = toneCurve(m.gb, state.gb.curve, state.gb.contrast, state.gb.brightness);
  document.querySelectorAll(".ed-photo canvas").forEach((canvas, i) => {
    const frame = frames[i];
    if (!frame) return;
    canvas.width = frame.width;
    canvas.height = frame.height;
    canvas._orig = state.gbPreview ? gbFrames[i] : frame;
    canvas.width = canvas._orig.width;
    canvas.height = canvas._orig.height;
    canvas._out = state.gbPreview ? renderGb(m, gbFrames[i], gb, gbCurve) : render(m, frame, preset, lut);
    if (!canvas.matches(":hover")) canvas.getContext("2d").putImageData(canvas._out, 0, 0);
  });
}

function loadPhoto(i) {
  return new Promise((resolve) => {
    const img = new Image();
    img.onload = () => {
      frames[i] = cameraFrame(m, img);
      gbFrames[i] = cameraFrame(m, img, true);
      resolve();
    };
    img.onerror = () => resolve();
    img.src = state.photos[i] ?? PHOTOS[i];
  });
}

function renderPhotos() {
  $("#ed-photos").innerHTML = PHOTOS.map(
    (_, i) => `
    <figure class="ed-photo" data-i="${i}">
      <canvas width="608" height="456"></canvas>
      <figcaption>
        <label class="ed-upload">Your photo&hellip;<input type="file" accept="image/*" /></label>
        ${state.photos[i] ? `<button type="button" class="ed-reset">Reset</button>` : ""}
      </figcaption>
    </figure>`,
  ).join("");
}

function shrinkImage(file, max = 1200) {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => {
      const k = Math.min(1, max / Math.max(img.width, img.height));
      const c = document.createElement("canvas");
      c.width = Math.round(img.width * k);
      c.height = Math.round(img.height * k);
      c.getContext("2d").drawImage(img, 0, 0, c.width, c.height);
      URL.revokeObjectURL(img.src);
      resolve(c.toDataURL("image/jpeg", 0.85));
    };
    img.onerror = reject;
    img.src = URL.createObjectURL(file);
  });
}

async function photoEvents(e) {
  const fig = e.target.closest(".ed-photo");
  if (!fig) return;
  const i = +fig.dataset.i;
  if (e.type === "change" && e.target.files?.[0]) {
    state.photos[i] = await shrinkImage(e.target.files[0]);
    track("upload_photo", { via: "picker" });
  } else if (e.type === "drop") {
    e.preventDefault();
    fig.classList.remove("drop");
    const file = [...e.dataTransfer.files].find((f) => f.type.startsWith("image/"));
    if (!file) return;
    state.photos[i] = await shrinkImage(file);
    track("upload_photo", { via: "drop" });
  } else if (e.type === "click" && e.target.closest(".ed-reset")) {
    state.photos[i] = null;
    track("reset_photo");
  } else if (e.type === "click" && e.target.matches("canvas")) {
    track("open_photo", { photo: i, own: !!state.photos[i] });
    return showLarge(e.target);
  } else return;
  await loadPhoto(i);
  renderPhotos();
  renderPreview();
  save();
}

// The page's photo viewer (main.js), with the photos as the preset renders
// them; the arrow keys step through all of them.
function showLarge(canvas) {
  if (!window.viewer) return;
  const canvases = [...document.querySelectorAll(".ed-photo canvas")].filter((c) => c._out);
  const photos = canvases.map((cv) => () => {
    const c = document.createElement("canvas");
    c.width = cv._out.width;
    c.height = cv._out.height;
    c.getContext("2d").putImageData(cv._out, 0, 0);
    return { src: c.toDataURL(), ar: c.width / c.height };
  });
  window.viewer.open(photos, Math.max(0, canvases.indexOf(canvas)));
}

function hoverPhoto(e) {
  const canvas = e.target.closest?.(".ed-photo canvas");
  if (!canvas) return;
  const i = +canvas.closest(".ed-photo").dataset.i;
  const show = e.type === "mouseover" ? canvas._orig : canvas._out;
  if (show) canvas.getContext("2d").putImageData(show, 0, 0);
}

// ---- the Game Boy Camera mode, the corner tag ----

// The Game Boy mode's row in the palette list (not draggable: it always comes last in the cycle).
function renderGbList() {
  const strip = state.gb.colours.map((c) => `<i style="background:${yuvToHex(c)}"></i>`).join("");
  $("#ed-gb-list").innerHTML = `
    <li class="${state.gbPreview ? "sel" : ""} ${state.gb.on ? "" : "off"}" tabindex="0" aria-current="${state.gbPreview}">
      <input type="checkbox" class="ed-gb-on" ${state.gb.on ? "checked" : ""} aria-label="Put the Game Boy Camera mode on the camera" />
      <span class="ed-pick">
        <img class="cam-tag" src="img/tags/GB.png" width="39" height="21" alt="GB" />
        <span class="ed-name">Game Boy Camera</span>
        <span class="ed-strip">${strip}</span>
      </span>
    </li>`;
}

function selectGb() {
  if (state.gbPreview) return;
  state.gbPreview = true;
  track("select_gb_mode");
  changed({ palette: true });
}

function gbListEvents(e) {
  if (e.target.matches(".ed-gb-on")) {
    if (e.type !== "change") return;
    state.gb.on = e.target.checked;
    track("toggle_gb_mode", { on: state.gb.on });
    return changed({ list: true, preview: false });
  }
  if (e.type === "click" && !e.target.closest("input") && e.target.closest("li")) selectGb();
  else if (e.type === "keydown" && (e.key === "Enter" || e.key === " ") && !e.target.closest("input")) {
    e.preventDefault();
    selectGb();
  }
}

// ---- sounds ----

async function soundBytes(slot) {
  const s = state.sounds[slot];
  if (s.src === "own" && s.wav) return Uint8Array.from(atob(s.wav), (ch) => ch.charCodeAt(0));
  const src = s.src === "own" ? "stock" : s.src;
  const key = `${src}/${slot}`;
  soundCache[key] ??= new Uint8Array(await (await fetch(`editor/sounds/${src}_${slot}.wav`)).arrayBuffer());
  return soundCache[key];
}

// The factory's mode-switch click, slot and all: the template has it silenced.
async function stockClick() {
  soundCache.click ??= new Uint8Array(await (await fetch("editor/sounds/stock_click.wav")).arrayBuffer());
  return soundCache.click;
}

// Any audio file -> 11025 Hz mono 16-bit, leading silence trimmed, cut to the
// slot with a short fade, peak-normalised.
async function convertSound(file, slot) {
  const ctx = new AudioContext();
  const decoded = await ctx.decodeAudioData(await file.arrayBuffer());
  ctx.close();
  const rate = m.wav.rate;
  const len = Math.ceil(Math.min(decoded.duration, 20) * rate);
  const off = new OfflineAudioContext(1, len, rate);
  const src = off.createBufferSource();
  src.buffer = decoded;
  src.connect(off.destination);
  src.start();
  const data = (await off.startRendering()).getChannelData(0);
  const peak = data.reduce((a, x) => Math.max(a, Math.abs(x)), 0) || 1;
  let start = data.findIndex((x) => Math.abs(x) > peak * 0.05);
  start = Math.max(0, start - Math.round(rate * 0.005));
  const n = Math.min(slotSamples(m, slot), data.length - start);
  const fade = Math.min(n, Math.round(rate * 0.02));
  const gain = 0.9 / peak;
  const samples = Int16Array.from({ length: n }, (_, i) => {
    const f = i >= n - fade && n < data.length - start ? (n - i) / fade : 1;
    return Math.max(-32768, Math.min(32767, Math.round(data[start + i] * gain * f * 32767)));
  });
  return { wav: encodeWav(m, samples), cut: data.length - start > n };
}

function renderSounds() {
  const s = state.sounds;
  $("#ed-sound-on").checked = s.on;
  $("#ed-sounds").classList.toggle("off", !s.on);
  $("#ed-volume").value = s.volume;
  $("#ed-volume").disabled = !s.on;
  $("#ed-volume-out").textContent = `${s.volume} %`;
  $("#ed-sound-slots").innerHTML = Object.entries(SOUND_LABELS)
    .map(([slot, label]) => {
      const cur = s[slot];
      const max = (slotSamples(m, slot) / m.wav.rate).toFixed(2);
      return `
      <div class="ed-sound" data-slot="${slot}">
        <span class="label">${label}</span>
        <select class="ed-sound-src" ${s.on ? "" : "disabled"}>
          ${Object.entries(SOUND_PRESETS).map(([k, v]) => `<option value="${k}" ${cur.src === k ? "selected" : ""}>${v}</option>`).join("")}
          <option value="own" ${cur.src === "own" ? "selected" : ""}>${cur.name ? esc(cur.name) : "Your own"}&hellip;</option>
        </select>
        <label class="ed-upload ${s.on ? "" : "dim"}">Upload&hellip;<input type="file" accept="audio/*" ${s.on ? "" : "disabled"} /></label>
        <button type="button" class="ed-play" ${s.on ? "" : "disabled"}>&#9654; Play</button>
        <span class="note">${cur.note ? esc(cur.note) + " " : ""}up to ${max} s</span>
      </div>`;
    })
    .join("");
}

async function soundEvents(e) {
  if (e.target.id === "ed-sound-on") {
    if (e.type !== "change") return;
    state.sounds.on = e.target.checked;
    track("toggle_sounds", { on: state.sounds.on });
    renderSounds();
    return changed({ list: false, preview: false });
  }
  if (e.target.id === "ed-volume") {
    state.sounds.volume = +e.target.value;
    $("#ed-volume-out").textContent = `${state.sounds.volume} %`;
    if (e.type === "change") track("set_volume", { volume: state.sounds.volume });
    return changed({ list: false, preview: false });
  }
  const row = e.target.closest(".ed-sound");
  if (!row) return;
  const slot = row.dataset.slot;
  const s = state.sounds[slot];
  if (e.type === "change" && e.target.matches(".ed-sound-src")) {
    if (e.target.value === "own" && !s.wav) {
      row.querySelector("input[type=file]").click();
      e.target.value = s.src;
      return;
    }
    s.src = e.target.value;
    track("choose_sound", { slot, src: s.src });
  } else if (e.type === "change" && e.target.files?.[0]) {
    const file = e.target.files[0];
    try {
      const { wav, cut } = await convertSound(file, slot);
      Object.assign(s, {
        src: "own",
        name: file.name.slice(0, 40),
        wav: btoa(String.fromCharCode(...wav)),
        note: cut ? "Cut to fit:" : "",
      });
      track("upload_sound", { slot, ok: true, cut });
    } catch {
      track("upload_sound", { slot, ok: false });
      alert(`Couldn't read ${file.name} as audio.`);
    }
  } else if (e.type === "click" && e.target.closest(".ed-play")) {
    const audio = new Audio(URL.createObjectURL(new Blob([await soundBytes(slot)], { type: "audio/wav" })));
    audio.volume = state.sounds.volume / 100;
    audio.play();
    track("play_sound", { slot, src: s.src });
    return;
  } else return;
  renderSounds();
  changed({ list: false, preview: false });
}

// ---- download ----

function renderDownload() {
  const on = enabled();
  const errors = configErrors(m, {
    presets: on.map((p) => ({ tag: p.tag, match: p.colours, paint: p.colours, lcd: p.lcd })),
    rnd: state.rnd,
    sounds: state.sounds.on,
    volume: state.sounds.volume,
    gb: { on: state.gb.on, curve: state.gb.curve, contrast: state.gb.contrast, brightness: state.gb.brightness, palette: state.gb.colours },
  });
  const rnd = state.rnd && on.length > 1;
  $("#ed-summary").textContent =
    `${on.length} palette${on.length === 1 ? "" : "s"} (${on.map((p) => p.tag || "?").join(", ")})` +
    `${rnd ? " + rnd" : ""}${state.gb.on ? ` + Game Boy${state.gb.curve ? " (S-curve)" : ""}` : ""}${state.normal ? " + normal" : ""}${state.tag ? " · corner tag" : ""} · ` +
    `${state.sounds.on ? `sounds on at ${state.sounds.volume} %` : "silent"}`;
  $("#ed-errors").innerHTML = errors.map((e) => `<li>${esc(e)}</li>`).join("");
  $("#ed-download").disabled = errors.length > 0;
}

// What the downloaded firmware is made of.
function downloadProps() {
  const on = enabled();
  return {
    palettes: on.length,
    tags: on.map((p) => p.tag),
    films: on.map((p) => film(p)?.name ?? "none"),
    rnd: state.rnd && on.length > 1,
    gb: state.gb.on,
    normal: state.normal,
    corner_tag: state.tag,
    sounds: state.sounds.on,
    volume: state.sounds.on ? state.sounds.volume : null,
    shutter: state.sounds.on ? state.sounds.shutter.src : null,
    poweron: state.sounds.on ? state.sounds.poweron.src : null,
  };
}

let template;
async function getTemplate() {
  if (template) return template;
  const bytes = new Uint8Array(await (await fetch(`editor/${m.file}`)).arrayBuffer());
  if ((await sha256(bytes)) !== m.sha256) throw new Error("the template firmware isn't the expected one");
  return (template = bytes);
}

async function download() {
  const button = $("#ed-download");
  button.disabled = true;
  button.textContent = "Building…";
  try {
    const fw = buildFirmware(await getTemplate(), m, await config(), {
      shutter: await soundBytes("shutter"),
      poweron: await soundBytes("poweron"),
      click: await stockClick(),
    });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob([fw], { type: "application/octet-stream" }));
    a.download = "GP_CARDVR_UPGRADE.BIN";
    a.click();
    setTimeout(() => URL.revokeObjectURL(a.href), 10_000);
    track("download_customized_firmware", downloadProps());
  } catch (err) {
    track("download_customized_firmware_failed", { ...downloadProps(), error: err.message });
    alert(`Couldn't build the firmware: ${err.message}`);
  } finally {
    button.textContent = "Download GP_CARDVR_UPGRADE.BIN";
    renderDownload();
  }
}

// ---- start ----

async function main() {
  [m, library] = await Promise.all(
    ["editor/template.json", "editor/library.json"].map((u) => fetch(u, { cache: "no-cache" }).then((r) => r.json())),
  );
  state = load();
  $("#ed-max").textContent = m.maxPresets;
  const list = $("#ed-list");
  list.addEventListener("pointerdown", listPointerDown);
  list.addEventListener("pointermove", listPointerMove);
  list.addEventListener("pointerup", listPointerUp);
  list.addEventListener("pointercancel", listPointerUp);
  list.addEventListener("change", listChange);
  list.addEventListener("keydown", listKey);
  $("#ed-rnd").addEventListener("change", (e) => {
    state.rnd = e.target.checked;
    changed({ preview: false });
    track("toggle_rnd", { on: state.rnd });
  });
  const panel = $("#ed-palette");
  panel.addEventListener("input", paletteInput);
  panel.addEventListener("change", paletteChange);
  panel.addEventListener("click", paletteClick);
  panel.addEventListener("mousemove", (e) => e.target.closest("#ed-lcd") && hoverSeg(e));
  panel.addEventListener("mouseout", (e) => e.target.closest("#ed-lcd") && !e.relatedTarget?.closest?.("#ed-lcd") && hoverSeg({ type: "mouseleave" }));
  for (const type of ["pointerdown", "pointermove", "pointerup", "pointercancel"]) panel.addEventListener(type, pickerPointer);
  const photos = $("#ed-photos");
  photos.addEventListener("change", photoEvents);
  photos.addEventListener("click", photoEvents);
  photos.addEventListener("drop", photoEvents);
  photos.addEventListener("dragover", (e) => {
    const fig = e.target.closest(".ed-photo");
    if (!fig || !e.dataTransfer.types.includes("Files")) return;
    e.preventDefault();
    e.dataTransfer.dropEffect = "copy";
    for (const f of photos.querySelectorAll(".ed-photo")) f.classList.toggle("drop", f === fig);
  });
  photos.addEventListener("dragleave", (e) => {
    const fig = e.target.closest(".ed-photo");
    if (fig && !fig.contains(e.relatedTarget)) fig.classList.remove("drop");
  });
  photos.addEventListener("mouseover", hoverPhoto);
  photos.addEventListener("mouseout", hoverPhoto);
  const sounds = $("#ed-sounds");
  sounds.addEventListener("change", soundEvents);
  sounds.addEventListener("click", soundEvents);
  sounds.addEventListener("input", (e) => e.target.id === "ed-volume" && soundEvents(e));
  const gbList = $("#ed-gb-list");
  for (const type of ["change", "click", "keydown"]) gbList.addEventListener(type, gbListEvents);
  $("#ed-normal-on").checked = state.normal;
  $("#ed-normal-on").addEventListener("change", (e) => {
    state.normal = e.target.checked;
    track("toggle_normal_mode", { on: state.normal });
    changed({ list: false, preview: false });
  });
  $("#ed-tag-on").checked = state.tag;
  $("#ed-tag-on").addEventListener("change", (e) => {
    state.tag = e.target.checked;
    track("toggle_corner_tag", { on: state.tag });
    changed({ palette: true });
  });
  $("#ed-download").addEventListener("click", download);
  $("#ed-reset-all").addEventListener("click", async () => {
    const sure = confirm("Start over? This forgets your palettes, sounds and photos.");
    track("start_over", { confirmed: sure });
    if (!sure) return;
    state = defaultState();
    renderPhotos();
    renderSounds();
    $("#ed-tag-on").checked = state.tag;
    $("#ed-normal-on").checked = state.normal;
    changed({ palette: true, preview: false });
    await Promise.all(PHOTOS.map((_, i) => loadPhoto(i)));
    renderPreview();
  });

  renderList();
  renderHead();
  renderPalette();
  renderSounds();
  renderDownload();
  renderPhotos();
  await Promise.all(PHOTOS.map((_, i) => loadPhoto(i)));
  await renderPreview();
  $("#editor").classList.add("ready");
}

main();
