import React from "react";
import { Link } from "react-router-dom";

import Button from "features/common-ui/Button";

export interface SurveyShellProps {
  stepIndex: number;
  totalSteps: number;
  eyebrow: string;
  title: string;
  description?: React.ReactNode;
  children: React.ReactNode;
  showBack: boolean;
  onBack: () => void;
  onNext: () => void;
  nextLabel?: string;
  nextDisabled?: boolean;
  nextVariant?: "primary" | "secondary";
  isSubmitting?: boolean;
}

/**
 * Typeform-inspired single-question layout using Manifest tokens.
 */
const SurveyShell: React.FC<SurveyShellProps> = ({
  stepIndex,
  totalSteps,
  eyebrow,
  title,
  description,
  children,
  showBack,
  onBack,
  onNext,
  nextLabel = "Continue",
  nextDisabled = false,
  nextVariant = "primary",
  isSubmitting = false,
}) => {
  const pct = totalSteps > 0 ? Math.round(((stepIndex + 1) / totalSteps) * 100) : 0;

  return (
    <div className="min-h-screen bg-theme-primary">
      <div className="mx-auto flex min-h-[100dvh] max-w-xl flex-col px-4 py-6 sm:px-5 sm:py-6 ps-[max(1rem,env(safe-area-inset-left,0px))] pe-[max(1rem,env(safe-area-inset-right,0px))] pb-[max(1.5rem,env(safe-area-inset-bottom,0px))] pt-[max(0.75rem,env(safe-area-inset-top,0px))]">
        <header className="mb-8 flex items-center justify-between gap-4">
          <Link
            to="/"
            className="text-[0.72rem] font-medium text-gray500 transition-colors hover:text-accent-600 dark:text-gray400 dark:hover:text-accent-300"
          >
            Manifest
          </Link>
          <span className="text-xs font-medium text-gray500 dark:text-gray400">
            {stepIndex + 1} / {totalSteps}
          </span>
        </header>

        <div className="mb-8 h-1.5 w-full overflow-hidden rounded-full bg-stone200 dark:bg-neutral800">
          <div
            className="h-full rounded-full bg-blue500 transition-[width] duration-300 ease-out"
            style={{ width: `${pct}%` }}
            role="progressbar"
            aria-valuenow={pct}
            aria-valuemin={0}
            aria-valuemax={100}
          />
        </div>

        <div className="flex min-h-0 min-w-0 flex-1 flex-col py-4">
          <p className="text-[0.72rem] font-medium text-gray500 dark:text-gray400">{eyebrow}</p>
          <h1 className="manifest-page-title mt-3">
            {title}
          </h1>
          {description ? (
            <div className="manifest-subtitle mt-3 space-y-3 text-sm leading-7 text-gray500 dark:text-gray400 sm:text-base">{description}</div>
          ) : null}
          <div className="mt-6 min-h-0 flex-1 sm:mt-8">{children}</div>
        </div>

        <div className="mt-6 flex flex-col-reverse gap-3 sm:mt-8 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex min-h-10 justify-center sm:justify-start">
            {showBack ? (
              <Button type="button" variant="secondary" className="w-full px-6 sm:w-auto" onClick={onBack}>
                Back
              </Button>
            ) : null}
          </div>
          <Button
            type="button"
            variant={nextVariant}
            className="w-full min-w-0 px-6 sm:min-w-[10rem] sm:w-auto sm:px-8"
            onClick={onNext}
            disabled={nextDisabled || isSubmitting}
          >
            {isSubmitting ? "Sending…" : nextLabel}
          </Button>
        </div>
      </div>
    </div>
  );
};

export default SurveyShell;
