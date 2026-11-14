import React, { useEffect, useMemo, useState } from 'react';

export type DocumentGenerationVariant =
  | 'business-model-canvas'
  | 'cost-structure'
  | 'pitch-deck'
  | 'prd'
  | 'legal'
  | 'pdf-packet';

export interface DocumentGenerationState {
  startedAt: number;
  pendingDocuments: string[];
  mode: 'initial' | 'refresh';
}

interface DocumentGenerationNoticeProps {
  layout?: 'full' | 'inline';
  state: DocumentGenerationState;
  title: string;
  variant: DocumentGenerationVariant;
}

interface VariantMeta {
  badge: string;
  eta: string;
  eyebrow: string;
  stages: [string, string, string];
}

const variantMeta: Record<DocumentGenerationVariant, VariantMeta> = {
  'business-model-canvas': {
    badge: 'Canvas Build',
    eyebrow: 'Structuring the business model in the background',
    eta: 'Usually under 2 minutes',
    stages: ['Analyze model', 'Map structure', 'Refine sections'],
  },
  'cost-structure': {
    badge: 'Cost Model',
    eyebrow: 'Deriving the operating cost profile from the business model',
    eta: 'Usually under 2 minutes',
    stages: ['Read canvas', 'Infer drivers', 'Group costs'],
  },
  'pitch-deck': {
    badge: 'Deck Refresh',
    eyebrow: 'Shaping an investor-facing narrative while you keep working',
    eta: 'Usually under 3 minutes',
    stages: ['Extract signal', 'Sequence slides', 'Polish language'],
  },
  prd: {
    badge: 'Spec Draft',
    eyebrow: 'Translating the idea into execution-ready requirements',
    eta: 'Usually under 3 minutes',
    stages: ['Frame scope', 'Organize requirements', 'Tighten detail'],
  },
  legal: {
    badge: 'Legal Draft',
    eyebrow: 'Preparing a more formal draft packet for review',
    eta: 'Usually under 3 minutes',
    stages: ['Structure filing', 'Compose sections', 'Prepare review draft'],
  },
  'pdf-packet': {
    badge: 'Packet Assembly',
    eyebrow: 'Preparing filing-style PDFs and packet assets',
    eta: 'Usually under 1 minute',
    stages: ['Prepare source', 'Render packet', 'Finalize assets'],
  },
};

const pulseBlock = 'animate-pulse rounded-full bg-gradient-to-r from-stone-200 via-stone-100 to-stone-200 dark:from-neutral-700 dark:via-neutral-800 dark:to-neutral-700';

const stageClassName = (status: 'complete' | 'active' | 'pending') => {
  if (status === 'complete') {
    return 'border-emerald-200 bg-emerald-50 text-emerald-900 dark:border-emerald-800 dark:bg-emerald-950/30 dark:text-emerald-200';
  }

  if (status === 'active') {
    return 'border-amber-200 bg-amber-50 text-amber-900 shadow-[0_16px_32px_-24px_rgba(217,119,6,0.55)] dark:border-amber-800 dark:bg-amber-950/30 dark:text-amber-100';
  }

  return 'border-stone-200 bg-white/80 text-stone-500 dark:border-neutral700 dark:bg-neutral900/70 dark:text-gray400';
};

const elapsedLabel = (elapsedMs: number) => {
  if (elapsedMs < 45000) {
    return 'Started moments ago';
  }

  if (elapsedMs < 120000) {
    return 'Actively drafting';
  }

  return 'Finalizing output';
};

const StageIndicator: React.FC<{ activeIndex: number; labels: [string, string, string] }> = ({
  activeIndex,
  labels,
}) => (
  <div className="grid gap-3 sm:grid-cols-3">
    {labels.map((label, index) => {
      const status = index < activeIndex ? 'complete' : index === activeIndex ? 'active' : 'pending';
      return (
        <div
          className={`rounded-2xl border px-4 py-3 transition-colors ${stageClassName(status)}`}
          key={label}
        >
          <div className="mb-2 flex items-center gap-2">
            {status === 'complete' ? (
              <span className="inline-flex h-5 w-5 items-center justify-center rounded-full bg-emerald-600 text-white">
                <svg className="h-3 w-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M5 13l4 4L19 7" />
                </svg>
              </span>
            ) : status === 'active' ? (
              <span className="relative inline-flex h-5 w-5 items-center justify-center">
                <span className="absolute inline-flex h-5 w-5 animate-ping rounded-full bg-amber-300 opacity-60" />
                <span className="relative inline-flex h-2.5 w-2.5 rounded-full bg-amber-600" />
              </span>
            ) : (
              <span className="inline-flex h-5 w-5 items-center justify-center rounded-full border border-stone-300 text-[10px] font-semibold text-stone-400">
                {index + 1}
              </span>
            )}
            <span className="text-[11px] font-semibold uppercase tracking-[0.18em]">
              {status === 'complete' ? 'Complete' : status === 'active' ? 'In progress' : 'Queued'}
            </span>
          </div>
          <p className="text-sm font-medium">{label}</p>
        </div>
      );
    })}
  </div>
);

const StandardSkeleton: React.FC = () => (
  <div className="mt-6 gap-6 lg:grid lg:grid-cols-[220px_minmax(0,1fr)]">
    <div className="rounded-[24px] border border-stone-200 bg-white/90 p-4">
      <div className={`${pulseBlock} h-3 w-24`} />
      <div className="mt-4 space-y-3">
        {Array.from({ length: 5 }).map((_, index) => (
          <div className="flex items-center gap-3" key={index}>
            <div className={`${pulseBlock} h-7 w-7`} />
            <div className={`${pulseBlock} h-3 flex-1`} />
          </div>
        ))}
      </div>
    </div>
    <div className="rounded-[30px] border border-stone-200 bg-white px-6 py-8 shadow-soft sm:px-10">
      <div className={`${pulseBlock} h-4 w-32`} />
      <div className="mt-4 space-y-3">
        <div className={`${pulseBlock} h-8 w-3/4`} />
        <div className={`${pulseBlock} h-3 w-full`} />
        <div className={`${pulseBlock} h-3 w-11/12`} />
        <div className={`${pulseBlock} h-3 w-10/12`} />
      </div>
      <div className="mt-10 space-y-4">
        <div className={`${pulseBlock} h-6 w-2/5`} />
        <div className={`${pulseBlock} h-3 w-full`} />
        <div className={`${pulseBlock} h-3 w-full`} />
        <div className={`${pulseBlock} h-3 w-4/5`} />
      </div>
      <div className="mt-10 space-y-4">
        <div className={`${pulseBlock} h-6 w-1/3`} />
        <div className={`${pulseBlock} h-3 w-full`} />
        <div className={`${pulseBlock} h-3 w-10/12`} />
        <div className={`${pulseBlock} h-3 w-8/12`} />
      </div>
    </div>
  </div>
);

const PitchDeckSkeleton: React.FC = () => (
  <div className="mx-auto mt-6 flex max-w-4xl flex-col gap-6">
    {Array.from({ length: 3 }).map((_, index) => (
      <div
        className="overflow-hidden rounded-[24px] border border-[#d6d1c4] bg-white shadow-soft"
        key={index}
      >
        <div className="flex aspect-video flex-col p-5 sm:p-7">
          <div className={`${pulseBlock} mb-3 h-7 w-24`} />
          <div className={`${pulseBlock} mb-4 h-8 w-2/3`} />
          <div className="mt-auto space-y-3">
            <div className={`${pulseBlock} h-3 w-full`} />
            <div className={`${pulseBlock} h-3 w-11/12`} />
            <div className={`${pulseBlock} h-3 w-9/12`} />
          </div>
        </div>
      </div>
    ))}
  </div>
);

const CanvasSkeleton: React.FC = () => (
  <div className="mt-6 grid gap-4 [grid-template-columns:repeat(auto-fit,minmax(220px,1fr))]">
    {Array.from({ length: 6 }).map((_, index) => (
      <div
        className="rounded-2xl border border-stone-200 bg-white p-4 shadow-soft dark:border-neutral700 dark:bg-neutral900"
        key={index}
      >
        <div className="mb-3 flex items-center gap-3">
          <div className={`${pulseBlock} h-10 w-10`} />
          <div className={`${pulseBlock} h-4 w-2/3`} />
        </div>
        <div className="space-y-2.5">
          <div className={`${pulseBlock} h-3 w-full`} />
          <div className={`${pulseBlock} h-3 w-10/12`} />
          <div className={`${pulseBlock} h-3 w-8/12`} />
        </div>
      </div>
    ))}
  </div>
);

const CostStructureSkeleton: React.FC = () => (
  <div className="mt-6 grid gap-4 [grid-template-columns:repeat(auto-fit,minmax(240px,1fr))]">
    {Array.from({ length: 4 }).map((_, index) => (
      <div
        className="rounded-[24px] border border-stone-200 bg-white p-5 shadow-soft dark:border-neutral700 dark:bg-neutral900"
        key={index}
      >
        <div className="flex items-center justify-between gap-3">
          <div className={`${pulseBlock} h-6 w-24`} />
          <div className={`${pulseBlock} h-3 w-24`} />
        </div>
        <div className={`${pulseBlock} mt-5 h-7 w-2/3`} />
        <div className="mt-5 space-y-3">
          <div className={`${pulseBlock} h-3 w-full`} />
          <div className={`${pulseBlock} h-3 w-11/12`} />
          <div className={`${pulseBlock} h-3 w-8/12`} />
        </div>
      </div>
    ))}
  </div>
);

const PacketSkeleton: React.FC = () => (
  <div className="mt-6 space-y-5">
    <div className="flex flex-wrap gap-3">
      <div className={`${pulseBlock} h-10 w-40`} />
      <div className={`${pulseBlock} h-10 w-36`} />
    </div>
    <div className="rounded-[28px] border border-stone-200 bg-white p-5 shadow-soft dark:border-neutral700 dark:bg-neutral900">
      <div className="mb-4 flex items-center justify-between">
        <div>
          <div className={`${pulseBlock} h-6 w-44`} />
          <div className={`${pulseBlock} mt-3 h-3 w-72 max-w-full`} />
        </div>
        <div className={`${pulseBlock} h-9 w-32`} />
      </div>
      <div className="grid gap-3 [grid-template-columns:repeat(auto-fit,minmax(180px,1fr))]">
        <div className="rounded-2xl border border-stone-200 bg-stone-50 p-4 dark:border-neutral700 dark:bg-neutral800">
          <div className={`${pulseBlock} h-28 w-full`} />
        </div>
        <div className="rounded-2xl border border-stone-200 bg-stone-50 p-4 dark:border-neutral700 dark:bg-neutral800 md:col-span-2">
          <div className={`${pulseBlock} h-28 w-full`} />
        </div>
      </div>
    </div>
  </div>
);

const renderSkeleton = (variant: DocumentGenerationVariant) => {
  if (variant === 'pitch-deck') {
    return <PitchDeckSkeleton />;
  }

  if (variant === 'business-model-canvas') {
    return <CanvasSkeleton />;
  }

  if (variant === 'cost-structure') {
    return <CostStructureSkeleton />;
  }

  if (variant === 'legal' || variant === 'pdf-packet') {
    return <PacketSkeleton />;
  }

  return <StandardSkeleton />;
};

export const DocumentGenerationNotice: React.FC<DocumentGenerationNoticeProps> = ({
  layout = 'full',
  state,
  title,
  variant,
}) => {
  const [now, setNow] = useState(Date.now());

  useEffect(() => {
    const intervalId = window.setInterval(() => setNow(Date.now()), 10000);
    return () => window.clearInterval(intervalId);
  }, []);

  const meta = variantMeta[variant];
  const elapsedMs = Math.max(0, now - state.startedAt);
  const activeStageIndex = elapsedMs < 35000 ? 0 : elapsedMs < 95000 ? 1 : 2;
  const pendingCount = state.pendingDocuments.length;
  const waitLabel = elapsedLabel(elapsedMs);
  const longerThanUsual = elapsedMs > 180000;

  const summary = useMemo(() => {
    if (state.mode === 'refresh') {
      return `Updating ${title.toLowerCase()} in the background while the current draft stays available.`;
    }

    return `Generating ${title.toLowerCase()} in the background. You can keep exploring the rest of Manifest while this fills in.`;
  }, [state.mode, title]);

  if (layout === 'inline') {
    return (
      <section
        aria-busy="true"
        aria-live="polite"
        className="rounded-[24px] border border-[#d9d2c4] bg-[linear-gradient(145deg,#fbf8f2,white_60%)] p-4 shadow-soft dark:border-neutral700 dark:bg-[linear-gradient(145deg,#111827,#0f172a_68%)]"
        role="status"
      >
        <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
          <div className="min-w-0">
            <div className="mb-2 flex flex-wrap items-center gap-2">
              <span className="inline-flex items-center gap-2 rounded-full border border-stone-300 bg-white px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.18em] text-stone-700 dark:border-neutral600 dark:bg-neutral900 dark:text-neutral100">
                <span className="relative inline-flex h-2.5 w-2.5">
                  <span className="absolute inline-flex h-2.5 w-2.5 animate-ping rounded-full bg-amber-300 opacity-70" />
                  <span className="relative inline-flex h-2.5 w-2.5 rounded-full bg-amber-600" />
                </span>
                {meta.badge}
              </span>
              <span className="text-xs uppercase tracking-[0.16em] text-stone-500 dark:text-gray400">{waitLabel}</span>
            </div>
            <p className="text-sm font-semibold text-neutral900 dark:text-white">{summary}</p>
            <p className="mt-1 text-sm leading-6 text-stone-600 dark:text-gray300">
              {longerThanUsual
                ? 'This is taking a bit longer than usual, but the app will keep refreshing automatically.'
                : `${meta.eyebrow}. ${meta.eta}.`}
            </p>
          </div>
          <div className="flex flex-wrap gap-2 text-xs uppercase tracking-[0.16em] text-stone-500 dark:text-gray400">
            <span className="rounded-full bg-white px-3 py-1 dark:bg-neutral900">{pendingCount} items pending</span>
            <span className="rounded-full bg-white px-3 py-1 dark:bg-neutral900">Non-blocking</span>
          </div>
        </div>
      </section>
    );
  }

  return (
    <section
      aria-busy="true"
      aria-live="polite"
      className="rounded-[28px] border border-[#d9d2c4] bg-[radial-gradient(circle_at_top_left,rgba(251,191,36,0.14),transparent_28%),linear-gradient(145deg,#fbf8f2,white_58%)] p-6 shadow-soft dark:border-neutral700 dark:bg-[radial-gradient(circle_at_top_left,rgba(251,191,36,0.12),transparent_24%),linear-gradient(145deg,#111827,#0f172a_62%)] sm:p-8"
      role="status"
    >
      <div className="flex flex-col gap-6 lg:flex-row lg:items-start lg:justify-between">
        <div className="max-w-3xl">
          <div className="mb-4 flex flex-wrap items-center gap-3">
            <span className="inline-flex items-center gap-2 rounded-full border border-stone-300 bg-white px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.18em] text-stone-700 dark:border-neutral600 dark:bg-neutral900 dark:text-neutral100">
              <span className="relative inline-flex h-2.5 w-2.5">
                <span className="absolute inline-flex h-2.5 w-2.5 animate-ping rounded-full bg-amber-300 opacity-70" />
                <span className="relative inline-flex h-2.5 w-2.5 rounded-full bg-amber-600" />
              </span>
              {meta.badge}
            </span>
            <span className="text-xs uppercase tracking-[0.18em] text-stone-500 dark:text-gray400">{waitLabel}</span>
          </div>
          <h3 className="text-3xl font-semibold tracking-tight text-neutral900 dark:text-white sm:text-4xl">
            {state.mode === 'refresh' ? `Updating ${title}` : `Generating ${title}`}
          </h3>
          <p className="mt-4 max-w-3xl text-[15px] leading-7 text-stone-600 dark:text-gray300">{summary}</p>
        </div>

        <div className="grid gap-3 text-sm text-stone-600 dark:text-gray300 sm:grid-cols-2 lg:min-w-[280px]">
          <div className="rounded-2xl border border-stone-200 bg-white/90 p-4 dark:border-neutral700 dark:bg-neutral900/90">
            <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-stone-500 dark:text-gray400">Document status</p>
            <p className="mt-2 text-lg font-semibold text-neutral900 dark:text-white">{pendingCount} updates in motion</p>
          </div>
          <div className="rounded-2xl border border-stone-200 bg-white/90 p-4 dark:border-neutral700 dark:bg-neutral900/90">
            <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-stone-500 dark:text-gray400">Expectation</p>
            <p className="mt-2 text-lg font-semibold text-neutral900 dark:text-white">{meta.eta}</p>
          </div>
        </div>
      </div>

      <div className="mt-6">
        <StageIndicator activeIndex={activeStageIndex} labels={meta.stages} />
      </div>

      <p className="mt-5 text-sm leading-6 text-stone-600 dark:text-gray300">
        {longerThanUsual
          ? 'Generation is taking longer than usual. Manifest will keep checking for the finished draft automatically.'
          : 'You can keep editing, switch tabs, or review other material while this continues in the background.'}
      </p>

      {renderSkeleton(variant)}
    </section>
  );
};
