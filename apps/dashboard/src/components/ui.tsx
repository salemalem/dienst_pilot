"use client";

import { CircleAlert, X } from "lucide-react";
import { useTranslations } from "next-intl";
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useId,
  useMemo,
  useRef,
  useState,
  type ButtonHTMLAttributes,
  type ReactNode,
} from "react";

const ICON = {
  size: 16,
  strokeWidth: 1.75,
  absoluteStrokeWidth: true,
  "aria-hidden": true,
} as const;
export { ICON };

type Variant = "primary" | "secondary" | "quiet" | "link" | "pencil";

/** A button that names what happens (UI_SPEC principles). */
export function Button({
  variant = "secondary",
  icon,
  className = "",
  children,
  ...rest
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant; icon?: ReactNode }): ReactNode {
  return (
    <button type="button" className={`dp-btn dp-btn--${variant} label ${className}`} {...rest}>
      {icon}
      {children}
    </button>
  );
}

export function Segmented<T extends string>({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: T;
  options: { value: T; label: string }[];
  onChange: (value: T) => void;
}): ReactNode {
  const name = useId();
  return (
    <div role="radiogroup" aria-label={label} className="dp-seg label">
      {options.map((o) => (
        <label key={o.value}>
          <input
            type="radio"
            name={name}
            value={o.value}
            checked={o.value === value}
            onChange={() => {
              onChange(o.value);
            }}
          />
          <span>{o.label}</span>
        </label>
      ))}
    </div>
  );
}

export function Switch({
  label,
  checked,
  onChange,
  disabled,
}: {
  label: string;
  checked: boolean;
  onChange: (checked: boolean) => void;
  disabled?: boolean;
}): ReactNode {
  return (
    <label className="dp-switch body">
      <span>{label}</span>
      <input
        type="checkbox"
        role="switch"
        checked={checked}
        disabled={disabled}
        onChange={(e) => {
          onChange(e.target.checked);
        }}
      />
      <span className="dp-switch-track" aria-hidden="true" />
    </label>
  );
}

/** A labelled input. An error always carries what is wrong and the fix (design system rule). */
export function Field({
  label,
  hint,
  error,
  fix,
  children,
}: {
  label: string;
  hint?: string;
  error?: string;
  fix?: string;
  children: (props: {
    id: string;
    "aria-describedby": string | undefined;
    "aria-invalid": boolean;
  }) => ReactNode;
}): ReactNode {
  const id = useId();
  const described = [hint ? `${id}-hint` : null, error ? `${id}-err` : null]
    .filter(Boolean)
    .join(" ");
  return (
    <div className={`dp-field ${error ? "is-invalid" : ""}`}>
      <label htmlFor={id} className="dp-field-label label">
        {label}
      </label>
      {children({ id, "aria-describedby": described || undefined, "aria-invalid": Boolean(error) })}
      {hint ? (
        <span id={`${id}-hint`} className="dp-field-hint caption">
          {hint}
        </span>
      ) : null}
      {error ? (
        <span id={`${id}-err`} className="dp-field-error label" role="alert">
          <CircleAlert {...ICON} />
          <span>
            <strong>{error}</strong> {fix}
          </span>
        </span>
      ) : null}
    </div>
  );
}

/** A modal dialog on the native `<dialog>` (focus trap, Esc, inert background). */
export function Dialog({
  open,
  title,
  onClose,
  children,
  footer,
  wide,
}: {
  open: boolean;
  title: string;
  onClose: () => void;
  children: ReactNode;
  footer?: ReactNode;
  wide?: boolean;
}): ReactNode {
  const ref = useRef<HTMLDialogElement>(null);
  const t = useTranslations("common");
  const titleId = useId();
  useEffect(() => {
    const d = ref.current;
    if (!d) return;
    if (open && !d.open) d.showModal();
    if (!open && d.open) d.close();
  }, [open]);
  return (
    <dialog
      ref={ref}
      aria-labelledby={titleId}
      onClose={onClose}
      className="m-auto max-h-[90vh] w-full rounded-panel border border-rule bg-sheet p-0 text-ink shadow-overlay backdrop:bg-ink/40"
      style={{ maxWidth: wide ? 720 : 520 }}
    >
      {open ? (
        <div className="flex flex-col gap-4 p-5">
          <div className="flex items-start gap-3">
            <h2 id={titleId} className="heading m-0 flex-1">
              {title}
            </h2>
            <Button
              variant="quiet"
              aria-label={t("close")}
              onClick={onClose}
              className="dp-iconbtn"
              icon={<X {...ICON} />}
            />
          </div>
          {children}
          {footer ? <div className="flex flex-wrap justify-end gap-2">{footer}</div> : null}
        </div>
      ) : null}
    </dialog>
  );
}

interface ToastApi {
  show: (message: string) => void;
}
const ToastCtx = createContext<ToastApi>({ show: () => undefined });
export const useToast = (): ToastApi => useContext(ToastCtx);

/** Confirmations that repeat the verb of the button ("Veröffentlicht"). */
export function ToastProvider({ children }: { children: ReactNode }): ReactNode {
  const [message, setMessage] = useState<string | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout>>(undefined);
  const show = useCallback((m: string) => {
    setMessage(m);
    clearTimeout(timer.current);
    timer.current = setTimeout(() => {
      setMessage(null);
    }, 6000);
  }, []);
  const api = useMemo(() => ({ show }), [show]);
  return (
    <ToastCtx.Provider value={api}>
      {children}
      <div
        role="status"
        aria-live="polite"
        className="pointer-events-none fixed inset-x-0 bottom-6 z-50 flex justify-center"
      >
        {message ? (
          <div
            className="body-strong pointer-events-auto rounded-panel bg-ink px-5 py-3 text-on-ink shadow-overlay"
            data-testid="toast"
          >
            {message}
          </div>
        ) : null}
      </div>
    </ToastCtx.Provider>
  );
}

/** A progress bar in ballpoint blue; the numbers are always written next to it. */
export function Progress({
  value,
  max,
  label,
}: {
  value: number;
  max: number;
  label: string;
}): ReactNode {
  const pct = max > 0 ? Math.min(100, Math.round((value / max) * 100)) : 0;
  return (
    <div
      role="progressbar"
      aria-label={label}
      aria-valuemin={0}
      aria-valuemax={max}
      aria-valuenow={value}
      className="h-3 w-full bg-sheet-sunk outline outline-1 outline-rule-strong"
    >
      <div className="h-full bg-ink" style={{ width: `${String(pct)}%` }} />
    </div>
  );
}

export function PageHeader({
  title,
  status,
  actions,
}: {
  title: string;
  /** The first line answers "what do I need to know or do now?" */
  status?: ReactNode;
  actions?: ReactNode;
}): ReactNode {
  return (
    <header className="flex flex-wrap items-start gap-x-6 gap-y-3">
      <div className="flex min-w-[24rem] flex-1 flex-col gap-1">
        <h1 className="display m-0" tabIndex={-1} data-page-title>
          {title}
        </h1>
        {status ? <p className="body m-0 text-ink-muted">{status}</p> : null}
      </div>
      {actions ? <div className="flex flex-wrap items-center gap-2">{actions}</div> : null}
    </header>
  );
}

export function Loading(): ReactNode {
  const t = useTranslations("common");
  return (
    <p role="status" className="body m-0 text-ink-muted">
      {t("loading")}
    </p>
  );
}

/** What is wrong and how to fix it; never an apology. */
export function ErrorState({ error, onRetry }: { error: Error; onRetry?: () => void }): ReactNode {
  const t = useTranslations("common");
  return (
    <div className="dp-rule" role="alert">
      <span className="dp-rule-icon">
        <CircleAlert size={20} strokeWidth={1.75} absoluteStrokeWidth aria-hidden />
      </span>
      <div className="dp-rule-text body">
        <strong>{t("error.title")}</strong>
        <span>{t("error.fix")}</span>
        <span className="caption text-ink-muted">{error.message}</span>
      </div>
      {onRetry ? (
        <div className="dp-rule-actions">
          <Button onClick={onRetry}>{t("retry")}</Button>
        </div>
      ) : null}
    </div>
  );
}

/** Loading, error or the data. */
export function Async<T>({
  query,
  children,
}: {
  query: { data: T | null; error: Error | null; loading: boolean; reload: () => void };
  children: (data: T) => ReactNode;
}): ReactNode {
  if (query.data) return children(query.data);
  if (query.error) return <ErrorState error={query.error} onRetry={query.reload} />;
  return <Loading />;
}

/** A section on the sheet: rule-separated, no shadow (the design system's card rule). */
export function Section({
  title,
  aside,
  children,
  id,
}: {
  title: string;
  aside?: ReactNode;
  children: ReactNode;
  id?: string;
}): ReactNode {
  const hid = useId();
  return (
    <section
      id={id}
      aria-labelledby={hid}
      className="flex flex-col gap-3 border border-rule bg-sheet p-5"
    >
      <div className="flex flex-wrap items-center gap-3">
        <h2 id={hid} className="heading m-0 flex-1">
          {title}
        </h2>
        {aside}
      </div>
      {children}
    </section>
  );
}

export function Table({ children, label }: { children: ReactNode; label: string }): ReactNode {
  return (
    <div className="overflow-x-auto" tabIndex={0} role="region" aria-label={label}>
      <table
        aria-label={label}
        className="body w-full border-collapse text-left [&_td]:border-b [&_td]:border-rule [&_td]:px-3 [&_td]:py-2 [&_th]:border-b [&_th]:border-rule-strong [&_th]:px-3 [&_th]:py-2 [&_th]:font-semibold [&_th]:text-ink-muted"
      >
        {children}
      </table>
    </div>
  );
}
