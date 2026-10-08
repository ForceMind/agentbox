// Focused DOM regressions. Native browser behavior is checked separately in verify.cjs.
const { JSDOM } = require(process.env.JSDOM_PATH || "jsdom");
const fs = require("fs");
const path = require("path");
const assert = require("assert");
const html = fs.readFileSync(
  process.env.PROTOTYPE_PATH || path.join(__dirname, "index.html"),
  "utf8",
);
const cases = [];
async function test(name, fn) {
  const dom = new JSDOM(html, {
    runScripts: "dangerously",
    url: "https://synthetic.invalid/",
    pretendToBeVisual: true,
    beforeParse(w) {
      w.scrollTo = () => {};
      w.HTMLDialogElement.prototype.showModal = function () {
        this.open = true;
      };
      w.HTMLDialogElement.prototype.close = function () {
        this.open = false;
      };
    },
  });
  const w = dom.window,
    d = w.document;
  const read = (source) => w.eval(source);
  const act = (name) => {
    const el = d.querySelector(`[data-action="${name}"]`);
    assert(el, name);
    el.click();
  };
  try {
    await fn({ w, d, read, act });
    cases.push({ name, status: "PASS" });
  } catch (error) {
    cases.push({ name, status: "FAIL", error: error.message });
  } finally {
    w.close();
  }
}
(async () => {
  await test("Offline invalidates prior recovery and disables exact Stop", ({
    w,
    d,
    read,
    act,
  }) => {
    read("navigate('recovery');setScene('success')");
    act("recover");
    assert.equal(read("state.recovered"), true);
    w.dispatchEvent(new w.Event("offline"));
    assert.equal(read("state.recovered"), false);
    assert(d.querySelector('[data-action="stop-dialog"]').disabled);
    assert.equal(read("state.stopped"), false);
  });
  await test("Hidden closes Stop dialog; stale confirmation cannot stop after reverify", ({
    w,
    d,
    read,
    act,
  }) => {
    read("navigate('recovery');setScene('success')");
    act("recover");
    act("stop-dialog");
    const oldButton = d.querySelector('[data-action="stop-confirm"]');
    Object.defineProperty(d, "hidden", { configurable: true, value: true });
    d.dispatchEvent(new w.Event("visibilitychange"));
    assert.equal(d.querySelector("#dialog").open, false);
    Object.defineProperty(d, "hidden", { configurable: true, value: false });
    act("recover");
    d.querySelector("#dialog").append(oldButton);
    oldButton.click();
    assert.equal(read("state.stopped"), false);
  });
  await test("Final Stop rechecks the exact target", ({ d, read, act }) => {
    read("navigate('recovery');setScene('success')");
    act("recover");
    act("stop-dialog");
    read("state.project='Changed synthetic target'");
    act("stop-confirm");
    assert.equal(read("state.stopped"), false);
    assert.equal(d.querySelector("#dialog").open, false);
  });
  await test("Choosing Agent then cancel preserves scope, draft, approval and result", ({
    d,
    read,
    act,
  }) => {
    read(
      "state.draft='Keep my synthetic draft';state.admitted=true;state.approval='approved';navigate('agents')",
    );
    const before = read("JSON.stringify(state)");
    act("choose:Claude Code");
    assert.equal(d.querySelector("#agent-choice").value, "Claude Code");
    act("close");
    assert.equal(read("JSON.stringify(state)"), before);
  });
  await test("Skip link focuses main without routing or clearing draft", async ({
    w,
    d,
    read,
  }) => {
    read("navigate('work');state.draft='Keep keyboard draft';render()");
    const hash = w.location.hash;
    d.querySelector(".skip").click();
    await new Promise((resolve) => w.setTimeout(resolve, 10));
    assert.equal(read("state.route"), "work");
    assert.equal(w.location.hash, hash);
    assert.equal(read("state.draft"), "Keep keyboard draft");
    assert.equal(d.activeElement.id, "main");
  });
  await test("Repeated recovery preserves stopped fixture; running detach does not stop", ({
    read,
    act,
  }) => {
    read("navigate('recovery');setScene('success')");
    act("recover");
    act("detach");
    assert.equal(read("state.stopped"), false);
    assert.equal(read("state.phase"), "running");
    read("navigate('recovery')");
    act("stop-dialog");
    act("stop-confirm");
    act("recover");
    assert.equal(read("state.stopped"), true);
    assert.equal(read("state.phase"), "interrupted");
  });
  await test("Send evidence, idempotent duplicate and exact revision increment", ({
    d,
    read,
    act,
  }) => {
    act("new");
    act("create-work");
    read("setScene('failure')");
    d.querySelector("#draft").value = "New failure request";
    read("send()");
    assert.equal(read("state.message"), "New failure request");
    assert.equal(read("state.requestCount"), 1);
    assert.equal(read("state.sendAttempts"), 1);
    assert.equal(read("state.acceptedCount"), 0);
    const id = read("state.requestId");
    assert(id);
    act("retry");
    read("send()");
    assert.equal(read("state.requestId"), id);
    assert.equal(read("state.requestCount"), 1);
    assert.equal(read("state.acceptedCount"), 1);
    assert.equal(read("state.sendAttempts"), 2);
    read("navigate('approval');setScene('expired')");
    const revision = read("state.revision");
    act("fresh-approval");
    assert.equal(read("state.revision"), revision + 1);
  });
  await test("Approval requester matches selected Claude Code", ({
    d,
    read,
  }) => {
    read("state.agent='Claude Code';navigate('approval')");
    assert(!d.querySelector("main").textContent.includes("申请者 Codex"));
    assert(d.querySelector(".card .muted").textContent.includes("Claude Code"));
  });
  await test("Fresh failure scene has no actionable retry until a request is sent", ({
    d,
    read,
    act,
  }) => {
    act("new");
    act("create-work");
    read("setScene('failure')");
    assert.equal(read("state.requestId"), "");
    assert(d.querySelector('[data-action="retry"]').disabled);
    d.querySelector("#draft").value = "Submit before retry";
    read("send()");
    assert(read("state.requestId"));
    assert.equal(d.querySelector('[data-action="retry"]').disabled, false);
    act("retry");
    assert.equal(read("state.acceptedCount"), 1);
  });
  await test("isComposing event cannot send; Cmd+Enter can submit", ({
    w,
    d,
    read,
    act,
  }) => {
    act("new");
    act("create-work");
    d.querySelector("#draft").value = "Synthetic Mac shortcut";
    d.querySelector("#draft").dispatchEvent(
      new w.KeyboardEvent("keydown", {
        bubbles: true,
        key: "Enter",
        metaKey: true,
        isComposing: true,
      }),
    );
    assert.equal(read("state.requestCount"), 0);
    d.querySelector("#draft").dispatchEvent(
      new w.KeyboardEvent("keydown", {
        bubbles: true,
        key: "Enter",
        metaKey: true,
      }),
    );
    assert.equal(read("state.requestCount"), 1);
    assert.equal(read("state.acceptedCount"), 1);
  });
  await test("Toast expiry, replacement, dismissal and route cleanup", async ({
    w,
    d,
    read,
    act,
  }) => {
    read('toast("route notice"); navigate("home")');
    assert.equal(d.getElementById("live").textContent, "");
    const timers = [];
    w.setTimeout = (fn) => {
      timers.push(fn);
      return timers.length;
    };
    w.clearTimeout = () => {};
    read('toast("old notice")');
    read('toast("current notice")');
    timers[0]();
    assert(d.getElementById("live").textContent.includes("current notice"));
    timers[1]();
    assert.equal(d.getElementById("live").textContent, "");
    read('toast("dismiss me")');
    act("dismiss-toast");
    assert.equal(d.getElementById("live").textContent, "");
    read('toast("route notice"); navigate("home")');
    assert.equal(d.getElementById("live").textContent, "");
  });
  console.log(JSON.stringify(cases, null, 2));
  if (cases.some((c) => c.status === "FAIL")) process.exitCode = 1;
})();
