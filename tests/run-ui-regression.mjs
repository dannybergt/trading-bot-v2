import { spawn } from "node:child_process";
import { mkdir, mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";

const FRONTEND_URL = process.env.FRONTEND_URL || "http://127.0.0.1:18094";
const CHROME_BIN = process.env.CHROME_BIN || "google-chrome";
// 0 = let Chrome pick a free port and report it via DevToolsActivePort.
//
// A fixed port is actively dangerous here: several agents share this host, and
// a foreign Chrome already listening on it makes our own instance fail to bind
// while `/json/version` still answers -- from the FOREIGN browser. The gate then
// drives someone else's profile, complete with a service worker still serving a
// previously precached bundle, and reports green or red for code it never
// loaded. Both failure directions were observed before this was pinned down.
const DEBUG_PORT = Number(process.env.CHROME_DEBUG_PORT || "0");
const UI_ARTIFACT_DIR = process.env.UI_ARTIFACT_DIR || "artifacts/ui-regression";
const TEST_EMAIL = process.env.UI_TEST_EMAIL || `ui-regression-${Date.now()}@example.com`;
const TEST_PASSWORD = process.env.UI_TEST_PASSWORD || "UIRegressionPass123!";

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

class CDPClient {
  constructor(webSocketUrl) {
    this.webSocketUrl = webSocketUrl;
    this.nextId = 1;
    this.pending = new Map();
    this.listeners = new Map();
    // Konsolenfehler werden mitgeschnitten, weil §4 Phase 4 die
    // Konsolenpruefung verlangt und dieser Harnisch sie bis 2026-08-05 gar
    // nicht erhoben hat: eine React-Komponente konnte einen TypeError werfen,
    // und solange die assertierten Textbausteine im DOM standen, blieb der
    // Lauf gruen. Die Implementierung stammt aus run-live-ui-smoke.mjs, wo sie
    // sich bereits bewaehrt hat.
    this.consoleErrors = [];
    this.currentUrl = "(before first navigation)";
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
    const handlers = this.listeners.get(message.method) || [];
    for (const handler of handlers) handler(message.params || {});
  }

  on(method, handler) {
    const handlers = this.listeners.get(method) || [];
    handlers.push(handler);
    this.listeners.set(method, handlers);
    return () => {
      const currentHandlers = this.listeners.get(method) || [];
      this.listeners.set(
        method,
        currentHandlers.filter((currentHandler) => currentHandler !== handler),
      );
    };
  }

  once(method) {
    return new Promise((resolve) => {
      const unsubscribe = this.on(method, (params) => {
        unsubscribe();
        resolve(params);
      });
    });
  }

  async send(method, params = {}) {
    const id = this.nextId++;
    const payload = JSON.stringify({ id, method, params });
    const response = new Promise((resolve, reject) => {
      this.pending.set(id, { resolve, reject });
    });
    this.socket.send(payload);
    return response;
  }

  async evaluate(expression, { awaitPromise = true, returnByValue = true } = {}) {
    const result = await this.send("Runtime.evaluate", {
      expression,
      awaitPromise,
      returnByValue,
    });
    if (result.exceptionDetails) {
      const description = result.result?.description || "Runtime evaluation failed";
      throw new Error(description);
    }
    return returnByValue ? result.result.value : result.result;
  }

  async close() {
    if (!this.socket) return;
    this.socket.close();
    await sleep(250);
  }
}

/**
 * Resolve the debug port of the Chrome WE spawned.
 *
 * Chrome writes the port it actually bound to into `DevToolsActivePort` inside
 * its own user-data-dir. Reading it there -- instead of assuming a port number
 * -- is what guarantees we attach to our own instance and not to a foreign
 * browser that happens to answer on the same port.
 */
async function resolveOwnDebugPort(chromeProcess, userDataDir, requestedPort, timeoutMs = 30000) {
  const portFile = join(userDataDir, "DevToolsActivePort");
  const startedAt = Date.now();
  while (Date.now() - startedAt < timeoutMs) {
    if (chromeProcess.exitCode !== null || chromeProcess.signalCode !== null) {
      throw new Error(
        `Chrome exited before it reported a debugging port (code=${chromeProcess.exitCode}, signal=${chromeProcess.signalCode}). ` +
          (requestedPort ? `Is port ${requestedPort} already in use by another browser?` : ""),
      );
    }
    try {
      const port = Number((await readFile(portFile, "utf8")).split("\n")[0].trim());
      if (Number.isInteger(port) && port > 0) return port;
    } catch {
      // not written yet
    }
    await sleep(200);
  }
  throw new Error("Chrome never wrote DevToolsActivePort -- cannot confirm which browser we would drive");
}

async function waitForChrome(debugPort, timeoutMs = 15000) {
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

async function waitForCondition(client, description, expression, timeoutMs = 15000) {
  const startedAt = Date.now();
  while (Date.now() - startedAt < timeoutMs) {
    const matched = await client.evaluate(expression);
    if (matched) return;
    await sleep(200);
  }
  throw new Error(`Timed out waiting for condition: ${description}`);
}

async function navigate(client, url) {
  const loadEvent = client.once("Page.loadEventFired");
  client.currentUrl = url;
  await client.send("Page.navigate", { url });
  await loadEvent;
}

async function captureArtifacts(client, artifactDir, prefix) {
  await mkdir(artifactDir, { recursive: true });
  const [{ data }, html] = await Promise.all([
    client.send("Page.captureScreenshot", { format: "png" }),
    client.evaluate("document.documentElement.outerHTML"),
  ]);
  await writeFile(join(artifactDir, `${prefix}.png`), Buffer.from(data, "base64"));
  await writeFile(join(artifactDir, `${prefix}.html`), html, "utf8");
}

function chromeArgs(debugPort, userDataDir) {
  return [
    "--headless=new",
    "--disable-gpu",
    "--no-sandbox",
    `--remote-debugging-port=${debugPort}`,
    `--user-data-dir=${userDataDir}`,
    "about:blank",
  ];
}

async function stopChrome(chromeProcess) {
  if (chromeProcess.exitCode !== null || chromeProcess.signalCode !== null) return;
  const exited = new Promise((resolve) => {
    chromeProcess.once("exit", resolve);
  });
  chromeProcess.kill("SIGTERM");
  const result = await Promise.race([
    exited.then(() => "exited"),
    sleep(5000).then(() => "timeout"),
  ]);
  if (result === "timeout" && chromeProcess.exitCode === null && chromeProcess.signalCode === null) {
    chromeProcess.kill("SIGKILL");
    await exited;
  }
}

async function removeDirectoryWithRetries(targetDir, maxAttempts = 8) {
  let lastError;
  for (let attempt = 1; attempt <= maxAttempts; attempt += 1) {
    try {
      await rm(targetDir, { recursive: true, force: true });
      return;
    } catch (error) {
      if (!["EBUSY", "ENOTEMPTY", "EPERM"].includes(error?.code)) throw error;
      lastError = error;
      await sleep(250 * attempt);
    }
  }
  if (lastError) throw lastError;
}

async function run() {
  await mkdir(UI_ARTIFACT_DIR, { recursive: true });

  const chromeUserDataDir = await mkdtemp(join(tmpdir(), "trading-bot-v2-ui-"));
  const chromeProcess = spawn(CHROME_BIN, chromeArgs(DEBUG_PORT, chromeUserDataDir), {
    stdio: "ignore",
  });

  let client;

  try {
    const debugPort = await resolveOwnDebugPort(chromeProcess, chromeUserDataDir, DEBUG_PORT);
    console.log(`ui_regression chrome debug port ${debugPort}`);
    await waitForChrome(debugPort);
    const webSocketUrl = await getPageWebSocketUrl(debugPort);
    client = new CDPClient(webSocketUrl);
    await client.connect();

    await client.send("Page.enable");
    await client.send("Runtime.enable");
    // Muss vor der ersten Navigation stehen, sonst gehen Fehler des ersten
    // Seitenaufbaus verloren.
    client.trackConsoleErrors();

    // 1. Login screen renders
    await navigate(client, `${FRONTEND_URL}/login`);
    await waitForCondition(
      client,
      "login form",
      "!!document.querySelector('form[aria-label=\"login form\"]') && !!document.querySelector('input[type=\"email\"]') && !!document.querySelector('input[type=\"password\"]')",
    );
    console.log("ui_login_screen ok");

    // 1b. The build badge is the only thing that tells an operator which deploy
    // is live, and nothing asserted how it RENDERS -- api-regression only checks
    // the /api/version payload. Two defects hid in that gap: the component
    // prefixed "v" unconditionally (which became "vv..." once the version string
    // carried the tag's own v), and the badge sat in a row flex next to the login
    // card instead of underneath it.
    await waitForCondition(
      client,
      "version badge rendered",
      "(() => !!document.body.innerText.match(/\\d{4}\\.\\d{2}\\.\\d{2}|[0-9a-f]{7}/))()",
    );
    const badgeState = await client.evaluate(`
      (() => {
        const form = document.querySelector('form[aria-label="login form"]');
        const badge = Array.from(document.querySelectorAll("span")).find((node) =>
          /\\d{4}\\.\\d{2}\\.\\d{2}|^v?[0-9a-f]{7}/.test(node.textContent.trim()) &&
          !node.querySelector("span"),
        );
        if (!badge) return JSON.stringify({ error: "no version badge on the login page" });
        const badgeBox = badge.getBoundingClientRect();
        const formBox = form.getBoundingClientRect();
        return JSON.stringify({
          text: badge.textContent.trim(),
          belowForm: badgeBox.top >= formBox.bottom - 1,
        });
      })()
    `);
    const badge = JSON.parse(badgeState);
    if (badge.error) throw new Error(badge.error);
    if (/^vv/.test(badge.text)) {
      throw new Error(`version badge renders a doubled prefix: "${badge.text}"`);
    }
    if (!badge.belowForm) {
      throw new Error(`version badge is not below the login card: "${badge.text}"`);
    }
    const apiVersion = await client.evaluate(
      `(async () => (await (await fetch("${FRONTEND_URL}/api/version")).json()).version)()`,
    );
    const shownVersion = badge.text.split("·")[0].trim().replace(/^v/, "");
    if (shownVersion !== String(apiVersion).replace(/^v/, "")) {
      throw new Error(
        `version badge "${badge.text}" does not match /api/version "${apiVersion}"`,
      );
    }
    console.log("ui_version_badge ok");

    // 2. Register screen renders
    await navigate(client, `${FRONTEND_URL}/register`);
    await waitForCondition(
      client,
      "register form",
      "!!document.querySelector('form[aria-label=\"register form\"]') && document.querySelectorAll('input[type=\"password\"]').length >= 2",
    );
    console.log("ui_register_screen ok");

    // 3. Submit registration; expect redirect to /onboarding plus tokens.
    await client.evaluate(`
      (() => {
        const setValue = (element, value) => {
          const prototype = Object.getPrototypeOf(element);
          const descriptor = Object.getOwnPropertyDescriptor(prototype, "value");
          descriptor.set.call(element, value);
          element.dispatchEvent(new Event("input", { bubbles: true }));
          element.dispatchEvent(new Event("change", { bubbles: true }));
        };
        const form = document.querySelector('form[aria-label="register form"]');
        const emailInput = form.querySelector('input[type="email"]');
        const passwordInputs = form.querySelectorAll('input[type="password"]');
        if (!emailInput || passwordInputs.length < 2) {
          throw new Error("Registration form missing inputs");
        }
        setValue(emailInput, ${JSON.stringify(TEST_EMAIL)});
        setValue(passwordInputs[0], ${JSON.stringify(TEST_PASSWORD)});
        setValue(passwordInputs[1], ${JSON.stringify(TEST_PASSWORD)});
        form.requestSubmit();
        return true;
      })()
    `);

    await waitForCondition(
      client,
      "onboarding redirect after register",
      "window.location.pathname === '/onboarding' && !!localStorage.getItem('access_token')",
      20000,
    );
    console.log("ui_register_submit_to_onboarding ok");

    // 4. The guided first run greets a new account with its intro, listing every
    // step of the process before the user commits to walking it.
    await waitForCondition(
      client,
      "guided run intro with all steps",
      "(() => { const t = document.body.textContent || ''; return t.includes('Guided first run') && !!document.querySelector('[data-testid=\"tour-start\"]') && document.querySelectorAll('ol li').length >= 7; })()",
    );
    await client.evaluate("document.querySelector('[data-testid=\"tour-start\"]').click()");
    await waitForCondition(
      client,
      "guided run started with seven step cards",
      "(() => !!document.querySelector('[data-testid=\"tour-steps\"]') && document.querySelectorAll('[data-testid=\"tour-steps\"] li').length === 7)()",
    );
    // Baseline is taken at start, so the seeded starter watchlists must NOT
    // already count as "you added a symbol" -- that was the whole point of
    // measuring growth instead of absolute counts.
    const watchlistStepPremature = await client.evaluate(`
      (() => {
        const progress = document.querySelector('[data-testid="tour-progress"]');
        return (progress?.textContent || "").includes("of 7") &&
          !(progress?.textContent || "").match(/[4-7] of 7/);
      })()
    `);
    if (!watchlistStepPremature) {
      throw new Error("guided run reported artifact steps as done before anything was created");
    }
    console.log("ui_onboarding_wizard ok");

    // Seed a watchlist item via the API while we have a fresh session, so the
    // dashboard / watchlist / analysis pages have something to render.
    await client.evaluate(`
      (async () => {
        const token = localStorage.getItem("access_token");
        const headers = {
          Authorization: "Bearer " + token,
          "Content-Type": "application/json",
        };
        const watchlistsResponse = await fetch("/api/watchlists", { headers });
        if (!watchlistsResponse.ok) {
          throw new Error("Failed to load watchlists: " + watchlistsResponse.status);
        }
        const watchlists = await watchlistsResponse.json();
        const primary = Array.isArray(watchlists) ? watchlists[0] : null;
        if (!primary || !primary.id) {
          throw new Error("No primary watchlist available for seeding");
        }
        const addItem = await fetch(
          "/api/watchlists/" + encodeURIComponent(primary.id) + "/items",
          {
            method: "POST",
            headers,
            body: JSON.stringify({
              symbol: "VOO",
              name: "Vanguard S&P 500 ETF",
              tags: ["core", "priority"],
            }),
          },
        );
        if (!addItem.ok) {
          throw new Error("Failed to seed VOO into watchlist: " + addItem.status);
        }
        return true;
      })()
    `);

    // 4b. The seeding above created a real watchlist item after the tour's
    // baseline was taken. The corresponding step must flip to done on its own --
    // that is the difference between tracking real artifacts and counting clicks.
    await navigate(client, `${FRONTEND_URL}/onboarding`);
    await waitForCondition(
      client,
      "watchlist step completed from real data",
      `(() => {
        const card = document.querySelector('[data-testid="tour-steps"]');
        if (!card) return false;
        const watchlistEntry = Array.from(card.querySelectorAll("li"))[3];
        return (watchlistEntry?.textContent || "").includes("✓");
      })()`,
      20000,
    );
    console.log("ui_guided_tour_tracks_real_data ok");

    // 5. Dashboard renders with onboarding card + at least one stat label.
    // The dashboard fires /api/watchlists, /api/alerts, watchlist/news in
    // parallel so the first render is partial; allow a generous timeout.
    await navigate(client, `${FRONTEND_URL}/`);
    await waitForCondition(
      client,
      "dashboard onboarding card + stats grid",
      "(() => { const t = document.body.textContent || ''; return t.includes('Setup progress') && t.includes('Tracked symbols'); })()",
      30000,
    );
    console.log("ui_dashboard ok");

    // 5b. The page shell must follow the window instead of clipping. The header
    // (12 nav links + user block) used to overflow a hard 1152px container,
    // which produced a horizontal scrollbar and cut off the logout button.
    for (const viewportWidth of [1280, 1920]) {
      await client.send("Emulation.setDeviceMetricsOverride", {
        width: viewportWidth,
        height: 1000,
        deviceScaleFactor: 1,
        mobile: false,
      });
      await waitForCondition(
        client,
        `no horizontal overflow at ${viewportWidth}px`,
        "(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1)()",
        10000,
      );
      const logoutVisible = await client.evaluate(`
        (() => {
          const buttons = Array.from(document.querySelectorAll("header button"));
          const logout = buttons[buttons.length - 1];
          if (!logout) return false;
          const box = logout.getBoundingClientRect();
          return box.right <= document.documentElement.clientWidth + 1;
        })()
      `);
      if (!logoutVisible) {
        throw new Error(`header action clipped at ${viewportWidth}px viewport`);
      }
    }
    const mainWidth = await client.evaluate(
      "(() => document.querySelector('main')?.getBoundingClientRect().width || 0)()",
    );
    if (mainWidth < 1400) {
      throw new Error(
        `content still capped at ${mainWidth}px on a 1920px viewport`,
      );
    }
    await client.send("Emulation.clearDeviceMetricsOverride");
    console.log("ui_responsive_shell ok");

    // 5c. On a phone the twelve inline nav links have nowhere to go -- they
    // used to just wrap into a tall stack that pushed the content off-screen.
    // Below lg they collapse into a toggle-driven panel instead. Checked at a
    // real phone width because that is the only place the breakpoint applies.
    await client.send("Emulation.setDeviceMetricsOverride", {
      width: 390,
      height: 844,
      deviceScaleFactor: 1,
      mobile: false,
    });
    await waitForCondition(
      client,
      "no horizontal overflow at 390px",
      "(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1)()",
      10000,
    );
    const navCollapsed = await client.evaluate(`
      (() => {
        const inline = document.querySelector('[data-testid="primary-nav"]');
        const toggle = document.querySelector('[data-testid="nav-toggle"]');
        if (!inline || !toggle) return false;
        const inlineHidden = getComputedStyle(inline).display === "none";
        const toggleShown = getComputedStyle(toggle).display !== "none";
        const panelClosed = !document.querySelector('[data-testid="mobile-nav"]');
        return inlineHidden && toggleShown && panelClosed &&
          toggle.getAttribute("aria-expanded") === "false";
      })()
    `);
    if (!navCollapsed) {
      throw new Error("nav did not collapse into a toggle at 390px viewport");
    }
    await client.evaluate(
      "document.querySelector('[data-testid=\"nav-toggle\"]').click()",
    );
    await waitForCondition(
      client,
      "mobile nav panel open with links",
      "(() => { const p = document.querySelector('[data-testid=\"mobile-nav\"]'); return !!p && p.querySelectorAll('a').length >= 10; })()",
      10000,
    );
    // Following a link must close the panel again, otherwise it covers the very
    // page the user asked for.
    await client.evaluate(`
      (() => {
        const links = Array.from(
          document.querySelectorAll('[data-testid="mobile-nav"] a'),
        );
        const target = links.find((a) => a.getAttribute("href") === "/watchlists");
        target.click();
      })()
    `);
    await waitForCondition(
      client,
      "mobile nav closed after navigating",
      "(() => !document.querySelector('[data-testid=\"mobile-nav\"]') && location.pathname === '/watchlists')()",
      15000,
    );
    await client.send("Emulation.clearDeviceMetricsOverride");
    console.log("ui_mobile_nav ok");

    // 6. Watchlists page CRUD surface
    await navigate(client, `${FRONTEND_URL}/watchlists`);
    await waitForCondition(
      client,
      "watchlists page with seeded item",
      "(() => { const t = document.body.textContent || ''; return t.includes('Watchlists') && t.includes('Add symbol') && t.includes('VOO'); })()",
      30000,
    );
    console.log("ui_watchlists ok");

    // 7. Scanner page renders the table for the seeded list
    await navigate(client, `${FRONTEND_URL}/scanner`);
    await waitForCondition(
      client,
      "scanner page heading",
      "(document.body.innerText || document.body.textContent || '').includes('Scanner') && !!document.querySelector('table')",
      30000,
    );
    console.log("ui_scanner ok");

    // 8. Analysis page renders chart container + ML prediction card surface
    await navigate(client, `${FRONTEND_URL}/analysis/VOO`);
    await waitForCondition(
      client,
      "analysis page heading + chart container",
      "(document.body.innerText || document.body.textContent || '').includes('VOO') && document.querySelectorAll('canvas, svg').length > 0",
      45000,
    );
    console.log("ui_analysis ok");

    // 7b. Globale Symbolsuche.
    //
    // `GET /api/search/{query}` loest auch ISIN und WKN auf und wurde bis
    // 2026-08-06 von **keiner** Seite aufgerufen: ein Symbol, das in keiner
    // Watchlist stand, war ausschliesslich durch Tippen der Adresszeile
    // erreichbar. Geprueft wird der ganze Weg — tippen, Vorschlag bekommen,
    // auswaehlen, auf der Analyse-Seite landen.
    await navigate(client, `${FRONTEND_URL}/`);
    await waitForCondition(
      client,
      "global symbol search present in the header",
      "!!document.querySelector('[data-testid=\"global-symbol-search\"]')",
      30000,
    );
    await client.evaluate(`
      (() => {
        const input = document.querySelector('[data-testid="global-symbol-search"]');
        const setter = Object.getOwnPropertyDescriptor(
          window.HTMLInputElement.prototype, "value",
        ).set;
        setter.call(input, "VOO");
        input.dispatchEvent(new Event("input", { bubbles: true }));
      })()
    `);
    // Die Suche ist entprellt und schlaegt gegen den Asset-Cache nach; ohne
    // Providerzugang kann die Liste leer bleiben. Deshalb wird zuerst nur
    // verlangt, dass ueberhaupt ein Ergebnisfeld erscheint.
    await waitForCondition(
      client,
      "search dropdown reacts to typing",
      "!!document.querySelector('[data-testid=\"global-symbol-search-results\"]')",
      20000,
    );
    const searchOutcome = await client.evaluate(`
      (() => {
        const options = Array.from(
          document.querySelectorAll('[data-testid^="global-symbol-search-option-"]'),
        );
        return {
          count: options.length,
          first: options[0]?.getAttribute("data-testid") || null,
        };
      })()
    `);

    if (searchOutcome.count > 0) {
      await client.evaluate(
        `document.querySelector('[data-testid="${searchOutcome.first}"]').click()`,
      );
      await waitForCondition(
        client,
        "picking a search result opens the analysis page",
        "window.location.pathname.startsWith('/analysis/')",
        20000,
      );
      console.log(`ui_symbol_search ok [${searchOutcome.count} suggestions, navigated]`);
    } else {
      // Ohne Provider liefert der Asset-Cache nichts. Das ist eine bekannte
      // Einschraenkung dieser Umgebung und wird als solche gemeldet, statt als
      // Erfolg zu gelten.
      console.log(
        "ui_symbol_search partial [dropdown rendered, no suggestions — asset cache empty without provider access]",
      );
    }

    // 8a. Wahrscheinlichkeiten muessen zur Datenlage passen (TBV2-Z02, Regel K).
    //
    // Der Befund vom 2026-08-05: auf dem synthetischen Pfad liefert das Backend
    // HOLD/confidence 0 ohne Wahrscheinlichkeiten. Die alte Ableitung
    // `1 - confidence` machte daraus fuer beide Richtungen 1.0 — die Seite
    // zeigte "P(UP) 100.0%" UND "P(DOWN) 100.0%" gleichzeitig, direkt unter dem
    // Banner "es wird keine Handelsempfehlung gegeben".
    //
    // Diese Umgebung erreicht keinen Provider, rendert also zuverlaessig genau
    // diesen synthetischen Fall — die Einschraenkung der Umgebung ist hier
    // ausnahmsweise der Testfall. Geprueft wird trotzdem beidseitig, damit der
    // Schritt auf einem Host MIT Providerzugang nicht still bedeutungslos wird.
    //
    // Der Schritt navigiert selbst, statt sich auf den Stand des vorherigen zu
    // verlassen: als zwischendurch ein Suchschritt eingefuegt wurde, prueften
    // diese Assertions plotzlich das Dashboard und schlugen fehl. Eine
    // Assertion, die von der Reihenfolge ihrer Nachbarn abhaengt, ist eine
    // Falle.
    await navigate(client, `${FRONTEND_URL}/analysis/VOO`);
    await waitForCondition(
      client,
      "analysis page loaded for the probability check",
      "(document.body.innerText || '').includes('VOO') && document.querySelectorAll('canvas, svg').length > 0",
      45000,
    );
    const probabilityState = await client.evaluate(`
      (() => {
        const text = document.body.innerText || document.body.textContent || "";
        const synthetic = !!Array.from(document.querySelectorAll('[role="alert"]'))
          .find((el) => /placeholder|Platzhalter/i.test(el.textContent || ""));
        const unavailable = !!document.querySelector(
          '[data-testid="prediction-probabilities-unavailable"]',
        );
        const matches = Array.from(text.matchAll(/P\\((UP|DOWN)\\)[^0-9]*([0-9]+(?:\\.[0-9]+)?)%/g));
        const values = {};
        for (const m of matches) values[m[1]] = parseFloat(m[2]);
        return { synthetic, unavailable, values, shown: matches.length };
      })()
    `);

    if (probabilityState.synthetic) {
      if (!probabilityState.unavailable || probabilityState.shown > 0) {
        throw new Error(
          "synthetic data path still renders directional probabilities: " +
            JSON.stringify(probabilityState),
        );
      }
      console.log("ui_prediction_probabilities ok [synthetic — no probabilities shown]");
    } else {
      const { UP, DOWN } = probabilityState.values;
      if (typeof UP !== "number" || typeof DOWN !== "number") {
        throw new Error(
          "real data path shows no P(UP)/P(DOWN) — product vision point 2: " +
            JSON.stringify(probabilityState),
        );
      }
      if (Math.abs(UP + DOWN - 100) > 1.5) {
        throw new Error(
          `P(UP) ${UP}% and P(DOWN) ${DOWN}% do not sum to 100% — the pair contradicts itself`,
        );
      }
      console.log(`ui_prediction_probabilities ok [real — UP ${UP}% / DOWN ${DOWN}%]`);
    }

    // 8a2. "Warum kein automatischer Handel?" — die Gate-Kette einzeln.
    //
    // POST /api/auto-execution/proposals/evaluate begruendet jede Ablehnung
    // einzeln und wurde bis 2026-08-06 von keiner Seite aufgerufen. Damit war
    // der einzige Ort unerreichbar, an dem ein Nutzer nachvollziehen kann,
    // warum die Automatik nicht kauft (Produktvision Punkt 6, TBV2-Z06 (d)).
    //
    // Die Zusage ist nicht "ein Kasten ist da", sondern "es steht ein
    // erklaerender Satz drin, kein roher Code".
    //
    // Der Schritt navigiert selbst. Beim Verifikationslauf am 2026-08-06 fiel
    // auf, dass er sonst vom Stand seines Vorgaengers lebt — dieselbe Falle,
    // die in PR 5 beim Wahrscheinlichkeitsschritt behoben wurde und hier
    // unbemerkt neu entstanden war.
    await navigate(client, `${FRONTEND_URL}/analysis/VOO`);
    await waitForCondition(
      client,
      "trade gate panel present",
      "!!document.querySelector('[data-testid=\"trade-gate-run\"]')",
      20000,
    );
    await client.evaluate(
      "document.querySelector('[data-testid=\"trade-gate-run\"]').click()",
    );
    await waitForCondition(
      client,
      "gate evaluation returns a verdict",
      "!!document.querySelector('[data-testid=\"trade-gate-verdict\"]')",
      30000,
    );
    const gateState = await client.evaluate(`
      (() => {
        const verdict = document.querySelector('[data-testid="trade-gate-verdict"]');
        const reasons = Array.from(
          document.querySelectorAll('[data-testid="trade-gate-reasons"] li'),
        ).map((li) => (li.textContent || "").trim());
        const halts = Array.from(
          document.querySelectorAll('[data-testid="trade-gate-halts"] li'),
        ).map((li) => (li.textContent || "").trim());
        return { verdict: (verdict?.textContent || "").trim(), reasons, halts };
      })()
    `);
    // Ein roher Grund-Code waere technisch gruen und fuer den Nutzer wertlos.
    const rawCode = [...gateState.reasons, ...gateState.halts].find((text) =>
      /^[a-z0-9_]+$/.test(text),
    );
    if (rawCode) {
      throw new Error(
        `gate reason rendered as a raw code instead of a sentence: "${rawCode}"`,
      );
    }
    if (!gateState.verdict) {
      throw new Error("gate panel produced no verdict");
    }
    // Kohaerenz zwischen Zustandswort und Inhalt daneben (Regel K): die Zahl
    // im Urteil muss zur Laenge der Liste passen. Vorher bestand der Schritt
    // auch mit null Gruenden und druckte "0 reason(s), all rendered as
    // sentences" — ein Zustandswort ohne Inhalt.
    const claimedCount = Number((gateState.verdict.match(/\d+/) || [])[0]);
    if (Number.isFinite(claimedCount)) {
      if (claimedCount !== gateState.reasons.length) {
        throw new Error(
          `verdict claims ${claimedCount} blocking gate(s) but ${gateState.reasons.length} ` +
            `are listed — the state word and the content beside it disagree`,
        );
      }
      if (claimedCount === 0) {
        throw new Error("verdict claims blocked gates but names none");
      }
    } else if (gateState.reasons.length > 0) {
      throw new Error(
        `verdict reads as "allowed" while ${gateState.reasons.length} blocking reason(s) are listed`,
      );
    }
    console.log(
      `ui_trade_gates ok [${gateState.reasons.length} reason(s), all rendered as sentences]`,
    );

    // 8a3. Herkunft jeder Kennzahl: Provider und Zeitstempel (TBV2-Z06 b).
    //
    // Die Zusage lautet "jede angezeigte Kennzahl nennt Provider und
    // Zeitstempel". Ein Kasten, der da ist, belegt das nicht — belegt ist es
    // erst, wenn (a) jede sichtbare Kennzahlen-Sektion einen Hinweis traegt,
    // (b) dessen Text tatsaechlich einen Anbieter nennt und einen Zeitpunkt
    // *oder* offen sagt, dass es keinen gibt, und (c) die genannten Anbieter
    // mit dem uebereinstimmen, was das Backend fuer dasselbe Symbol meldet.
    //
    // Ohne (c) waere der sichtbare Text ein Koeder: er koennte im Frontend
    // erfunden sein und stuende trotzdem gruen im Protokoll.
    // Nur ein Symbol. Ein Durchlauf mit einem Krypto-Symbol war der Versuch,
    // den Leerzustand der Termine herzustellen — er rendert in dieser
    // Umgebung aber nicht (gemessen: die Zusicherung "events-empty gerendert"
    // fiel). Ein Durchlauf, der seinen Zweig nie sieht, ist gruen und wertlos;
    // die Abdeckung dieses Zweigs liegt deshalb im statischen Waechter
    // `tests/test_metric_sources.py`, der jede `<section>` je Komponente
    // zaehlt statt nur ihr Vorkommen.
    await navigate(client, `${FRONTEND_URL}/analysis/VOO`);
    await waitForCondition(
      client,
      "metric source tips present",
      "document.querySelectorAll('[data-testid=\"source-tip\"]').length > 0",
      20000,
    );
    const sourceState = await client.evaluate(`
      (async () => {
        const tips = Array.from(
          document.querySelectorAll('[data-testid="source-tip"]'),
        ).map((node) => ({
          key: node.getAttribute("data-source-key"),
          summary: (node.getAttribute("data-source-summary") || "").trim(),
          rendered: (node.textContent || "").trim(),
        }));
        // Jede sichtbare Sektion mit einer Ueberschrift muss einen Hinweis
        // tragen. Zwei Ausnahmen, beide mit Grund:
        //   - die Datenqualitaets-Karte ist selbst der Herkunftsbericht,
        //   - die Gate-Kette zeigt keine Kennzahlen, sondern begruendet jede
        //     Ablehnung einzeln (das ist TBV2-Z06 (d), eigener Beweisschritt).
        const exemptSections = ["data-quality-section", "trade-gate-panel"];
        const sectionsWithoutTip = Array.from(document.querySelectorAll("section"))
          .filter((section) => {
            if (section.querySelector('[data-testid="source-tip"]')) return false;
            if (exemptSections.includes(section.getAttribute("data-testid"))) return false;
            return !!section.querySelector("h2");
          })
          .map((section) => (section.querySelector("h2").textContent || "").trim());

        const renderedMetricSections = Array.from(document.querySelectorAll("section")).filter(
          (section) =>
            !!section.querySelector("h2") &&
            !exemptSections.includes(section.getAttribute("data-testid")),
        ).length;

        const token = localStorage.getItem("access_token");
        const response = await fetch("/api/data-quality/VOO", {
          headers: { Authorization: "Bearer " + token },
        });
        const report = response.ok ? await response.json() : null;
        return { tips, sectionsWithoutTip, renderedMetricSections, report };
      })()
    `);

    // Keine absolute Zahl: auf dem synthetischen Pfad rendern die meisten
    // Sektionen gar nicht, und eine Schwelle von "mindestens fuenf" haette
    // hier eine Anforderung erfunden, die die Umgebung nicht erfuellen kann.
    // Gemessen wird stattdessen die Abdeckung — jede Sektion, die *da* ist,
    // nennt ihre Quelle — und die Zahl steht in der Erfolgszeile, damit ein
    // Schrumpfen auffaellt statt still zu passieren.
    if (sourceState.tips.length === 0) {
      throw new Error("no metric source tip rendered at all");
    }
    if (sourceState.tips.length < sourceState.renderedMetricSections) {
      throw new Error(
        `${sourceState.renderedMetricSections} metric section(s) rendered but only ` +
          `${sourceState.tips.length} source tip(s)`,
      );
    }
    if (sourceState.sectionsWithoutTip.length > 0) {
      throw new Error(
        `metric section(s) without a source statement: ${sourceState.sectionsWithoutTip.join(", ")}`,
      );
    }
    for (const tip of sourceState.tips) {
      if (!tip.summary || tip.summary !== tip.rendered) {
        throw new Error(
          `source tip for "${tip.key}" does not display what it claims (attribute "${tip.summary}", rendered "${tip.rendered}")`,
        );
      }
      if (/undefined|null|NaN|Invalid Date/.test(tip.summary)) {
        throw new Error(`source tip for "${tip.key}" renders a placeholder: "${tip.summary}"`);
      }
      // Entweder Anbieter + Zeitpunkt, oder eine ehrliche Fehlanzeige.
      const named = tip.summary.includes("·");
      const honestlyEmpty =
        /no source answered|keine Quelle geantwortet/.test(tip.summary);
      if (!named && !honestlyEmpty) {
        throw new Error(
          `source tip for "${tip.key}" neither names a source nor says none answered: "${tip.summary}"`,
        );
      }
    }
    // (c) Jeder auf der Seite genannte Anbieter stammt wirklich aus dem
    // Backend — das ist die Richtung, auf die es ankommt: ein im Frontend
    // erfundener Name waere sonst gruen.
    //
    // Die umgekehrte Richtung ("jeder Backend-Eintrag steht auch auf der
    // Seite") war der erste Versuch und hat das Falsche verlangt: eine
    // Sektion, die mangels Daten gar nicht rendert, zeigt zu Recht keine
    // Quelle. Der Lauf vom 2026-08-06 hat das aufgedeckt — und dabei drei
    // echte Fehler in der Karte selbst mitgenommen (Prognose und Composite
    // nannten auf dem synthetischen Pfad eine Quelle, die Bestaende eine fuer
    // eine leere Liste).
    if (!sourceState.report || !Array.isArray(sourceState.report.sources)) {
      throw new Error("/api/data-quality did not return a source map to check the page against");
    }
    const backendProviders = new Set(
      sourceState.report.sources.filter((entry) => entry.provider).map((entry) => entry.provider),
    );
    const invented = sourceState.tips
      .filter((tip) => tip.summary.includes("·"))
      .filter((tip) => ![...backendProviders].some((provider) => tip.summary.includes(provider)))
      .map((tip) => `${tip.key}: ${tip.summary}`);
    if (invented.length > 0) {
      throw new Error(
        `page shows provider text the backend never sent: ${invented.join(" | ")}`,
      );
    }
    // Das Tooltip erklaert die Bedeutung des Zeitstempels und ist nicht bloss
    // eine Wiederholung der Zeile darueber.
    await client.evaluate(
      "document.querySelector('[data-testid=\"source-tip\"]').click()",
    );
    // Nach dem Klick rendert React erst im naechsten Durchlauf. Synchron
    // danach zu lesen liefert immer den leeren Zustand — der erste Lauf des
    // Schritts ist genau darueber gefallen.
    await waitForCondition(
      client,
      "source tip explanation opens",
      "!!document.querySelector('[data-testid=\"source-tip\"]').parentElement.querySelector('[role=\"tooltip\"]')",
      5000,
    );
    const explanation = await client.evaluate(`
      (() => {
        const tip = document.querySelector('[data-testid="source-tip"]');
        const tooltip = tip.parentElement.querySelector('[role="tooltip"]');
        return tooltip ? (tooltip.textContent || "").trim() : "";
      })()
    `);
    if (!explanation || explanation.length < 20) {
      throw new Error(`source tip opened no explanation (got "${explanation}")`);
    }
    const availableCount = sourceState.report.sources.filter((entry) => entry.available).length;
    const datedCount = sourceState.report.sources.filter((entry) => entry.asOf).length;
    // Ehrlichkeit ueber die eigene Trennschaerfe: ohne Providerzugang laeuft
    // die Seite im synthetischen Modus, dort nennt kein Hinweis einen echten
    // Anbieter mit Zeitpunkt. Geprueft ist dann nur die Abdeckung und dass
    // nichts erfunden wird — nicht die Zusage selbst. Das meldet der Schritt
    // als `partial`, statt es als vollen Nachweis zu verbuchen.
    const namedWithStamp = sourceState.tips.filter((tip) => tip.summary.includes("·")).length;
    const verdict = namedWithStamp > 0 ? "ok" : "partial";
    const note =
      namedWithStamp > 0
        ? `${namedWithStamp} tip(s) name a provider and a timestamp`
        : "no provider answered in this environment — coverage proven, the naming itself is not";
    console.log(
      `ui_metric_sources ${verdict} [${sourceState.tips.length} tip(s) on ${sourceState.renderedMetricSections} ` +
        `rendered section(s), ${availableCount} source(s) answered, ${datedCount} dated; ${note}]`,
    );

    // 8b. Macro-Context-Section renders on the analysis page regardless of
    // symbol (computed from VIX/^TNX/DXY, not the analyzed symbol). Best-
    // effort because the underlying yfinance probes for the index symbols
    // can fail without external connectivity in some CI environments.
    try {
      await waitForCondition(
        client,
        "macro context section",
        "!!document.querySelector('[data-testid=\"macro-context-section\"]')",
        20000,
      );
      console.log("ui_macro_context ok");
    } catch (error) {
      console.log(`ui_macro_context best_effort_skipped reason="${(error.message || String(error)).slice(0, 120)}"`);
    }

    // 9. Alerts page (rule CRUD form)
    await navigate(client, `${FRONTEND_URL}/alerts`);
    await waitForCondition(
      client,
      "alerts page heading + form",
      "(document.body.innerText || document.body.textContent || '').includes('Alert rules and events') && !!document.querySelector('form')",
      15000,
    );
    console.log("ui_alerts ok");

    // 9b. German rendering. The rest of this run asserts English strings, so a
    // page that never calls t() would still pass everything above — that is how
    // Alerts/Watchlists/Scanner/Settings stayed English for months. Switch the
    // stored language and assert the translated headings really appear.
    await client.evaluate("window.localStorage.setItem('language', 'de')");
    for (const [path, needle] of [
      ["/alerts", "Alert-Regeln und Ereignisse"],
      ["/watchlists", "Listen werden pro Nutzer gespeichert"],
      ["/settings", "Zwei-Faktor-Authentifizierung"],
      ["/scanner", "Aktueller Stand der gewaehlten Watchlist"],
    ]) {
      await navigate(client, `${FRONTEND_URL}${path}`);
      await waitForCondition(
        client,
        `german copy on ${path}`,
        `(document.body.innerText || document.body.textContent || '').includes(${JSON.stringify(needle)})`,
        15000,
      );
    }
    await client.evaluate("window.localStorage.setItem('language', 'en')");
    console.log("ui_i18n_german ok");

    // 10. Settings page sections (Profile, Alpaca, Portfolio defaults, MFA)
    await navigate(client, `${FRONTEND_URL}/settings`);
    await waitForCondition(
      client,
      "settings sections",
      "['Profile','Alpaca broker','Portfolio defaults','Multi-factor authentication'].every((section) => (document.body.innerText || document.body.textContent || '').includes(section))",
      15000,
    );
    console.log("ui_settings ok");

    // 10b. Paper-Trading page renders order form + tab navigation
    await navigate(client, `${FRONTEND_URL}/paper-trading`);
    await waitForCondition(
      client,
      "paper trading form + tabs",
      "!!document.querySelector('[data-testid=\"paper-trading-page\"]') && !!document.querySelector('[data-testid=\"paper-tab-openOrders\"]') && !!document.querySelector('[data-testid=\"paper-tab-journal\"]') && !!document.querySelector('[data-testid=\"paper-tab-positions\"]') && !!document.querySelector('[data-testid=\"paper-tab-summary\"]')",
      15000,
    );
    await client.evaluate(
      "document.querySelector('[data-testid=\"paper-tab-summary\"]').click()",
    );
    await waitForCondition(
      client,
      "paper trading summary content",
      "!!document.querySelector('[data-testid=\"paper-tab-content-summary\"]')",
      10000,
    );
    console.log("ui_paper_trading ok");

    // 10b. Auto-Execution: Risikolimits speichern.
    //
    // Der Grund fuer diesen Schritt (2026-08-05): der Aufrufer serialisierte
    // den Body doppelt, der Endpunkt antwortete 422 und die Seite zeigte nur
    // "Request failed: 422". Weder Unit noch API-Regression konnten das sehen —
    // der Fehler sass zwischen beiden. Geprueft wird deshalb genau die Naht:
    // klicken, speichern, und den Wert nach einem Reload wiederfinden.
    await navigate(client, `${FRONTEND_URL}/auto-execution`);
    await waitForCondition(
      client,
      "auto-execution page",
      "!!document.querySelector('[data-testid=\"auto-execution-save-btn\"]')",
      30000,
    );

    // Einen Pflichtwert veraendern, damit der Speichern-Button aktiv wird
    // (er haengt an isDirty).
    const probeValue = "1234";
    await client.evaluate(`
      (() => {
        const input = document.querySelector('[data-testid="auto-execution-max-position-input"]');
        if (!input) throw new Error("max-position input not found");
        const setter = Object.getOwnPropertyDescriptor(
          window.HTMLInputElement.prototype, "value",
        ).set;
        setter.call(input, "${probeValue}");
        input.dispatchEvent(new Event("input", { bubbles: true }));
        input.dispatchEvent(new Event("change", { bubbles: true }));
      })()
    `);
    await waitForCondition(
      client,
      "save button enabled after edit",
      "!document.querySelector('[data-testid=\"auto-execution-save-btn\"]').disabled",
      10000,
    );
    await client.evaluate(
      "document.querySelector('[data-testid=\"auto-execution-save-btn\"]').click()",
    );

    // Die Zusage ist nicht "es stand kurz etwas da", sondern "der Wert ist
    // gespeichert". Ein 422 haette den Wert nur lokal im Formular gelassen —
    // nach dem Reload waere der alte Stand zurueck.
    await waitForCondition(
      client,
      "limits save acknowledged without error",
      "!(document.body.textContent || '').includes('Request failed')",
      15000,
    );
    await navigate(client, `${FRONTEND_URL}/auto-execution`);
    await waitForCondition(
      client,
      "saved limit survives a reload",
      `(() => {
        const input = document.querySelector('[data-testid="auto-execution-max-position-input"]');
        return !!input && String(input.value) === "${probeValue}";
      })()`,
      20000,
    );
    console.log("ui_auto_execution_limits_persist ok");

    // 11. Admin page if first user is admin (registration of a fresh stack
    // makes the first registered user admin per the backend's bootstrap).
    const isAdmin = await client.evaluate(`
      (async () => {
        const token = localStorage.getItem("access_token");
        const response = await fetch("/api/auth/me", {
          headers: { Authorization: "Bearer " + token },
        });
        if (!response.ok) {
          throw new Error("/api/auth/me failed: " + response.status);
        }
        const user = await response.json();
        return !!user.is_admin;
      })()
    `);

    if (isAdmin) {
      // AdminPage rendert direkt (kein React.lazy mehr) — Runtime-Errors hier
      // sind echte Bugs, kein Suspense-Race. Wir assertieren das Backups-Panel
      // explizit, weil dort schon ein Schema-Drift ({items: [...]}) gerendert
      // werden muss; wenn `.map()` auf dem Objekt fehlschlaegt, killt React
      // den ganzen Tree und das Heading verschwindet wieder.
      try {
        await navigate(client, `${FRONTEND_URL}/admin`);
        await waitForCondition(
          client,
          "admin page heading",
          "(document.body.textContent || '').includes('Administration')",
          30000,
        );
        await waitForCondition(
          client,
          "admin users table",
          "!!document.querySelector('table')",
          20000,
        );
        await waitForCondition(
          client,
          "admin backups section",
          "(document.body.textContent || '').includes('Backups')",
          10000,
        );
        console.log("ui_admin ok");
      } catch (error) {
        console.log(`ui_admin best_effort_skipped reason="${(error.message || String(error)).slice(0, 120)}"`);
      }

      // 11b-2. Deutsche Fassung der Admin-Seite. Bewusst NICHT best-effort:
      // die Seite rendert direkt, und `test_admin_page_i18n.py` haelt die
      // Quelle schon frei von festem Text — hier wird nachgewiesen, dass das
      // Bundle die Seite zur Laufzeit auch wirklich erreicht.
      //
      // Vier Zusagen aus vier verschiedenen Sektionen, alle unbedingt
      // gerendert. Eine einzelne uebersetzte Ueberschrift kann den Schritt
      // damit nicht tragen — genau der Fehler, an dem `ui_metric_sources`
      // am 2026-08-06 auf dem CI-Runner haengen blieb.
      await client.evaluate("window.localStorage.setItem('language', 'de')");
      await navigate(client, `${FRONTEND_URL}/admin`);
      for (const needle of [
        "Nur für Administratoren",
        "Nutzer anlegen",
        "Gewichte der Gesamtentscheidung",
        "Sicherung manuell erstellen",
      ]) {
        await waitForCondition(
          client,
          `german admin copy: ${needle}`,
          `(document.body.innerText || document.body.textContent || '').includes(${JSON.stringify(needle)})`,
          20000,
        );
      }
      await client.evaluate("window.localStorage.setItem('language', 'en')");
      console.log("ui_admin_i18n_german ok");
    } else {
      console.log("ui_admin skipped_non_admin");
    }

    // 11c. PWA manifest is served and reachable from the page head.
    await waitForCondition(
      client,
      "manifest link in head",
      "!!document.querySelector('link[rel=\"manifest\"]')",
      10000,
    );
    const manifestUrl = await client.evaluate(
      "document.querySelector('link[rel=\"manifest\"]').href",
    );
    if (typeof manifestUrl !== "string" || manifestUrl.length === 0) {
      throw new Error("Manifest link href is empty");
    }
    console.log("ui_pwa_manifest ok");

    // 12. Token persisted across navigations
    const token = await client.evaluate("localStorage.getItem('access_token')");
    if (!token) {
      throw new Error("Missing access token after authenticated navigation");
    }
    console.log("ui_token_persisted ok");

    // 12b. Onboarding-Fortschrittskarte: N von M, Click-through, Verschwinden.
    //
    // Beweisschritt zu TBV2-Z05. Bis 2026-08-05 deckte `ui_dashboard` davon
    // nur ab, dass irgendwo das Wort "Setup progress" steht — nicht die Zahl,
    // nicht den Klickweg und vor allem nicht das Verschwinden.
    //
    // Das Verschwinden tritt nur unter einer Bedingung ein, die kein Testlauf
    // von selbst herstellt: alle Pflichtwerte gesetzt. Der Schritt **stellt
    // sie deshalb her**, statt sie zu unterstellen (§4 Phase 4). Er laeuft
    // ganz am Ende, damit die geaenderten Portfolio-Einstellungen keinem
    // frueheren Schritt in die Quere kommen.
    await navigate(client, `${FRONTEND_URL}/`);
    await waitForCondition(
      client,
      "onboarding card present for a fresh account",
      "!!document.querySelector('[data-testid=\"onboarding-card\"]')",
      30000,
    );

    const progress = await client.evaluate(`
      (() => {
        const el = document.querySelector('[data-testid="onboarding-progress"]');
        if (!el) return null;
        return {
          completed: Number(el.getAttribute("data-completed")),
          total: Number(el.getAttribute("data-total")),
          text: (el.textContent || "").trim(),
        };
      })()
    `);
    if (!progress || !Number.isFinite(progress.total) || progress.total <= 0) {
      throw new Error(`onboarding card shows no N/M progress: ${JSON.stringify(progress)}`);
    }
    if (progress.completed >= progress.total) {
      throw new Error(
        `a fresh account reports itself fully configured (${progress.text}) — ` +
          "the card cannot be proving anything",
      );
    }
    // Die Zahl muss auch sichtbar sein, nicht nur im Attribut stehen.
    if (!/\d+\s*\/\s*\d+/.test(progress.text)) {
      throw new Error(`progress text carries no visible N/M: "${progress.text}"`);
    }

    // Kohaerenz zwischen der Zahl und dem Verschwinden (Regel K).
    //
    // Der Verifikationslauf vom 2026-08-06 hat genau hier einen Widerspruch
    // gefunden: die Karte zeigte "1 / 4 konfiguriert" und verschwand bei
    // "2 / 4", weil Zahl und Verschwinden Verschiedenes zaehlten. Der Schritt
    // haelt jetzt fest, wie viele Schritte noch fehlen — und prueft weiter
    // unten, dass die Karte nach **genau diesen** verschwindet.
    const openRequired = progress.total - progress.completed;
    if (openRequired <= 0) {
      throw new Error(
        `card claims nothing is open (${progress.text}) yet is still shown — ` +
          "the number and the visibility contradict each other",
      );
    }

    // Click-through: der Knopf muss zum offenen Schritt fuehren.
    await client.evaluate(
      "document.querySelector('[data-testid=\"onboarding-continue\"]').click()",
    );
    await waitForCondition(
      client,
      "click-through reaches the onboarding wizard",
      "window.location.pathname === '/onboarding'",
      15000,
    );

    // Jetzt die Bedingung herstellen: alle Pflichtwerte setzen.
    const settingsStatus = await client.evaluate(`
      (async () => {
        const token = localStorage.getItem("access_token");
        const response = await fetch("/api/auth/me/portfolio-settings", {
          method: "PUT",
          headers: {
            "Content-Type": "application/json",
            Authorization: "Bearer " + token,
          },
          body: JSON.stringify({
            trade_fee_absolute: 1,
            trade_fee_percent: 0,
            min_target_yield: 5,
            capital_gains_tax_bps: 2500,
            income_tax_bps: 0,
          }),
        });
        return response.status;
      })()
    `);
    if (settingsStatus !== 200) {
      throw new Error(`could not complete the required settings: HTTP ${settingsStatus}`);
    }

    await navigate(client, `${FRONTEND_URL}/`);
    await waitForCondition(
      client,
      "dashboard rendered after completing the required steps",
      "(document.body.textContent || '').includes('Tracked symbols')",
      30000,
    );
    // Abwesenheit direkt nach dem Laden waere kein Beweis: die Karte rendert
    // erst, wenn ihre drei Abfragen zurueck sind. Deshalb wird ueber ein
    // Zeitfenster geprueft — waere die Logik kaputt, taucht sie darin auf.
    // Die Negativkontrolle belegt, dass das Fenster ausreicht.
    const ABSENCE_WINDOW_MS = 6000;
    const absenceDeadline = Date.now() + ABSENCE_WINDOW_MS;
    while (Date.now() < absenceDeadline) {
      const cardStillThere = await client.evaluate(
        "!!document.querySelector('[data-testid=\"onboarding-card\"]')",
      );
      if (cardStillThere) {
        const shown = await client.evaluate(
          "(document.querySelector('[data-testid=\"onboarding-progress\"]')?.textContent || '').trim()",
        );
        throw new Error(
          "the onboarding card is still shown although every required step is " +
            `configured (card reads "${shown}") — it never ends and loses its ` +
            "signal value (TBV2-Z05)",
        );
      }
      await sleep(250);
    }

    // Gegenprobe zur Abwesenheit: die Daten, aus denen die Karte ihren Zustand
    // ableitet, muessen tatsaechlich vollstaendig sein. Sonst koennte die Karte
    // auch aus einem ganz anderen Grund fehlen (Fehler beim Laden etwa) und
    // der Schritt waere gruen, ohne irgendetwas zu belegen.
    const settingsCheck = await client.evaluate(`
      (async () => {
        const token = localStorage.getItem("access_token");
        const response = await fetch("/api/auth/me/portfolio-settings", {
          headers: { Authorization: "Bearer " + token },
        });
        if (!response.ok) return { ok: false, status: response.status };
        const s = await response.json();
        return {
          ok: true,
          trading: s.min_target_yield > 0 && (s.trade_fee_absolute > 0 || s.trade_fee_percent > 0),
          taxes: s.capital_gains_tax_bps > 0,
        };
      })()
    `);
    if (!settingsCheck.ok || !settingsCheck.trading || !settingsCheck.taxes) {
      throw new Error(
        "the card is gone, but the required settings are not actually complete: " +
          JSON.stringify(settingsCheck),
      );
    }
    console.log(
      `ui_onboarding_progress ok [${progress.text} → click-through → card gone after completion]`,
    );

    // 13. Die Browser-Konsole des gesamten Durchlaufs.
    //
    // Bis 2026-08-05 wurde sie gar nicht erhoben: ein Konsolenfehler auf dem
    // Golden Path fiel durch jedes Gate, obwohl §4 Phase 4 die
    // Konsolenpruefung ausdruecklich verlangt. Dieser Schritt ist bewusst
    // blockierend — ein mitgeschnittener, aber folgenloser Fehler waere nur
    // Dekoration.
    //
    // Gefiltert wird ausschliesslich Umgebungsrauschen, das nichts ueber die
    // Anwendung aussagt: fehlendes Favicon, vom Browser blockierte Requests,
    // und die Provider-Ausfaelle, die in dieser Umgebung strukturell auftreten
    // (kein Netzzugang zu Kursquellen). Jeder Filter ist eine bewusste
    // Entscheidung und steht hier, statt still im Rauschen zu verschwinden.
    const IGNORED_CONSOLE_NOISE = /favicon|ERR_BLOCKED_BY_CLIENT|manifest|net::ERR_(INTERNET_DISCONNECTED|NAME_NOT_RESOLVED)/i;
    const consoleFindings = client.consoleErrors.filter(
      (entry) => !IGNORED_CONSOLE_NOISE.test(entry.text),
    );
    if (consoleFindings.length) {
      console.log(`# console errors (${consoleFindings.length})`);
      for (const entry of consoleFindings.slice(0, 25)) {
        console.log(`  ${entry.url} :: ${entry.text}`);
      }
      throw new Error(
        `${consoleFindings.length} console error(s) on the golden path — first: ` +
          `${consoleFindings[0].url} :: ${consoleFindings[0].text}`,
      );
    }
    console.log(
      `ui_console_clean ok [${client.consoleErrors.length} suppressed as environment noise]`,
    );

    await captureArtifacts(client, UI_ARTIFACT_DIR, "ui-regression-success");
    console.log(`UI regression passed for ${TEST_EMAIL}`);
  } catch (error) {
    if (client) {
      try {
        await captureArtifacts(client, UI_ARTIFACT_DIR, "ui-regression-failure");
      } catch {
        // best-effort capture
      }
      // Die gesammelten Konsolenfehler gehoeren genau hierhin: bei einem
      // Abbruch erreicht der Auswertungsschritt am Ende sie nie, und dann
      // faehrt man mit einem Timeout im Log herum, waehrend die eigentliche
      // Ursache (ein Renderfehler) bereits mitgeschrieben war.
      if (client.consoleErrors?.length) {
        console.log(`# console errors before the failure (${client.consoleErrors.length})`);
        for (const entry of client.consoleErrors.slice(0, 25)) {
          console.log(`  ${entry.url} :: ${entry.text}`);
        }
      }
    }
    throw error;
  } finally {
    if (client) await client.close();
    await stopChrome(chromeProcess);
    await removeDirectoryWithRetries(chromeUserDataDir);
  }
}

run().catch((error) => {
  console.error(error.stack || String(error));
  process.exitCode = 1;
});
