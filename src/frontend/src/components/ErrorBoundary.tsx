import { Component, type ErrorInfo, type ReactNode } from "react";
import { useTranslation } from "react-i18next";

type Variant = "page" | "section";

interface Props {
  children: ReactNode;
  variant?: Variant;
  scope?: string;
  fallback?: (error: Error, reset: () => void) => ReactNode;
}

interface State {
  error: Error | null;
}

export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    const scopeTag = this.props.scope ? ` ${this.props.scope}` : "";
    // eslint-disable-next-line no-console
    console.error(
      `[ErrorBoundary${scopeTag}]`,
      error,
      info.componentStack,
    );
  }

  reset = (): void => {
    this.setState({ error: null });
  };

  render(): ReactNode {
    if (this.state.error) {
      if (this.props.fallback) {
        return this.props.fallback(this.state.error, this.reset);
      }
      return (
        <DefaultErrorFallback
          variant={this.props.variant ?? "page"}
          reset={this.reset}
        />
      );
    }
    return this.props.children;
  }
}

function DefaultErrorFallback({
  variant,
  reset,
}: {
  variant: Variant;
  reset: () => void;
}) {
  const { t } = useTranslation();
  if (variant === "section") {
    return (
      <div
        role="alert"
        data-testid="error-boundary-section"
        className="rounded-md border border-amber-500/40 bg-amber-900/10 p-4 text-sm text-amber-100"
      >
        <p className="font-medium">{t("errorBoundary.sectionTitle")}</p>
        <p className="mt-1 text-xs text-amber-200/80">
          {t("errorBoundary.sectionDescription")}
        </p>
        <button
          type="button"
          className="mt-2 text-xs underline hover:text-amber-50"
          onClick={reset}
        >
          {t("errorBoundary.retry")}
        </button>
      </div>
    );
  }
  return (
    <div
      role="alert"
      data-testid="error-boundary-page"
      className="card border-amber-500/40 bg-amber-900/10 p-6"
    >
      <h2 className="text-lg font-semibold text-amber-200">
        {t("errorBoundary.pageTitle")}
      </h2>
      <p className="mt-2 text-sm text-slate-300">
        {t("errorBoundary.pageDescription")}
      </p>
      <div className="mt-3 flex flex-wrap gap-2">
        <button type="button" className="btn" onClick={reset}>
          {t("errorBoundary.retry")}
        </button>
        <button
          type="button"
          className="btn"
          onClick={() => window.location.reload()}
        >
          {t("errorBoundary.reload")}
        </button>
      </div>
    </div>
  );
}
