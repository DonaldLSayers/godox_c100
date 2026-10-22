// The camera's effect in the browser (tools/sim_palette.py with the camera's
// lookup table): per 2x2 block the average luma plus a 4x4 Bayer offset, the
// block's Y, U, V looked up in a 33x33x33 table of nearest match colours,
// painted with the paint colour at that index; then the tag, top right (if
// it's on). renderGb is the Game Boy Camera mode (tools/sim_gb.py).
import { tagCells, tagColours, yuvToRgb } from "./firmware.js";

const BAYER = [0, 8, 2, 10, 12, 4, 14, 6, 3, 11, 1, 9, 15, 7, 13, 5];
const N = 33;

// What lut_fill puts in the table: per bin centre (multiples of 8), the
// nearest match colour by wy*|dY| + |dU| + |dV|, the first one on ties.
export function buildLut(match, wy) {
  const lut = new Uint8Array(N * N * N);
  let i = 0;
  for (let y = 0; y < N * 8; y += 8)
    for (let u = 0; u < N * 8; u += 8)
      for (let v = 0; v < N * 8; v += 8) {
        let best = Infinity;
        let at = 0;
        match.forEach((c, k) => {
          const d = wy * Math.abs(y - c[0]) + Math.abs(u - c[1]) + Math.abs(v - c[2]);
          if (d < best) (best = d), (at = k);
        });
        lut[i++] = at;
      }
  return lut;
}

// The photo cropped and scaled to the size the camera uses for its aspect.
export function cameraSize(m, w, h) {
  const name = Object.keys(m.sizes).reduce((a, b) =>
    Math.abs(m.sizes[a][0] / m.sizes[a][1] - w / h) <= Math.abs(m.sizes[b][0] / m.sizes[b][1] - w / h) ? a : b,
  );
  return { crop: m.crops[name], size: m.sizes[name] };
}

// `gb`: the Game Boy mode's own size and crop (8:7), which it selects on the camera, instead of the
// nearest aspect's.
export function cameraFrame(m, img, gb = false) {
  const w = img.naturalWidth || img.width;
  const h = img.naturalHeight || img.height;
  const { crop, size } = gb ? { crop: m.gb.crop, size: m.gb.size } : cameraSize(m, w, h);
  let sx = 0, sy = 0, sw = w, sh = h;
  if (w * crop[1] > h * crop[0]) (sw = Math.round((h * crop[0]) / crop[1])), (sx = (w - sw) / 2);
  else (sh = Math.round((w * crop[1]) / crop[0])), (sy = (h - sh) / 2);
  const c = document.createElement("canvas");
  [c.width, c.height] = size;
  const ctx = c.getContext("2d", { willReadFrequently: true });
  ctx.imageSmoothingQuality = "high";
  ctx.drawImage(img, sx, sy, sw, sh, 0, 0, size[0], size[1]);
  return ctx.getImageData(0, 0, size[0], size[1]);
}

// frame: ImageData at camera size; returns a new ImageData.
export function render(m, frame, preset, lut) {
  const { width: w, height: h, data } = frame;
  const bw = w >> 1;
  const bh = h >> 1;
  const paint = preset.paint.map(yuvToRgb);
  const blocks = new Uint8Array(bw * bh);
  for (let by = 0; by < bh; by++)
    for (let bx = 0; bx < bw; bx++) {
      let ys = 0, us = 0, vs = 0;
      for (const [dx, dy] of [[0, 0], [1, 0], [0, 1], [1, 1]]) {
        const i = ((2 * by + dy) * w + 2 * bx + dx) * 4;
        const r = data[i], g = data[i + 1], b = data[i + 2];
        ys += 0.299 * r + 0.587 * g + 0.114 * b;
        us += 128 - 0.168736 * r - 0.331264 * g + 0.5 * b;
        vs += 128 + 0.5 * r - 0.418688 * g - 0.081312 * b;
      }
      let y = Math.round(ys) >> 2;
      y = (((y - 128) * (preset.contrastFix ?? 128)) >> 7) + (preset.brightFix ?? 128);   // the firmware's pre-map
      y = Math.max(0, Math.min(255, y + (BAYER[(by & 3) * 4 + (bx & 3)] - 8) * 4));
      const u = Math.max(0, Math.min(255, Math.round(us / 4)));
      const v = Math.max(0, Math.min(255, Math.round(vs / 4)));
      blocks[by * bw + bx] = lut[(((y + 4) >> 3) * N + ((u + 4) >> 3)) * N + ((v + 4) >> 3)];
    }

  if (preset.tag) {
    const [dark, light] = tagColours(preset.paint);
    const cells = tagCells(m, preset.tag);
    const s = m.tag.scale;
    const c0 = bw - m.tag.right - cells[0].length * s;
    cells.forEach((row, r) =>
      row.forEach((v, c) => {
        if (!v) return;
        for (let yy = 0; yy < s; yy++)
          for (let xx = 0; xx < s; xx++) blocks[(m.tag.top + r * s + yy) * bw + c0 + c * s + xx] = v === 1 ? dark : light;
      }),
    );
  }

  const out = new ImageData(w, h);
  for (let y = 0; y < h; y++)
    for (let x = 0; x < w; x++) {
      const [r, g, b] = paint[blocks[(y >> 1) * bw + (x >> 1)]];
      const i = (y * w + x) * 4;
      out.data[i] = r;
      out.data[i + 1] = g;
      out.data[i + 2] = b;
      out.data[i + 3] = 255;
    }
  return out;
}

// The Game Boy Camera mode (tools/sim_gb.py, gb_strip in photo_cave.s): per 4x4
// block the mean luma, tone curve (identity or the S-curve), exposure, the 50 % horizontal edge, three thresholds
// picked by the block's place in the 4x4 pattern; painted with one of the
// four colours ([r, g, b], dark to light). frame: ImageData at the mode's 512x448 (4x4 blocks: 128x112).
export function renderGb(m, frame, colours, curve = m.gb.identity) {
  const { width: w, height: h, data } = frame;
  const gw = w >> 2;
  const gh = h >> 2;
  const p = new Int32Array(gw * gh);
  for (let by = 0; by < gh; by++)
    for (let bx = 0; bx < gw; bx++) {
      let sum = 0;
      for (let dy = 0; dy < 4; dy++)
        for (let dx = 0; dx < 4; dx++) {
          const i = ((4 * by + dy) * w + 4 * bx + dx) * 4;
          sum += Math.round(0.299 * data[i] + 0.587 * data[i + 1] + 0.114 * data[i + 2]);
        }
      const exposed = (curve[sum >> 4] * m.gb.gain) >> 8; // the tone curve, then the exposure
      p[by * gw + bx] = Math.trunc((exposed - 128) / 8);
    }
  const out = new ImageData(w, h);
  for (let by = 0; by < gh; by++)
    for (let bx = 0; bx < gw; bx++) {
      const at = by * gw + bx;
      const l = p[by * gw + Math.max(bx - 1, 0)];
      const r = p[by * gw + Math.min(bx + 1, gw - 1)];
      const code = 128 + Math.trunc((4 * p[at] - l - r) / 2);
      const pos = (by & 3) * 4 + (bx & 3);
      const shade = m.gb.thresholds.reduce((n, t) => n + (code >= t[pos]), 0);
      const [cr, cg, cb] = colours[shade];
      for (let dy = 0; dy < 4; dy++)
        for (let dx = 0; dx < 4; dx++) {
          const i = ((4 * by + dy) * w + 4 * bx + dx) * 4;
          out.data[i] = cr;
          out.data[i + 1] = cg;
          out.data[i + 2] = cb;
          out.data[i + 3] = 255;
        }
    }
  return out;
}
