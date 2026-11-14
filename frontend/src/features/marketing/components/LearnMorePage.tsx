import React from "react";

import { createLogger } from "features/core/logError";

const logger = createLogger("LearnMorePage");

const storyBeats = [
  {
    title: "Capture the spark",
    description:
      "Start with a rough thought, voice note, or founder brief. Manifest turns that ambiguity into a structured working foundation.",
  },
  {
    title: "Develop the case",
    description:
      "Generate business models, product requirements, market comparables, legal drafts, and execution workflows from one shared idea object.",
  },
  {
    title: "Operate with confidence",
    description:
      "Bring collaborators, investors, and advisors into a professional workspace built for iteration, alignment, and momentum.",
  },
];

const principles = [
  "Founder-first workflows that reduce blank-page work without replacing judgment.",
  "Professional outputs that look credible in front of customers, investors, and collaborators.",
  "A shared system that can scale from solo ideation to structured team execution.",
];

const LearnMorePage: React.FC = () => {
  logger.log("rendered");

  return (
    <div className="manifest-page">
      <div className="manifest-page-shell">
        <section className="manifest-page-header overflow-hidden">
          <div className="grid gap-5 lg:grid-cols-[minmax(0,1.2fr)_20rem] lg:items-center">
            <div>
              <span className="manifest-kicker">About Manifest</span>
              <h1 className="manifest-page-title mt-2">
                A more professional operating system for turning ideas into real companies.
              </h1>
              <p className="manifest-subtitle mt-3 max-w-3xl text-sm">
                Manifest was created for founders who need more than a note-taking app and less chaos than stitching together
                disconnected tools. It helps transform an early concept into structured business outputs, operating documents,
                and collaboration systems that can actually move a venture forward.
              </p>

              <div className="mt-4 flex flex-wrap gap-3">
                <a
                  href="/auth"
                  className="manifest-control manifest-control-primary"
                >
                  Start Building
                </a>
                <a
                  href="https://www.mihirkavishwar.com"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="manifest-control manifest-control-secondary"
                >
                  Founder Portfolio
                </a>
              </div>
            </div>

            <div className="manifest-panel-muted p-5 sm:p-6">
              <div className="mb-5 flex items-center gap-4">
                <img
                  src="https://2.gravatar.com/avatar/1446df28fdb20c2b938269c8ba9eed9f19b5f851a210a597b3e8d6a0b72fa7b2?s=240"
                  alt="Mihir Kavishwar"
                  className="h-20 w-20 rounded-lg border border-stone200 object-cover shadow-none dark:border-neutral700"
                />
                <div>
                  <p className="text-[0.72rem] font-medium text-gray500 dark:text-gray400">
                    Founder Note
                  </p>
                  <h2 className="mt-1 text-xl font-semibold text-neutral900 dark:text-white">Built from real startup friction</h2>
                </div>
              </div>
              <p className="manifest-prose text-sm sm:text-[0.95rem]">
                Manifest began as a response to the practical friction early-stage founders face: too many unknowns, not enough
                structure, and a constant gap between an exciting concept and investor-ready execution.
              </p>
              <div className="mt-5 grid gap-3">
                <div className="manifest-card px-4 py-3">
                  <p className="text-xs font-medium text-gray500 dark:text-gray400">Designed for</p>
                  <p className="mt-1 text-sm font-semibold text-neutral900 dark:text-white">Founders, operators, and startup collaborators</p>
                </div>
                <div className="manifest-card px-4 py-3">
                  <p className="text-xs font-medium text-gray500 dark:text-gray400">Core outcome</p>
                  <p className="mt-1 text-sm font-semibold text-neutral900 dark:text-white">Professional documents and execution systems from one idea workspace</p>
                </div>
              </div>
            </div>
          </div>
        </section>

        <section className="grid gap-4 lg:grid-cols-3">
          {storyBeats.map((beat) => (
            <article className="manifest-panel p-4 sm:p-5" key={beat.title}>
              <p className="text-[0.72rem] font-medium text-gray500 dark:text-gray400">Workflow</p>
              <h2 className="mt-3 text-2xl font-semibold tracking-[-0.03em] text-neutral900 dark:text-white">{beat.title}</h2>
              <p className="manifest-prose mt-3 text-sm sm:text-[0.95rem]">{beat.description}</p>
            </article>
          ))}
        </section>

        <section className="grid gap-6 lg:grid-cols-[minmax(0,1.15fr)_minmax(0,0.85fr)]">
          <article className="manifest-panel p-4 sm:p-5">
            <p className="manifest-kicker">Why It Exists</p>
            <h2 className="mt-3 text-xl font-semibold text-theme-primary">
              Manifest helps founders go from uncertainty to a working business narrative.
            </h2>
            <div className="manifest-prose mt-6 space-y-4 text-sm sm:text-[0.98rem]">
              <p>
                Most startup ideas fail to advance because the work between “I have a concept” and “I have a credible operating plan”
                is messy. Research is scattered, documentation is inconsistent, and collaborators rarely work from the same source of truth.
              </p>
              <p>
                Manifest closes that gap by turning a single idea into a connected set of professional outputs: notes, business model
                canvases, product requirements, legal drafts, workflow systems, and investor-facing materials.
              </p>
              <p>
                The product direction is intentionally long-term: the same capability should be reusable across web, mobile, future
                investor tooling, and AI-assisted workflows without rebuilding the logic from scratch each time.
              </p>
            </div>
          </article>

          <aside className="manifest-panel-muted p-6 sm:p-7">
            <p className="text-[0.72rem] font-medium text-gray500 dark:text-gray400">Principles</p>
            <div className="mt-4 space-y-3">
              {principles.map((principle, index) => (
                <div className="manifest-card flex gap-3 px-4 py-4" key={principle}>
                  <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-2xl bg-accent-50 text-sm font-bold text-accent-600 dark:bg-accent-900/40 dark:text-accent-300">
                    0{index + 1}
                  </div>
                  <p className="text-sm leading-6 text-neutral900 dark:text-white">{principle}</p>
                </div>
              ))}
            </div>
          </aside>
        </section>

        <section className="manifest-panel p-4 sm:p-5">
          <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
            <div>
              <span className="manifest-kicker">Contact</span>
              <h2 className="mt-5 text-3xl font-semibold tracking-[-0.03em] text-neutral900 dark:text-white">Build with Manifest</h2>
            <p className="manifest-subtitle mt-3 max-w-3xl text-sm sm:text-base">
              If you are exploring founder tooling, collaboration systems, investor workflows, or AI-assisted venture building,
              Manifest is being shaped around those exact operating needs.
            </p>
          </div>
            <a
              href="mailto:hello@manifeststartup.com"
              className="manifest-control manifest-control-secondary"
            >
              hello@manifeststartup.com
            </a>
          </div>
        </section>
      </div>
    </div>
  );
};

export default LearnMorePage;
