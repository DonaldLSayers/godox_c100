// The background: a slowly moving field, ordered-dithered in light greys.
(() => {
  const CELL = 4; // CSS pixels per background pixel
  const FPS = 30;
  const MAX = 0.5; // how dark the field gets, 0..1 on the LEVELS scale

  // Greys the background dithers between, light to dark.
  const LEVELS = [255, 238, 222, 204, 186].map((g) => (255 << 24) | (g << 16) | (g << 8) | g);

  const canvas = document.getElementById("bg");
  const ctx = canvas.getContext("2d");
  const reduceMotion = matchMedia("(prefers-reduced-motion: reduce)").matches;

  // 8×8 Bayer matrix, thresholds in (0, 1).
  const BAYER = (() => {
    let m = [[0]];
    while (m.length < 8) {
      const s = m.length;
      const next = [];
      for (let y = 0; y < 2 * s; y++) {
        next.push([]);
        for (let x = 0; x < 2 * s; x++) {
          next[y].push(4 * m[y % s][x % s] + [[0, 2], [3, 1]][(y / s) | 0][(x / s) | 0]);
        }
      }
      m = next;
    }
    return m.flat().map((v) => (v + 0.5) / 64);
  })();

  let w = 0;
  let h = 0;
  let image = null; // ImageData we write into
  let pixels = null; // Uint32 view on it

  function resize() {
    w = Math.max(1, Math.ceil(innerWidth / CELL));
    h = Math.max(1, Math.ceil(innerHeight / CELL));
    canvas.width = w;
    canvas.height = h;
    image = ctx.createImageData(w, h);
    pixels = new Uint32Array(image.data.buffer);
    draw(reduceMotion ? 0 : performance.now());
  }

  // Overlapping sine waves and a drifting ripple: soft blobs that wander.
  function draw(ms) {
    const t = ms / 1000;
    const col = new Float32Array(w);
    const row = new Float32Array(h);
    const diag = new Float32Array(w + h);
    for (let x = 0; x < w; x++) col[x] = Math.sin(x * CELL * 0.011 + t * 0.35);
    for (let y = 0; y < h; y++) row[y] = Math.sin(y * CELL * 0.014 - t * 0.27);
    for (let d = 0; d < w + h; d++) diag[d] = Math.sin(d * CELL * 0.007 + t * 0.2);
    const cx = w * (0.5 + 0.35 * Math.sin(t * 0.07));
    const cy = h * (0.5 + 0.35 * Math.cos(t * 0.05));
    const top = LEVELS.length - 1;
    for (let y = 0; y < h; y++) {
      for (let x = 0; x < w; x++) {
        const r = Math.hypot(x - cx, y - cy) * CELL;
        const v = col[x] + row[y] + diag[x + y] + Math.sin(r * 0.012 - t * 0.5);
        const n = Math.min(1, Math.max(0, (v + 1.2) / 4.4)); // mostly light, some dark blobs
        const s = n * n * MAX * top;
        const lo = s | 0;
        pixels[y * w + x] = LEVELS[Math.min(top, lo + (s - lo > BAYER[(y & 7) * 8 + (x & 7)] ? 1 : 0))];
      }
    }
    ctx.putImageData(image, 0, 0);
  }

  let last = 0;
  function loop(ms) {
    requestAnimationFrame(loop);
    if (ms - last < 1000 / FPS) return;
    last = ms;
    draw(ms);
  }

  addEventListener("resize", resize);
  resize();
  if (!reduceMotion) requestAnimationFrame(loop);

  // Click a photo to see it larger.
  const gallery = document.querySelector(".gallery");
  const dialog = document.getElementById("viewer");
  if (dialog.showModal) {
    const big = dialog.querySelector("img");
    gallery.addEventListener("click", (e) => {
      const a = e.target.closest("a");
      if (!a) return;
      e.preventDefault();
      big.src = a.href;
      dialog.showModal();
    });
    dialog.addEventListener("click", (e) => {
      if (e.target === dialog) dialog.close();
    });
  }
})();
