import { useId, useState } from "react";
import { Link } from "react-router-dom";
import { useTranslation } from "react-i18next";

type Props = {
  /** Short, already-translated explanation shown on hover/focus. */
  text: string;
  /** Optional docs slug — renders a "more" link into the full help topic. */
  topic?: string;
  /** Accessible label for the trigger (falls back to a generic one). */
  label?: string;
  testId?: string;
};

/**
 * Small "i" info trigger with a hover/focus tooltip. Accessible (keyboard
 * focus opens it, `aria-describedby` ties the text to the trigger) and
 * touch-friendly (tap focuses → opens). When `topic` is set the tooltip also
 * links onward to the full in-app help topic (`/docs/<topic>`), bridging the
 * short explanation to the complete documentation.
 */
export function InfoTooltip({ text, topic, label, testId }: Props) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const id = useId();

  return (
    <span
      className="relative inline-flex align-middle"
      onMouseEnter={() => setOpen(true)}
      onMouseLeave={() => setOpen(false)}
    >
      <button
        type="button"
        aria-label={label ?? t("tooltips.ariaLabel")}
        aria-describedby={open ? id : undefined}
        data-testid={testId}
        className="inline-flex h-4 w-4 items-center justify-center rounded-full border border-slate-500 text-[10px] font-semibold leading-none text-slate-400 hover:border-slate-300 hover:text-slate-200 focus:outline-none focus:ring-1 focus:ring-slate-400"
        onFocus={() => setOpen(true)}
        onBlur={() => setOpen(false)}
        onClick={() => setOpen(true)}
      >
        i
      </button>
      {open ? (
        <span
          role="tooltip"
          id={id}
          className="absolute left-1/2 top-full z-50 mt-1 w-56 -translate-x-1/2 rounded border border-slate-700 bg-slate-800 p-2 text-left text-xs font-normal normal-case text-slate-200 shadow-lg"
        >
          {text}
          {topic ? (
            <Link
              to={`/docs/${topic}`}
              className="mt-1 block text-bergt-green hover:underline"
              data-testid={testId ? `${testId}-more` : undefined}
            >
              {t("tooltips.more")}
            </Link>
          ) : null}
        </span>
      ) : null}
    </span>
  );
}
