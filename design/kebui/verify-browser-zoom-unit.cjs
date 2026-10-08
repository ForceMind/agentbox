const assert = require("node:assert/strict");
const { assertZoom, wheelDelta } = require("./verify-browser-zoom.cjs");
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
