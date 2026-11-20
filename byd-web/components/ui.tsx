"use client";

import { forwardRef, type ButtonHTMLAttributes, type HTMLAttributes, type ReactNode } from "react";

/* The shared vocabulary. Every control in the app is built from these, so a
   stock element never appears inside a committed surface. */

function cx(...parts: Array<string | false | null | undefined>) {
  return parts.filter(Boolean).join(" ");
}

/* --- Panel ---------------------------------------------------------------
   A white surface on the grey canvas. Separated by value; it carries no border
   and only the faintest lift, because the contrast is already doing the work. */

export function Panel({
  className,
  children,
  ...rest
}: HTMLAttributes<HTMLDivElement> & { children?: ReactNode }) {
  return (
    <div
      className={cx("rounded-[var(--r-panel)] bg-surface shadow-[var(--lift-1)]", className)}
      {...rest}
    >
      {children}
    </div>
  );
}

/* --- Button -------------------------------------------------------------- */

type ButtonVariant = "primary" | "secondary" | "ghost" | "danger";
type ButtonSize = "sm" | "md" | "lg";

const BUTTON_VARIANT: Record<ButtonVariant, string> = {
  // White on violet measures 6.1:1.
  primary:
    "bg-violet text-white hover:bg-[var(--violet-press)] active:bg-[var(--violet-press)] shadow-[var(--lift-1)]",
  secondary: "bg-surface text-ink ring-1 ring-inset ring-hairline hover:bg-sunken",
  ghost: "bg-transparent text-body hover:bg-sunken hover:text-ink",
  // Coral carries white text only above ~18px, so this stays at text-sm+ weight 600.
  danger: "bg-coral text-white hover:brightness-95 shadow-[var(--lift-1)]",
};

const BUTTON_SIZE: Record<ButtonSize, string> = {
  sm: "h-8 px-3 text-[13px] gap-1.5",
  md: "h-10 px-4 text-sm gap-2",
  lg: "h-12 px-5 text-[15px] gap-2",
};

export const Button = forwardRef<
  HTMLButtonElement,
  ButtonHTMLAttributes<HTMLButtonElement> & {
    variant?: ButtonVariant;
    size?: ButtonSize;
    pill?: boolean;
  }
>(function Button(
  { variant = "secondary", size = "md", pill = false, className, children, ...rest },
  ref,
) {
  return (
    <button
      ref={ref}
      className={cx(
        "inline-flex items-center justify-center font-semibold whitespace-nowrap",
        "transition-[background-color,color,box-shadow,transform] duration-150 ease-[var(--ease-out)]",
        "active:translate-y-px disabled:pointer-events-none disabled:opacity-45",
        pill ? "rounded-[var(--r-pill)]" : "rounded-[var(--r-control)]",
        BUTTON_SIZE[size],
        BUTTON_VARIANT[variant],
        className,
      )}
      {...rest}
    >
      {children}
    </button>
  );
});

/* --- IconButton ----------------------------------------------------------
   The circular ghost control that sits at the corner of every panel. */

export const IconButton = forwardRef<
  HTMLButtonElement,
  ButtonHTMLAttributes<HTMLButtonElement> & { label: string; tone?: "default" | "danger" }
>(function IconButton({ label, tone = "default", className, children, ...rest }, ref) {
  return (
    <button
      ref={ref}
      aria-label={label}
      title={label}
      className={cx(
        "inline-grid size-9 place-items-center rounded-full text-muted",
        "transition-colors duration-150 ease-[var(--ease-out)]",
        tone === "danger" ? "hover:bg-coral-wash hover:text-coral" : "hover:bg-sunken hover:text-ink",
        "disabled:pointer-events-none disabled:opacity-40",
        className,
      )}
      {...rest}
    >
      {children}
    </button>
  );
});

/* --- Chip ---------------------------------------------------------------- */

type ChipTone = "neutral" | "violet" | "amber" | "coral" | "teal";

const CHIP_TONE: Record<ChipTone, string> = {
  neutral: "bg-sunken text-body",
  violet: "bg-violet-wash text-violet",
  amber: "bg-amber-wash text-[#8a5a00]",
  coral: "bg-coral-wash text-[#b5301c]",
  teal: "bg-teal-wash text-[#0a6b60]",
};

export function Chip({
  tone = "neutral",
  className,
  children,
  ...rest
}: HTMLAttributes<HTMLSpanElement> & { tone?: ChipTone }) {
  return (
    <span
      className={cx(
        "inline-flex items-center gap-1.5 rounded-[var(--r-pill)] px-2.5 py-1",
        "text-[12px] font-semibold leading-none",
        CHIP_TONE[tone],
        className,
      )}
      {...rest}
    >
      {children}
    </span>
  );
}

/* --- Segmented -----------------------------------------------------------
   A grey track with a filled pill for the active option. */

export function Segmented<T extends string>({
  options,
  value,
  onChange,
  className,
}: {
  options: Array<{ value: T; label: string; icon?: ReactNode }>;
  value: T;
  onChange: (next: T) => void;
  className?: string;
}) {
  return (
    <div
      role="tablist"
      className={cx("inline-flex items-center gap-1 rounded-[var(--r-pill)] bg-sunken p-1", className)}
    >
      {options.map((option) => {
        const active = option.value === value;
        return (
          <button
            key={option.value}
            role="tab"
            aria-selected={active}
            onClick={() => onChange(option.value)}
            className={cx(
              "inline-flex items-center gap-1.5 rounded-[var(--r-pill)] px-3 h-8",
              "text-[13px] font-semibold transition-all duration-200 ease-[var(--ease-out)]",
              active
                ? "bg-surface text-ink shadow-[var(--lift-1)]"
                : "text-muted hover:text-ink",
            )}
          >
            {option.icon}
            {option.label}
          </button>
        );
      })}
    </div>
  );
}

/* --- Field --------------------------------------------------------------- */

export function Field({
  label,
  hint,
  children,
  htmlFor,
}: {
  label: string;
  hint?: string;
  children: ReactNode;
  htmlFor?: string;
}) {
  return (
    <label htmlFor={htmlFor} className="block">
      <span className="mb-1.5 block text-[13px] font-semibold text-ink">{label}</span>
      {children}
      {hint ? <span className="mt-1.5 block text-[12px] text-muted">{hint}</span> : null}
    </label>
  );
}

export const inputClass =
  "w-full rounded-[var(--r-control)] bg-surface px-3.5 h-11 text-sm text-ink " +
  "ring-1 ring-inset ring-hairline placeholder:text-muted " +
  "transition-shadow duration-150 ease-[var(--ease-out)] " +
  "focus:outline-none focus:ring-2 focus:ring-violet";

/* --- Empty state --------------------------------------------------------- */

export function EmptyState({
  icon,
  title,
  body,
  action,
}: {
  icon?: ReactNode;
  title: string;
  body: string;
  action?: ReactNode;
}) {
  return (
    <div className="flex flex-col items-center justify-center px-6 py-16 text-center">
      {icon ? (
        <div className="mb-4 grid size-12 place-items-center rounded-[var(--r-card)] bg-violet-wash text-violet">
          {icon}
        </div>
      ) : null}
      <h3 className="text-lg font-semibold text-ink">{title}</h3>
      <p className="mt-1.5 max-w-sm text-sm text-muted">{body}</p>
      {action ? <div className="mt-5">{action}</div> : null}
    </div>
  );
}
