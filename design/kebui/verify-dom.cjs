// DOM-only checks. This is NOT browser, layout, pixel, accessibility or physical-device qualification.
const { JSDOM } = require(process.env.JSDOM_PATH || "jsdom");
const fs = require("fs");
const path = require("path");
const assert = require("assert");
const html = fs.readFileSync(path.join(__dirname, "index.html"), "utf8");
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
const read = (x) => w.eval(x);
const act = (a) => {
  const el = d.querySelector(`[data-action="${a}"]`);
  assert(el, `missing action ${a}`);
  el.click();
};
const scene = (s) => read(`setScene('${s}')`);
const go = (s) => read(`navigate('${s}')`);
const eq = (x, v) => assert.equal(read(x), v);
const checks = [];
act("new");
act("create-work");
d.querySelector("#draft").value = "Synthetic test";
d.querySelector("#draft").dispatchEvent(
  new w.Event("input", { bubbles: true }),
);
d.querySelector("#draft").dispatchEvent(
  new w.CompositionEvent("compositionstart", { bubbles: true }),
);
d.querySelector("#draft").dispatchEvent(
  new w.KeyboardEvent("keydown", {
    bubbles: true,
    key: "Enter",
    ctrlKey: true,
  }),
);
eq("state.phase", "idle");
d.querySelector("#draft").dispatchEvent(
  new w.CompositionEvent("compositionend", { bubbles: true }),
);
d.querySelector("#draft").dispatchEvent(
  new w.KeyboardEvent("keydown", { bubbles: true, key: "Enter" }),
);
eq("state.phase", "idle");
d.querySelector("#draft").dispatchEvent(
  new w.KeyboardEvent("keydown", {
    bubbles: true,
    key: "Enter",
    ctrlKey: true,
  }),
);
eq("state.phase", "accepted");
read("send()");
eq("state.phase", "accepted");
act("advance");
act("advance");
eq("state.phase", "succeeded");
act("go:results");
assert(!d.querySelector("#diff"));
act("read-result");
assert(d.querySelector("#diff"));
act("invalidate-result");
assert(!d.querySelector("#diff"));
act("back-work");
eq("state.route", "work");
checks.push(
  "Journey A success, IME, newline, Ctrl+Enter, duplicate send suppression, explicit result read and invalidation",
);
scene("failure");
read("state.draft='Synthetic retry'");
read("send()");
eq("state.phase", "failed");
act("retry");
eq("state.phase", "accepted");
act("disconnect");
eq("state.route", "recovery");
eq("state.phase", "unknown");
checks.push("Journey A failed send, explicit retry and interruption");
go("approval");
scene("success");
act("approve");
eq("state.approval", "approved");
act("approve");
eq("state.approval", "approved");
scene("failure");
act("approve");
eq("state.approval", "unknown");
act("read-approval");
eq("state.approval", "expired");
act("fresh-approval");
eq("state.approval", "pending");
act("reject");
eq("state.approval", "rejected");
scene("interrupted");
act("approve");
eq("state.approval", "unknown");
scene("expired");
act("approve");
eq("state.approval", "expired");
checks.push(
  "Journey B approval success, duplicate blocked, failed/interrupted outcome unknown, read-only recovery, rejection and expiry",
);
go("recovery");
scene("failure");
act("recover");
eq("state.recovered", false);
scene("interrupted");
act("recover");
eq("state.recovered", true);
act("stop-dialog");
assert(d.querySelector("#dialog").open);
act("close");
eq("state.stopped", false);
act("stop-dialog");
act("stop-confirm");
eq("state.stopped", true);
act("detach");
eq("state.stopped", true);
checks.push(
  "Journey C failed verify, interrupt recovery, cancel exact Stop, exact synthetic readback, detach does not stop",
);
go("work");
scene("success");
read("state.draft='<img src=x onerror=alert(1)>'");
read("send()");
assert(!d.querySelector("img"));
act("new");
act("create-work");
eq("state.message", "");
eq("state.admitted", false);
checks.push("Escaped user input and new-scope clearing");
go("home");
act("fixture:work");
eq("state.project", "Observatory");
eq("state.agent", "Claude Code");
eq("state.phase", "accepted");
checks.push("Conversation row opens matching Project and Agent");
let combinations = 0;
for (const lang of ["zh", "en"])
  for (const theme of ["light", "dark"])
    for (const screen of read("Object.keys(titles)"))
      for (const scenario of [
        "success",
        "failure",
        "interrupted",
        "expired",
        "empty",
        "unknown",
      ]) {
        read(
          `state.lang='${lang}';document.documentElement.dataset.theme='${theme}';state.route='${screen}';setScene('${scenario}')`,
        );
        assert(d.querySelector("h1"));
        assert(
          !d.querySelector(
            'script[src],iframe,img,form[action],a[href^="http"]',
          ),
        );
        combinations++;
      }
checks.push(
  `${combinations} screen/language/theme/scenario DOM renders (no layout claims)`,
);
go("results");
scene("success");
act("read-result");
assert(d.querySelector("#diff"));
w.dispatchEvent(new w.Event("offline"));
eq("state.admitted", false);
eq("state.route", "recovery");
checks.push("Offline clears admitted body and moves to unknown recovery");
const result = { type: "DOM only; browser NOT RUN", checks, combinations };
fs.mkdirSync(path.join(__dirname, "evidence"), { recursive: true });
fs.writeFileSync(
  path.join(__dirname, "evidence", "dom-verification.json"),
  JSON.stringify(result, null, 2),
);
console.log(JSON.stringify(result, null, 2));
w.close();
