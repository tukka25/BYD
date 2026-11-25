// npm run previews: a picture of each dashboard's first charts, for its card
// on the landing page. It serves the static build in out/ itself, drives the
// Google Chrome already on this machine over the DevTools protocol, and writes
// public/previews/<name>.webp and data/previews.json.
//
// Run `npm run build` first, because the pictures are taken of the built
// pages; then build again, so out/ carries them. Node 24 built-ins only: no
// npm dependency and no download. Chrome is $CHROME, or else the standard
// macOS install.

import { spawn } from "node:child_process";
import { createHash } from "node:crypto";
import {
  existsSync,
  mkdirSync,
  mkdtempSync,
  readdirSync,
  readFileSync,
  rmSync,
  statSync,
  unlinkSync,
  writeFileSync,
} from "node:fs";
import { createServer } from "node:http";
import { tmpdir } from "node:os";
import { extname, join, relative, resolve, sep } from "node:path";
import { fileURLToPath } from "node:url";

const SITE = fileURLToPath(new URL("..", import.meta.url));
const OUT = resolve(SITE, "out");
const DASHBOARDS = join(SITE, "data", "dashboards");
const IMAGES = join(SITE, "public", "previews");
const RECORD = join(SITE, "data", "previews.json");
// What the dashboard pages are built from: out/ must be newer than all of it.
const SOURCES = ["app", "components", "lib", join("data", "dashboards")];

const DEFAULT_CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const VIEWPORT_WIDTH = 960; // the dashboard's 12-column grid applies from 768 px
const IMAGE_WIDTH = 640; // about twice the width of the card's picture
const QUALITY = 80;
const MAX_BYTES = 150 * 1024; // tests/previews.test.mts holds every picture under this
const TIMEOUT_MS = 60_000; // per dashboard
// One rule for every dashboard; if a picture looks wrong, change the rule,
// never one dashboard. It starts at the first chart because the card's source
// chip sits at the picture's top left, where every dashboard has a KPI tile:
// started there, the chip hid the tile's number.
const CROP =
  "the dashboard grid's full width, from the top of its first chart (notes and KPI tiles are skipped), " +
  "at 4:5 (height = width × 5/4) or to the grid's bottom if that comes first, scaled to 640 px wide";

const TYPES = {
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".json": "application/json",
  ".txt": "text/plain; charset=utf-8",
  ".woff2": "font/woff2",
  ".webp": "image/webp",
  ".svg": "image/svg+xml",
  ".png": "image/png",
};

const sleep = (ms) => new Promise((done) => setTimeout(done, ms));
const isWebp = (bytes) =>
  bytes.subarray(0, 4).toString("latin1") === "RIFF" && bytes.subarray(8, 12).toString("latin1") === "WEBP";

/* What to undo, newest first: Chrome stops before its profile is removed.
   One run of it, even when a signal and the normal ending both ask. */
const cleanups = [];
let cleaning = null;
function cleanUp() {
  cleaning ??= (async () => {
    while (cleanups.length) {
      const step = cleanups.pop();
      try {
        await step();
      } catch (error) {
        console.error(`previews: while cleaning up: ${error.message}`);
        process.exitCode = 1;
      }
    }
  })();
  return cleaning;
}

/* Each dashboard file, sorted by name, with what the picture is checked against. */
function readDashboards() {
  const files = readdirSync(DASHBOARDS)
    .filter((file) => file.endsWith(".json"))
    .sort();
  if (!files.length) throw new Error("data/dashboards/ holds no dashboard");
  return files.map((file) => {
    const bytes = readFileSync(join(DASHBOARDS, file));
    const dashboard = JSON.parse(bytes.toString("utf8"));
    const name = file.slice(0, -".json".length);
    if (dashboard.name !== name) throw new Error(`data/dashboards/${file} is named "${dashboard.name}"`);
    const charts = dashboard.build?.charts_drawn;
    if (!Number.isInteger(charts) || charts < 1) throw new Error(`data/dashboards/${file} has no build.charts_drawn`);
    return { name, charts, sha256: createHash("sha256").update(bytes).digest("hex") };
  });
}

/* The newest file under a directory, with its time. */
function newestIn(dir) {
  let newest = { path: dir, time: 0 };
  for (const entry of readdirSync(dir, { withFileTypes: true, recursive: true })) {
    if (!entry.isFile()) continue;
    const path = join(entry.parentPath, entry.name);
    const time = statSync(path).mtimeMs;
    if (time > newest.time) newest = { path, time };
  }
  return newest;
}

/* Pictures of a stale build would show pages that no longer exist. */
function checkBuild() {
  const built = join(OUT, "index.html");
  if (!existsSync(built)) throw new Error("out/ is missing: run npm run build first");
  const time = statSync(built).mtimeMs;
  for (const dir of SOURCES) {
    const newest = newestIn(join(SITE, dir));
    if (newest.time > time) {
      throw new Error(`out/ is older than ${relative(SITE, newest.path)}: run npm run build first`);
    }
  }
}

function findChrome() {
  const named = process.env.CHROME;
  if (named && existsSync(named)) return named;
  if (existsSync(DEFAULT_CHROME)) {
    if (named) console.warn(`previews: CHROME=${named} does not exist; using ${DEFAULT_CHROME}`);
    return DEFAULT_CHROME;
  }
  throw new Error(
    `Google Chrome not found: ${named ? `CHROME=${named}` : "CHROME is not set"}, and ${DEFAULT_CHROME} does not exist. ` +
      "Install Google Chrome, or set CHROME to the path of a Chrome binary.",
  );
}

/* out/ over HTTP on 127.0.0.1, on a port the system picks. /x/ is
   /x/index.html, and no path resolves outside out/. */
function serve(root) {
  const server = createServer((request, response) => {
    if (request.method !== "GET" && request.method !== "HEAD") {
      response.writeHead(405).end();
      return;
    }
    let path;
    try {
      path = decodeURIComponent(new URL(request.url ?? "/", "http://127.0.0.1").pathname);
    } catch {
      response.writeHead(400).end();
      return;
    }
    if (path.endsWith("/")) path += "index.html";
    let file = resolve(root, `.${path}`);
    if (path.includes("\0") || !file.startsWith(root + sep)) {
      response.writeHead(403).end();
      return;
    }
    try {
      if (statSync(file).isDirectory()) file = join(file, "index.html");
      const body = readFileSync(file);
      response.writeHead(200, {
        "Content-Type": TYPES[extname(file)] ?? "application/octet-stream",
        "Content-Length": body.length,
      });
      response.end(request.method === "HEAD" ? undefined : body);
    } catch {
      response.writeHead(404).end();
    }
  });
  return new Promise((done, fail) => {
    server.once("error", fail);
    server.listen(0, "127.0.0.1", () => {
      cleanups.push(
        () =>
          new Promise((closed) => {
            server.close(() => closed());
            server.closeAllConnections();
          }),
      );
      done(`http://127.0.0.1:${server.address().port}`);
    });
  });
}

/* Stop the Chrome this script started, and only that one. */
async function stopChrome(child) {
  if (!child.pid || child.exitCode !== null || child.signalCode !== null) return;
  const exited = new Promise((done) => child.once("exit", done));
  child.kill("SIGTERM");
  let timer;
  const late = new Promise((done) => {
    timer = setTimeout(() => done("late"), 5000);
  });
  if ((await Promise.race([exited, late])) === "late") {
    child.kill("SIGKILL");
    await exited;
  }
  clearTimeout(timer);
}

/* Headless Chrome on a fresh, temporary profile (without one, a Chrome that
   is already running swallows the launch). Returns its debugging port. */
async function launchChrome(binary) {
  const profile = mkdtempSync(join(tmpdir(), "promptdash-previews-"));
  cleanups.push(() => rmSync(profile, { recursive: true, force: true, maxRetries: 10, retryDelay: 100 }));
  const child = spawn(
    binary,
    [
      "--headless=new",
      // Port 0: Chrome picks a free port and writes it to DevToolsActivePort.
      "--remote-debugging-port=0",
      `--user-data-dir=${profile}`,
      "--no-first-run",
      "--no-default-browser-check",
      "--hide-scrollbars",
      "about:blank",
    ],
    { stdio: ["ignore", "ignore", "pipe"] },
  );
  cleanups.push(() => stopChrome(child));
  let log = "";
  let failure = null;
  child.stderr.on("data", (chunk) => {
    log = (log + chunk).slice(-2000);
  });
  child.once("error", (error) => {
    failure = error;
  });
  const portFile = join(profile, "DevToolsActivePort");
  const deadline = Date.now() + 20_000;
  for (;;) {
    if (failure) throw new Error(`Chrome did not start (${binary}): ${failure.message}`);
    if (existsSync(portFile)) {
      const [port, path] = readFileSync(portFile, "utf8").split("\n");
      if (Number(port) > 0 && path) return Number(port);
    }
    if (child.exitCode !== null || child.signalCode !== null) {
      throw new Error(`Chrome exited before it opened its debugging port:\n${log.trim()}`);
    }
    if (Date.now() > deadline) throw new Error(`Chrome opened no debugging port within 20 s:\n${log.trim()}`);
    await sleep(100);
  }
}

/* One tab, driven over its DevTools WebSocket. Every call has a time limit,
   and a protocol error rejects with Chrome's own message. */
async function openTab(port) {
  const response = await fetch(`http://127.0.0.1:${port}/json/new?about:blank`, { method: "PUT" });
  if (!response.ok) throw new Error(`Chrome would not open a tab: HTTP ${response.status}`);
  const { webSocketDebuggerUrl } = await response.json();
  const socket = new WebSocket(webSocketDebuggerUrl);
  await new Promise((done, fail) => {
    socket.addEventListener("open", done, { once: true });
    socket.addEventListener("error", () => fail(new Error("could not connect to Chrome's tab")), { once: true });
  });
  cleanups.push(() => socket.close());

  let last = 0;
  const calls = new Map();
  const listeners = new Set();
  socket.addEventListener("message", (event) => {
    const message = JSON.parse(event.data);
    if (message.id === undefined) {
      for (const listener of [...listeners]) listener(message);
      return;
    }
    const call = calls.get(message.id);
    if (!call) return;
    calls.delete(message.id);
    clearTimeout(call.timer);
    if (message.error) call.fail(new Error(`${call.method}: ${message.error.message}`));
    else call.done(message.result);
  });
  socket.addEventListener("close", () => {
    for (const call of calls.values()) {
      clearTimeout(call.timer);
      call.fail(new Error(`${call.method}: Chrome closed the connection`));
    }
    calls.clear();
  });

  const seconds = (ms) => `${Math.round(ms / 1000)} s`;
  const send = (method, params = {}, ms = 30_000) => {
    if (socket.readyState !== WebSocket.OPEN) return Promise.reject(new Error(`${method}: Chrome is not connected`));
    return new Promise((done, fail) => {
      const id = ++last;
      const timer = setTimeout(() => {
        calls.delete(id);
        fail(new Error(`${method}: no answer within ${seconds(ms)}`));
      }, ms);
      calls.set(id, { method, done, fail, timer });
      socket.send(JSON.stringify({ id, method, params }));
    });
  };
  const event = (method, ms = 30_000) =>
    new Promise((done, fail) => {
      const timer = setTimeout(() => {
        listeners.delete(listener);
        fail(new Error(`no ${method} within ${seconds(ms)}`));
      }, ms);
      const listener = (message) => {
        if (message.method !== method) return;
        clearTimeout(timer);
        listeners.delete(listener);
        done(message.params);
      };
      listeners.add(listener);
    });
  const evaluate = async (expression, ms = 30_000) => {
    const { result, exceptionDetails } = await send(
      "Runtime.evaluate",
      { expression, awaitPromise: true, returnByValue: true },
      ms,
    );
    if (exceptionDetails) throw new Error(exceptionDetails.exception?.description ?? exceptionDetails.text);
    return result.value;
  };

  await send("Page.enable");
  return { send, event, evaluate };
}

/* Refuse early, and in words, when this Chrome cannot write WebP. Never fall
   back to another format. */
async function checkWebp(tab, binary) {
  let data;
  try {
    ({ data } = await tab.send("Page.captureScreenshot", {
      format: "webp",
      quality: QUALITY,
      clip: { x: 0, y: 0, width: 8, height: 8, scale: 1 },
    }));
  } catch (error) {
    throw new Error(`${binary} will not write WebP (${error.message}). Use a newer Google Chrome, or set CHROME to one.`);
  }
  if (!isWebp(Buffer.from(data, "base64"))) {
    throw new Error(`${binary} was asked for WebP and wrote something else. Use a newer Google Chrome, or set CHROME to one.`);
  }
}

/* Run in the page: how far the charts have got. A chart is done when Plotly
   has drawn it (.js-plotly-plot holding a .main-svg) and LazyChart has taken
   its waiting veil off (data-chart="drawn"). */
const PROGRESS = `(() => {
  const grid = document.querySelector("[data-preview-grid]");
  if (!grid) return { problem: "the page has no [data-preview-grid]" };
  const charts = [...grid.querySelectorAll("[data-chart]")];
  const failed = charts.find((chart) => chart.dataset.chart === "failed");
  if (failed) return { problem: "a chart failed: " + failed.textContent.trim() };
  return {
    charts: charts.length,
    plots: [...grid.querySelectorAll(".js-plotly-plot")].filter((plot) => plot.querySelector(".main-svg")).length,
    unveiled: charts.filter((chart) => chart.dataset.chart === "drawn").length,
  };
})()`;

/* Run in the page: resolves once nothing in the grid has changed for 500 ms
   (Plotly lays a chart out again after it first draws), then two frames. */
const SETTLED = `new Promise((done) => {
  const grid = document.querySelector("[data-preview-grid]");
  let timer;
  const quiet = () => {
    watch.disconnect();
    requestAnimationFrame(() => requestAnimationFrame(() => done(true)));
  };
  const watch = new MutationObserver(() => {
    clearTimeout(timer);
    timer = setTimeout(quiet, 500);
  });
  watch.observe(grid, { subtree: true, childList: true, attributes: true, characterData: true });
  timer = setTimeout(quiet, 500);
})`;

/* Run in the page: the grid's box, and the top of its highest chart (a block
   that is neither a note nor a KPI tile). */
const GRID_BOX = `(() => {
  const grid = document.querySelector("[data-preview-grid]");
  const tops = [...grid.querySelectorAll("[data-block-kind]")]
    .filter((block) => block.dataset.blockKind === "chart")
    .map((block) => block.getBoundingClientRect().top + scrollY);
  const box = grid.getBoundingClientRect();
  return { left: box.left + scrollX, width: box.width, bottom: box.bottom + scrollY, top: tops.length ? Math.min(...tops) : null };
})()`;

/* Run in the page: Chrome decodes the picture it wrote and reports its size. */
const DECODED_SIZE = (base64) => `(async () => {
  const image = new Image();
  image.src = "data:image/webp;base64,${base64}";
  await image.decode();
  return { width: image.naturalWidth, height: image.naturalHeight };
})()`;

async function capture(tab, base, { name, charts, sha256 }) {
  const deadline = Date.now() + TIMEOUT_MS;
  const left = () => Math.max(1, deadline - Date.now());
  const viewport = (height) =>
    tab.send(
      "Emulation.setDeviceMetricsOverride",
      { width: VIEWPORT_WIDTH, height, deviceScaleFactor: 1, mobile: false },
      left(),
    );
  let stage = "opening its page";
  try {
    await viewport(900);
    const loaded = tab.event("Page.loadEventFired", left());
    loaded.catch(() => {});
    const { errorText } = await tab.send("Page.navigate", { url: `${base}/dashboards/${name}/` }, left());
    if (errorText) throw new Error(`the page did not open (${errorText})`);
    await loaded;
    stage = "waiting for its fonts";
    await tab.evaluate("document.fonts.ready.then(() => true)", left());

    // Taller than the whole page: the sticky prompt box then sits below the
    // charts instead of over them, and every chart is inside LazyChart's
    // 600 px margin, so all of them draw.
    const height = await tab.evaluate("document.documentElement.scrollHeight", left());
    await viewport(height + 200);

    stage = `drawing its charts (none of ${charts} drawn yet)`;
    for (;;) {
      const progress = await tab.evaluate(PROGRESS, left());
      if (progress.problem) throw new Error(progress.problem);
      if (progress.charts > charts) {
        throw new Error(`the page holds ${progress.charts} charts, and build.charts_drawn says ${charts}`);
      }
      if (progress.plots === charts && progress.unveiled === charts) break;
      stage = `drawing its charts (${progress.plots} of ${charts} drawn)`;
      if (Date.now() >= deadline) throw new Error("timed out");
      await sleep(200);
    }
    stage = "waiting for the charts to settle";
    await tab.evaluate(SETTLED, left());
    await tab.evaluate("document.fonts.ready.then(() => true)", left());

    stage = "taking the picture";
    const grid = await tab.evaluate(GRID_BOX, left());
    if (grid.top === null) throw new Error("the grid holds no chart");
    const x = Math.round(grid.left);
    const y = Math.round(grid.top);
    const width = Math.round(grid.width);
    const tall = Math.min(Math.round((width * 5) / 4), Math.floor(grid.bottom) - y);
    const { data } = await tab.send(
      "Page.captureScreenshot",
      {
        format: "webp",
        quality: QUALITY,
        captureBeyondViewport: true,
        clip: { x, y, width, height: tall, scale: IMAGE_WIDTH / width },
      },
      left(),
    );
    const bytes = Buffer.from(data, "base64");
    if (!isWebp(bytes)) throw new Error("Chrome wrote something other than WebP");
    const size = await tab.evaluate(DECODED_SIZE(data), left());
    if (size.width !== IMAGE_WIDTH) throw new Error(`the picture is ${size.width} px wide, not ${IMAGE_WIDTH}`);
    return { name, sha256, bytes, ...size, clip: { x, y, width, height: tall } };
  } catch (error) {
    if (Date.now() >= deadline) throw new Error(`${name}: timed out after ${TIMEOUT_MS / 1000} s, ${stage}`);
    throw new Error(`${name}: ${error.message}`);
  }
}

/* Every picture is taken before any file is written, so a failure halfway
   leaves the previous set whole. */
function write(shots) {
  mkdirSync(IMAGES, { recursive: true });
  const record = { made_by: "scripts/previews.mjs", viewport_width: VIEWPORT_WIDTH, crop: CROP, dashboards: {} };
  let tooBig = 0;
  for (const shot of shots) {
    writeFileSync(join(IMAGES, `${shot.name}.webp`), shot.bytes);
    record.dashboards[shot.name] = {
      file: `/previews/${shot.name}.webp`,
      width: shot.width,
      height: shot.height,
      sha256: shot.sha256,
    };
    const { x, y, width, height } = shot.clip;
    console.log(
      `${shot.name}: ${shot.width} × ${shot.height} px, ${(shot.bytes.length / 1024).toFixed(1)} KB ` +
        `(from ${width} × ${height} CSS px at ${x}, ${y})`,
    );
    if (shot.bytes.length >= MAX_BYTES) {
      console.error(`previews: ${shot.name}.webp is ${shot.bytes.length} bytes, at or over ${MAX_BYTES}`);
      tooBig += 1;
    }
  }
  for (const file of readdirSync(IMAGES)) {
    if (file.endsWith(".webp") && !record.dashboards[file.slice(0, -".webp".length)]) {
      unlinkSync(join(IMAGES, file));
      console.log(`removed public/previews/${file}: no dashboard of that name`);
    }
  }
  writeFileSync(RECORD, `${JSON.stringify(record, null, 2)}\n`);
  console.log(`wrote public/previews/ and data/previews.json. Run npm run build again, so out/ carries them.`);
  if (tooBig) process.exitCode = 1;
}

async function main() {
  const dashboards = readDashboards();
  checkBuild();
  const binary = findChrome();
  const base = await serve(OUT);
  const tab = await openTab(await launchChrome(binary));
  await checkWebp(tab, binary);
  const shots = [];
  for (const dashboard of dashboards) shots.push(await capture(tab, base, dashboard));
  write(shots);
}

let stoppedBy = null;
for (const signal of ["SIGINT", "SIGTERM"]) {
  process.on(signal, () => {
    if (stoppedBy) return; // a repeat while cleaning up changes nothing
    stoppedBy = signal;
    console.error(`previews: stopped by ${signal}`);
    void cleanUp().finally(() => process.exit(130));
  });
}

try {
  await main();
} catch (error) {
  // After a signal, the error is only Chrome going away under the run.
  if (!stoppedBy) console.error(`previews: ${error.message}`);
  process.exitCode = 1;
} finally {
  await cleanUp();
}
