const assert = require("node:assert/strict");
const { assertZoom, wheelDelta, nativePoint, readConfig, waitForNativeWindow, waitForStableGeometry } = require("./verify-browser-zoom.cjs");
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

const test = require("node:test");
test("native window discovery waits for the same unique title, not a fallback", async () => {
  let time = 0;
  let calls = 0;
  const trace = [];
  const id = await waitForNativeWindow(() => ++calls === 1
    ? [{ id: "7", title: "工作 · Kebui U1 Design Demo - Chromium" }]
    : [{ id: "7", title: "Work · Kebui U1 Design Demo - Chromium" }],
    "Work · Kebui U1 Design Demo", trace,
    { now: () => time, pause: async (ms) => { time += ms; } });
  assert.equal(id, "7");
  assert.equal(calls, 2);
  assert.equal(trace[0].matches.length, 0);
  assert.deepEqual(trace[1].matches, ["7"]);
});
test("native window discovery does not accept stale or ambiguous windows", async () => {
  let time = 0;
  const options = { now: () => time, pause: async (ms) => { time += ms; }, timeoutMs: 100 };
  await assert.rejects(waitForNativeWindow(() => [{ id: "7", title: "unrelated" }], "Work", [], options), /did not become ready/);
  await assert.rejects(waitForNativeWindow(() => [{ id: "7", title: "Work" }, { id: "8", title: "Work" }], "Work", [], options), /ambiguous/);
});

test("native window discovery rejects ready observations after its deadline", async () => {
  let time = 0;
  await assert.rejects(waitForNativeWindow((remaining) => {
    assert.equal(remaining(), 100);
    time = 101;
    return [{ id: "7", title: "Work" }];
  }, "Work", [], { now: () => time, pause: async () => {}, timeoutMs: 100 }), /did not become ready/);
});

test("geometry waits through the measured 65.5 to 0 scroll and real end state", async () => {
  let time = 0;
  const samples = [
    { y: 370.789, documentScroll: 65.5, pending: true },
    { y: 436.289, documentScroll: 0, pending: true },
    { y: 436.289, documentScroll: 0, pending: false },
    { y: 436.289, documentScroll: 0, pending: false },
  ];
  let i = 0;
  const result = await waitForStableGeometry(() => samples[i++], {
    now: () => time, pause: async (ms) => { time += ms; },
  });
  assert.equal(result.observations, 4);
  assert.equal(result.geometry.y, 436.289);
  assert.equal(result.geometry.documentScroll, 0);
});
test("geometry cannot qualify while scroll is pending or bounds still move", async () => {
  let time = 0;
  const options = { now: () => time, pause: async (ms) => { time += ms; }, timeoutMs: 100 };
  await assert.rejects(waitForStableGeometry(() => ({ y: 10, pending: true }), options), /did not settle/);
  let y = 0;
  await assert.rejects(waitForStableGeometry(() => ({ y: y++, pending: false }), options), /did not settle/);
});
test("geometry rejects late stable observations", async () => {
  let time = 0;
  let i = 0;
  await assert.rejects(waitForStableGeometry(() => {
    if (i++) time = 101;
    return { y: 0, pending: false };
  }, { now: () => time, pause: async () => {}, timeoutMs: 100 }), /did not settle/);
});
