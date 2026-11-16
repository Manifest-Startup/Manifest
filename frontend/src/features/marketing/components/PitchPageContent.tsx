import React from "react";
import { useReactiveVar } from "@apollo/client/react";
import { Link, useNavigate } from "react-router-dom";

import { useStartGuestSession } from "features/auth/hooks/useStartGuestSession";
import { trackEvent } from "features/analytics/projectAnalytics";
import Button from "features/common-ui/Button";
import { userVar } from "features/core/apollo/localState";

const previewSteps = [
  { number: "01", title: "Add your idea", copy: "Start with a simple note." },
  { number: "02", title: "Shape the plan", copy: "Turn it into clear next steps." },
  { number: "03", title: "Build the story", copy: "Create a pitch-ready workspace." },
];

const previewOutputs = ["Market brief", "Business model", "Pitch outline"];

const ArrowIcon = () => (
  <svg aria-hidden="true" className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 12h14m-6-6 6 6-6 6" />
  </svg>
);

const CheckIcon = () => (
  <svg aria-hidden="true" className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="m5 12 4 4L19 6" />
  </svg>
);

const PitchPageContent = () => {
  const navigate = useNavigate();
  const { isLoggedIn } = useReactiveVar(userVar);
  const { start: startGuest, loading: guestSessionLoading } = useStartGuestSession("landing");

  const handleExploreDemo = async () => {
    trackEvent("landing_cta_clicked", {
      cta: isLoggedIn ? "open_workspace" : "explore_demo",
      authenticated: isLoggedIn,
    });

    if (isLoggedIn) {
      navigate("/ideas");
      return;
    }

    await startGuest();
  };

  return (
    <div className="relative min-h-screen min-h-[100dvh] overflow-hidden bg-theme-primary text-theme-primary">

      <div className="relative mx-auto flex min-h-screen min-h-[100dvh] w-full max-w-[1200px] flex-col px-4 sm:px-5">
        <header className="flex items-center justify-between border-b border-stone200/80 py-5 dark:border-neutral700/70">
          <Link to="/" className="flex items-center gap-3" aria-label="Manifest home">
            <span className="flex h-10 w-10 items-center justify-center rounded-2xl bg-neutral900 text-sm font-bold text-white shadow-none dark:bg-white dark:text-neutral900">
              M
            </span>
            <span className="text-base font-bold tracking-[-0.02em]">Manifest</span>
          </Link>

          <div className="flex items-center gap-3">
            <span className="hidden items-center gap-2 rounded-full border border-amber-200 bg-amber-50 px-3 py-1.5 text-[0.68rem] font-bold uppercase tracking-[0.12em] text-amber-800 sm:inline-flex dark:border-amber-700/50 dark:bg-amber-950/30 dark:text-amber-200">
              <span className="h-1.5 w-1.5 rounded-full bg-amber-500" />
              Demo · In development
            </span>
            <Button variant="ghost" onClick={() => navigate(isLoggedIn ? "/ideas" : "/login")}>
              {isLoggedIn ? "Workspace" : "Sign in"}
            </Button>
          </div>
        </header>

        <main className="flex flex-1 flex-col justify-center py-9 sm:py-11 lg:py-12">
          <div className="grid items-center gap-8 lg:grid-cols-[1fr_0.9fr] lg:gap-12">
            <section className="max-w-3xl">
              <div className="mb-7 inline-flex items-center gap-2 rounded-full border border-amber-200 bg-amber-50 px-3.5 py-2 text-xs font-bold text-amber-900 sm:hidden dark:border-amber-700/50 dark:bg-amber-950/30 dark:text-amber-100">
                <span className="h-1.5 w-1.5 rounded-full bg-amber-500" />
                Demo · In development
              </div>

              <p className="text-xs font-medium text-accent-600 dark:text-accent-300">
                Ideas, made actionable
              </p>
              <h1 className="manifest-title mt-4 max-w-3xl text-[clamp(2.25rem,5vw,4rem)] text-balance">
                Turn your idea into a plan.
              </h1>
              <p className="mt-5 max-w-xl text-lg font-medium leading-8 text-neutral600 dark:text-gray300 sm:text-xl">
                One simple workspace for strategy, research, and startup documents.
              </p>

              <div role="note" className="mt-6 max-w-xl rounded-2xl border border-amber-200 bg-amber-50/90 p-4 dark:border-amber-700/50 dark:bg-amber-950/30">
                <div className="flex gap-3">
                  <span className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-amber-200 text-xs font-black text-amber-900 dark:bg-amber-800 dark:text-amber-50">
                    !
                  </span>
                  <div>
                    <p className="text-sm font-bold text-amber-950 dark:text-amber-100">Demo only</p>
                    <p className="mt-1 text-sm leading-6 text-amber-900/80 dark:text-amber-100/75">
                      Manifest is still being built. This preview is not operational and should not be used for real business decisions.
                    </p>
                  </div>
                </div>
              </div>

              <div className="mt-6 flex flex-col gap-3 sm:flex-row sm:items-center">
                <Button
                  variant="primary"
                  className="min-h-12 px-6"
                  onClick={() => void handleExploreDemo()}
                  disabled={guestSessionLoading}
                >
                  {guestSessionLoading ? "Opening demo…" : isLoggedIn ? "Open workspace" : "Explore the demo"}
                  {!guestSessionLoading ? <ArrowIcon /> : null}
                </Button>
                <Button variant="secondary" className="min-h-12 px-6" onClick={() => navigate("/learn-more")}>
                  How it works
                </Button>
              </div>
            </section>

            <section aria-label="Manifest demo preview" className="relative mx-auto w-full max-w-xl">
              <div className="relative overflow-hidden rounded-xl border border-theme-primary bg-theme-primary p-4 sm:p-5">
                <div className="flex items-center justify-between border-b border-stone200 pb-5 dark:border-neutral700">
                  <div>
                    <p className="text-[0.68rem] font-bold uppercase tracking-[0.15em] text-gray500 dark:text-gray400">Demo workspace</p>
                    <p className="mt-1 text-base font-bold">Neighborhood meal exchange</p>
                  </div>
                  <span className="rounded-full bg-stone100 px-3 py-1.5 text-[0.68rem] font-bold uppercase tracking-[0.12em] text-neutral600 dark:bg-neutral700 dark:text-gray300">
                    Preview
                  </span>
                </div>

                <div className="mt-5 rounded-2xl bg-stone50 p-4 dark:bg-neutral900/70">
                  <p className="text-xs font-medium text-gray500 dark:text-gray400">Idea</p>
                  <p className="mt-2 text-sm font-semibold leading-6">Help neighbors share extra home-cooked meals nearby.</p>
                </div>

                <div className="mt-4 grid gap-3 sm:grid-cols-3">
                  {previewOutputs.map((output) => (
                    <div key={output} className="rounded-2xl border border-stone200 bg-white p-4 dark:border-neutral700 dark:bg-neutral800">
                      <span className="flex h-7 w-7 items-center justify-center rounded-full bg-success-50 text-success-600 dark:bg-success-700/20 dark:text-success-500">
                        <CheckIcon />
                      </span>
                      <p className="mt-3 text-sm font-bold">{output}</p>
                    </div>
                  ))}
                </div>

                <div className="mt-4 flex items-center gap-3 rounded-2xl border border-accent-100 bg-accent-50/80 p-4 text-accent-800 dark:border-accent-800 dark:bg-accent-900/30 dark:text-accent-100">
                  <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-xl bg-white text-sm font-bold shadow-none dark:bg-neutral800">1</span>
                  <p className="text-sm font-semibold">Next: validate demand with 10 local interviews.</p>
                </div>
              </div>
            </section>
          </div>

          <section aria-labelledby="preview-heading" className="mt-12 border-t border-stone200/80 pt-7 dark:border-neutral700/70 lg:mt-14">
            <h2 id="preview-heading" className="sr-only">How the Manifest demo works</h2>
            <div className="grid gap-6 sm:grid-cols-3">
              {previewSteps.map((step) => (
                <div key={step.number} className="flex gap-4">
                  <span className="text-xs font-bold tracking-[0.14em] text-accent-600 dark:text-accent-300">{step.number}</span>
                  <div>
                    <p className="font-bold">{step.title}</p>
                    <p className="mt-1 text-sm text-neutral600 dark:text-gray400">{step.copy}</p>
                  </div>
                </div>
              ))}
            </div>
          </section>
        </main>

        <footer className="flex flex-col gap-3 border-t border-stone200/80 py-5 text-xs text-gray500 dark:border-neutral700/70 dark:text-gray400 sm:flex-row sm:items-center sm:justify-between">
          <p>Manifest demo · Not operational</p>
          <nav aria-label="Footer" className="flex flex-wrap gap-4">
            <Link className="hover:text-neutral900 dark:hover:text-white" to="/about">About</Link>
            <Link className="hover:text-neutral900 dark:hover:text-white" to="/contact">Contact</Link>
            <Link className="hover:text-neutral900 dark:hover:text-white" to="/docs/api">API docs</Link>
            <Link className="hover:text-neutral900 dark:hover:text-white" to="/legal/privacy">Privacy</Link>
            <Link className="hover:text-neutral900 dark:hover:text-white" to="/legal/terms">Terms</Link>
          </nav>
        </footer>
      </div>
    </div>
  );
};

export default PitchPageContent;
