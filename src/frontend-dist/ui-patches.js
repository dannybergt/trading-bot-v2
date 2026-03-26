(function () {
  const ADMIN_ICON = [
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none"',
    ' stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"',
    ' class="h-4 w-4 text-bergt-green">',
    '<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"></path>',
    '<circle cx="9" cy="7" r="4"></circle>',
    '<path d="M22 21v-2a4 4 0 0 0-3-3.87"></path>',
    '<path d="M16 3.13a4 4 0 0 1 0 7.75"></path>',
    "</svg>",
  ].join("");
  const BACK_ICON = [
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none"',
    ' stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"',
    ' class="h-4 w-4">',
    '<path d="m12 19-7-7 7-7"></path>',
    '<path d="M19 12H5"></path>',
    "</svg>",
  ].join("");
  const INSIGHT_ICON = [
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none"',
    ' stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"',
    ' class="h-5 w-5 text-amber-500">',
    '<path d="M12 3 2 21h20L12 3z"></path>',
    '<path d="M12 9v4"></path>',
    '<path d="M12 17h.01"></path>',
    "</svg>",
  ].join("");
  const CACHE_TTL_MS = 60 * 1000;
  const ERROR_TTL_MS = 15 * 1000;
  const WATCHLIST_STATE = {
    cache: new Map(),
    inflight: new Map(),
    seenAlertKeys: new Map(),
    primedWatchlists: new Set(),
    toastIds: new Set(),
  };

  function setButtonLabel(button, title) {
    button.setAttribute("title", title);
    button.setAttribute("aria-label", title);
  }

  function patchDashboardShortcuts() {
    const header = Array.from(document.querySelectorAll("header")).find((candidate) =>
      candidate.textContent.includes("NexusPulse"),
    );
    if (!header) {
      return;
    }

    const buttons = Array.from(header.querySelectorAll("button"));
    for (const button of buttons) {
      const className = button.className || "";
      if (
        className.includes("hover:border-bergt-green/50") &&
        className.includes("hover:bg-bergt-green/10")
      ) {
        setButtonLabel(button, "Account Settings");
        continue;
      }
      if (
        className.includes("hover:border-slate-300") &&
        className.includes("hover:bg-slate-100") &&
        className.includes("relative")
      ) {
        setButtonLabel(button, "Multi-Factor Authentication");
        continue;
      }
      if (
        className.includes("bg-bergt-green/10") &&
        className.includes("border-bergt-green/30")
      ) {
        setButtonLabel(button, "User Administration");
        if (button.innerHTML !== ADMIN_ICON) {
          button.innerHTML = ADMIN_ICON;
        }
      }
    }
  }

  function patchSettingsBackButton() {
    const existing = document.getElementById("ui-patch-settings-back");
    if (window.location.pathname !== "/settings") {
      if (existing) {
        existing.remove();
      }
      return;
    }

    if (existing) {
      return;
    }

    const intro = document.querySelector(".max-w-4xl.mx-auto .mb-8");
    if (!intro) {
      return;
    }

    const button = document.createElement("button");
    button.id = "ui-patch-settings-back";
    button.type = "button";
    button.className =
      "mb-4 inline-flex items-center gap-2 rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 px-4 py-2.5 text-sm font-semibold text-slate-600 dark:text-slate-300 hover:border-bergt-green/40 hover:text-bergt-green transition-colors";
    button.innerHTML = BACK_ICON + "<span>Back to Dashboard</span>";
    button.addEventListener("click", function () {
      window.location.assign("/");
    });
    intro.prepend(button);
  }

  function getAccessToken() {
    try {
      return window.localStorage.getItem("access_token");
    } catch {
      return null;
    }
  }

  function getActiveWatchlistMeta() {
    const select = document.querySelector("select");
    if (!select) {
      return null;
    }
    const option = select.options[select.selectedIndex];
    return {
      id: select.value || "",
      name: option ? option.textContent.trim() : "Watchlist",
    };
  }

  function getCachedInsights(watchlistId) {
    const entry = WATCHLIST_STATE.cache.get(watchlistId);
    if (!entry) {
      return null;
    }

    const maxAge = entry.status === "error" ? ERROR_TTL_MS : CACHE_TTL_MS;
    if (Date.now() - entry.fetchedAt > maxAge) {
      WATCHLIST_STATE.cache.delete(watchlistId);
      return null;
    }
    return entry;
  }

  function updateInsightCache(watchlistMeta, updates) {
    const current =
      WATCHLIST_STATE.cache.get(watchlistMeta.id) || {
        status: "loading",
        fetchedAt: Date.now(),
        watchlistName: watchlistMeta.name,
        alerts: null,
        news: null,
        alertsError: "",
        newsError: "",
        error: "",
      };
    const next = Object.assign({}, current, updates, {
      fetchedAt: Date.now(),
      watchlistName: current.watchlistName || watchlistMeta.name,
    });

    const hasAlerts = !!next.alerts;
    const hasNews = !!next.news;
    const hasAlertError = !!next.alertsError;
    const hasNewsError = !!next.newsError;

    if (hasAlerts && hasNews) {
      next.status = "ready";
    } else if (hasAlerts || hasNews) {
      next.status = "partial";
    } else if (hasAlertError && hasNewsError) {
      next.status = "error";
    } else {
      next.status = "loading";
    }

    if (next.status === "error") {
      next.error = [next.alertsError, next.newsError].filter(Boolean).join(" ");
    } else if (hasAlertError || hasNewsError) {
      next.error = next.alertsError || next.newsError || "";
    } else {
      next.error = "";
    }

    WATCHLIST_STATE.cache.set(watchlistMeta.id, next);
    schedulePatches();
    return next;
  }

  async function fetchJson(url) {
    const token = getAccessToken();
    if (!token) {
      throw new Error("Authentication token missing");
    }

    const response = await fetch(url, {
      headers: {
        Authorization: "Bearer " + token,
      },
    });

    if (!response.ok) {
      throw new Error("Request failed with status " + response.status);
    }
    return response.json();
  }

  function ensureWatchlistInsights(watchlistMeta) {
    if (!watchlistMeta || !watchlistMeta.id || !getAccessToken()) {
      return;
    }

    const cached = getCachedInsights(watchlistMeta.id);
    if (cached || WATCHLIST_STATE.inflight.has(watchlistMeta.id)) {
      return;
    }

    updateInsightCache(watchlistMeta, {
      status: "loading",
      alerts: null,
      news: null,
      alertsError: "",
      newsError: "",
      error: "",
    });

    const alertsRequest = fetchJson(
      "/api/watchlists/" + encodeURIComponent(watchlistMeta.id) + "/alerts?limit=4&news_limit=2",
    )
      .then(function (response) {
        maybeNotifyHighPriorityAlerts(watchlistMeta, response);
        updateInsightCache(watchlistMeta, {
          alerts: response,
          alertsError: "",
        });
      })
      .catch(function (error) {
        updateInsightCache(watchlistMeta, {
          alertsError: error instanceof Error ? error.message : String(error),
        });
      });

    const newsRequest = fetchJson(
      "/api/watchlists/" + encodeURIComponent(watchlistMeta.id) + "/news?limit_per_symbol=2&limit_total=12",
    )
      .then(function (response) {
        updateInsightCache(watchlistMeta, {
          news: response,
          newsError: "",
        });
      })
      .catch(function (error) {
        updateInsightCache(watchlistMeta, {
          newsError: error instanceof Error ? error.message : String(error),
        });
      });

    const request = Promise.allSettled([alertsRequest, newsRequest])
      .finally(function () {
        WATCHLIST_STATE.inflight.delete(watchlistMeta.id);
        schedulePatches();
      });

    WATCHLIST_STATE.inflight.set(watchlistMeta.id, request);
  }

  function createNode(tagName, className, text) {
    const element = document.createElement(tagName);
    if (className) {
      element.className = className;
    }
    if (typeof text === "string") {
      element.textContent = text;
    }
    return element;
  }

  function navigateToRoute(path) {
    window.location.assign(path);
  }

  function replaceChildren(target, children) {
    while (target.firstChild) {
      target.removeChild(target.firstChild);
    }
    for (const child of children) {
      target.appendChild(child);
    }
  }

  function formatRelativeTime(rawTimestamp) {
    if (!rawTimestamp) {
      return "recent";
    }

    const parsed = new Date(rawTimestamp);
    if (Number.isNaN(parsed.getTime())) {
      return "recent";
    }

    const diffMs = Date.now() - parsed.getTime();
    const diffMinutes = Math.max(1, Math.round(diffMs / 60000));
    if (diffMinutes < 60) {
      return diffMinutes + "m ago";
    }
    const diffHours = Math.round(diffMinutes / 60);
    if (diffHours < 24) {
      return diffHours + "h ago";
    }
    const diffDays = Math.round(diffHours / 24);
    return diffDays + "d ago";
  }

  function buildPill(label, className) {
    return createNode(
      "span",
      "inline-flex items-center rounded-full border px-2.5 py-1 text-[11px] font-semibold " + className,
      label,
    );
  }

  function getPriorityPill(priorityLabel) {
    if (priorityLabel === "high") {
      return buildPill("High Priority", "border-rose-500/30 bg-rose-500/10 text-rose-600 dark:text-rose-300");
    }
    if (priorityLabel === "medium") {
      return buildPill(
        "Medium Priority",
        "border-amber-500/30 bg-amber-500/10 text-amber-600 dark:text-amber-300",
      );
    }
    return buildPill("Low Priority", "border-slate-300 dark:border-slate-700 bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300");
  }

  function getAlertTypePill(alertType) {
    const normalized = String(alertType || "watch").toLowerCase();
    if (normalized === "signal") {
      return buildPill("Signal", "border-emerald-500/30 bg-emerald-500/10 text-emerald-600 dark:text-emerald-300");
    }
    if (normalized === "news") {
      return buildPill("News", "border-sky-500/30 bg-sky-500/10 text-sky-600 dark:text-sky-300");
    }
    if (normalized === "watchlist") {
      return buildPill("Tagged", "border-violet-500/30 bg-violet-500/10 text-violet-600 dark:text-violet-300");
    }
    return buildPill("Watch", "border-slate-300 dark:border-slate-700 bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300");
  }

  function createActionButton(label, className, onClick) {
    const button = createNode(
      "button",
      "inline-flex items-center justify-center rounded-xl border px-3 py-2 text-xs font-semibold transition-colors " +
        className,
      label,
    );
    button.type = "button";
    button.addEventListener("click", onClick);
    return button;
  }

  function formatAssetLabel(item) {
    if (item && item.assetLabel) {
      return item.assetLabel;
    }
    const assetClass = String((item && item.assetClass) || "").trim().toLowerCase();
    if (!assetClass) {
      return "Asset";
    }
    if (assetClass === "etf") {
      return "ETF";
    }
    return assetClass.charAt(0).toUpperCase() + assetClass.slice(1);
  }

  function formatCompactCurrency(value, currency) {
    const amount = Number(value);
    if (!Number.isFinite(amount)) {
      return null;
    }

    try {
      return new Intl.NumberFormat("en-US", {
        style: "currency",
        currency: currency || "USD",
        notation: Math.abs(amount) >= 1000000 ? "compact" : "standard",
        maximumFractionDigits: Math.abs(amount) >= 1000 ? 1 : 2,
      }).format(amount);
    } catch {
      return (currency || "USD") + " " + amount.toFixed(2);
    }
  }

  function formatPercentValue(value) {
    const amount = Number(value);
    if (!Number.isFinite(amount)) {
      return null;
    }
    return (amount > 0 ? "+" : amount < 0 ? "" : "") + amount.toFixed(2) + "%";
  }

  function getProviderStatusPill(provider) {
    if (!provider || !provider.source) {
      return null;
    }

    if (provider.status === "live") {
      return buildPill(
        provider.source,
        "border-emerald-500/20 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300",
      );
    }
    if (provider.status === "partial") {
      return buildPill(
        provider.source + " partial",
        "border-amber-500/20 bg-amber-500/10 text-amber-700 dark:text-amber-300",
      );
    }
    return buildPill(
      provider.source + " pending",
      "border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 text-slate-500 dark:text-slate-300",
    );
  }

  function buildProviderDetailLine(provider) {
    if (!provider || !provider.source) {
      return null;
    }

    const quote = provider.quote || {};
    const research = provider.research || {};
    const parts = [];
    const priceLabel = formatCompactCurrency(quote.price, quote.currency || "USD");
    const changeLabel = formatPercentValue(quote.changePercent);
    const netAssetsLabel = formatCompactCurrency(research.netAssets, "USD");
    const firstHolding = research.topHoldings && research.topHoldings[0];

    if (priceLabel) {
      parts.push("Price " + priceLabel);
    }
    if (changeLabel) {
      parts.push("Move " + changeLabel);
    }
    if (research.expenseRatio !== null && research.expenseRatio !== undefined) {
      parts.push("Expense ratio " + research.expenseRatio + "%");
    }
    if (netAssetsLabel) {
      parts.push("Net assets " + netAssetsLabel);
    }
    if (firstHolding && firstHolding.symbol && firstHolding.weightPercent !== null && firstHolding.weightPercent !== undefined) {
      parts.push("Top holding " + firstHolding.symbol + " " + firstHolding.weightPercent + "%");
    }
    if (provider.lastUpdated) {
      parts.push("Updated " + formatRelativeTime(provider.lastUpdated));
    }
    if (provider.status === "unavailable") {
      parts.push("Set ALPHA_VANTAGE_API_KEY to activate live ETF/Crypto enrichment");
    }

    if (parts.length === 0) {
      return null;
    }
    return createNode(
      "div",
      "mt-3 text-xs text-slate-500 dark:text-slate-400",
      parts.join(" | "),
    );
  }

  function getTrackedAssets(alerts, news) {
    if (alerts && Array.isArray(alerts.trackedAssets) && alerts.trackedAssets.length > 0) {
      return alerts.trackedAssets;
    }
    if (news && Array.isArray(news.trackedAssets)) {
      return news.trackedAssets;
    }
    return [];
  }

  function summarizeTrackedAssets(trackedAssets) {
    const assetClasses = new Map();
    const tags = new Map();

    for (const item of trackedAssets) {
      const label = formatAssetLabel(item);
      assetClasses.set(label, (assetClasses.get(label) || 0) + 1);

      for (const rawTag of item && Array.isArray(item.tags) ? item.tags : []) {
        const tag = String(rawTag || "").trim().toLowerCase();
        if (!tag) {
          continue;
        }
        tags.set(tag, (tags.get(tag) || 0) + 1);
      }
    }

    return {
      assetClasses: Array.from(assetClasses.entries()).sort(function (left, right) {
        return right[1] - left[1] || left[0].localeCompare(right[0]);
      }),
      tags: Array.from(tags.entries()).sort(function (left, right) {
        return right[1] - left[1] || left[0].localeCompare(right[0]);
      }),
    };
  }

  function buildMetaPill(label) {
    return buildPill(
      label,
      "border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 text-slate-500 dark:text-slate-300",
    );
  }

  function getSignalSummary(signal) {
    const direction = String((signal && signal.direction) || "HOLD").toUpperCase();
    const confidence = Number((signal && signal.confidencePercent) || 0);
    if (direction === "UP") {
      return "BUY bias " + confidence.toFixed(0) + "%";
    }
    if (direction === "DOWN") {
      return "SELL bias " + confidence.toFixed(0) + "%";
    }
    return "Watch";
  }

  function buildAlertRow(item) {
    const row = createNode(
      "div",
      "rounded-2xl border border-slate-200 dark:border-slate-800 bg-slate-50/90 dark:bg-slate-950/50 p-4",
    );
    const header = createNode("div", "flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between");
    const titleBlock = createNode("div", "min-w-0");
    const titleLine = createNode("div", "flex flex-wrap items-center gap-2");
    titleLine.appendChild(createNode("span", "text-sm font-bold text-slate-900 dark:text-white", item.symbol || "Asset"));
    if (formatAssetLabel(item)) {
      titleLine.appendChild(
        buildPill(
          formatAssetLabel(item),
          "border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 text-slate-500 dark:text-slate-300",
        ),
      );
    }
    titleBlock.appendChild(titleLine);
    titleBlock.appendChild(
      createNode("p", "mt-1 text-sm text-slate-500 dark:text-slate-400 truncate", item.name || "Tracked asset"),
    );

    const pillRow = createNode("div", "flex flex-wrap items-center gap-2");
    pillRow.appendChild(getPriorityPill(item.priorityLabel));
    pillRow.appendChild(getAlertTypePill(item.alertType));
    if (item.provider && item.provider.source) {
      const providerPill = getProviderStatusPill(item.provider);
      if (providerPill) {
        pillRow.appendChild(providerPill);
      }
    }
    pillRow.appendChild(
      buildPill(
        getSignalSummary(item.signal || {}),
        "border-emerald-500/20 bg-emerald-500/5 text-emerald-600 dark:text-emerald-300",
      ),
    );

    header.appendChild(titleBlock);
    header.appendChild(pillRow);
    row.appendChild(header);

    const metrics = createNode("div", "mt-3 flex flex-wrap items-center gap-3 text-xs text-slate-500 dark:text-slate-400");
    metrics.appendChild(createNode("span", "font-semibold text-slate-700 dark:text-slate-200", "Score " + (item.priorityScore || 0)));
    if (item.signal && item.signal.expectedYieldPct !== null && item.signal.expectedYieldPct !== undefined) {
      metrics.appendChild(createNode("span", "", "Expected yield " + item.signal.expectedYieldPct + "%"));
    }
    if (item.signal && item.signal.requiredYieldPct !== null && item.signal.requiredYieldPct !== undefined) {
      metrics.appendChild(createNode("span", "", "Required " + item.signal.requiredYieldPct + "%"));
    }
    row.appendChild(metrics);

    const providerMeta = buildProviderDetailLine(item.provider);
    if (providerMeta) {
      row.appendChild(providerMeta);
    }

    if (item.tags && item.tags.length > 0) {
      const tagRow = createNode("div", "mt-3 flex flex-wrap items-center gap-2");
      for (const tag of item.tags.slice(0, 5)) {
        tagRow.appendChild(
          buildPill(
            "#" + tag,
            "border-amber-500/20 bg-amber-500/5 text-amber-700 dark:text-amber-300",
          ),
        );
      }
      row.appendChild(tagRow);
    }

    const headline = item.news && item.news.headlines && item.news.headlines[0];
    if (headline && headline.title) {
      const headlineBox = createNode(
        "div",
        "mt-3 rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 px-3 py-2.5",
      );
      headlineBox.appendChild(
        createNode("div", "text-sm font-medium text-slate-800 dark:text-slate-100", headline.title),
      );
      const meta = createNode("div", "mt-1 flex flex-wrap items-center gap-3 text-xs text-slate-500 dark:text-slate-400");
      meta.appendChild(createNode("span", "", (headline.source || "Market feed") + " " + formatRelativeTime(headline.timestamp)));
      meta.appendChild(
        createNode(
          "span",
          "",
          "Sentiment " + String(headline.label || "neutral").toUpperCase(),
        ),
      );
      headlineBox.appendChild(meta);
      row.appendChild(headlineBox);
    }

    const actionRow = createNode("div", "mt-4 flex flex-wrap items-center gap-2");
    actionRow.appendChild(
      createActionButton(
        "Open Analysis",
        "border-emerald-500/30 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300 hover:bg-emerald-500/20",
        function () {
          navigateToRoute("/analysis/" + encodeURIComponent(item.symbol || ""));
        },
      ),
    );
    actionRow.appendChild(
      createActionButton(
        "Open Trade",
        "border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 text-slate-700 dark:text-slate-200 hover:border-bergt-green/40 hover:text-bergt-green",
        function () {
          navigateToRoute("/trade/" + encodeURIComponent(item.symbol || ""));
        },
      ),
    );
    if (headline && headline.url) {
      actionRow.appendChild(
        createActionButton(
          "Open Story",
          "border-sky-500/30 bg-sky-500/10 text-sky-700 dark:text-sky-300 hover:bg-sky-500/20",
          function () {
            window.open(headline.url, "_blank", "noopener,noreferrer");
          },
        ),
      );
    }
    row.appendChild(actionRow);

    return row;
  }

  function buildTrackedAssetCard(item, relatedAlert) {
    const row = createNode(
      "div",
      "rounded-2xl border border-slate-200 dark:border-slate-800 bg-slate-50/90 dark:bg-slate-950/50 p-4",
    );
    row.dataset.symbol = item.symbol || "";

    const header = createNode("div", "flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between");
    const titleBlock = createNode("div", "min-w-0");
    const titleLine = createNode("div", "flex flex-wrap items-center gap-2");
    titleLine.appendChild(createNode("span", "text-sm font-bold text-slate-900 dark:text-white", item.symbol || "Asset"));
    titleLine.appendChild(buildMetaPill(formatAssetLabel(item)));
    if (relatedAlert && relatedAlert.priorityLabel) {
      titleLine.appendChild(getPriorityPill(relatedAlert.priorityLabel));
    }
    titleBlock.appendChild(titleLine);
    titleBlock.appendChild(
      createNode("p", "mt-1 text-sm text-slate-500 dark:text-slate-400 truncate", item.name || "Tracked asset"),
    );
    header.appendChild(titleBlock);

    const overview = createNode("div", "flex flex-wrap items-center gap-2");
    if (item.exchange) {
      overview.appendChild(buildMetaPill(item.exchange));
    }
    if (item.market) {
      overview.appendChild(buildMetaPill(item.market));
    }
    if (item.provider && item.provider.source) {
      const providerPill = getProviderStatusPill(item.provider);
      if (providerPill) {
        overview.appendChild(providerPill);
      }
    }
    if (item.isCrypto) {
      overview.appendChild(
        buildPill(
          "Crypto-enabled",
          "border-sky-500/20 bg-sky-500/10 text-sky-600 dark:text-sky-300",
        ),
      );
    }
    if (relatedAlert && relatedAlert.alertType) {
      overview.appendChild(getAlertTypePill(relatedAlert.alertType));
    }
    header.appendChild(overview);
    row.appendChild(header);

    if (item.tags && item.tags.length > 0) {
      const tagRow = createNode("div", "mt-3 flex flex-wrap items-center gap-2");
      for (const tag of item.tags.slice(0, 6)) {
        tagRow.appendChild(
          buildPill(
            "#" + tag,
            "border-amber-500/20 bg-amber-500/5 text-amber-700 dark:text-amber-300",
          ),
        );
      }
      row.appendChild(tagRow);
    }

    const providerMeta = buildProviderDetailLine(item.provider);
    if (providerMeta) {
      row.appendChild(providerMeta);
    }

    if (relatedAlert && relatedAlert.signal) {
      const signalLine = createNode(
        "div",
        "mt-3 flex flex-wrap items-center gap-3 text-xs text-slate-500 dark:text-slate-400",
      );
      signalLine.appendChild(
        createNode("span", "font-semibold text-slate-700 dark:text-slate-200", getSignalSummary(relatedAlert.signal)),
      );
      if (
        relatedAlert.signal.expectedYieldPct !== null &&
        relatedAlert.signal.expectedYieldPct !== undefined
      ) {
        signalLine.appendChild(
          createNode("span", "", "Expected yield " + relatedAlert.signal.expectedYieldPct + "%"),
        );
      }
      row.appendChild(signalLine);
    }

    const actionRow = createNode("div", "mt-4 flex flex-wrap items-center gap-2");
    actionRow.appendChild(
      createActionButton(
        "Open Analysis",
        "border-emerald-500/30 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300 hover:bg-emerald-500/20",
        function () {
          navigateToRoute("/analysis/" + encodeURIComponent(item.symbol || ""));
        },
      ),
    );
    actionRow.appendChild(
      createActionButton(
        "Open Trade",
        "border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 text-slate-700 dark:text-slate-200 hover:border-bergt-green/40 hover:text-bergt-green",
        function () {
          navigateToRoute("/trade/" + encodeURIComponent(item.symbol || ""));
        },
      ),
    );
    row.appendChild(actionRow);

    return row;
  }

  function buildAlertToastKey(watchlistId, item) {
    const headline = item.news && item.news.headlines && item.news.headlines[0];
    return [
      watchlistId,
      item.symbol || "asset",
      item.alertType || "watch",
      item.priorityScore || 0,
      headline && headline.title ? headline.title : "",
    ].join("|");
  }

  function showAlertToast(watchlistMeta, item) {
    const toastKey = buildAlertToastKey(watchlistMeta.id, item);
    if (WATCHLIST_STATE.toastIds.has(toastKey)) {
      return;
    }

    WATCHLIST_STATE.toastIds.add(toastKey);
    let host = document.getElementById("ui-patch-alert-toasts");
    if (!host) {
      host = createNode("div", "fixed right-4 top-4 z-[90] flex max-w-sm flex-col gap-3");
      host.id = "ui-patch-alert-toasts";
      document.body.appendChild(host);
    }

    const toast = createNode(
      "div",
      "rounded-2xl border border-rose-500/20 bg-white/95 dark:bg-slate-950/95 shadow-2xl backdrop-blur px-4 py-4",
    );
    toast.dataset.toastKey = toastKey;
    toast.appendChild(
      createNode("div", "text-xs font-semibold uppercase tracking-wide text-rose-500", "High Priority Alert"),
    );
    toast.appendChild(
      createNode(
        "div",
        "mt-1 text-sm font-bold text-slate-900 dark:text-white",
        (item.symbol || "Asset") + " moved to the top of " + watchlistMeta.name + ".",
      ),
    );
    toast.appendChild(
      createNode(
        "div",
        "mt-1 text-sm text-slate-500 dark:text-slate-400",
        getSignalSummary(item.signal || {}) + " | Score " + (item.priorityScore || 0),
      ),
    );
    const headline = item.news && item.news.headlines && item.news.headlines[0];
    if (headline && headline.title) {
      toast.appendChild(
        createNode(
          "div",
          "mt-2 text-xs text-slate-500 dark:text-slate-400",
          headline.title,
        ),
      );
    }

    const actions = createNode("div", "mt-3 flex flex-wrap items-center gap-2");
    actions.appendChild(
      createActionButton(
        "Open Analysis",
        "border-emerald-500/30 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300 hover:bg-emerald-500/20",
        function () {
          navigateToRoute("/analysis/" + encodeURIComponent(item.symbol || ""));
        },
      ),
    );
    actions.appendChild(
      createActionButton(
        "Dismiss",
        "border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 text-slate-700 dark:text-slate-200 hover:border-slate-400 dark:hover:border-slate-500",
        function () {
          toast.remove();
          WATCHLIST_STATE.toastIds.delete(toastKey);
        },
      ),
    );
    toast.appendChild(actions);
    host.appendChild(toast);

    window.setTimeout(function () {
      if (toast.isConnected) {
        toast.remove();
      }
      WATCHLIST_STATE.toastIds.delete(toastKey);
    }, 10000);
  }

  function maybeNotifyHighPriorityAlerts(watchlistMeta, alerts) {
    if (!watchlistMeta || !alerts || !alerts.items) {
      return;
    }

    const highPriorityItems = alerts.items.filter(function (item) {
      return item.priorityLabel === "high";
    });
    const latestKeys = new Set(highPriorityItems.map(function (item) {
      return buildAlertToastKey(watchlistMeta.id, item);
    }));
    const existingKeys = WATCHLIST_STATE.seenAlertKeys.get(watchlistMeta.id) || new Set();

    if (!WATCHLIST_STATE.primedWatchlists.has(watchlistMeta.id)) {
      WATCHLIST_STATE.primedWatchlists.add(watchlistMeta.id);
      WATCHLIST_STATE.seenAlertKeys.set(watchlistMeta.id, latestKeys);
      return;
    }

    for (const item of highPriorityItems) {
      const alertKey = buildAlertToastKey(watchlistMeta.id, item);
      if (!existingKeys.has(alertKey)) {
        showAlertToast(watchlistMeta, item);
      }
    }
    WATCHLIST_STATE.seenAlertKeys.set(watchlistMeta.id, latestKeys);
  }

  function renderWatchlistInsights(container, watchlistMeta, entry) {
    const status = entry ? entry.status : "loading";
    const alerts = entry && entry.alerts ? entry.alerts : null;
    const news = entry && entry.news ? entry.news : null;
    const trackedAssets = getTrackedAssets(alerts, news);
    const trackedSummary = summarizeTrackedAssets(trackedAssets);
    const watchlistName =
      (alerts && alerts.watchlist && alerts.watchlist.name) ||
      (news && news.watchlist && news.watchlist.name) ||
      (entry && entry.watchlistName) ||
      (watchlistMeta && watchlistMeta.name) ||
      "Watchlist";
    const renderKeyParts = [
      status,
      watchlistMeta ? watchlistMeta.id : "none",
      watchlistName,
      alerts && alerts.summary ? alerts.summary.alertItems : 0,
      alerts && alerts.summary ? alerts.summary.highPriority : 0,
      news && news.summary ? news.summary.newsItems : 0,
      trackedAssets.length,
      trackedSummary.assetClasses[0] ? trackedSummary.assetClasses[0][0] + ":" + trackedSummary.assetClasses[0][1] : "",
      trackedSummary.tags[0] ? trackedSummary.tags[0][0] + ":" + trackedSummary.tags[0][1] : "",
      trackedAssets
        .slice(0, 3)
        .map(function (asset) {
          const provider = asset && asset.provider ? asset.provider : null;
          const quote = provider && provider.quote ? provider.quote : null;
          return [
            asset && asset.symbol ? asset.symbol : "",
            provider && provider.status ? provider.status : "",
            provider && provider.source ? provider.source : "",
            quote && quote.price !== null && quote.price !== undefined ? quote.price : "",
          ].join(":");
        })
        .join(","),
      alerts && alerts.items && alerts.items[0] ? alerts.items[0].symbol : "",
      entry && entry.error ? entry.error : "",
    ];
    const renderKey = renderKeyParts.join("|");
    if (container.dataset.renderKey === renderKey) {
      return;
    }

    container.dataset.renderKey = renderKey;
    container.dataset.state = status;
    container.dataset.watchlistId = watchlistMeta ? watchlistMeta.id : "";
    container.className = "mb-8";

    const panel = createNode(
      "section",
      "rounded-3xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 shadow-xl overflow-hidden transition-colors",
    );
    const inner = createNode("div", "p-6 sm:p-8");
    const header = createNode("div", "flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between");
    const heading = createNode("div", "min-w-0");
    const headingTitle = createNode("div", "flex items-center gap-3");
    const iconWrap = createNode(
      "div",
      "flex h-11 w-11 items-center justify-center rounded-2xl border border-amber-500/20 bg-amber-500/10",
    );
    iconWrap.innerHTML = INSIGHT_ICON;
    headingTitle.appendChild(iconWrap);
    const titleCopy = createNode("div");
    titleCopy.appendChild(createNode("h3", "text-xl font-bold text-slate-900 dark:text-white", "Watchlist Alerts"));
    titleCopy.appendChild(
      createNode(
        "p",
        "mt-1 text-sm text-slate-500 dark:text-slate-400",
        "Priority-ranked signals and headlines for " + watchlistName + ".",
      ),
    );
    headingTitle.appendChild(titleCopy);
    heading.appendChild(headingTitle);
    header.appendChild(heading);

    const summaryRow = createNode("div", "flex flex-wrap items-center gap-2");
    summaryRow.appendChild(
      buildPill(
        watchlistName,
        "border-slate-300 dark:border-slate-700 bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-200",
      ),
    );
    if (status === "ready" && alerts && alerts.summary) {
      summaryRow.appendChild(
        buildPill(
          alerts.summary.highPriority + " high",
          "border-rose-500/20 bg-rose-500/10 text-rose-600 dark:text-rose-300",
        ),
      );
      summaryRow.appendChild(
        buildPill(
          alerts.summary.signalAlerts + " signal",
          "border-emerald-500/20 bg-emerald-500/10 text-emerald-600 dark:text-emerald-300",
        ),
      );
      summaryRow.appendChild(
        buildPill(
          (news && news.summary ? news.summary.newsItems : 0) + " headlines",
          "border-sky-500/20 bg-sky-500/10 text-sky-600 dark:text-sky-300",
        ),
      );
    }
    header.appendChild(summaryRow);
    inner.appendChild(header);

    if (entry && entry.error && status !== "error") {
      inner.appendChild(
        createNode(
          "p",
          "mt-4 rounded-2xl border border-amber-500/20 bg-amber-500/10 px-4 py-3 text-sm font-medium text-amber-700 dark:text-amber-300",
          "Signals are still catching up. " + entry.error,
        ),
      );
    }

    if (status === "loading" && trackedAssets.length === 0) {
      inner.appendChild(
        createNode(
          "p",
          "mt-6 text-sm text-slate-500 dark:text-slate-400",
          "Loading watchlist signals and news context...",
        ),
      );
      panel.appendChild(inner);
      replaceChildren(container, [panel]);
      return;
    }

    if (status === "error" && trackedAssets.length === 0) {
      inner.appendChild(
        createNode(
          "p",
          "mt-6 rounded-2xl border border-rose-500/20 bg-rose-500/10 px-4 py-3 text-sm font-medium text-rose-600 dark:text-rose-300",
          "Watchlist insights are temporarily unavailable. " + (entry.error || "Please retry shortly."),
        ),
      );
      panel.appendChild(inner);
      replaceChildren(container, [panel]);
      return;
    }

    const summary = createNode("div", "mt-6 grid grid-cols-1 gap-3 md:grid-cols-4");
    const cards = [
      [
        "Tracked Symbols",
        alerts && alerts.summary
          ? String(alerts.summary.trackedSymbols || 0)
          : String(trackedAssets.length || 0),
      ],
      ["High Priority", alerts && alerts.summary ? String(alerts.summary.highPriority || 0) : "0"],
      ["Signal Alerts", alerts && alerts.summary ? String(alerts.summary.signalAlerts || 0) : "0"],
      ["Headlines", news && news.summary ? String(news.summary.newsItems || 0) : "0"],
    ];
    for (const card of cards) {
      const stat = createNode(
        "div",
        "rounded-2xl border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-950/50 px-4 py-3",
      );
      stat.appendChild(createNode("div", "text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400", card[0]));
      stat.appendChild(createNode("div", "mt-1 text-2xl font-bold text-slate-900 dark:text-white", card[1]));
      summary.appendChild(stat);
    }
    inner.appendChild(summary);

    if (trackedAssets.length > 0) {
      const assetSection = createNode(
        "section",
        "mt-6 rounded-2xl border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-950/40 px-4 py-4 sm:px-5",
      );
      assetSection.id = "ui-patch-watchlist-map";

      const assetHeader = createNode("div", "flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between");
      const assetTitle = createNode("div");
      assetTitle.appendChild(createNode("h4", "text-sm font-bold text-slate-900 dark:text-white", "Tracked Assets"));
      assetTitle.appendChild(
        createNode(
          "p",
          "mt-1 text-sm text-slate-500 dark:text-slate-400",
          trackedAssets.length +
            " symbols are active in this watchlist, grouped by asset class and watch tags.",
        ),
      );
      assetHeader.appendChild(assetTitle);

      const assetSummary = createNode("div", "flex flex-wrap items-center gap-2");
      for (const entryItem of trackedSummary.assetClasses.slice(0, 4)) {
        assetSummary.appendChild(
          buildPill(
            entryItem[1] + " " + entryItem[0],
            "border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 text-slate-700 dark:text-slate-200",
          ),
        );
      }
      assetHeader.appendChild(assetSummary);
      assetSection.appendChild(assetHeader);

      const tagSection = createNode("div", "mt-4 flex flex-col gap-2");
      tagSection.id = "ui-patch-watchlist-tags";
      tagSection.appendChild(
        createNode("div", "text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400", "Top Tags"),
      );
      const tagRow = createNode("div", "flex flex-wrap items-center gap-2");
      if (trackedSummary.tags.length === 0) {
        tagRow.appendChild(
          createNode(
            "span",
            "text-sm text-slate-500 dark:text-slate-400",
            "No watchlist tags yet. Add tags to highlight catalysts, setups or urgency.",
          ),
        );
      } else {
        for (const tagEntry of trackedSummary.tags.slice(0, 6)) {
          tagRow.appendChild(
            buildPill(
              "#" + tagEntry[0] + " x" + tagEntry[1],
              "border-amber-500/20 bg-amber-500/5 text-amber-700 dark:text-amber-300",
            ),
          );
        }
      }
      tagSection.appendChild(tagRow);
      assetSection.appendChild(tagSection);

      const alertBySymbol = new Map();
      for (const item of alerts && alerts.items ? alerts.items : []) {
        alertBySymbol.set(String(item.symbol || "").toUpperCase(), item);
      }

      const assetGrid = createNode("div", "mt-4 grid grid-cols-1 gap-4 xl:grid-cols-2");
      assetGrid.id = "ui-patch-watchlist-assets";
      for (const asset of trackedAssets.slice(0, 6)) {
        assetGrid.appendChild(
          buildTrackedAssetCard(
            asset,
            alertBySymbol.get(String(asset.symbol || "").toUpperCase()) || null,
          ),
        );
      }
      assetSection.appendChild(assetGrid);
      inner.appendChild(assetSection);
    }

    const list = createNode("div", "mt-6 grid grid-cols-1 gap-4 xl:grid-cols-2");
    const items = alerts && alerts.items ? alerts.items : [];
    if (items.length === 0 && (status === "loading" || status === "partial")) {
      list.appendChild(
        createNode(
          "div",
          "rounded-2xl border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-950/50 px-4 py-4 text-sm text-slate-500 dark:text-slate-400",
          "Signal ranking is still loading. Asset classes, tags and watchlist news are already available in this panel.",
        ),
      );
    } else if (items.length === 0 && status === "error") {
      list.appendChild(
        createNode(
          "div",
          "rounded-2xl border border-rose-500/20 bg-rose-500/10 px-4 py-4 text-sm text-rose-600 dark:text-rose-300",
          "Watchlist alert ranking is temporarily unavailable. Asset classes and tags remain visible from the watchlist snapshot.",
        ),
      );
    } else if (items.length === 0) {
      list.appendChild(
        createNode(
          "div",
          "rounded-2xl border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-950/50 px-4 py-4 text-sm text-slate-500 dark:text-slate-400",
          "No urgent watchlist alerts right now. The dashboard is still tracking fresh signals and headlines for this list.",
        ),
      );
    } else {
      for (const item of items.slice(0, 4)) {
        list.appendChild(buildAlertRow(item));
      }
    }
    inner.appendChild(list);

    panel.appendChild(inner);
    replaceChildren(container, [panel]);
  }

  function findDashboardContentRoot() {
    const title = Array.from(document.querySelectorAll("h2")).find(
      (element) => element.textContent.trim() === "Portfolio Dashboard",
    );
    return title ? title.parentElement : null;
  }

  function patchWatchlistInsightsPanel(watchlistMeta) {
    const dashboardRoot = findDashboardContentRoot();
    const existing = document.getElementById("ui-patch-watchlist-alerts");
    if (!dashboardRoot || window.location.pathname !== "/") {
      if (existing) {
        existing.remove();
      }
      return;
    }

    let container = existing;
    if (!container) {
      container = document.createElement("div");
      container.id = "ui-patch-watchlist-alerts";
      const dashboardTitle = Array.from(dashboardRoot.children).find(
        (child) => child.tagName === "H2" && child.textContent.trim() === "Portfolio Dashboard",
      );
      const statsGrid = dashboardTitle ? dashboardTitle.nextElementSibling : null;
      const contentGrid = statsGrid ? statsGrid.nextElementSibling : null;
      dashboardRoot.insertBefore(container, contentGrid || null);
    }

    const entry = watchlistMeta ? getCachedInsights(watchlistMeta.id) : null;
    renderWatchlistInsights(container, watchlistMeta, entry);
    ensureWatchlistInsights(watchlistMeta);
  }

  function renderTickerItem(item) {
    const wrapper = createNode(
      "span",
      "flex items-center gap-2 group cursor-default hover:text-bergt-green dark:hover:text-bergt-greenLight transition-colors",
    );
    const dot = createNode("span", "w-1.5 h-1.5 rounded-full flex-shrink-0");
    const label = String(item.label || item.aggregateLabel || "neutral").toLowerCase();
    if (label === "bullish") {
      dot.className += " bg-emerald-500 dark:bg-emerald-400";
    } else if (label === "bearish") {
      dot.className += " bg-rose-500 dark:bg-rose-400";
    } else {
      dot.className += " bg-slate-400 dark:bg-slate-600";
    }
    wrapper.appendChild(dot);

    wrapper.appendChild(createNode("span", "font-mono text-[10px] opacity-75", item.symbol || "WL"));
    wrapper.appendChild(
      createNode(
        "span",
        label === "bullish"
          ? "whitespace-nowrap uppercase tracking-wide text-emerald-600 dark:text-emerald-400"
          : label === "bearish"
            ? "whitespace-nowrap uppercase tracking-wide text-rose-600 dark:text-rose-400"
            : "whitespace-nowrap uppercase tracking-wide text-slate-800 dark:text-slate-200",
        item.title || "Watchlist update",
      ),
    );
    wrapper.appendChild(
      createNode(
        "span",
        "text-[10px] px-1.5 py-0.5 bg-slate-100 dark:bg-slate-900 text-slate-600 dark:text-slate-400 rounded border border-slate-200 dark:border-slate-800",
        item.source ? item.source + " " + formatRelativeTime(item.timestamp) : formatRelativeTime(item.timestamp),
      ),
    );
    return wrapper;
  }

  function renderWatchlistTicker(watchlistMeta, entry) {
    const marquee = document.querySelector(".animate-marquee");
    if (!marquee) {
      return;
    }

    const status = entry ? entry.status : "loading";
    const news = entry && entry.news ? entry.news : null;
    const watchlistName =
      (news && news.watchlist && news.watchlist.name) ||
      (entry && entry.watchlistName) ||
      (watchlistMeta && watchlistMeta.name) ||
      "Watchlist";
    const renderKey = [
      status,
      watchlistMeta ? watchlistMeta.id : "none",
      watchlistName,
      news && news.items ? news.items.length : 0,
      news && news.items && news.items[0] ? news.items[0].title : "",
      entry && entry.error ? entry.error : "",
    ].join("|");
    if (marquee.dataset.renderKey === renderKey) {
      return;
    }

    marquee.dataset.renderKey = renderKey;
    marquee.dataset.watchlistId = watchlistMeta ? watchlistMeta.id : "";

    const children = [];
    if (status === "loading") {
      children.push(
        createNode(
          "span",
          "text-slate-400 dark:text-slate-600 italic text-[11px] flex items-center gap-2",
          "Loading watchlist news for " + watchlistName + "...",
        ),
      );
    } else if (status === "error") {
      children.push(
        createNode(
          "span",
          "text-slate-400 dark:text-slate-600 italic text-[11px] flex items-center gap-2",
          "Watchlist news unavailable for " + watchlistName + ".",
        ),
      );
    } else if (news && news.items && news.items.length > 0) {
      for (const item of news.items.slice(0, 10)) {
        children.push(renderTickerItem(item));
      }
    } else {
      children.push(
        createNode(
          "span",
          "text-slate-400 dark:text-slate-600 italic text-[11px] flex items-center gap-2",
          "Watching " +
            ((news && news.summary && news.summary.trackedSymbols) || 0) +
            " symbols in " +
            watchlistName +
            ". Waiting for fresh headlines...",
        ),
      );
    }

    replaceChildren(marquee, children);
    ensureWatchlistInsights(watchlistMeta);
  }

  function patchWatchlistInsights() {
    const watchlistMeta = getActiveWatchlistMeta();
    patchWatchlistInsightsPanel(watchlistMeta);
    renderWatchlistTicker(watchlistMeta, watchlistMeta ? getCachedInsights(watchlistMeta.id) : null);
  }

  let scheduled = false;
  function applyPatches() {
    scheduled = false;
    patchDashboardShortcuts();
    patchSettingsBackButton();
    patchWatchlistInsights();
  }

  function schedulePatches() {
    if (scheduled) {
      return;
    }
    scheduled = true;
    requestAnimationFrame(function () {
      requestAnimationFrame(applyPatches);
    });
  }

  const originalPushState = history.pushState;
  history.pushState = function () {
    const result = originalPushState.apply(this, arguments);
    schedulePatches();
    return result;
  };

  const originalReplaceState = history.replaceState;
  history.replaceState = function () {
    const result = originalReplaceState.apply(this, arguments);
    schedulePatches();
    return result;
  };

  window.addEventListener("popstate", schedulePatches);
  window.addEventListener("load", schedulePatches);
  window.addEventListener("change", schedulePatches, true);
  window.setInterval(function () {
    WATCHLIST_STATE.cache.clear();
    schedulePatches();
  }, 60000);

  const observer = new MutationObserver(schedulePatches);
  observer.observe(document.documentElement, { childList: true, subtree: true });
})();
