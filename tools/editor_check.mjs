// Writes test cases for tools/editor_check.sh: random configs (presets, rnd, sounds and
// their volume, the corner tag, the Game Boy mode and its colours) patched into the
// template by the site's editor (site/editor/firmware.js), plus what build.sh
// needs to build the same config itself.
//   node tools/editor_check.mjs OUTDIR COUNT
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { buildFirmware, encodeWav, rgbToYuv, slotSamples, yuvToRgb } from "../site/editor/firmware.js";

const [out, count] = [process.argv[2], +process.argv[3] || 12];
const m = JSON.parse(readFileSync("site/editor/template.json"));
const template = new Uint8Array(readFileSync(`site/editor/${m.file}`));
const sounds = (name) => new Uint8Array(readFileSync(`site/editor/sounds/${name}.wav`));

let seed = 1;
const rand = () => ((seed = (seed * 1103515245 + 12345) % 2 ** 31) / 2 ** 31);
const int = (n) => Math.floor(rand() * n);
const colour = () => [int(256), int(256), int(256)];
const letters = Object.keys(m.font);

function randomTag(taken) {
  for (;;) {
    const tag = Array.from({ length: 1 + int(3) }, () => letters[int(letters.length)]).join("");
    const width = [...tag].reduce((w, ch) => w + m.font[ch][0].length + 1, 1);
    if (width <= m.tag.cols && !taken.has(tag)) return taken.add(tag), tag;
  }
}

function randomConfig(i) {
  const n = i === 1 ? m.maxPresets : i === 2 ? 1 : 1 + int(m.maxPresets);
  const taken = new Set();
  const presets = Array.from({ length: n }, (_, k) => {
    const size = k === 0 && i === 1 ? m.maxColours : 1 + int(m.maxColours);
    const match = Array.from({ length: size }, colour);
    const paint = rand() < 0.5 ? match : Array.from({ length: size }, colour);
    const lcd = Array.from({ length: 3 }, () => [..."abcdefg"].filter(() => rand() < 0.5).join(""));
    return { tag: randomTag(taken), match, paint, lcd };
  });
  const rgb = Array.from({ length: 4 }, colour);
  const gb = { on: rand() < 0.5, curve: rand() < 0.5, contrast: int(101) - 50, brightness: int(101) - 50, palette: rgb.map(rgbToYuv), rgb };
  return { contrast: int(101) - 50, brightness: int(101) - 50, presets, rnd: rand() < 0.5, sounds: rand() < 0.5, tag: rand() < 0.5, normal: rand() < 0.5, gb, volume: 1 + int(100) };
}

function randomWav(slot) {
  const n = 1 + int(slotSamples(m, slot));
  return encodeWav(m, Int16Array.from({ length: n }, () => int(65536) - 32768));
}

for (let i = 0; i < count; i++) {
  const dir = `${out}/case${i}`;
  mkdirSync(dir, { recursive: true });
  // case 0: the built-in presets, silent (Mario WAVs silenced) = the template itself
  const cfg = i === 0 ? { ...m.defaults, sounds: false } : randomConfig(i);
  const s =
    i === 0 ? { shutter: sounds("mario_shutter"), poweron: sounds("mario_poweron") }
    : i % 3 === 0 ? { shutter: sounds("stock_shutter"), poweron: sounds("stock_poweron") }
    : { shutter: randomWav("shutter"), poweron: randomWav("poweron") };
  s.click = sounds("stock_click");
  writeFileSync(`${dir}/config.json`, JSON.stringify(cfg));
  writeFileSync(`${dir}/shutter.wav`, s.shutter);
  writeFileSync(`${dir}/poweron.wav`, s.poweron);
  writeFileSync(`${dir}/silent`, cfg.sounds ? "0" : "1");
  // what build.sh takes for the same config
  const hex = (c) => c.map((x) => x.toString(16).padStart(2, "0")).join("");
  writeFileSync(
    `${dir}/env`,
    `TAG=${cfg.tag ? 1 : 0} GB_ON=${cfg.gb.on ? 1 : 0} NORMAL_ON=${cfg.normal ? 1 : 0} GB_CURVE=${cfg.gb.curve ? 1 : 0} CONTRAST=${100 + (cfg.contrast ?? 0)} BRIGHT=${cfg.brightness ?? 0} GB_CONTRAST=${cfg.gb.contrast} GB_BRIGHTNESS=${cfg.gb.brightness} GB_PALETTE=${(cfg.gb.rgb ?? m.defaults.gb.palette.map(yuvToRgb)).map(hex).join(",")} VOLUME=${cfg.volume}`,
  );
  const fw = buildFirmware(template, m, cfg, s);
  writeFileSync(`${dir}/editor.bin`, fw);
  if (i === 0 && !fw.every((b, k) => b === template[k])) throw new Error("case 0 should equal the template");
  console.log(`case${i}: ${cfg.presets.length} presets (${cfg.presets.map((p) => `${p.tag}:${p.match.length}`).join(" ")}), rnd ${cfg.rnd}, sounds ${cfg.sounds} at ${cfg.volume} %, tag ${cfg.tag}, normal ${cfg.normal}, GB ${cfg.gb.on}${cfg.gb.curve ? " + S-curve" : ""}`);
}
