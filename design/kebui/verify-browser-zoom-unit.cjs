const assert = require("node:assert/strict");
const { assertZoom, wheelDelta, nativePoint, readConfig } = require("./verify-browser-zoom.cjs");
const base = {
  dpr: 1,
  scale: 1,
  width: 1440,
  height: 900,
  outerWidth: 1440,
  outerHeight: 1000,
  bodyFont: "15px",
  bodyZoom: "1",
  bodyTransform: "none",
  large: false,
};
const zoom = { ...base, dpr: 2, width: 720, height: 450 };
assertZoom(base, zoom);
for (const y of [-16, 26]) {
  const geometry = { y, height: 390, top: 2, bottom: 398 };
  const after = y - wheelDelta(geometry);
  assert(
    after >= 2 && after + 390 <= 398,
    "near-viewport target converges without oscillation",
  );
}
for (const bad of [
  { ...zoom, dpr: 1 }, // viewport-only reflow / CSS zoom cannot qualify
  { ...zoom, width: 1440 }, // DPR-only emulation cannot qualify
  { ...zoom, scale: 2 }, // pinch zoom cannot qualify
  { ...zoom, bodyFont: "30px" }, // text-only enlargement cannot qualify
  { ...zoom, bodyZoom: "2" },
  { ...zoom, bodyTransform: "matrix(2, 0, 0, 2, 0, 0)" },
  { ...zoom, large: true },
  { ...zoom, outerWidth: 720 },
])
  assert.throws(() => assertZoom(base, bad));
console.log(
  "Zoom calibration classifier: 1 accepted case, 8 rejected substitutes; no browser qualification",
);

assert.deepEqual(nativePoint(632.81640625, 159.1953125, 2, { left: 0, top: 87 }), { x: 1266, y: 405 });
assert.deepEqual(nativePoint(100, 100, 1, { left: 0, top: 87 }), { x: 100, y: 187 });

assert.deepEqual(readConfig({}), { width: 1440, lang: "zh", theme: "light", key: "1440-zh-light" });
for (const width of ["1440", "780"]) for (const lang of ["zh", "en"]) for (const theme of ["light", "dark"]) {
  assert.equal(readConfig({ KEBUI_ZOOM_WIDTH: width, KEBUI_ZOOM_LANG: lang, KEBUI_ZOOM_THEME: theme }).key, `${width}-${lang}-${theme}`);
}
for (const invalid of [{ KEBUI_ZOOM_WIDTH: "390" }, { KEBUI_ZOOM_LANG: "other" }, { KEBUI_ZOOM_THEME: "other" }]) assert.throws(() => readConfig(invalid));
