import { spawn } from "node:child_process";
import { mkdir, mkdtemp, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";

const FRONTEND_URL = process.env.FRONTEND_URL || "http://127.0.0.1:18094";
const CHROME_BIN = process.env.CHROME_BIN || "google-chrome";
const DEBUG_PORT = Number(process.env.CHROME_DEBUG_PORT || "9222");
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
      if (!deferred) {
        return;
      }
      this.pending.delete(message.id);
      if (message.error) {
        deferred.reject(new Error(message.error.message || "Unknown CDP error"));
        return;
      }
      deferred.resolve(message.result);
      return;
    }

    const handlers = this.listeners.get(message.method) || [];
    for (const handler of handlers) {
      handler(message.params || {});
    }
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
    if (!this.socket) {
      return;
    }
    this.socket.close();
    await sleep(250);
  }
}

async function waitForChrome(debugPort, timeoutMs = 15000) {
  const startedAt = Date.now();
  while (Date.now() - startedAt < timeoutMs) {
    try {
      const response = await fetch(`http://127.0.0.1:${debugPort}/json/version`);
      if (response.ok) {
        return;
      }
    } catch {
      // Retry until the debug endpoint comes up.
    }
    await sleep(250);
  }
  throw new Error("Chrome remote debugging endpoint did not become ready");
}

async function getPageWebSocketUrl(debugPort) {
  const response = await fetch(`http://127.0.0.1:${debugPort}/json/list`);
  const pages = await response.json();
  const page = pages.find((entry) => entry.type === "page" && entry.webSocketDebuggerUrl);
  if (!page) {
    throw new Error("No debuggable page target found");
  }
  return page.webSocketDebuggerUrl;
}

async function waitForCondition(client, description, expression, timeoutMs = 15000) {
  const startedAt = Date.now();
  while (Date.now() - startedAt < timeoutMs) {
    const matched = await client.evaluate(expression);
    if (matched) {
      return;
    }
    await sleep(200);
  }
  throw new Error(`Timed out waiting for condition: ${description}`);
}

async function navigate(client, url) {
  const loadEvent = client.once("Page.loadEventFired");
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
  if (chromeProcess.exitCode !== null || chromeProcess.signalCode !== null) {
    return;
  }

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
      if (!["EBUSY", "ENOTEMPTY", "EPERM"].includes(error?.code)) {
        throw error;
      }
      lastError = error;
      await sleep(250 * attempt);
    }
  }

  if (lastError) {
    throw lastError;
  }
}

async function run() {
  await mkdir(UI_ARTIFACT_DIR, { recursive: true });

  const chromeUserDataDir = await mkdtemp(join(tmpdir(), "trading-bot-v2-ui-"));
  const chromeProcess = spawn(CHROME_BIN, chromeArgs(DEBUG_PORT, chromeUserDataDir), {
    stdio: "ignore",
  });

  let client;

  try {
    await waitForChrome(DEBUG_PORT);
    const webSocketUrl = await getPageWebSocketUrl(DEBUG_PORT);
    client = new CDPClient(webSocketUrl);
    await client.connect();

    await client.send("Page.enable");
    await client.send("Runtime.enable");

    await navigate(client, `${FRONTEND_URL}/login`);
    await waitForCondition(
      client,
      "login screen",
      "document.body.innerText.includes('Sign In') && !!document.querySelector('input[type=\"email\"]') && !!document.querySelector('input[type=\"password\"]')",
    );
    console.log("ui_login_screen ok");

    await navigate(client, `${FRONTEND_URL}/register`);
    await waitForCondition(
      client,
      "register screen",
      "document.body.innerText.includes('Create Account') && document.querySelectorAll('input[type=\"password\"]').length >= 2",
    );
    console.log("ui_register_screen ok");

    await client.evaluate(`
      (() => {
        const setValue = (element, value) => {
          const prototype = Object.getPrototypeOf(element);
          const descriptor = Object.getOwnPropertyDescriptor(prototype, "value");
          descriptor.set.call(element, value);
          element.dispatchEvent(new Event("input", { bubbles: true }));
          element.dispatchEvent(new Event("change", { bubbles: true }));
        };

        const emailInput = document.querySelector('input[type="email"]');
        const passwordInputs = document.querySelectorAll('input[type="password"]');
        const submitButton = Array.from(document.querySelectorAll("button"))
          .find((button) => button.textContent.includes("Create Account"));

        if (!emailInput || passwordInputs.length < 2 || !submitButton) {
          throw new Error("Registration form is incomplete");
        }

        setValue(emailInput, ${JSON.stringify(TEST_EMAIL)});
        setValue(passwordInputs[0], ${JSON.stringify(TEST_PASSWORD)});
        setValue(passwordInputs[1], ${JSON.stringify(TEST_PASSWORD)});
        submitButton.click();
        return true;
      })()
    `);

    await waitForCondition(
      client,
      "authenticated session",
      "!!localStorage.getItem('access_token') && !!localStorage.getItem('refresh_token')",
      20000,
    );
    console.log("ui_register_submit ok");

    await client.evaluate(`
      (async () => {
        const token = localStorage.getItem("access_token");
        if (!token) {
          throw new Error("Missing access token while seeding watchlist metadata");
        }

        const headers = {
          Authorization: "Bearer " + token,
          "Content-Type": "application/json",
        };
        const watchlistsResponse = await fetch("/api/watchlists", { headers });
        if (!watchlistsResponse.ok) {
          throw new Error("Failed to load watchlists for UI regression seeding: " + watchlistsResponse.status);
        }

        const watchlists = await watchlistsResponse.json();
        const primaryWatchlist = Array.isArray(watchlists) ? watchlists[0] : null;
        const primaryItem = primaryWatchlist && Array.isArray(primaryWatchlist.items) ? primaryWatchlist.items[0] : null;
        if (!primaryWatchlist || !primaryWatchlist.id || !primaryItem || !primaryItem.symbol) {
          throw new Error("Primary watchlist seed data is missing");
        }

        const updateResponse = await fetch(
          "/api/watchlists/" +
            encodeURIComponent(primaryWatchlist.id) +
            "/items/" +
            encodeURIComponent(primaryItem.symbol),
          {
            method: "PUT",
            headers,
            body: JSON.stringify({
              name: primaryItem.name,
              tags: ["priority", "earnings"],
            }),
          },
        );
        if (!updateResponse.ok) {
          throw new Error("Failed to update watchlist tags for UI regression: " + updateResponse.status);
        }

        const extraItems = [
          {
            symbol: "VOO",
            name: "Vanguard S&P 500 ETF",
            tags: ["core", "provider"],
          },
          {
            symbol: "BTC/USD",
            name: "Bitcoin Core",
            tags: ["crypto", "provider"],
          },
        ];

        for (const extraItem of extraItems) {
          const addResponse = await fetch("/api/watchlists/" + encodeURIComponent(primaryWatchlist.id) + "/items", {
            method: "POST",
            headers,
            body: JSON.stringify(extraItem),
          });
          if (!addResponse.ok) {
            throw new Error(
              "Failed to add UI regression provider asset " + extraItem.symbol + ": " + addResponse.status,
            );
          }
        }

        window.__uiPatchSeededSymbol = primaryItem.symbol;
        return primaryItem.symbol;
      })()
    `);
    console.log("ui_watchlist_seeded ok");

    await navigate(client, `${FRONTEND_URL}/`);
    await waitForCondition(
      client,
      "dashboard settings shortcuts",
      "['Account Settings','Multi-Factor Authentication'].every((title) => !!document.querySelector(`button[title=\"${title}\"]`))",
      15000,
    );
    await waitForCondition(
      client,
      "watchlist alerts panel",
      "!!document.getElementById('ui-patch-watchlist-alerts') && document.body.innerText.includes('Watchlist Alerts')",
      15000,
    );
    await waitForCondition(
      client,
      "watchlist alert drilldown",
      "document.body.innerText.includes('Open Analysis')",
      30000,
    );
    console.log("ui_dashboard_shortcuts ok");

    await waitForCondition(
      client,
      "watchlist metadata map",
      "!!document.getElementById('ui-patch-watchlist-map') && !!document.getElementById('ui-patch-watchlist-assets')",
      15000,
    );
    await waitForCondition(
      client,
      "watchlist metadata tags",
      "!!document.getElementById('ui-patch-watchlist-tags') && document.getElementById('ui-patch-watchlist-tags').textContent.includes('#priority') && document.getElementById('ui-patch-watchlist-tags').textContent.includes('#earnings')",
      15000,
    );
    await waitForCondition(
      client,
      "watchlist metadata asset class",
      "!!document.getElementById('ui-patch-watchlist-map') && ['Stock','ETF','Crypto'].every((label) => document.getElementById('ui-patch-watchlist-map').textContent.includes(label)) && document.querySelectorAll('#ui-patch-watchlist-assets [data-symbol]').length >= 3",
      15000,
    );
    console.log("ui_watchlist_metadata ok");

    await waitForCondition(
      client,
      "watchlist provider metadata",
      "!!document.getElementById('ui-patch-watchlist-assets') && document.getElementById('ui-patch-watchlist-assets').textContent.includes('Alpha Vantage') && document.getElementById('ui-patch-watchlist-assets').textContent.includes('VOO') && document.getElementById('ui-patch-watchlist-assets').textContent.includes('BTC/USD')",
      15000,
    );
    console.log("ui_watchlist_provider_metadata ok");

    await waitForCondition(
      client,
      "watchlist provider coverage",
      "!!document.getElementById('ui-patch-provider-coverage') && document.getElementById('ui-patch-provider-coverage').textContent.includes('Provider Coverage') && document.getElementById('ui-patch-provider-coverage').textContent.includes('Alpha Vantage')",
      15000,
    );
    console.log("ui_watchlist_provider_coverage ok");

    await navigate(client, `${FRONTEND_URL}/analysis/VOO`);
    await waitForCondition(
      client,
      "symbol research panel",
      "!!document.getElementById('ui-patch-symbol-research') && document.getElementById('ui-patch-symbol-research').textContent.includes('Provider Research') && document.getElementById('ui-patch-symbol-research').textContent.includes('Alpha Vantage') && document.getElementById('ui-patch-symbol-research').textContent.includes('Top Holdings')",
      30000,
    );
    console.log("ui_symbol_research ok");

    await navigate(client, `${FRONTEND_URL}/`);

    const isAdmin = await client.evaluate(`
      (async () => {
        const token = localStorage.getItem("access_token");
        if (!token) {
          throw new Error("Missing access token while checking current user role");
        }

        const response = await fetch("/api/auth/me", {
          headers: {
            Authorization: "Bearer " + token,
          },
        });
        if (!response.ok) {
          throw new Error("Current user profile request failed: " + response.status);
        }

        const user = await response.json();
        return !!user.is_admin;
      })()
    `);

    if (isAdmin) {
      await waitForCondition(
        client,
        "admin shortcut",
        "!!document.querySelector('button[title=\"User Administration\"]')",
        15000,
      );
      await waitForCondition(
        client,
        "distinct admin shortcut icon",
        "document.querySelector('button[title=\"Account Settings\"]').innerHTML !== document.querySelector('button[title=\"User Administration\"]').innerHTML",
        15000,
      );
      console.log("ui_dashboard_admin_shortcut ok");
    } else {
      console.log("ui_dashboard_admin_shortcut skipped_non_admin");
    }

    await navigate(client, `${FRONTEND_URL}/settings`);
    await waitForCondition(
      client,
      "settings page",
      "document.body.innerText.includes('Account Settings') && document.body.innerText.includes('Alpaca API Keys') && !!Array.from(document.querySelectorAll('button')).find((button) => button.textContent.includes('Back to Dashboard'))",
      15000,
    );
    console.log("ui_settings_route ok");

    await client.evaluate(`
      (() => {
        const button = Array.from(document.querySelectorAll("button"))
          .find((candidate) => candidate.textContent.includes("Back to Dashboard"));
        if (!button) {
          throw new Error("Back button not found on settings page");
        }
        button.click();
        return true;
      })()
    `);
    await waitForCondition(
      client,
      "return to dashboard",
      "window.location.pathname === '/' && !!document.querySelector('button[title=\"Account Settings\"]')",
      15000,
    );
    console.log("ui_settings_back_navigation ok");

    const token = await client.evaluate("localStorage.getItem('access_token')");
    if (!token) {
      throw new Error("Missing access token after authenticated navigation");
    }
    console.log("ui_token_persisted ok");

    await captureArtifacts(client, UI_ARTIFACT_DIR, "ui-regression-success");
    console.log(`UI regression passed for ${TEST_EMAIL}`);
  } catch (error) {
    if (client) {
      try {
        await captureArtifacts(client, UI_ARTIFACT_DIR, "ui-regression-failure");
      } catch {
        // Best-effort artifact capture only.
      }
    }
    throw error;
  } finally {
    if (client) {
      await client.close();
    }
    await stopChrome(chromeProcess);
    await removeDirectoryWithRetries(chromeUserDataDir);
  }
}

run().catch((error) => {
  console.error(error.stack || String(error));
  process.exitCode = 1;
});
