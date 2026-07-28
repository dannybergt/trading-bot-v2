// Live smoke probe against a DEPLOYED instance (public domain or internal IP).
//
// Unlike tests/run-ui-regression.mjs this is a read-only diagnostic, not a gate:
// it never boots a stack, never registers a user and never mutates data. It
// drives headless Chrome over CDP so the checks see the real artifact through
// the real reverse proxy, which is exactly where the last two defects lived
// (shallow-checkout version string, proxy-collapsed client IPs).
//
// Anonymous checks always run. The authenticated block only runs when
// LIVE_TEST_EMAIL / LIVE_TEST_PASSWORD are present in the environment -- keep
// those in .env.local (mode 600, gitignored), never on the command line.
//
// Usage:
//   node tests/run-live-ui-smoke.mjs
//   LIVE_URL=http://172.30.15.75:18094 node tests/run-live-ui-smoke.mjs
//   set -a; . ./.env.local; set +a; node tests/run-live-ui-smoke.mjs

import { spawn } from "node:child_process";
import { mkdir, mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";

const LIVE_URL = (process.env.LIVE_URL || "https://nex-trade.bergt-consulting.de").replace(/\/$/, "");
const CHROME_BIN = process.env.CHROME_BIN || "google-chrome";
// 0 = let Chrome pick a free port and report it via DevToolsActivePort. Never
// assume a fixed port: a foreign Chrome listening on it still answers
// /json/version, and we would silently drive someone else's browser.
const DEBUG_PORT = Number(process.env.CHROME_DEBUG_PORT || "0");
const ARTIFACT_DIR = process.env.LIVE_ARTIFACT_DIR || "artifacts/live-ui-smoke";
const TEST_EMAIL = process.env.LIVE_TEST_EMAIL || "";
const TEST_PASSWORD = process.env.LIVE_TEST_PASSWORD || "";

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

const findings = [];
const passed = [];

function ok(step, detail = "") {
  passed.push(step);
  console.log(`ok   ${step}${detail ? ` -- ${detail}` : ""}`);
}

function finding(step, detail) {
  findings.push({ step, detail });
  console.log(`FAIL ${step} -- ${detail}`);
}

class CDPClient {
  constructor(webSocketUrl) {
    this.webSocketUrl = webSocketUrl;
    this.nextId = 1;
    this.pending = new Map();
    this.listeners = new Map();
    this.consoleErrors = [];
  }

  async connect() {
    await new Promise((resolve, reject) => {
      this.socket = new WebSocket(this.webSocketUrl);
      this.socket.addEventListener("open", resolve, { once: true });
      this.socket.addEventListener("error", reject, { once: true });
      this.socket.addEventListener("message", (event) => this.handleMessage(event));
      this.socket.addEventListener("close", () => {
        for (const { reject: rejectPending } of this.pending.values()) {
          rejectPending(new Error("CDP socket closed"));
        }
        this.pending.clear();
      });
    });
  }

  handleMessage(event) {
    const message = JSON.parse(event.data);
    if (message.id) {
      const deferred = this.pending.get(message.id);
      if (!deferred) return;
      this.pending.delete(message.id);
      if (message.error) {
        deferred.reject(new Error(message.error.message || "Unknown CDP error"));
        return;
      }
      deferred.resolve(message.result);
      return;
    }
    for (const handler of this.listeners.get(message.method) || []) {
      handler(message.params);
    }
  }

  on(method, handler) {
    const handlers = this.listeners.get(method) || [];
    handlers.push(handler);
    this.listeners.set(method, handlers);
  }

  once(method) {
    return new Promise((resolve) => {
      const handlers = this.listeners.get(method) || [];
      const wrapped = (params) => {
        this.listeners.set(
          method,
          (this.listeners.get(method) || []).filter((entry) => entry !== wrapped),
        );
        resolve(params);
      };
      handlers.push(wrapped);
      this.listeners.set(method, handlers);
    });
  }

  async send(method, params = {}) {
    const id = this.nextId++;
    const response = new Promise((resolve, reject) => {
      this.pending.set(id, { resolve, reject });
    });
    this.socket.send(JSON.stringify({ id, method, params }));
    return response;
  }

  async evaluate(expression) {
    const result = await this.send("Runtime.evaluate", {
      expression,
      awaitPromise: true,
      returnByValue: true,
    });
    if (result.exceptionDetails) {
      throw new Error(result.result?.description || "Runtime evaluation failed");
    }
    return result.result.value;
  }

  trackConsoleErrors() {
    this.on("Runtime.exceptionThrown", (params) => {
      const text =
        params?.exceptionDetails?.exception?.description ||
        params?.exceptionDetails?.text ||
        "unknown exception";
      this.consoleErrors.push({ url: this.currentUrl, text: String(text).split("\n")[0] });
    });
    this.on("Runtime.consoleAPICalled", (params) => {
      if (params.type !== "error") return;
      const text = (params.args || [])
        .map((arg) => arg.value ?? arg.description ?? "")
        .join(" ")
        .trim();
      if (!text) return;
      this.consoleErrors.push({ url: this.currentUrl, text: text.split("\n")[0] });
    });
  }
}

async function resolveOwnDebugPort(chromeProcess, userDataDir, timeoutMs = 30000) {
  const portFile = join(userDataDir, "DevToolsActivePort");
  const startedAt = Date.now();
  while (Date.now() - startedAt < timeoutMs) {
    if (chromeProcess.exitCode !== null || chromeProcess.signalCode !== null) {
      throw new Error("Chrome exited before reporting a debugging port");
    }
    try {
      const port = Number((await readFile(portFile, "utf8")).split("\n")[0].trim());
      if (Number.isInteger(port) && port > 0) return port;
    } catch {
      // not written yet
    }
    await sleep(200);
  }
  throw new Error("Chrome never wrote DevToolsActivePort");
}

async function waitForChrome(debugPort, timeoutMs = 20000) {
  const startedAt = Date.now();
  while (Date.now() - startedAt < timeoutMs) {
    try {
      const response = await fetch(`http://127.0.0.1:${debugPort}/json/version`);
      if (response.ok) return;
    } catch {
      // retry
    }
    await sleep(250);
  }
  throw new Error("Chrome remote debugging endpoint did not become ready");
}

async function getPageWebSocketUrl(debugPort) {
  const response = await fetch(`http://127.0.0.1:${debugPort}/json/list`);
  const pages = await response.json();
  const page = pages.find((entry) => entry.type === "page" && entry.webSocketDebuggerUrl);
  if (!page) throw new Error("No debuggable page target found");
  return page.webSocketDebuggerUrl;
}

async function waitFor(client, description, expression, timeoutMs = 20000) {
  const startedAt = Date.now();
  let lastError = "";
  while (Date.now() - startedAt < timeoutMs) {
    try {
      if (await client.evaluate(expression)) return true;
    } catch (error) {
      lastError = error.message;
    }
    await sleep(250);
  }
  throw new Error(`timed out waiting for ${description}${lastError ? ` (${lastError})` : ""}`);
}

async function navigate(client, path) {
  const url = path.startsWith("http") ? path : `${LIVE_URL}${path}`;
  client.currentUrl = url;
  const loadEvent = client.once("Page.loadEventFired");
  await client.send("Page.navigate", { url });
  await Promise.race([loadEvent, sleep(30000)]);
  await sleep(600);
}

async function setViewport(client, width, height) {
  await client.send("Emulation.setDeviceMetricsOverride", {
    width,
    height,
    deviceScaleFactor: 1,
    mobile: false,
  });
  await sleep(400);
}

async function shot(client, name) {
  await mkdir(ARTIFACT_DIR, { recursive: true });
  const { data } = await client.send("Page.captureScreenshot", { format: "png" });
  await writeFile(join(ARTIFACT_DIR, `${name}.png`), Buffer.from(data, "base64"));
}

async function noHorizontalOverflow(client) {
  return client.evaluate(
    "(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1)()",
  );
}

async function checkStep(step, fn) {
  try {
    const detail = await fn();
    ok(step, typeof detail === "string" ? detail : "");
  } catch (error) {
    finding(step, error.message);
  }
}

async function runAnonymousChecks(client) {
  await checkStep("live_login_screen", async () => {
    await navigate(client, "/login");
    await waitFor(
      client,
      "login form",
      "!!document.querySelector('form[aria-label=\"login form\"]') && !!document.querySelector('input[type=\"email\"]') && !!document.querySelector('input[type=\"password\"]')",
    );
    await shot(client, "01-login");
    return LIVE_URL;
  });

  await checkStep("live_version_badge", async () => {
    // Read the whole badge, not just a regex match inside it -- a doubled "v"
    // prefix hides from any pattern that starts matching at the version itself.
    const badge = await client.evaluate(
      "(() => (document.body.innerText.match(/^\\s*(v\\S+(?: \\u00b7 \\S+)?)\\s*$/m) || [])[1] || '')()",
    );
    const api = await fetch(`${LIVE_URL}/api/version`).then((r) => r.json());
    if (!badge) throw new Error("no version string rendered on the login page");
    const shown = badge.split("·")[0].trim();
    if (/^vv/.test(shown)) {
      throw new Error(
        `version badge renders a doubled prefix: "${shown}" (api reports "${api.version}")`,
      );
    }
    if (shown.replace(/^v/, "") !== api.version.replace(/^v/, "")) {
      throw new Error(`badge "${shown}" does not match /api/version "${api.version}"`);
    }
    return `${badge} matches ${api.version}`;
  });

  await checkStep("live_language_toggle", async () => {
    // LanguageToggle renders a <select>, so a click is not enough -- the change
    // event is what drives setLanguage().
    const before = await client.evaluate("document.body.innerText.slice(0, 400)");
    const switched = await client.evaluate(`
      (() => {
        const select = document.querySelector("select");
        if (!select) return "";
        const target = Array.from(select.options).find((o) => o.value === "de") || select.options[1];
        if (!target) return "";
        select.value = target.value;
        select.dispatchEvent(new Event("change", { bubbles: true }));
        return target.value;
      })()
    `);
    if (!switched) throw new Error("no language select found on the login page");
    await sleep(600);
    const after = await client.evaluate("document.body.innerText.slice(0, 400)");
    if (before === after) throw new Error(`switching to "${switched}" did not change any copy`);
    const stored = await client.evaluate("localStorage.getItem('language')");
    if (stored !== switched) {
      throw new Error(`language "${switched}" was not persisted (localStorage.language = ${stored})`);
    }
    // Persistence has to survive a reload, that is the whole point of storing
    // it. Compare the submit label rather than a slice of body text -- the
    // service-worker toast appears and disappears on its own and would make a
    // broad text comparison flap.
    const submitLabel = () =>
      client.evaluate(
        "(() => document.querySelector('form[aria-label=\"login form\"] button[type=\"submit\"]')?.textContent.trim() || '')()",
      );
    const labelBefore = await submitLabel();
    await navigate(client, "/login");
    const labelAfter = await submitLabel();
    if (labelAfter !== labelBefore || !labelAfter) {
      throw new Error(
        `language choice did not survive a reload ("${labelBefore}" -> "${labelAfter}")`,
      );
    }
    return `switched to "${switched}", persisted, survives reload ("${labelAfter}")`;
  });

  for (const [path, marker, label] of [
    ["/register", "form", "register"],
    ["/forgot-password", "form", "forgot-password"],
    ["/reset-password", "form", "reset-password"],
  ]) {
    await checkStep(`live_public_page_${label}`, async () => {
      await navigate(client, path);
      await waitFor(client, `${label} ${marker}`, `!!document.querySelector('${marker}')`);
      if (!(await noHorizontalOverflow(client))) {
        throw new Error("horizontal overflow at default viewport");
      }
      return "renders";
    });
  }

  await checkStep("live_public_viewports", async () => {
    await navigate(client, "/login");
    const bad = [];
    for (const width of [390, 768, 1280, 1920]) {
      await setViewport(client, width, width === 390 ? 844 : 1000);
      if (!(await noHorizontalOverflow(client))) bad.push(width);
      await shot(client, `02-login-${width}`);
    }
    await client.send("Emulation.clearDeviceMetricsOverride");
    if (bad.length) throw new Error(`horizontal overflow at ${bad.join(", ")}px`);
    return "390 / 768 / 1280 / 1920 clean";
  });
}

async function login(client) {
  await navigate(client, "/login");
  await waitFor(client, "login form", "!!document.querySelector('input[type=\"password\"]')");
  // Credentials are injected via CDP from the environment. They are never
  // logged, never written to an artifact and never appear in the transcript.
  await client.send("Runtime.evaluate", {
    expression: `
      (() => {
        const setValue = (el, value) => {
          const setter = Object.getOwnPropertyDescriptor(
            window.HTMLInputElement.prototype, "value",
          ).set;
          setter.call(el, value);
          el.dispatchEvent(new Event("input", { bubbles: true }));
        };
        setValue(document.querySelector('input[type="email"]'), ${JSON.stringify(TEST_EMAIL)});
        setValue(document.querySelector('input[type="password"]'), ${JSON.stringify(TEST_PASSWORD)});
        document.querySelector('form[aria-label="login form"] button[type="submit"]').click();
        return true;
      })()
    `,
    awaitPromise: true,
    returnByValue: true,
  });
  await waitFor(
    client,
    "authenticated shell",
    "(() => !location.pathname.startsWith('/login') && !!document.querySelector('header'))()",
    25000,
  );
}

async function runAuthenticatedChecks(client) {
  await checkStep("live_login_flow", async () => {
    await login(client);
    await shot(client, "10-dashboard");
    return await client.evaluate("location.pathname");
  });

  if (findings.some((entry) => entry.step === "live_login_flow")) {
    console.log("skip authenticated checks -- login did not succeed");
    return;
  }

  await checkStep("live_mobile_nav", async () => {
    await setViewport(client, 390, 844);
    await navigate(client, "/");
    if (!(await noHorizontalOverflow(client))) {
      throw new Error("horizontal overflow at 390px");
    }
    const collapsed = await client.evaluate(`
      (() => {
        const inline = document.querySelector('[data-testid="primary-nav"]');
        const toggle = document.querySelector('[data-testid="nav-toggle"]');
        if (!inline || !toggle) return "missing nav testids";
        if (getComputedStyle(inline).display !== "none") return "inline nav still visible";
        if (getComputedStyle(toggle).display === "none") return "toggle not visible";
        if (document.querySelector('[data-testid="mobile-nav"]')) return "panel open by default";
        if (toggle.getAttribute("aria-expanded") !== "false") return "aria-expanded not false";
        return "";
      })()
    `);
    if (collapsed) throw new Error(collapsed);
    await shot(client, "11-mobile-collapsed");

    await client.evaluate("document.querySelector('[data-testid=\"nav-toggle\"]').click()");
    await waitFor(
      client,
      "mobile nav panel",
      "(() => { const p = document.querySelector('[data-testid=\"mobile-nav\"]'); return !!p && p.querySelectorAll('a').length >= 10; })()",
    );
    const linkCount = await client.evaluate(
      "document.querySelectorAll('[data-testid=\"mobile-nav\"] a').length",
    );
    await shot(client, "12-mobile-open");

    await client.evaluate(`
      (() => {
        const links = Array.from(document.querySelectorAll('[data-testid="mobile-nav"] a'));
        (links.find((a) => a.getAttribute("href") === "/watchlists") || links[0]).click();
      })()
    `);
    await waitFor(
      client,
      "panel closes after navigation",
      "(() => !document.querySelector('[data-testid=\"mobile-nav\"]'))()",
    );
    await client.send("Emulation.clearDeviceMetricsOverride");
    return `collapsed, ${linkCount} links, closes after navigation`;
  });

  await checkStep("live_wide_shell", async () => {
    const bad = [];
    for (const width of [1280, 1920]) {
      await setViewport(client, width, 1000);
      await navigate(client, "/");
      if (!(await noHorizontalOverflow(client))) bad.push(`${width}px overflow`);
      const clipped = await client.evaluate(`
        (() => {
          const buttons = Array.from(document.querySelectorAll("header button"));
          const last = buttons[buttons.length - 1];
          if (!last) return true;
          return last.getBoundingClientRect().right > document.documentElement.clientWidth + 1;
        })()
      `);
      if (clipped) bad.push(`${width}px header action clipped`);
      await shot(client, `13-shell-${width}`);
    }
    const mainWidth = await client.evaluate(
      "(() => document.querySelector('main')?.getBoundingClientRect().width || 0)()",
    );
    if (mainWidth < 1400) bad.push(`content capped at ${Math.round(mainWidth)}px on 1920`);
    await client.send("Emulation.clearDeviceMetricsOverride");
    if (bad.length) throw new Error(bad.join("; "));
    return `1280 + 1920 clean, main ${Math.round(mainWidth)}px`;
  });

  await checkStep("live_i18n_german", async () => {
    await client.evaluate("localStorage.setItem('language', 'de')");
    const englishLeftovers = [];
    for (const [path, marker] of [
      ["/alerts", "Alerts"],
      ["/watchlists", "Watchlists"],
      ["/scanner", "Scanner"],
      ["/settings", "Settings"],
      ["/news", "News"],
      ["/discover", "Discover"],
      ["/paper-trading", "Paper Trading"],
      ["/auto-execution", "Auto Execution"],
    ]) {
      await navigate(client, path);
      await waitFor(client, `${path} heading`, "!!document.querySelector('h1, h2')");
      const heading = await client.evaluate(
        "(() => document.querySelector('main h1, main h2')?.textContent.trim() || '')()",
      );
      if (heading === marker) englishLeftovers.push(`${path} -> "${heading}"`);
    }
    if (englishLeftovers.length) {
      throw new Error(`still english with language=de: ${englishLeftovers.join(", ")}`);
    }
    return "alerts/watchlists/scanner/settings/news/discover/paper-trading/auto-execution translated";
  });

  await checkStep("live_analysis_composite", async () => {
    await navigate(client, "/analysis/AAPL");
    await waitFor(client, "analysis content", "!!document.querySelector('main h1, main h2')", 40000);
    await sleep(3000);
    await shot(client, "14-analysis");
    const text = await client.evaluate("document.body.innerText");
    const hasComposite = /composite|gesamt/i.test(text);
    const hasSynthetic = /synthet/i.test(text);
    if (!hasComposite) throw new Error("no composite verdict rendered on /analysis/AAPL");
    return hasSynthetic ? "composite present, SYNTHETIC banner shown" : "composite present, real data";
  });

  await checkStep("live_watchlist_delete_affordance", async () => {
    await navigate(client, "/watchlists");
    await waitFor(client, "watchlists page", "!!document.querySelector('main')", 25000);
    await sleep(1500);
    await shot(client, "15-watchlists");
    // Read-only: production data is not deleted here. This only proves the
    // affordance the 2026-07-26 fix introduced is present in the artifact.
    const state = await client.evaluate(`
      (() => {
        const text = document.body.innerText;
        const buttons = Array.from(document.querySelectorAll("main button"))
          .map((b) => b.textContent.trim().toLowerCase());
        return JSON.stringify({
          deleteButtons: buttons.filter((t) => /delete|l(o|oe)schen/.test(t)).length,
          defaultBadge: /default|start/i.test(text),
        });
      })()
    `);
    const parsed = JSON.parse(state);
    if (!parsed.deleteButtons) throw new Error("no delete affordance on any watchlist");
    return `${parsed.deleteButtons} delete controls, default badge ${parsed.defaultBadge ? "shown" : "absent"}`;
  });

  await checkStep("live_help_docs", async () => {
    await navigate(client, "/docs");
    await waitFor(client, "docs page", "!!document.querySelector('main')", 25000);
    await sleep(1000);
    const topics = await client.evaluate(
      "document.querySelectorAll('main a[href^=\"/docs/\"]').length",
    );
    if (!topics) throw new Error("docs page lists no topics");
    await shot(client, "16-docs");
    return `${topics} help topics linked`;
  });
}

async function run() {
  await mkdir(ARTIFACT_DIR, { recursive: true });
  const userDataDir = await mkdtemp(join(tmpdir(), "trading-bot-v2-live-"));
  const chromeProcess = spawn(
    CHROME_BIN,
    [
      "--headless=new",
      "--disable-gpu",
      "--no-sandbox",
      `--remote-debugging-port=${DEBUG_PORT}`,
      `--user-data-dir=${userDataDir}`,
      "about:blank",
    ],
    { stdio: "ignore" },
  );

  let client;
  try {
    const debugPort = await resolveOwnDebugPort(chromeProcess, userDataDir);
    await waitForChrome(debugPort);
    client = new CDPClient(await getPageWebSocketUrl(debugPort));
    await client.connect();
    await client.send("Page.enable");
    await client.send("Runtime.enable");
    client.trackConsoleErrors();

    console.log(`# live smoke against ${LIVE_URL}`);
    await runAnonymousChecks(client);

    if (TEST_EMAIL && TEST_PASSWORD) {
      await runAuthenticatedChecks(client);
    } else {
      console.log(
        "skip authenticated checks -- LIVE_TEST_EMAIL / LIVE_TEST_PASSWORD not set in the environment",
      );
    }

    const noise = client.consoleErrors.filter(
      (entry) => !/favicon|ERR_BLOCKED_BY_CLIENT|manifest/i.test(entry.text),
    );
    if (noise.length) {
      console.log(`\n# console errors (${noise.length})`);
      for (const entry of noise.slice(0, 25)) {
        console.log(`  ${entry.url} :: ${entry.text}`);
      }
    } else {
      ok("live_console_clean", "no console errors on the visited pages");
    }
  } finally {
    if (client) {
      try {
        await client.socket?.close();
      } catch {
        // ignore
      }
    }
    if (chromeProcess.exitCode === null && chromeProcess.signalCode === null) {
      chromeProcess.kill("SIGTERM");
      await sleep(1500);
      if (chromeProcess.exitCode === null && chromeProcess.signalCode === null) {
        chromeProcess.kill("SIGKILL");
      }
    }
    await rm(userDataDir, { recursive: true, force: true }).catch(() => {});
  }

  console.log(`\n# ${passed.length} ok, ${findings.length} findings`);
  for (const entry of findings) {
    console.log(`  FAIL ${entry.step}: ${entry.detail}`);
  }
  console.log(`# screenshots in ${ARTIFACT_DIR}`);
  process.exitCode = findings.length ? 1 : 0;
}

run().catch((error) => {
  console.error(`live smoke aborted: ${error.message}`);
  process.exitCode = 2;
});
